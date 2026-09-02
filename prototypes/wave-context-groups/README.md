# Wave context groups — throwaway logic prototype

This prototype asks whether the upward portion of Signalix's Elliott context can be made more complete and legible for rising stocks that are not currently classified as Wave 3.

Open `index.html` directly in a browser. It is self-contained and uses synthetic in-memory scenarios only. It does not import production code, call an API, access a database, or change filtering.

## Assumptions explored

- Structural state and display context are separate layers.
- Structural state uses only the existing canonical Wave 1–5/`UNKNOWN` vocabulary.
- `WAVE_3_EXTENDED` is **not** a structural state. It appears only as the exploratory secondary marker `upward_context: WAVE_3_EXTENDED` over `WAVE_3_CONTINUATION`.
- Wave 1 and Wave 5 are visible upward context. Wave 2 pullback and Wave 4 sideways/correction are visible non-filter context.
- Existing-filter eligibility is true only for `EARLY_WAVE_3` and `WAVE_3_CONTINUATION` when evidence is sufficient, structural anchors are ordered, and the interpretation is not materially ambiguous. It is not a trade recommendation and does not bypass setup/risk/freshness review.
- Ambiguous, insufficient, or unordered inputs fail closed to `UNKNOWN` / `NONE` / `LOW`; unordered input visibly records missing `ordered confirmed anchors` evidence.

## Before any promotion

This is throwaway prototype evidence, not a proposed production contract. Promotion would require an owner decision reconciling the broad Wave 1–5 context with the current Wave-3-only publication boundary, deterministic detection rules for Wave 1/4/5 and extension, point-in-time replay without lookahead, explicit false-positive/missed-candidate analysis, representative Arm chart review, contract and documentation updates, production tests, and Lite's independent runtime/browser acceptance. The context marker name and whether an extended Wave 3 should remain in discovery after setup/risk checks also require validation.

## Read-only Daily replay adapter

`replay_context_groups.py` applies the exploratory display mapping to the fixed owner-labelled set (BCP, APO, BBGI, BGRIM, CBG, CENTEL, CPF, PROUD, SPRC, TC) for every available Daily trading date from 2025-08-28 through 2026-08-28 inclusive. It reuses the prior replay lab's read-only connection, guarded `SELECT`, Daily loader, and marginable-universe helper. Symbols outside `marginable_long` are reported and still replayed.

For each date, the production classifier receives only that symbol's sorted prefix ending on the date. Outputs are restricted to `/tmp`:

```bash
python3 prototypes/wave-context-groups/replay_context_groups.py --help
python3 prototypes/wave-context-groups/replay_context_groups.py --synthetic-smoke
/root/signalix/.analysis-venv/bin/python prototypes/wave-context-groups/replay_context_groups.py \
  --manifest /tmp/wave_context_groups_manifest.json \
  --report /tmp/wave_context_groups_report.md
```

Rule `canonical-context-evidence-map` v1.0.0 never changes structural state. Its optional `WAVE_3_EXTENDED` marker requires canonical `WAVE_3_CONTINUATION`, at least 10 consecutive Daily closes above the Wave-1 high, a greater-than-10% 20-session advance, emitted measurable-continuation evidence, and breakout volume above the 20-session average. Any missing or false condition returns `NOT_EXPOSED`. Wave 4 maps to sideways only when the emitted 20-session change is within ±3% and drawdown is no worse than 8%; it maps to correction only for emitted measurable pullback or a 20-session decline of at least 3%, and otherwise returns `UNKNOWN`.
