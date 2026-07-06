# Story: From Naive Skill Extraction to Tri-Track Skill Evolution

## One-Sentence Thesis

We began with skill extraction as summarization, but found that continual
learning requires epistemic bookkeeping: what was observed, how reusable it is,
what kind of knowledge it is, and how much evidence that kind of knowledge needs
before it should change behavior.

Put differently:

> The evolution from naive skill extraction to tri-track skill evolution is the
> evolution from writing memories to governing when memories are allowed to
> become policy.

## The Continuous Motivation

The natural starting point for continual learning is simple: after each task
instance, ask the model to reflect on what happened, write useful lessons into a
`skill.md`, and provide that document back to the agent on future instances. This
tests the most basic hypothesis:

> If an agent can convert feedback into reusable text, then it should improve
> over time.

That hypothesis is partly right. A persistent skill document can carry useful
knowledge forward. But a naive append-only extractor quickly exposes a deeper
problem: not all remembered text deserves the same trust. Some observations are
stable environment facts. Some are probabilistic strategies. Some are warnings
about failures. Some are one-off anecdotes. Some are the agent's own unsupported
guesses. Treating all of these as the same kind of memory pollutes the skill
document and eventually makes it less reliable.

The system therefore evolves through a sequence of failure-driven refinements.
Each step adds the smallest mechanism needed to fix the previous step's
weakness.

## 1. Naive Extraction: Memory as Text

The first baseline treats skill extraction as reflection:

- run one task instance;
- ask the model what lesson should be remembered;
- append the lesson to `skill.md`;
- inject `skill.md` into the next instance.

This is useful because it gives the agent an external memory. It can remember
schemas, recurring mistakes, successful procedures, and task-specific hints that
may not be repeated in later prompts.

The problem is that naive memory has no evidence discipline. It tends to record:

- per-instance anecdotes rather than reusable knowledge;
- the agent's hypotheses as if they were environment facts;
- every action in a successful trajectory as if it caused success;
- duplicate or near-duplicate lessons;
- contradictory advice from different contexts;
- stale claims that should have been replaced.

This motivates the first shift:

> Reflection is not enough; reusable skills need evidence and identity.

## 2. Canonicalized Skills: Memory as Supported Claims

The next step is to stop treating `skill.md` as a raw append log. Instead, the
system extracts candidate knowledge items and canonicalizes them into stable
claims.

Each canonical claim carries bookkeeping:

- a description;
- evidence snippets;
- support quantity;
- contributing trials;
- an effect label;
- a status;
- an update operation such as `add`, `refine`, or `replace`.

This changes the question from "what did the model say after this trial?" to
"what reusable claim is being supported across experience?"

Canonicalization fixes important problems:

- repeated observations reinforce the same claim instead of creating duplicate
  bullets;
- weak claims can wait until they reach a trigger threshold;
- later evidence can refine or replace older entries;
- `skill.md` becomes the deployed view of memory, while the aggregator holds the
  evidence state behind it.

But this still leaves a second issue: single-trial extraction often misses the
cross-instance pattern. If each trajectory is summarized in isolation, the model
has to infer recurrence indirectly later.

This motivates the next shift:

> Support is a batch property, not just a single-trial property.

## 3. Batch Extraction: Memory as Cross-Instance Patterns

Batch extraction lets the optimizer inspect an entire epoch of recent trials at
once. Instead of extracting one candidate from one trajectory at a time, the model
sees multiple trajectories together and reports which trials support each point.

This has two advantages:

- recurrence is observed directly;
- the support count can be grounded in the batch's actual trajectories.

The extractor emits structured points with fields such as:

- `description`;
- `evidence`;
- `trajectories`;
- `match`;
- `update_op`;
- `support_type`.

The listed trajectory indices become the support quantity added to the canonical
aggregator. This reduces fragmentation and makes "how many independent instances
support this claim?" an explicit part of the learning signal.

However, better counting does not solve a structural problem: the skill document
still needs to know where different kinds of knowledge belong.

This motivates the next shift:

> The structure of memory determines what can be learned.

## 4. Planner Skeleton: Memory as Task-Shaped Structure

A generic `skill.md` with broad sections like "facts", "strategy", and
"mistakes" is often too coarse. Important task-specific knowledge may have no
obvious home:

- answer/cache values may be buried or omitted;
- strategy may remain a flat, vague section;
- failure modes may mix with ordinary procedures;
- sections may drift during refinement;
- extraction may under-produce the very content the task rewards.

The planner skeleton addresses this by designing the structure of `skill.md`
after the first full batch. The planner reads the task description and real
trajectories, then creates task-specific sections and subsections.

The skeleton records:

- the task objective and scoring rule, frozen up front;
- reference or structural knowledge slots;
- strategy decision-point slots;
- failure-mode slots;
- answer/cache slots only when values are genuinely key-determined.

This turns memory from a free-form note pile into a task-shaped interface. The
skeleton becomes both the scaffold of `skill.md` and the focus plan that guides
future extraction.

But once memory is structured, another problem becomes visible: different
sections do not obey the same evidence rules.

This motivates the final shift:

> Different knowledge types have different epistemology.

## 5. Tri-Track Evolution: Memory as Typed Knowledge With Different Evidence Bars

The key limitation of a single global aggregator is that it applies one threshold
and one promotion policy to every kind of knowledge. That is not coherent.

A stable environment fact and a probabilistic strategy read are not the same kind
of claim:

- A schema field, table name, fixed encoding, or key-determined value can be
  trusted from one authoritative observation.
- A strategy such as "this opponent tends to fold" or "this procedure usually
  works" is probabilistic and can be dangerous if over-applied from one example.
- A failure mode may be immediately trustworthy when grounded in a hard error,
  but more tentative when inferred from a poor outcome.

A single threshold creates two opposite failures:

- It is too conservative for authoritative facts, causing useful fixed knowledge
  to wait forever.
- It is too aggressive for strategies, causing the agent to over-trust
  single-instance tendencies.

`skill_evo_tri_track` fixes this by keeping one deployed `skill.md` but using
three separate learning tracks behind it:

| Track | Default threshold | Fast-track | Role |
|---|---:|---|---|
| `factual` | 1 | on | Stable environment facts and key-determined values. |
| `strategy` | 2 | off | Procedures, decision policies, and probabilistic reads. |
| `failure` | 2 | on | Demonstrated traps, with hard failures promotable from one observation. |

Each track has its own prompt, focus plan, aggregator, trigger threshold, and
fast-track policy. The final agent still consumes one coherent skill document,
but the optimizer maintains separate evidence regimes for different kinds of
knowledge.

This is the core design claim:

> Continual learning systems should not merely accumulate experience. They
> should decide what kind of knowledge each experience supports, and apply the
> right evidence bar before that knowledge changes future behavior.

## The Design Ladder

The system can be presented as this progression:

1. **Naive extraction:** memory as text.
2. **Canonicalization:** memory as supported claims.
3. **Batch extraction:** memory as cross-instance patterns.
4. **Planner skeleton:** memory as task-shaped structure.
5. **Tri-track evolution:** memory as typed knowledge with different evidence
   bars.

This framing keeps the story continuous. The final system is not a collection of
extra mechanisms. It is the result of repeatedly asking why the previous memory
system failed and adding only the machinery needed to make memory reliable enough
to guide future behavior.

