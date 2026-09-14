# Signalix Documentation

> **STATUS: CURRENT** · Directory map only; not product or runtime authority.
> **First read:** [`START-HERE.md`](START-HERE.md)

## Where to start

- [`START-HERE.md`](START-HERE.md) — the single Signalix entrypoint and task router.
- [`../AGENTS.md`](../AGENTS.md) — agent safety contract and working rules.
- [`../GLOSSARY.md`](../GLOSSARY.md) — domain vocabulary and preferred wording.

## Directory map

```text
docs/
├── README.md                 ← this directory map
├── START-HERE.md             ← Signalix entrypoint
├── current/                  ← current decision records and evidence handoffs
├── superpowers/
│   ├── specs/                ← focused current product/API/UI contracts
│   └── plans/                ← historical implementation plans
└── archive/                  ← historical reviews and superseded plans
```

## Authority boundary

- Product, acceptance, architecture, deployment, and governance authorities live in `../vault/` and focused specs.
- `current/` contains bounded records that support those authorities; a dated record does not override them.
- `superpowers/specs/` contains current focused contracts.
- `archive/` contains historical evidence and is not current direction.
- Generated HTML/JSON, logs, snapshots, scratch files, and research artifacts are evidence or outputs, not documentation authorities.

## Maintenance

Keep this file structural. Update it only when the docs layout or first-read path changes. Put task routing in `START-HERE.md`, durable decisions in their owning authority, and historical rationale in dated records.
