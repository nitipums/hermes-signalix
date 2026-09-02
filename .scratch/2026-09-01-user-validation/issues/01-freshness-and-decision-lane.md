# 01: Freshness and Decision-Lane Separation

**What to build:** Keep candidates evaluable when the latest official Daily EOD is pending but the latest official Daily snapshot and current 60m data are usable. Show separate Daily official, 60m provisional/current, data availability, and setup-readiness states so fresh intraday data is not presented as generic `DATA_BLOCKED`.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

## Acceptance criteria

- [ ] Latest official Daily remains structural Wave authority.
- [ ] Current 60m evidence is labelled with its own timestamp and provisional/freshness state.
- [ ] Missing current-session official Daily EOD alone does not force generic `DATA_BLOCKED` when required prior Daily and current 60m evidence are usable.
- [ ] True missing, stale, invalid, or incoherent evidence remains fail-closed with explicit reason codes.
- [ ] Setup-not-detected remains distinct from unavailable data.
- [ ] Full 237-symbol evaluated/returned metadata remains intact.
- [ ] Representative TASCO, KCE, IRPC, BCP, RCL, and BBGI payloads are captured as evidence; no labels are hard-coded from the examples.
- [ ] Focused tests and public API/UI probe pass.
