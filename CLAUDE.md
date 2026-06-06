# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync --all-extras        # install all dependencies
source .venv/bin/activate   # activate the venv

uv run pytest               # run all tests
uv run pytest tests/test_rollout.py  # run a single test file
uv run pytest -k test_name  # run a single test by name

uv run ruff check --fix     # lint (also: make lint)
uv run ruff format          # format (also: make format)

clbench list                # list all registered tasks and systems
clbench inspect task exploitable_poker  # show task params, schedules, variants
clbench smoke exploitable_poker --system icl  # one-interaction wiring check
clbench run exploitable_poker --system icl --schedule quick_test  # run a benchmark
clbench run-all --name my_run --system icl  # run all tasks with a default schedule
clbench doctor              # check environment prerequisites
```

## Architecture

### Core contracts (`src/interface.py`)

The entire framework pivots on two abstract base classes:

- **`ContinualLearningTask`** — implements `build_canonical_run_state()`, `step(response) → TaskStepResult`, `evaluate() → TaskResult`, `build_current_query() → Query`. Must set `r_max` (mean per-instance max reward for the default schedule) and accept `num_instances` in `__init__`.
- **`ContinualLearningSystem`** — implements `respond(query) → Response`, `reset()`, and optionally `observe(observation, next_query)`. Systems call `self.record_usage_event(UsageEvent(...))` for billable LLM calls.

The interaction dataflow: `Query → system.respond() → Response → task.step() → TaskStepResult(observation, next_query, done)`. The runtime calls `system.observe(observation, next_query)` after each step so systems can update state before the next turn.

### Discovery and registration

Tasks live in `src/tasks/<name>/task.py` and systems live in `src/systems/<name>/` (or `src/systems/<name>.py`). Both are auto-discovered by the registry (`src/registry.py`) via filesystem glob — no manual import lists. Classes must be decorated with `@register_task("name")` or `@register_system("name")`.

### Execution harness (`src/runs/`, `src/runtime/`)

`clbench run` resolves task + system classes, runs a stateless baseline (one worker per instance, parallelized), then runs the full stateful rollout(s). The `RunMode` (permute/replay) controls how instance ordering varies across repeated runs. Traces are written to `results/<task>/` as gzip JSON; viewer artifacts bundle the full run for `viewers/` HTML pages.

### Skill Evolution system (`src/systems/skill_evolution/`)

An epoch-based system that maintains a self-evolving `skill.md` document:

1. **Stage A** — initializes the skill.md skeleton from the first trial
2. **Stage B** — extracts atomic `Candidate` skill edits from each trial trajectory (parallelized via `ThreadPoolExecutor`)
3. **Stage C** — canonicalizes candidates into an `Aggregator` (deduplication, tracking quantity/evidence)
4. **Stage D** — when a `Canonical` reaches `trigger_threshold`, generates an updated skill.md; high-confidence canonicals (≥ `trigger_threshold × fast_promote_multiplier`) are fast-promoted; others enter canary validation
5. **Stage F** — canary epoch compares Δ(canary_mean − baseline_score): promote if ≥ 0, revert otherwise
6. **Stage decay** — removes canonicals that haven't been reinforced for `decay_threshold` epochs
7. **Stage G** — periodic structural refinement of skill.md every `refine_interval` trials

The system uses Amazon Bedrock Converse API directly (`BedrockClient`), not LiteLLM. Prompt templates are markdown files in `src/systems/skill_evolution/prompts/`.

### Configs and schedules

`configs/<task>/` holds JSON run configs. Schedules are defined in `src/tasks/<name>/schedules/` (e.g. `default.json`, `quick_test.json`) and control `num_instances`, `runs`, `max_workers`, and `mode`. `clbench run-all` requires a `default.json` schedule per task.

## Key constraints

- Tasks must be deterministic from `self.seed`; `Query.instance_id` and `Query.instance_index` must be stable across runs.
- Systems must isolate state across concurrent runs unless `parallel_safe = False`.
- `ContinualLearningTask.__init_subclass__` enforces that all concrete task classes accept `num_instances` — this check runs at import time.
- Do not break public CLI flags, trace/artifact schemas, or task/system interfaces without explicit approval.
