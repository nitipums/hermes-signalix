# Signalix Setup Discovery

This context defines the product language for discovering and preparing Thai swing-trade setups for Arm’s review. Signalix presents deterministic evidence; Arm interprets the chart and decides whether to trade.

## Language

**Marginable Long Universe**:
The product universe of active Thai ordinary shares present on the owner-supplied marginable list with `can_buy=true`. Active ORD symbols outside this universe are audit or rollback coverage, not product candidates.
_Avoid_: Thai ORD universe, full universe, eligible universe

**Daily Candidate**:
A symbol whose Daily trend and Elliott evidence is worth continued observation, whether or not a lower-timeframe entry setup exists yet.
_Avoid_: Ready setup, buy candidate

**Setup Forming**:
A Daily Candidate with usable 60-minute evidence whose trigger, invalidation, target, or entry confirmation is still developing.
_Avoid_: Data blocked, failed setup

**Review Now**:
A pre-break setup with complete, fresh evidence and a coherent trigger, invalidation, target, and risk/reward profile that is ready for Arm’s chart review. It is not an instruction or permission to trade.
_Avoid_: Buy, actionable order, confirmed trade

**Pre-Trigger**:
A Review Now setup whose entry trigger is fully defined but has not yet occurred. This is the preferred preparation state because Arm can review the plan before price breaks out.
_Avoid_: Unconfirmed data, incomplete setup

**Elliott Structural State**:
A conservative machine interpretation of observable Daily structure across Wave 1 through Wave 5, with explicit evidence and uncertainty. It is not an authoritative Elliott count.
_Avoid_: Confirmed wave count, Elliott signal

**Wave 1 Preparation**:
Setup preparation during an observable Wave 1 advance. It can reach Review Now when a fresh 60-minute base or pullback defines a pre-trigger plan with R:R of at least 2:1 and price is not extended.
_Avoid_: Wave 1 watch only

**Primary Wave State**:
The best-supported Elliott Structural State under the current evidence. It is accompanied by confidence, contradicting evidence, missing evidence, and an Alternative Wave State when another interpretation remains plausible.
_Avoid_: Confirmed wave count

**Alternative Wave State**:
The next plausible Elliott Structural State when current evidence does not uniquely support the Primary Wave State.
_Avoid_: Error state, duplicate signal

**Daily Primary Wave**:
The single authoritative Elliott Structural State for the medium-to-large structure. Higher-timeframe context may support it, while lower-timeframe structures cannot replace it.
_Avoid_: Competing wave count, 60-minute primary wave

**60-Minute Minor Structure**:
The lower-degree structure used to prepare and confirm an entry within the Daily Primary Wave.
_Avoid_: Daily wave state

**Minimum Review Risk/Reward**:
A reward-to-risk ratio of 2:1 required before a setup can enter Review Now. Passing this threshold does not override structure, freshness, trigger, invalidation, or target-quality requirements.
_Avoid_: Minimum interesting R:R, automatic acceptance threshold

**Trade Stop**:
The lower-timeframe structural level that bounds the planned trade risk and is used for R:R. Reaching it closes the current setup instance without necessarily invalidating the larger Daily thesis.
_Avoid_: Thesis invalidation

**Stopped**:
A terminal Setup Attempt state reached when price hits the Trade Stop while the larger Candidate Thesis may remain valid.
_Avoid_: Thesis invalidated

**Thesis Invalidation**:
The Daily structural level or condition whose failure breaks the larger trend/Elliott interpretation.
_Avoid_: Trade stop

**Primary Target**:
The nearest technically valid target. Its reward relative to the Trade Stop determines whether the setup meets the minimum 2:1 Review Now gate.
_Avoid_: Maximum target, exceptional target

**Tested Trigger**:
A setup whose price trades above its 60-minute structural trigger before a 60-minute candle closes above it.
_Avoid_: Triggered

**Triggered**:
A setup with a completed 60-minute candle closing above its structural trigger.
_Avoid_: Intrabar break, automatic entry

**Entry Zone**:
The valid post-trigger price range from the trigger through `trigger + 0.5R`, provided reward to the Primary Target remains at least 2:1.
_Avoid_: Buy zone, unlimited chase range

**Extended**:
A triggered setup whose price exceeds the Entry Zone or whose reward to the Primary Target has fallen below 2:1.
_Avoid_: Elliott wave state

**Data Blocked**:
A state where required evidence is missing, stale, invalid, or incoherent, preventing an honest evaluation. A valid candidate whose setup is merely unfinished is Setup Forming, not Data Blocked.
_Avoid_: Not ready, waiting for trigger

**Tested High**:
A session whose price trades at or above the prior 52-week or all-time High reference but does not close above it.
_Avoid_: Breakout

**High Breakout**:
A session whose Close finishes above the prior 52-week or all-time High reference. The reference is derived from prior High prices, not prior Closes.
_Avoid_: Intraday breakout, wick breakout

**Session-Aware Freshness**:
Freshness measured against the latest observation required by the exchange session calendar. The final observation from the latest completed trading day remains current through weekends and exchange holidays.
_Avoid_: Wall-clock freshness

**Market Regime**:
Market-wide risk context that changes warnings, ranking, and confirmation strictness without removing a valid Daily Candidate or blanket-blocking Review Now.
_Avoid_: Universe filter, automatic candidate rejection

**Candidate Thesis**:
One Daily trend/Elliott interpretation tracked under a stable candidate identity while its larger structure remains valid.
_Avoid_: Entry attempt, setup

**Setup Attempt**:
One immutable pre-trigger or triggered entry plan under a Candidate Thesis. A changed, stopped, expired, or invalidated plan closes that attempt; a later opportunity receives a new identity.
_Avoid_: Candidate thesis, mutable setup

**Arm Review Event**:
An append-only owner judgement attached to the exact machine snapshot, such as Agree, Watch, Disagree Wave, Reject Setup, Missed Candidate, or Note. It never overwrites the machine interpretation.
_Avoid_: Machine correction, historical override
