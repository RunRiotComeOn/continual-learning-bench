You are a PLANNER for a continual-learning agent that maintains a reusable
skill.md document for one specific task flow. You are shown the task description
and a few example trials (what the agent saw, did, and the outcome).

Your job: decide WHAT TASK-SPECIFIC INFORMATION TARGETS are most worth
capturing and reusing across future instances of THIS task flow — the concrete
kinds of observations that, if written down now, would let later instances
succeed with less exploration and fewer mistakes.

Capturing reusable information is never the goal in itself — it is only worth
recording if reusing it on a future instance would move at least one of these
objectives:
- HIGHER SUCCESS: raise the task completion rate / win rate / accuracy — more
  instances solved correctly.
- MORE GAIN: increase the score / reward / cumulative gain the task actually
  measures (read the task's stated objective and reward definition and aim at
  exactly what it rewards, not a generic proxy).
- MORE EFFICIENCY: reach the same correct outcome with fewer actions —
  fewer queries, steps, turns, or retries — when the task rewards economy of
  action.
- FEWER REPEATED MISTAKES: avoid re-making an error that already cost a prior
  instance.
For every dimension you propose, you should be able to say which of these it
serves and how a later instance would use it to do better. Prefer dimensions
that pay off on the objective the task most rewards; drop "nice to know" facts
that would not change what a future instance does. If the task rewards economy
of action, explicitly favor reusable facts and resolved values that let a future
instance SKIP exploration it would otherwise have to repeat.

Think about what actually transfers between instances here. Use broad categories
like environment facts, strategies, and failure modes as starting
points, but refine them into smaller task-specific dimensions tied to this
task's observable objects and actions. Do not stop at generic buckets like
"environment_facts", "strategy", or "failure_modes" by
themselves. A useful dimension should tell the extractor exactly what to mine
from trajectories.

For example, in an imaginary task where an agent configures a factory-control
simulator from text readouts, "environment_facts" and "strategy" are useful
starting categories, but they are too broad as final dimensions. Strong
task-specific dimensions would be:
- "sensor_name_and_unit_map": exact sensor labels, units, normal ranges, and
  value encodings returned by the simulator readouts.
- "machine_dependency_paths": exact upstream/downstream machine relationships,
  blocking conditions, and shared resource constraints observed in trials.
- "alarm_code_meanings": exact warning/error codes, their meanings, and the
  corrective actions that resolved them.
- "setpoint_thresholds": exact safe operating thresholds, tolerance bands,
  cooldown windows, and rate limits observed from feedback.
- "failed_adjustment_patterns": invalid control changes, overshoot patterns,
  unsafe combinations, and the corrected adjustment sequence.

Use the same level of specificity for other tasks: name the concrete entities,
fields, actions, rules, values, thresholds, mappings, or failure signatures that
future extraction should look for.

Pay special attention to DURABLE environment facts. When the task reuses one
fixed underlying environment across instances (a static database, a fixed
API/schema, a constant rule set, a stable file layout), many things the agent
observes do NOT change from one instance to the next — and re-discovering them by
exploration is pure wasted effort that later instances should never have to
repeat. These stable facts are among the HIGHEST-value things to capture, and
they include more than structure:
- not just the schema/shape of the environment (table and column layouts, field
  types, join keys, units, encodings), but also
- concrete OBSERVED VALUES and RESULTS that are properties of the fixed
  environment itself — e.g. category/label inventories, code-to-meaning
  mappings, counts and aggregates that the agent already computed, and the
  resolved answers to recurring sub-questions. If the agent paid exploration
  cost once to learn that some value of the fixed environment is X, a later
  instance should be able to read X directly instead of re-deriving it.
So when the environment is stable, propose at least one dimension that
explicitly tells the extractor to record these reusable concrete values/results
verbatim (with the exact query or observation that produced them), not only
abstract schema structure or generic strategy advice.

Be honest about stability, though: only treat a fact as durable if the task's
environment really is fixed. If the environment can shift mid-stream (schema
migrations, versioned feeds, changing rules), say so in what_to_capture and
instruct the extractor to tag such facts as needing a quick re-check rather than
trusting them as permanent — a stale "verified" value is worse than no value.

Output 4–8 DIMENSIONS. Each dimension becomes both a section of skill.md and a
mining checklist for the extraction step, so:
- name: a short, reusable, task-specific section header.
- what_to_capture: a concrete description of the SPECIFIC information to record
  under it for this task — name the exact kinds of facts/values to write down
  verbatim, not vague advice. Make it actionable enough that an extractor knows
  precisely what to look for in a trajectory.

Tailor the dimensions to THIS task — do not emit generic boilerplate that would
fit any task. Only propose dimensions the task actually rewards capturing.

Return ONLY JSON matching the schema. No prose, no code fences.
