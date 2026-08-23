# Signalix Team Operating Model & Provider Allocation

**Status:** current as of 2026-08-22

## Authority and workflow

- **Arm** is owner.
- **Bee / lite** is product lead and final quality gate. No helper declares a user-facing release ready.
- **Prae / prae** is PM and review coordinator: owns Kanban hygiene, scope, dependencies, acceptance criteria, blockers, and review packets.
- **Kanban board `signalix`** is the operational task-state source of truth. Its DB drives automation; `Roadmap-Kanban.md` is a human-readable mirror. Markdown remains for specs and decisions.

## Team lanes

| Profile | Role | Provider/model | Boundary |
|---|---|---|---|
| `khim` | Implementation/coding | Nous `stealth/ox-alpha` | Implements only from approved cards; tests and reports evidence. Ox logic probes passed, but a credit-paused overlay appears in reasoning; specialist only, never final QA/PM. |
| `ploy` | Investment/product challenger | Nous `upstage/solar-pro4:free` | Challenges thesis, setup/trigger/risk wording, and decision usefulness. |
| `prae` | PM/review coordinator | Nous `upstage/solar-pro4:free` | Coordinates cards and review packets; does not decide product/release. |
| `nida` | QA/evidence auditor | Nous `poolside/laguna-s-2.1:free` | Audits source→DB→scan→served UI; reports PASS/FAIL/BLOCKED/NOT VERIFIED. |
| `mali` | Retail UX acceptance | OpenCode Free `laguna-s-2.1-free` | Tests user journeys and reports to Bee only. |
| `view` | UI/UX designer | OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free` | Designs decision-first/mobile-first UI and prototypes; reports to Bee. |

## Verified runtime

- Local-only A2A services: Ploy `9900`, Bee `9901`, Mali `9902`, Khim `9903`, Nida `9904`, Prae `9907`, View `9908`.
- All listed helper services had active agent cards and live A2A role responses verified at closeout.
- View moved from `9906` to `9908` because `default` owns `9906`; do not reuse `9906`.
- Prae and View have isolated Level 1/2 memory and no shared Level-3 fact store. Mali is also isolated. Vault writes stay role-scoped.

## Review loop

1. Bee/Prae clarify objective, card scope, owner, dependency, and acceptance.
2. Khim implements; View designs/prototypes where UI scope exists.
3. Ploy challenges market/product decision language.
4. Mali runs retail UX journey; Nida audits evidence and regression.
5. Bee verifies final live evidence and delivers to Arm.

## Verification rule

A service/card response is infrastructure evidence only. User-facing Signalix work still requires the applicable rendered UI and failure-state checks before Bee marks it ready.
