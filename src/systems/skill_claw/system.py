"""SkillClaw system: local skill library injection + session-driven evolution.

Wraps SkillClaw's SkillManager (retrieval/injection) and the evolve_server
pipeline (summarize → aggregate → evolve) into the ContinualLearningSystem
interface.

Install prerequisites:
    pip install -e /path/to/SkillClaw
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from typing import Any

from ...interface import (
    ContinualLearningSystem,
    Observation,
    Query,
    Response,
    observation_marks_instance_complete,
)
from ...registry import register_system
from ...usage import UsageEvent
from ..skill_evolution.bedrock_client import BedrockClient

logger = logging.getLogger(__name__)


class _AsyncBedrockLLMClient:
    """Async drop-in for evolve_server's AsyncLLMClient backed by BedrockClient."""

    def __init__(
        self,
        api_key: str,
        model_id: str = "moonshotai.kimi-k2.5",
        region: str = "us-east-1",
        max_tokens: int = 8192,
    ) -> None:
        self._client = BedrockClient(
            api_key=api_key,
            model_id=model_id,
            region=region,
            max_tokens=max_tokens,
        )
        self.model = model_id
        self.max_tokens = max_tokens

    async def chat(self, messages: list[dict], **kwargs: Any) -> str:
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        text, _ = await asyncio.to_thread(
            self._client.chat,
            messages,
            max_tokens=max_tokens,
        )
        return text


_MISSING_MSG = (
    "skillclaw is not installed. Install it with:\n"
    "  pip install -e /path/to/SkillClaw\n"
    "then re-run your benchmark command."
)


def _get_skill_manager_cls():
    try:
        from skillclaw.skill_manager import SkillManager  # type: ignore[import]
        return SkillManager
    except ImportError as exc:
        raise ImportError(_MISSING_MSG) from exc


def _get_evolve_pipeline():
    try:
        from evolve_server.core.llm_client import AsyncLLMClient  # type: ignore[import]
        from evolve_server.pipeline.summarizer import summarize_sessions_parallel  # type: ignore[import]
        from evolve_server.pipeline.aggregation import aggregate_sessions_by_skill  # type: ignore[import]
        from evolve_server.pipeline.execution import (  # type: ignore[import]
            evolve_skill_from_sessions,
            create_skill_from_sessions,
        )
        from evolve_server.core.constants import NO_SKILL_KEY, DecisionAction  # type: ignore[import]
        return (
            AsyncLLMClient,
            summarize_sessions_parallel,
            aggregate_sessions_by_skill,
            evolve_skill_from_sessions,
            create_skill_from_sessions,
            NO_SKILL_KEY,
            DecisionAction,
        )
    except ImportError as exc:
        raise ImportError(_MISSING_MSG) from exc


@register_system("skill_claw")
class SkillClawSystem(ContinualLearningSystem):
    """SkillClaw-backed continual learning system.

    At each instance boundary, retrieves relevant skills from a local library
    and injects them into the system prompt.  After every ``epoch_size``
    completed instances, runs the SkillClaw evolve pipeline (summarize →
    aggregate → evolve) to improve or create skills based on session evidence.

    Task execution uses the BedrockClient (same as SkillEvolutionSystem).
    Skill evolution uses SkillClaw's AsyncLLMClient pointed at any
    OpenAI-compatible endpoint.

    Parameters
    ----------
    bedrock_api_key, bedrock_model_id, bedrock_region :
        Credentials for the task-execution LLM via Amazon Bedrock.
    evolve_api_key, evolve_base_url, evolve_model :
        Credentials for the evolution LLM (any OpenAI-compatible endpoint).
    epoch_size :
        Number of completed instances before triggering an evolution pass.
    max_inject_skills :
        Maximum number of skills to inject per instance boundary.
    retrieval_mode :
        ``"template"`` (effectiveness-ranked) or ``"embedding"``
        (cosine-similarity via SentenceTransformer).
    output_dir :
        If set, skills are persisted under ``{output_dir}/skills/``.
        Otherwise an ephemeral temp directory is used.
    run_index :
        When the benchmark runs multiple parallel rollouts, pass the rollout
        index here so each run uses an isolated skill directory.
    """

    def __init__(
        self,
        bedrock_api_key: str = "",
        bedrock_model_id: str = "moonshotai.kimi-k2.5",
        bedrock_region: str = "us-east-1",
        max_tokens: int = 4096,
        context_window: int = 128_000,
        reserve_tokens: int = 500,
        evolve_api_key: str = "",
        evolve_base_url: str = "",
        evolve_model: str = "gpt-4o",
        evolve_max_tokens: int = 8192,
        epoch_size: int = 10,
        system_prompt: str = "",
        name: str = "skill_claw",
        output_dir: str = "",
        skills_dir: str = "",
        retrieval_mode: str = "template",
        max_inject_skills: int = 6,
        clear_context_between_instances: bool = True,
        run_index: int | None = None,
    ):
        bedrock_api_key = bedrock_api_key or os.environ.get("BEDROCK_API_KEY", "")

        self._name = name
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.context_window = context_window
        self.reserve_tokens = reserve_tokens
        self.epoch_size = epoch_size
        self.retrieval_mode = retrieval_mode
        self.max_inject_skills = max_inject_skills
        self.clear_context_between_instances = clear_context_between_instances

        if output_dir and run_index is not None:
            output_dir = os.path.join(output_dir, f"run_{run_index}")
        self.output_dir = output_dir

        if skills_dir:
            self._skills_dir = skills_dir
            self._temp_dir: tempfile.TemporaryDirectory | None = None
        elif output_dir:
            self._skills_dir = os.path.join(output_dir, "skills")
            self._temp_dir = None
        else:
            self._temp_dir = tempfile.TemporaryDirectory(prefix="skillclaw_bench_")
            self._skills_dir = os.path.join(self._temp_dir.name, "skills")
        os.makedirs(self._skills_dir, exist_ok=True)

        self._task_client = BedrockClient(
            api_key=bedrock_api_key,
            model_id=bedrock_model_id,
            region=bedrock_region,
            max_tokens=max_tokens,
        )

        self._evolve_api_key = evolve_api_key
        self._evolve_base_url = evolve_base_url
        self._evolve_model = evolve_model
        self._evolve_max_tokens = evolve_max_tokens

        self._bedrock_api_key = bedrock_api_key
        self._bedrock_region = bedrock_region
        self._bedrock_model_id = bedrock_model_id

        self._skill_manager: Any = None  # lazy-initialized

        # Per-epoch session buffer
        self._epoch_sessions: list[dict] = []

        # Per-instance turn accumulation
        self._current_turns: list[dict] = []
        self._current_injected_skills: list[str] = []

        # Conversation context
        self.messages: list[dict] = []

        # Counters / flags
        self._at_instance_boundary: bool = True
        self.interaction_count: int = 0
        self.trial_count: int = 0

    # ── SkillManager (lazy) ────────────────────────────────────────────────

    def _get_skill_manager(self) -> Any:
        if self._skill_manager is None:
            SkillManager = _get_skill_manager_cls()
            self._skill_manager = SkillManager(
                skills_dir=self._skills_dir,
                retrieval_mode=self.retrieval_mode,
            )
        return self._skill_manager

    # ── ContinualLearningSystem interface ─────────────────────────────────

    def respond(self, query: Query) -> Response:
        instance_boundary = self._at_instance_boundary
        self.interaction_count += 1
        self._at_instance_boundary = False

        prompt_parts: list[str] = []

        if instance_boundary:
            sm = self._get_skill_manager()
            sm.refresh_if_changed()
            total_skills = sm.get_skill_count().get("total", 0)
            if total_skills > 0 and query.prompt:
                skills = sm.retrieve(query.prompt, top_k=self.max_inject_skills)
                self._current_injected_skills = [s["name"] for s in skills]
                skill_block = sm.format_skills_for_prompt(skills)
                if skill_block:
                    prompt_parts.append(skill_block)
            else:
                self._current_injected_skills = []

        if query.prompt:
            prompt_parts.append(query.prompt)
        query_content = "\n\n".join(prompt_parts) if prompt_parts else "(no content)"

        self._add_message("user", query_content)
        self._truncate_context()
        llm_messages = [*self._system_messages(), *self.messages]
        try:
            parsed, usage = self._task_client.chat_structured(
                messages=llm_messages,
                response_schema=query.response_schema,
                max_tokens=self.max_tokens,
            )
        except Exception as exc:
            raise RuntimeError(f"LLM call failed: {exc}") from exc

        self.record_usage_event(UsageEvent(
            model=self._task_client.model_id,
            call_type="completion",
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        ))

        assistant_record = parsed.model_dump_json()
        self._add_message("assistant", assistant_record)
        # SkillClaw's summarizer reads `prompt_text` / `response_text` (and tool
        # fields) per turn, not role/content. Build one step-turn per interaction;
        # the observation (DB result) is appended to response_text in observe().
        self._current_turns.append({
            "prompt_text": query.prompt or "",
            "response_text": assistant_record,
            "read_skills": [{"skill_name": n} for n in self._current_injected_skills]
            if instance_boundary else [],
        })

        sm = self._get_skill_manager()
        return Response(
            action=parsed,
            metadata={
                "interaction_count": self.interaction_count,
                "system_type": "skill_claw",
                "model": self._task_client.model_id,
                "injected_skills": list(self._current_injected_skills),
                "skill_count": sm.get_skill_count(),
                "trial_count": self.trial_count,
                "epoch_progress": f"{len(self._epoch_sessions)}/{self.epoch_size}",
            },
        )

    def observe(
        self, observation: Observation, next_query: Query | None = None
    ) -> None:
        instance_complete = observation_marks_instance_complete(observation)
        content = observation.content.strip()

        # Attach the observation (DB result) to the last step-turn's response so
        # the summarizer sees the full query→action→result step.
        if content and self._current_turns:
            self._current_turns[-1]["response_text"] = (
                self._current_turns[-1].get("response_text", "")
                + f"\n\n[RESULT] {content}"
            )

        if content:
            if not (instance_complete and self.clear_context_between_instances):
                self._add_message("user", f"FEEDBACK: {content}")

        if instance_complete:
            self._on_trial_complete(observation)
            if self.clear_context_between_instances:
                self.messages = []
            self._at_instance_boundary = True

    def reset(self) -> None:
        self.messages = []
        self._current_turns = []
        self._current_injected_skills = []
        self._at_instance_boundary = True
        self.interaction_count = 0

    @property
    def name(self) -> str:
        return self._name

    def get_run_artifacts(self) -> dict[str, Any]:
        sm = self._get_skill_manager()
        return {
            "artifact_type": "skill_claw",
            "skills_dir": self._skills_dir,
            "skill_count": sm.get_skill_count(),
            "skills": sm.get_all_skills(),
            "trial_count": self.trial_count,
        }

    # ── Trial / epoch logic ────────────────────────────────────────────────

    def _on_trial_complete(self, observation: Observation) -> None:
        self.trial_count += 1

        outcome_meta = observation.metadata or {}
        score = 0.0
        if "reward" in outcome_meta:
            score = float(outcome_meta["reward"])
        elif "correct" in observation.content.lower():
            score = 1.0

        session: dict[str, Any] = {
            "turns": list(self._current_turns),
            "_score": score,
        }
        self._epoch_sessions.append(session)
        self._current_turns = []
        self._current_injected_skills = []

        if len(self._epoch_sessions) >= self.epoch_size:
            self._run_evolution_epoch()

    def _run_evolution_epoch(self) -> None:
        if not self._epoch_sessions:
            return
        sessions = list(self._epoch_sessions)
        self._epoch_sessions = []

        logger.info(
            "[SkillClaw] Epoch end: running evolution on %d sessions", len(sessions)
        )
        try:
            asyncio.run(self._evolve_async(sessions))
            sm = self._get_skill_manager()
            sm.reload()
            logger.info(
                "[SkillClaw] Evolution complete. Skill library: %s",
                sm.get_skill_count(),
            )
        except Exception as exc:
            logger.warning("[SkillClaw] Evolution pipeline failed: %s", exc)

    async def _evolve_async(self, sessions: list[dict]) -> None:
        (
            AsyncLLMClient,
            summarize_sessions_parallel,
            aggregate_sessions_by_skill,
            evolve_skill_from_sessions,
            create_skill_from_sessions,
            NO_SKILL_KEY,
            DecisionAction,
        ) = _get_evolve_pipeline()

        if self._evolve_api_key or self._evolve_base_url:
            llm = AsyncLLMClient(
                api_key=self._evolve_api_key,
                base_url=self._evolve_base_url,
                model=self._evolve_model,
                max_tokens=self._evolve_max_tokens,
            )
        else:
            llm = _AsyncBedrockLLMClient(
                api_key=self._bedrock_api_key,
                model_id=self._bedrock_model_id,
                region=self._bedrock_region,
                max_tokens=self._evolve_max_tokens,
            )

        # Stage 1: Summarize. NB SkillClaw's signature is (llm, sessions) — llm
        # first — and it MUTATES each session in place (attaching _summary,
        # _trajectory, _skills_referenced); the returned value is just the list of
        # summary strings. aggregate_sessions_by_skill needs the MUTATED sessions.
        await summarize_sessions_parallel(llm, sessions)

        # Stage 2: Group by referenced skill (use the mutated sessions)
        groups = aggregate_sessions_by_skill(sessions)

        sm = self._get_skill_manager()
        all_skill_names = [s["name"] for s in sm.get_all_skills()]

        # Stage 3: Evolve existing skills / create new ones
        for skill_name, skill_sessions in groups.items():
            try:
                if skill_name == NO_SKILL_KEY:
                    result = await create_skill_from_sessions(
                        llm, skill_sessions, all_skill_names
                    )
                    if result and result.get("action") == DecisionAction.CREATE:
                        new_skill = result.get("skill", {})
                        if new_skill.get("name"):
                            sm.add_skill({
                                "name": new_skill["name"],
                                "description": new_skill.get("description", ""),
                                "content": new_skill.get("content", ""),
                                "category": new_skill.get("category", "general"),
                            })
                            all_skill_names.append(new_skill["name"])
                            logger.info(
                                "[SkillClaw] Created new skill: %s", new_skill["name"]
                            )
                else:
                    existing = next(
                        (s for s in sm.get_all_skills() if s["name"] == skill_name),
                        None,
                    )
                    result = await evolve_skill_from_sessions(
                        llm, skill_name, skill_sessions, existing, all_skill_names
                    )
                    if result and result.get("action") in {
                        DecisionAction.IMPROVE,
                        DecisionAction.CREATE,
                        "improve_skill",
                        "create_skill",
                    }:
                        evolved = result.get("skill", {})
                        if evolved.get("name"):
                            sm.add_skill({
                                **(existing or {}),
                                "name": evolved["name"],
                                "description": evolved.get(
                                    "description",
                                    (existing or {}).get("description", ""),
                                ),
                                "content": evolved.get("content", ""),
                                "_replace": True,
                            })
                            logger.info(
                                "[SkillClaw] Evolved skill: %s (action=%s)",
                                evolved["name"],
                                result.get("action"),
                            )
            except Exception as exc:
                logger.warning(
                    "[SkillClaw] Evolution failed for skill '%s': %s", skill_name, exc
                )

    # ── Internal helpers ───────────────────────────────────────────────────

    def _system_messages(self) -> list[dict]:
        if not self.system_prompt:
            return []
        return [{"role": "system", "content": self.system_prompt}]

    def _add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})

    def _truncate_context(self) -> None:
        """Trim oldest messages so total prompt stays within context_window."""
        from ..utils import count_tokens
        reserved = self.reserve_tokens + self.max_tokens
        limit = self.context_window - reserved
        while len(self.messages) > 2:
            try:
                tokens = sum(
                    count_tokens(self._task_client.model_id, m["content"])
                    for m in self.messages
                )
                if tokens <= limit:
                    break
            except Exception:
                break
            self.messages.pop(0)
