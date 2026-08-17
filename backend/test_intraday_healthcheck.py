import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from intraday_healthcheck import (
    _journal_failure_records,
    evaluate_health,
    read_failure_observations,
    record_failure_observations,
    render_alert_payload,
    unobserved_failures,
)


UTC = dt.timezone.utc
NOW = dt.datetime(2026, 8, 14, 5, 30, tzinfo=UTC)


class IntradayHealthcheckTests(unittest.TestCase):
    def test_failed_service_is_alerted(self):
        alerts = evaluate_health(
            service_state={"Result": "failed", "ExecMainStatus": "1"},
            price_ts=NOW,
            evaluated_at=NOW,
            now=NOW,
            max_age_minutes=30,
        )
        self.assertEqual(alerts[0]["code"], "service_failed")
        self.assertEqual(alerts[0]["exec_main_status"], 1)

    def test_stale_price_data_is_alerted(self):
        alerts = evaluate_health(
            service_state={"Result": "success", "ExecMainStatus": "0"},
            price_ts=NOW - dt.timedelta(minutes=31),
            evaluated_at=NOW,
            now=NOW,
            max_age_minutes=30,
        )
        self.assertEqual([a["code"] for a in alerts], ["price_data_stale"])
        self.assertEqual(alerts[0]["age_minutes"], 31.0)

    def test_stale_evaluator_state_is_alerted(self):
        alerts = evaluate_health(
            service_state={"Result": "success", "ExecMainStatus": "0"},
            price_ts=NOW,
            evaluated_at=NOW - dt.timedelta(minutes=45),
            now=NOW,
            max_age_minutes=30,
        )
        self.assertEqual([a["code"] for a in alerts], ["intraday_state_stale"])

    def test_missing_freshness_rows_are_alerted(self):
        alerts = evaluate_health(
            service_state={"Result": "success", "ExecMainStatus": "0"},
            price_ts=None,
            evaluated_at=None,
            now=NOW,
            max_age_minutes=30,
        )
        self.assertEqual(
            [a["code"] for a in alerts],
            ["price_data_missing", "intraday_state_missing"],
        )

    def test_60m_candle_uses_interval_aware_threshold(self):
        alerts = evaluate_health(
            service_state={"Result": "success", "ExecMainStatus": "0"},
            price_ts=NOW - dt.timedelta(minutes=70),
            evaluated_at=NOW - dt.timedelta(minutes=20),
            now=NOW,
            price_max_age_minutes=90,
            state_max_age_minutes=30,
        )
        self.assertEqual(alerts, [])

    def test_alert_payload_is_machine_detectable_and_names_source_session_risk(self):
        alerts = [{"code": "service_failed", "result": "failed", "exec_main_status": 1}]
        payload = json.loads(render_alert_payload(alerts, now=NOW, service="signalix-intraday.service"))
        self.assertEqual(payload["level"], "ALERT")
        self.assertEqual(payload["component"], "signalix_intraday")
        self.assertIn("U-102", payload["operator_hint"])
        self.assertEqual(payload["alerts"], alerts)
        self.assertEqual(payload["checked_at"], "2026-08-14T05:30:00+00:00")

    def test_failed_journal_invocation_remains_alerted_after_current_service_succeeds(self):
        failed = [{
            "invocation_id": "failed-run-1",
            "failed_at": "2026-08-14T05:20:00+00:00",
            "message": "Main process exited, code=exited, status=1/FAILURE",
        }]
        alerts = evaluate_health(
            service_state={"Result": "success", "ExecMainStatus": "0"},
            price_ts=NOW,
            evaluated_at=NOW,
            now=NOW,
            failed_invocations=failed,
        )
        self.assertEqual([alert["code"] for alert in alerts], ["service_failed"])
        self.assertEqual(alerts[0]["failed_invocations"], failed)

    def test_failed_invocation_is_suppressed_only_after_durable_observation(self):
        failed = [{
            "invocation_id": "failed-run-1",
            "failed_at": "2026-08-14T05:20:00+00:00",
            "message": "Failed with result 'exit-code'.",
        }]
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "observations.json"
            observations = read_failure_observations(state_path)
            self.assertEqual(unobserved_failures(failed, observations), failed)
            record_failure_observations(observations, failed, NOW, state_path)
            persisted = read_failure_observations(state_path)
            self.assertEqual(unobserved_failures(failed, persisted), [])
            self.assertEqual(persisted["seen_invocation_ids"], ["failed-run-1"])

    def test_journal_failure_records_are_correlated_and_deduplicated_by_invocation(self):
        records = [
            {
                "INVOCATION_ID": "failed-run-1",
                "__REALTIME_TIMESTAMP": "1786684800000000",
                "MESSAGE": "Main process exited, code=exited, status=1/FAILURE",
            },
            {
                "INVOCATION_ID": "failed-run-1",
                "__REALTIME_TIMESTAMP": "1786684800001000",
                "MESSAGE": "Failed with result 'exit-code'.",
            },
        ]
        failures = _journal_failure_records(records)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["invocation_id"], "failed-run-1")
        self.assertEqual(failures[0]["failed_at"], "2026-08-14T05:20:00+00:00")

    def test_outside_session_shell_path_emits_valid_json(self):
        unit = Path(__file__).with_name("signalix-intraday-healthcheck.service").read_text()
        command = next(line.split("'", 1)[1].rsplit("'", 1)[0]
                       for line in unit.splitlines() if line.startswith("ExecStart="))
        command = command.replace("%%", "%", 1).replace(
            "t=$(TZ=Asia/Bangkok date +%H%M);", "t=0000;", 1)
        command = command.replace("/root/.venv_img/bin/python", sys.executable)
        command = command.replace(
            "/root/signalix/backend/intraday_healthcheck.py",
            str(Path(__file__).with_name("intraday_healthcheck.py")),
        )
        output = subprocess.run(
            ["/bin/bash", "-lc", command], check=True, text=True, capture_output=True
        ).stdout
        payload = json.loads(output)
        self.assertEqual(payload["level"], "HEALTHY")
        self.assertEqual(payload["status"], "outside_session_skipped")


if __name__ == "__main__":
    unittest.main()
