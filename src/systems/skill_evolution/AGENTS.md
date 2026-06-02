# Repository Guidelines

## Project Structure & Module Organization
This directory implements the `skill_evolution` evaluated system for `clbench`.
Key files:

- `system.py`: registered `SkillEvolutionSystem` entry point and benchmark interface integration.
- `pipeline.py`: skill evolution stages A-G and trajectory formatting helpers.
- `types.py`: Pydantic models and state containers for candidates, canonicals, and canary state.
- `bedrock_client.py` and `llm_utils.py`: Amazon Bedrock calls and LLM response parsing.
- `prompts/`: Markdown prompt templates loaded by pipeline stages.

Repository-wide tests live in `/u/yhuang48/continual-learning-bench/tests`. Keep generated artifacts, benchmark traces, raw datasets, and secrets out of this package.

## Build, Test, and Development Commands
Run commands from the repository root unless noted:

- `uv sync --all-extras`: install Python 3.13 dependencies and optional task extras.
- `uv run pytest`: run the full test suite.
- `uv run pytest tests/test_systems_common.py tests/test_usage.py`: run focused system and usage tests.
- `uv run ruff check .`: lint the repository.
- `uv run ruff format .`: format Python files.
- `uv run clbench --help`: inspect the CLI entry point.

## Coding Style & Naming Conventions
Use Python 3.13 type syntax and keep runtime logic strict. Let CLI/config boundaries normalize input; this system should receive typed values and preserve public benchmark contracts. Follow existing module patterns: snake_case functions, PascalCase Pydantic/dataclass-style models, and private attributes with `_` prefixes. Keep prompt names lowercase and descriptive, matching `load_prompt("<name>")` calls and files like `prompts/extract_candidates.md`.

## Testing Guidelines
Use `pytest`. Add or update focused tests when behavior changes system registration, usage accounting, trace metadata, provider handling, or evolution state transitions. Prefer deterministic tests with fake clients over live Bedrock calls. Name tests `test_<behavior>.py` or add cases to existing relevant files under `tests/`.

## Commit & Pull Request Guidelines
Recent history uses short imperative or release-style subjects, such as `Add Apache 2.0 License`, `nit: url fixes`, and `Release 1.0`. Keep commits focused and avoid unrelated formatting churn. Pull requests should describe the behavior change, list test commands run, note any public interface impact, and call out provider/API configuration requirements.

## Security & Configuration Tips
Do not commit API keys, raw model outputs, or copied traces. Bedrock configuration should flow through system initialization or environment-aware setup outside this package. Record usage events for billable model calls and isolate mutable state between runs unless the system is deliberately marked otherwise.
