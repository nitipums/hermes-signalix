# Codex Standard Workflow

**Status:** CURRENT · adopted 2026-08-29

## Team

| Member | Role | Boundary |
|---|---|---|
| Arm | Owner / decision maker | Approves scope and production-impacting decisions |
| Lite | Orchestrator + final quality gate | Defines brief, controls scope, verifies source → tests → runtime → browser, and owns final PASS/FAIL/NOT VERIFIED |
| Codex CLI | Coding / review / implementation agent | Uses `gpt-5.6-luna`; reviews and implements bounded changes; never self-declares production readiness |
| Ploy | Trader / product / risk challenger | Uses OpenCode Free `muse-spark-1.2-contributor-free`; challenges setup, trigger, risk wording, actionability, and trader usefulness. Contributor tier data-training accepted by Arm. |

Khim and Nida are no longer active members of the default Signalix team. Their historical notes remain audit evidence only.

## Standard Codex invocation

Preserve the Lite Hermes HOME and use the separate ChatGPT subscription auth directory:

```bash
cd /root/signalix
HOME=/root/.hermes/profiles/lite/home \
CODEX_HOME=/root/.codex \
codex -m gpt-5.6-luna -s workspace-write
```

For read-only review:

```bash
HOME=/root/.hermes/profiles/lite/home \
CODEX_HOME=/root/.codex \
codex exec --ephemeral -m gpt-5.6-luna -s read-only "<bounded review brief>"
```

Never use `/root` as the Codex working directory. Use the actual project repository or a disposable temp Git workspace. Never place secrets in prompts or output files.

## Implementation contract

1. Capture `git status --short --branch` before Codex starts.
2. Treat existing uncommitted changes as owned work; Codex must not reset, stash, checkout, rebase, commit, or push them.
3. Give Codex a bounded file/scope brief and explicit no-go areas.
4. Require focused tests, syntax checks, and `git diff --check`.
5. Lite independently inspects the resulting diff and filesystem; Codex self-report is input, not proof.
6. For UI/product work, verify the served artifact and real desktop/mobile journey, including an error or empty state.
7. Verify live API/runtime and source → DB → scan → API → UI lineage before release.
8. Production verdict vocabulary is `PASS`, `FAIL`, `REVISE`, or `NOT VERIFIED`; missing evidence is never PASS.
9. Do not call a code-only pass production-ready when public ingress, freshness, data completeness, or browser evidence is unverified.

## Verified adoption evidence

- Codex CLI `0.150.1` installed system-wide.
- ChatGPT subscription login verified.
- `gpt-5.6-luna` inference smoke test passed.
- Signalix review + bounded remediation completed without Codex commit.
- Full backend test suite passed after remediation.
- Served dashboard and public `/mvp` route were independently checked by Lite.

## Known operational caveats

- Codex reports a missing `bubblewrap` binary but uses its bundled fallback.
- The direct dashboard port is currently publicly reachable without authentication for owner access; authentication/reverse-proxy hardening remains a follow-up security task.
- Free disk space must be monitored before large agent runs.
