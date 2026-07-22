# Skill Entry Reliability Audit

This level-1--3 pilot uses interface checks, deterministic environment
policies, and observational future traces. No entry is labelled `harmful`;
that label requires level-4 paired counterfactual replay.

## Label definitions

- `reliable`
- `contradicted`
- `harmful`
- `overgeneralized`
- `unexecutable`
- `inert`
- `insufficient_test`

## Summary

| Document | UER | Confirmed / all | OGR | Coverage | Token-weighted UER |
|---|---:|---:|---:|---:|---:|
| skillopt_poker_gpt5_run_0 | 24/40 (60.0%) | 24/48 (50.0%) | 5/20 (25.0%) | 40/48 (83.3%) | 60.3% |
| skillopt_poker_gpt5_run_1 | 4/4 (100.0%) | 4/11 (36.4%) | 4/4 (100.0%) | 4/11 (36.4%) | 100.0% |
| **All documents (micro)** | 28/44 (63.6%) | 28/59 (47.5%) | 9/24 (37.5%) | 44/59 (74.6%) | 63.7% |

UER is conditional on evaluability: `insufficient_test` entries are
excluded from its denominator. Coverage must therefore be reported
beside UER; a high UER with low coverage means that the tested subset
failed, not that the same fraction of the whole document is known to fail.
`Confirmed / all` is the conservative observed fraction of all substantive
entries already assigned an unreliable label; unevaluated entries remain
unknown rather than being treated as reliable.

## Label-review check

Agreement before resolution: 27/30 (90.0%).

Second-pass self-review, not independent human agreement; all final overgeneralized and unexecutable entries plus six controls were re-read against code and traces.

Resolved disagreements:

- r1-e001: overgeneralized -> insufficient_test because no paired price/range cases establish failure
- r1-e008: overgeneralized -> insufficient_test because the text is scoped to thin value/fold equity, not strong value
- r1-e010: overgeneralized -> insufficient_test because 'can justify' is permissive rather than universal

## skillopt_poker_gpt5_run_0

Source: `results/validation/exploitable_poker/skillopt_poker_gpt5/run_0/skill_opt_ckpt/skill_v0004_accept.md`

### Label counts

| Label | Count |
|---|---:|
| `reliable` | 16 |
| `contradicted` | 4 |
| `harmful` | 0 |
| `overgeneralized` | 5 |
| `unexecutable` | 15 |
| `inert` | 0 |
| `insufficient_test` | 8 |

### Entry audit

| ID | Lines | Type | Label | Level | Reason |
|---|---:|---|---|---:|---|
| r0-b001 | 3–4 | boilerplate | `reliable` | 0 | Unchanged template metadata; excluded from reliability denominators. |
| r0-e001 | 8–8 | strategy | `insufficient_test` | 3 | Plausible poker principle, but aggregate future outcomes do not isolate this entry or establish benefit across variants. |
| r0-e002 | 10–10 | strategy | `overgeneralized` | 2 | The sizing rule omits opponent type; the calling-station policy always calls, so smaller sizing is not needed to induce calls, and fully missed hands do not generally pay value bets. |
| r0-e003 | 12–12 | strategy | `overgeneralized` | 2 | Calling with weak equity is price- and opponent-dependent; fit-or-fold continuation is stronger while a LAG flop bet is much wider. |
| r0-e004 | 14–14 | strategy | `overgeneralized` | 2 | Repeated value betting is sound, but the deterministic calling station calls every bet; the preference for smaller sizing is not supported for strong value hands. |
| r0-e005 | 16–16 | strategy | `reliable` | 2 | This matches the task objective and the calling-station and fit-or-fold policies, with scope explicitly conditioned on observed tendencies. |
| r0-e006 | 18–18 | procedure | `unexecutable` | 1 | PokerAction requires the `thinking` field, so keeping all rationale outside the returned structured action conflicts with the interface. |
| r0-e007 | 22–25 | procedure | `unexecutable` | 1 | SkillOpt exposes no `reset_per_hand` tool; reset occurs at completed-instance boundaries in system code, not through model actions. |
| r0-e008 | 27–35 | procedure | `reliable` | 1 | These fields are explicitly present in the task prompt and re-grounding on them is executable. |
| r0-e009 | 34–38 | procedure | `unexecutable` | 1 | Opponent stack is absent from the prompt and legal_actions exists only in Query.metadata; SkillOpt sends query.prompt, not metadata, to the model. |
| r0-e010 | 36–39 | procedure | `contradicted` | 1 | The task explicitly prints `min raise to X`; converting that known value to null reverses the intended data flow. |
| r0-e011 | 41–43 | strategy | `contradicted` | 2 | Board, pot, and stacks normally change every street; discarding opponent memory on any change contradicts the benchmark's cross-hand learning objective. |
| r0-e012 | 45–47 | procedure | `reliable` | 1 | The prompt explicitly supplies call cost and minimum raise-to amount. |
| r0-e013 | 47–50 | procedure | `insufficient_test` | 1 | The normal task prompt always supplies these thresholds; no held-out missing-threshold cases test the fallback formulas. |
| r0-e014 | 50–51 | procedure | `unexecutable` | 1 | The required opponent stack and contribution are not in the prompt visible to SkillOpt. |
| r0-e015 | 51–51 | procedure | `unexecutable` | 1 | No log-writing tool is exposed to the task model; prose cannot guarantee a persistent internal log. |
| r0-e016 | 53–58 | procedure | `reliable` | 1 | The core CHECK/CALL/RAISE constraints match the prompt, although the unavailable Legal_actions field should not be required. |
| r0-e017 | 58–58 | procedure | `insufficient_test` | 3 | The trace does not expose deterministic parse attempts, so the claimed recovery behavior cannot be verified. |
| r0-e018 | 60–63 | strategy | `insufficient_test` | 3 | No identified future cases isolate the ambiguity fallback, and safety is not equivalent to reward reliability. |
| r0-e018b | 77–77 | strategy | `insufficient_test` | 3 | This restates the unisolated ambiguity fallback with a different textual priority. |
| r0-e019 | 65–66 | procedure | `unexecutable` | 1 | Neither a clock nor persistent internal logging interface is available to the task model. |
| r0-e020 | 68–75 | procedure | `unexecutable` | 1 | PokerAction requires `thinking`; all supplied action-only examples fail the declared schema. |
| r0-e021 | 79–87 | procedure | `reliable` | 1 | Re-grounding transient hand facts in the explicit prompt is executable and does not itself require deleting the learned opponent policy. |
| r0-e021b | 79–79 | procedure | `unexecutable` | 1 | The task prompt shows only the system player's chips; SkillOpt does not expose Query.metadata to the model. |
| r0-e022 | 89–95 | procedure | `unexecutable` | 1 | This repeated action-only instruction conflicts with the required `thinking` field. |
| r0-b002 | 90–91 | boilerplate | `insufficient_test` | 0 | Generic template advice; excluded from reliability denominators. |
| r0-e023 | 98–100 | strategy | `reliable` | 2 | The deterministic calling-station policy always calls facing a bet, and the benchmark explicitly rewards cross-hand opponent learning. |
| r0-e024 | 102–102 | strategy | `reliable` | 2 | This directly matches the always-call deterministic policy and is correctly scoped. |
| r0-e025 | 104–106 | strategy | `reliable` | 2 | Avoiding fold-dependent preflop bluffs follows from the opponent's always-call policy; the exact value range remains intentionally qualitative. |
| r0-e026 | 108–109 | strategy | `reliable` | 2 | The calling-station policy never folds facing a legal bet. |
| r0-e027 | 110–110 | strategy | `reliable` | 2 | The opponent checks when not facing a bet and calls when facing one, so direct value betting is policy-aligned. |
| r0-e028 | 110–110 | strategy | `insufficient_test` | 2 | The opponent never folds, so this is not a conventional semi-bluff; whether betting for equity value helps needs paired replay. |
| r0-e029 | 111–111 | strategy | `contradicted` | 2 | The deterministic policy already calls every bet; reducing size cannot increase its call frequency and can leave value unrealized. |
| r0-e030 | 112–112 | strategy | `reliable` | 2 | The primary no-bluff rule matches the policy; the evidence clause correctly allows updating a stale classification. |
| r0-e030b | 114–115 | strategy | `reliable` | 2 | This correctly repeats the opponent-conditioned gate rather than applying the exploit universally. |
| r0-e030c | 114–116 | strategy | `reliable` | 2 | This repeats a correctly scoped consequence of the always-call policy. |
| r0-e030d | 114–117 | strategy | `reliable` | 2 | This repeats the policy-aligned direct value-betting rule. |
| r0-e030e | 114–117 | strategy | `insufficient_test` | 2 | This repeats a draw-betting recommendation whose causal benefit is not established. |
| r0-e030f | 114–117 | strategy | `reliable` | 2 | This repeats the correctly scoped no-pure-bluff rule. |
| r0-e031 | 114–119 | strategy | `overgeneralized` | 2 | Requiring improvement is too narrow: a strong flop hand can remain ahead and should continue extracting from an always-calling opponent. |
| r0-e032 | 114–119 | strategy | `overgeneralized` | 2 | A bare one-pair threshold ignores board texture and relative hand strength; always being called makes mistaken thin value especially costly. |
| r0-e033 | 121–121 | strategy | `reliable` | 2 | This is the explicit continual-learning objective and all three variants have deterministic stable policies within stages. |
| r0-e034 | 123–128 | procedure | `unexecutable` | 1 | The second protocol repeats a nonexistent API and makes its absence an unconditional fallback trigger. |
| r0-e035 | 130–137 | procedure | `unexecutable` | 1 | The protocol both references invisible fields and contains an internal exactly-once versus reparse contradiction. |
| r0-e036 | 139–140 | strategy | `contradicted` | 2 | This repeats the rule that conflicts with the task's cross-hand adaptation requirement. |
| r0-e037 | 142–145 | procedure | `unexecutable` | 1 | The legal-action goal is sound, but this repeated implementation requires values the model does not receive. |
| r0-e038 | 147–149 | procedure | `unexecutable` | 1 | This is a third action-only instruction that conflicts with PokerAction. |
| r0-e039 | 151–153 | procedure | `unexecutable` | 1 | The model has neither logging nor reset tools, and cannot execute a post-response action in the same turn. |
| r0-e040 | 155–157 | strategy | `insufficient_test` | 3 | This repeats a fallback whose behavioral reliability is not isolated by existing traces. |
| r0-e041 | 159–159 | procedure | `unexecutable` | 1 | A skill prompt cannot turn unavailable operations into instrumentally enforced runtime controls. |

### Paired-replay candidates

- `r0-e001`: Use pot odds, implied odds, effective stack depth, and position to decide speculative preflop calls.
- `r0-e002`: Avoid large value bets when the board improves the opponent calling range; prefer smaller bets to extract from missed hands, thin pairs, or sticky callers.
- `r0-e003`: With a weak pair or no meaningful draw, prefer checking or calling to realize equity instead of building the pot.
- `r0-e004`: When ahead of a passive caller's range, prefer smaller repeated value bets over one large polarizing overbet.
- `r0-e011`: If any newly parsed field differs from the previous state, discard all previous memory about the hand and opponent.
- `r0-e018`: When required values remain ambiguous or a raise is illegal, fall back to CHECK, then affordable CALL, then FOLD.
- `r0-e028`: Against a calling station, bet strong draws as semi-bluffs.
- `r0-e029`: Use medium later-street sizes to encourage a calling station to call rather than large polarizing sizes.
- `r0-e031`: On the turn, continue value betting only hands that improved; otherwise use pot control when marginal.
- `r0-e032`: On the river against a calling station, thin value bet whenever holding at least one pair or reasonable showdown equity.
- `r0-e036`: If any new state field differs from any stored per-hand state, discard all previous hand and opponent memory.
- `r0-e040`: When parsing or legality remains ambiguous, choose CHECK, then affordable CALL, then FOLD.

## skillopt_poker_gpt5_run_1

Source: `results/validation/exploitable_poker/skillopt_poker_gpt5/run_1/skill_opt_ckpt/skill_v0005_accept_new_best.md`

### Label counts

| Label | Count |
|---|---:|
| `reliable` | 0 |
| `contradicted` | 0 |
| `harmful` | 0 |
| `overgeneralized` | 4 |
| `unexecutable` | 0 |
| `inert` | 0 |
| `insufficient_test` | 7 |

### Entry audit

| ID | Lines | Type | Label | Level | Reason |
|---|---:|---|---|---:|---|
| r1-b001 | 3–4 | boilerplate | `reliable` | 0 | Unchanged template metadata; excluded from reliability denominators. |
| r1-e001 | 8–8 | strategy | `insufficient_test` | 3 | The rule came from a special LAG-era node, but existing traces do not provide paired price/range cases proving that its qualified 'usually' claim fails elsewhere. |
| r1-e002 | 8–8 | strategy | `overgeneralized` | 2 | The rule omits value 3-bets and incorrectly makes deep stacks a general prerequisite; fold equity also vanishes against the calling station. |
| r1-e003 | 10–10 | strategy | `overgeneralized` | 2 | This resembles a LAG flop-float exploit but omits opponent, position, price, and street conditions. |
| r1-e004 | 10–10 | strategy | `insufficient_test` | 3 | Plausible but too qualitative for existing aggregate future outcomes to verify. |
| r1-e005 | 12–12 | strategy | `overgeneralized` | 2 | A later-street LAG check is informative, but calling-station and fit-or-fold policies also check routinely when not facing a bet; check alone does not justify betting. |
| r1-e006 | 12–12 | strategy | `overgeneralized` | 2 | This is plausible against the LAG policy after it tightens, but directly lacks fold equity against the calling station and is not generally implied by checks. |
| r1-e007 | 14–14 | strategy | `insufficient_test` | 3 | Reasonable generic caution, but neither deterministic policy code nor aggregate traces establish a universal reward effect. |
| r1-e008 | 14–14 | strategy | `insufficient_test` | 3 | The text is limited to thin value and fold equity; deterministic policies alone do not establish the best sizing within those objectives. |
| r1-e009 | 16–16 | strategy | `insufficient_test` | 3 | Plausible general poker knowledge, but this pilot lacks entry-isolated dangerous-board replay. |
| r1-e010 | 18–18 | strategy | `insufficient_test` | 3 | The permissive 'can justify' claim is not universal enough for the calling-station counterexample alone to falsify it; paired blocker cases are required. |
| r1-e011 | 18–18 | strategy | `insufficient_test` | 3 | The condition is sensible but too qualitative to classify without matched replay. |
| r1-b002 | 19–20 | boilerplate | `insufficient_test` | 0 | Generic template advice; excluded from reliability denominators. |

### Paired-replay candidates

- `r1-e001`: On the button facing a modest blind raise, prefer calling with marginal playable hands because position, price, and implied odds usually dominate folding or light 3-betting.
- `r1-e002`: Reserve 3-bets for deep stacks, clear fold equity, or a specific read.
- `r1-e003`: With limited showdown value or medium equity, favor check-call lines on flop and turn for pot control.
- `r1-e004`: Use positional advantage to avoid inflating pots with marginal holdings.
- `r1-e005`: Whenever an opponent checks on flop, turn, or river, frequently make a roughly half-pot value or protection bet.
- `r1-e006`: After multi-street passivity, make a modest river value-representative bet to maximize fold equity.
- `r1-e008`: Prefer consistent small or medium sizing for thin value and fold equity.
- `r1-e010`: Strong blockers can justify firmer preflop or river aggression.
