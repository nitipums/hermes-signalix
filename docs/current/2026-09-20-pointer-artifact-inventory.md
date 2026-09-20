# Active pointer/artifact inventory — Ticket #66

> **STATUS: PARTIAL / NOT VERIFIED** · Read-only evidence captured from
> release HEAD `0bf2642` on 2026-09-20 ICT. No pointer, artifact, historical
> filename, or Git history was deleted, moved, regenerated, or rewritten.

## Current protected targets

| Surface | Current pointer | Pointer status | Target status |
|---|---|---|---|
| Trend Map | `backend/trend-map-read-model/current.json` | `VERIFIED`; `shadow-trend-map-quote-envelope-v2-2026-09-18-87dce5718dd0784a-e76ebcbf1637fac9-f34bcb3ad1244662-f3783cb9724c81a5` | Exists; root-contained; schema, identity, report validation, content hash, and measurement hash match |
| Intraday quotes | `backend/trend-map-read-model/intraday-quotes/current.json` | `VERIFIED`; `intraday-quotes-02f113b87e784369bd3807099bda46fa-36ffbec7a6be76099883b2b2` | Exists; root-contained; schema, identity, artifact validation, and content hash match |
| Market Breadth | `backend/market-breadth-read-model/current.json` | `NOT_VERIFIED` | **Blocked:** current pointer is absent; no artifact was guessed or regenerated |
| Chart `1D`, `60M`, `1W`, `1M` | `backend/read-model/charts/current-{timeframe}.json` | `NOT_VERIFIED` for each | **Blocked:** current pointers are absent; no chart pointer or artifact was invented |

## Retained non-current candidates

These are inventory results only. “Non-current” does not authorize deletion or
movement and does not establish that a candidate is obsolete.

- Trend Map versions: `shadow-trend-map-quote-envelope-v2-2026-09-14-87dce5718dd0784a-e76ebcbf1637fac9-8c236750e06098fe-9bc135a0b63c1de0.json`, `shadow-trend-map-quote-envelope-v2-2026-09-15-87dce5718dd0784a-e76ebcbf1637fac9-1d6e8d1855625d62-d02fa89b7971c506.json`, `shadow-trend-map-quote-envelope-v2-2026-09-15-87dce5718dd0784a-e76ebcbf1637fac9-809b34d8ec7e747c-70480ca3405df2a2.json`.
- Intraday versions: `intraday-quotes-1ad1ff7a355c4b5b8402591851276325-67e7c27582374346e03b95c0.json`, `intraday-quotes-68824145c5504a14aa01160057c15f2b-742f0b31d1251513d557aaff.json`, `intraday-quotes-dbd4148c11e245a98a428868bf93504b-0a50e3d40be7ebc376c53aea.json`.
- Market Breadth and chart candidate directories were absent in this checkout; no candidate versions were inferred.

## Validation seam and blockers

`backend/artifact_pointer_inventory.py` performs read-only pointer and target
inspection. It fails closed for missing, escaping, identity-mismatched,
schema-mismatched, or tampered targets. Tests use only temporary fixtures:
`backend/test_artifact_pointer_inventory.py`.

The release gate remains `PARTIAL / NOT VERIFIED` because Market Breadth and
all chart current pointers are absent. This slice grants no cleanup authority;
historical filenames and Git rollback remain preserved.
