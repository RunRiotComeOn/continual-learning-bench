"""skill_evo_tri_track — a self-contained, per-track skill-evolution system.

This is NOT a subclass of the skill_evo_planner family. It owns its whole loop
(``TriTrackSystem`` extends only the abstract ``ContinualLearningSystem``) and
deliberately leaves out every mechanism that is disabled in tri_keyed anyway —
there is NO canary/validation, NO decay, NO contradiction-audit, NO naive/raw/
stateless ablation switch. It reuses only stateless helper FUNCTIONS from the
planner package (extraction, promotion, skeleton design, refine).

The one new idea: the three knowledge tracks are handled with DIFFERENT policies,
because they carry different kinds of knowledge that deserve different evidence
bars (see README.md):

  track      threshold   fast-track (promote a grounded canonical at quantity=1)
  -------    ---------   --------------------------------------------------------
  factual    1           ON   — a grounded environment fact is true on one sighting
  strategy   2           OFF  — a strategy is a probabilistic read; needs repetition
  failure    2           ON   — a HARD/explicit failure promotes at once; an
                               inferred trap waits for a 2nd confirmation

Each track keeps its OWN aggregator, so its quantity/threshold gate is independent.
At each batch boundary every active track runs its own extraction pass (its own
``extract_<track>`` prompt + its track's sections) into its own aggregator, then
its own promotion pass folds the triggered canonicals into the single shared
skill.md.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
import re
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
from ..skill_evo_planner.batch_system import stage_bc_batch_summarize
from ..skill_evo_planner.bedrock_client import BedrockClient
from ..skill_evo_planner.pipeline import (
    _chat,
    _strip_open_questions_sections,
    fmt_trajectory,
    stage_d_trigger_and_update,
    stage_g_refine_skeleton,
)
from ..skill_evo_planner.prompts import load_prompt
from ..skill_evo_planner.types import Aggregator, TrialRecord
from ..skill_evo_planner_tri.system import (
    TRACKS,
    build_track_plans,
    generate_skeleton_plan,
    resolve_section_tracks,
)

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_MAX_CONTEXT = 128_000
_OBJECTIVE_HEADER = "## task_objective_and_scoring"

_SKILL_USAGE_NOTE = (
    "\nHow to use it: the FACTS about the fixed environment (structure, rules, "
    "values that do not change) are stable — rely on them. But STRATEGY / "
    "exploitation notes about how a counterpart or other adaptive party tends to "
    "behave are PROBABILISTIC tendencies learned from past cases: true on AVERAGE, "
    "not every time. Use them as priors that tilt a close call, NOT as guarantees. "
    "Do not take an irreversible or high-variance action purely because a read "
    "'usually' holds — size your commitment to the strength you actually hold in "
    "THIS instance, because the rare exception to a tendency is exactly where "
    "over-trusting it is most costly. (Stable-environment tasks have no such "
    "adaptive counterpart, so their learned regularities can be relied on directly.)"
)


def build_fewshot_plan(
    task_description: str,
    trials: list[TrialRecord],
    client: Any,
    prompt_dir: str | None,
    objective_name: str,
    max_samples: int,
) -> tuple[str, dict[str, str], dict[str, str], bool]:
    """Few-shot variant of the planner (see prompts/section_plan_fewshot.md).

    The planner returns TWO parts separated by ``===EXTRACTION_EXAMPLES===``:
    PART 1 is a SECTION-LEVEL-ONLY skeleton (coarse `##` sections + track tags, no
    task-specific `###` subsections) that becomes the skill.md file scaffold; PART 2
    is per-section few-shot examples of what to extract, which become the extraction
    focus plans fed to the extractor prompts but are NEVER written to the file.

    This decouples the two jobs the old skeleton conflated: the file stays free of
    task-prompt-derived subsection headings (the framing-bias vehicle), while the
    extractor still gets rich, trajectory-grounded guidance.

    Returns ``(file_skeleton, section_track, track_plans, factual_enabled)`` — same
    shape the caller expects from the skeleton path.
    """
    system_prompt = load_prompt("section_plan_fewshot", prompt_dir)
    trajs = ""
    for i, t in enumerate(trials[:max_samples], 1):
        trajs += (
            f"\n### Example trial {i} (outcome={t.final_outcome})\n"
            f"{fmt_trajectory(t.trajectory)}\n"
        )
    user = (
        f"## Task description\n{task_description or '(unknown)'}\n\n"
        f"## Example trials (a full batch)\n{trajs or '(none)'}"
    )
    raw = _chat(client, system_prompt, user, max_tokens=8192)
    parts = re.split(r"===\s*EXTRACTION_EXAMPLES\s*===", raw, maxsplit=1)
    part1 = _strip_open_questions_sections(parts[0]).strip()
    part2 = parts[1] if len(parts) > 1 else ""

    # PART 1 is a tagged section-only skeleton → reuse the shared resolver to get the
    # section→track map, the factual-enabled flag, and the tag-stripped file skeleton.
    section_track, factual_enabled, file_skeleton = resolve_section_tracks(
        part1, client, prompt_dir, objective_name, task_description=task_description
    )
    track_lookup = {k.lower(): v for k, v in section_track.items()}

    # PART 2 example bullets, grouped by their section's track → per-track focus plan.
    track_lines: dict[str, list[str]] = {t: [] for t in TRACKS}
    current: str | None = None
    for raw_ln in part2.splitlines():
        s = raw_ln.strip()
        if s.startswith("### "):
            current = s[4:].strip().lstrip("#").strip()
        elif s[:1] in ("-", "*") and current:
            tr = track_lookup.get(current.lower())
            if tr:
                track_lines[tr].append(f"- {current}: {s.lstrip('-* ').strip()}")
    track_plans = {t: "\n".join(v) for t, v in track_lines.items() if v}
    return file_skeleton, section_track, track_plans, factual_enabled


@register_system("skill_evo_tri_track")
class TriTrackSystem(ContinualLearningSystem):
    """Per-track skill evolution. Own loop; no canary/decay/audit."""

    def __init__(
        self,
        bedrock_api_key: str = "",
        bedrock_model_id: str = "moonshotai.kimi-k2.5",
        bedrock_region: str = "us-east-1",
        optimizer_model_id: str = "",
        task_temperature: float = 0.0,
        optimizer_temperature: float = 0.0,
        max_tokens: int = 8192,
        context_window: int = _DEFAULT_MAX_CONTEXT,
        system_prompt: str = "",
        name: str = "skill_evo_tri_track",
        reserve_tokens: int = 500,
        accumulation_batch_size: int = 5,
        refine_interval: int = 5,
        clear_context_between_instances: bool = True,
        retain_context_within_batch: bool = False,
        output_dir: str = "",
        run_index: int | None = None,
        prompt_dir: str | None = None,
        # ── per-track policy ──────────────────────────────────────────────
        factual_threshold: int = 1,
        strategy_threshold: int = 2,
        failure_threshold: int = 2,
        factual_fast_track: bool = True,
        strategy_fast_track: bool = False,
        failure_fast_track: bool = True,
        enable_replace: bool = True,
        enable_merge: bool = True,
        enable_match: bool = True,
        use_trajectory_count: bool = True,
        fewshot_plan: bool = False,
        skill_at_tail: bool = False,
    ):
        self._name = name
        # When True: inject skill.md at the TAIL of the LLM context (appended to the
        # current turn's message, after all interaction history) on EVERY turn,
        # instead of once at the front of the instance. Maximizes recency (the doc
        # sits right before the decision) and is truncation-safe (added after
        # _truncate_context, never evicted). Not persisted into history.
        self.skill_at_tail = skill_at_tail
        # When True: planner emits coarse SECTION-LEVEL skeleton (no task-specific
        # subsections in the file) + few-shot extraction examples that go ONLY to the
        # extractor prompts. See build_fewshot_plan / prompts/section_plan_fewshot.md.
        self.fewshot_plan = fewshot_plan
        self.prompt_dir = prompt_dir or os.path.join(_HERE, "prompts")
        if output_dir and run_index is not None:
            output_dir = os.path.join(output_dir, f"run_{run_index}")
        self.run_index = run_index
        self.output_dir = output_dir

        self.system_prompt = system_prompt
        self.clear_context_between_instances = clear_context_between_instances
        # When True: keep the raw multi-instance conversation IN CONTEXT across the
        # instances of one accumulation batch (a small ICL window), clearing only at
        # the batch boundary (after skill.md extraction). Hybrid of ICL recency
        # (within batch) + skill.md compression (across batches). Overrides
        # clear_context_between_instances' per-instance clearing when set.
        self.retain_context_within_batch = retain_context_within_batch
        self.accumulation_batch_size = accumulation_batch_size
        self.refine_interval = refine_interval
        self.max_tokens = max_tokens
        self.context_window = context_window
        self.reserve_tokens = reserve_tokens

        # Per-track configuration: (threshold, fast_track).
        self.track_cfg: dict[str, dict[str, Any]] = {
            "factual": {"threshold": factual_threshold, "fast_track": factual_fast_track},
            "strategy": {"threshold": strategy_threshold, "fast_track": strategy_fast_track},
            "failure": {"threshold": failure_threshold, "fast_track": failure_fast_track},
        }
        self.enable_replace = enable_replace
        self.enable_merge = enable_merge
        self.enable_match = enable_match
        self.use_trajectory_count = use_trajectory_count

        bedrock_api_key = bedrock_api_key or os.environ.get("BEDROCK_API_KEY", "")
        self._task_client = self._make_client(
            bedrock_api_key, bedrock_model_id, bedrock_region, max_tokens, task_temperature
        )
        opt_model = optimizer_model_id or bedrock_model_id
        self._optimizer_client = self._make_client(
            bedrock_api_key, opt_model, bedrock_region, max_tokens, optimizer_temperature
        )

        self._init_state()

    # ── state ────────────────────────────────────────────────────────────

    def _init_state(self) -> None:
        self.skill_md: str = ""
        # One aggregator per track, each with its own trigger_threshold.
        self.aggs: dict[str, Aggregator] = {
            t: Aggregator(trigger_threshold=self.track_cfg[t]["threshold"]) for t in TRACKS
        }
        self._track_plans: dict[str, str] = {}
        self._factual_enabled: bool = True
        self._skeleton_built: bool = False
        self._frozen_objective: str = ""

        self._epoch_buffer: list[TrialRecord] = []
        self._epoch_counter: int = 0
        self._current_trajectory: list[dict[str, Any]] = []
        self._current_instance_id: str = ""
        self._current_task_type: str = ""
        self._current_goal: str = ""
        self.messages: list[dict[str, str]] = []
        self.interaction_count: int = 0
        self.trial_count: int = 0
        self._at_instance_boundary: bool = True
        self._pending_feedback: str | None = None
        self._task_description: str = ""

    def _make_client(self, api_key, model_id, region, max_tokens, temperature):
        # Provider routing by env key, in priority order:
        #   OPENAI_PROXY_* → custom OpenAI-compatible proxy (verbatim model id)
        #   OPENROUTER_API_KEY → OpenRouter (OpenAI-compatible; respects temperature)
        #   MOONSHOT_API_KEY   → official Moonshot API (forces temperature=1)
        #   else               → Bedrock
        proxy_base = os.environ.get("OPENAI_PROXY_BASE_URL", "")
        proxy_key = os.environ.get("OPENAI_PROXY_KEY", "")
        if proxy_base and proxy_key:
            from ..skill_evo_planner.openrouter_client import OpenRouterClient

            # strip any bedrock "vendor." prefix but keep the version dot intact
            raw_model = model_id.split(".", 1)[-1] if model_id.startswith("moonshotai.") else model_id
            return OpenRouterClient(
                api_key=proxy_key,
                model_id=raw_model,
                base_url=proxy_base,
                max_tokens=max_tokens,
                temperature=temperature,
                map_model=False,
            )
        ork = os.environ.get("OPENROUTER_API_KEY", "")
        if ork:
            from ..skill_evo_planner.openrouter_client import OpenRouterClient

            return OpenRouterClient(
                api_key=ork,
                model_id=model_id,
                base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
                max_tokens=max_tokens,
                temperature=temperature,
            )
        # If a Moonshot key is present, use the official OpenAI-compatible Moonshot
        # API instead of Bedrock. The bedrock model id ("moonshotai.kimi-k2.5") maps
        # to the Moonshot model id by dropping the "moonshotai." vendor prefix.
        mk = os.environ.get("MOONSHOT_API_KEY", "")
        if mk:
            from ..skill_evo_planner.moonshot_client import MoonshotClient

            return MoonshotClient(
                api_key=mk,
                model_id=model_id.split("moonshotai.")[-1],
                base_url=os.environ.get("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1"),
                max_tokens=max_tokens,
                temperature=temperature,
            )
        return BedrockClient(
            api_key=api_key, model_id=model_id, region=region,
            max_tokens=max_tokens, temperature=temperature,
        )

    # ── respond / observe ──────────────────────────────────────────────────

    def respond(self, query: Query) -> Response:
        self.skill_md = _strip_open_questions_sections(self.skill_md)
        instance_boundary = self._at_instance_boundary

        if query.instance_id:
            self._current_instance_id = query.instance_id
        if query.metadata:
            self._current_task_type = query.metadata.get("task_type", "")
            self._current_goal = query.metadata.get("goal", query.prompt[:200])
        if not self._task_description and query.prompt:
            self._task_description = query.prompt[:2000]

        query_parts: list[str] = []
        if self._pending_feedback and instance_boundary:
            query_parts.append(f"FEEDBACK FROM PREVIOUS INSTANCE:\n{self._pending_feedback}")
            self._pending_feedback = None
        if self.skill_md and instance_boundary and not self.skill_at_tail:
            query_parts.append(self._skill_block())
        if query.prompt:
            query_parts.append(query.prompt)
        query_content = "\n\n".join(query_parts) if query_parts else "(no content)"

        self.interaction_count += 1
        self._at_instance_boundary = False
        self._add_message("user", query_content)
        self._current_trajectory.append({"role": "situation", "content": query.prompt})

        try:
            self._truncate_context()
            llm_messages = [*self._system_messages(), *self.messages]
            # Tail-injection: append skill.md AFTER all history (recency-max,
            # truncation-safe) onto a transient copy of the last message so it is
            # never persisted into self.messages.
            if self.skill_at_tail and self.skill_md and llm_messages:
                tail = dict(llm_messages[-1])
                tail["content"] = f"{tail['content']}\n\n{self._skill_block()}"
                llm_messages = [*llm_messages[:-1], tail]
            parsed, usage = self._task_client.chat_structured(
                messages=llm_messages,
                response_schema=query.response_schema,
                max_tokens=self.max_tokens,
            )
            self.record_usage_event(
                UsageEvent(
                    model=self._task_client.model_id,
                    call_type="completion",
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                )
            )
            action = parsed
            assistant_record = parsed.model_dump_json()
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {e}") from e

        self._add_message("assistant", assistant_record)
        self._current_trajectory.append({"role": "action", "content": assistant_record})

        return Response(
            action=action,
            metadata={
                "interaction_count": self.interaction_count,
                "system_type": "skill_evo_tri_track",
                "model": self._task_client.model_id,
                "skill_md": self.skill_md,
                "skill_md_length": len(self.skill_md),
                "aggregator_sizes": {t: len(a.canonicals) for t, a in self.aggs.items()},
                "trial_count": self.trial_count,
                "epoch_progress": f"{len(self._epoch_buffer)}/{self.accumulation_batch_size}",
            },
        )

    def observe(self, observation: Observation, next_query: Query | None = None) -> None:
        instance_complete = observation_marks_instance_complete(observation)
        content = observation.content.strip()
        self._current_trajectory.append({"role": "feedback", "content": content})

        if self.retain_context_within_batch:
            # Batch-scoped context: keep the raw trace in-context across instances
            # of the batch; the last instance's feedback is added inline too so the
            # next in-batch instance sees the outcome. Clearing happens only at the
            # batch boundary below.
            if content:
                self._add_message("user", f"FEEDBACK: {content}")
            if instance_complete:
                self._on_trial_complete(observation)  # may hit batch boundary → extract + reset buffer
                batch_just_ended = len(self._epoch_buffer) == 0
                if batch_just_ended:
                    # extraction done: start a fresh window with the updated skill.md
                    self.messages = []
                    self._at_instance_boundary = True
                # else: mid-batch — keep context, do NOT re-prepend skill.md
            return

        if content:
            if instance_complete and self.clear_context_between_instances:
                self._pending_feedback = content
            else:
                self._add_message("user", f"FEEDBACK: {content}")

        if instance_complete:
            self._on_trial_complete(observation)
            if self.clear_context_between_instances:
                self.messages = []
            self._at_instance_boundary = True

    # ── evolution loop ─────────────────────────────────────────────────────

    def _on_trial_complete(self, observation: Observation) -> None:
        self.trial_count += 1
        # Do NOT expose the benchmark's explicitly-computed reward/score to the
        # extractor: that is the grader's privileged scalar, which the acting agent
        # (and ICL, which learns only from observation.content) never sees. The
        # extractor must judge success from the SAME observable feedback text the
        # agent got — which is already present verbatim in the trajectory's feedback
        # turns. So final_outcome carries only that observable feedback, no
        # success/score fields. (This also nullifies the db "INCORRECT" substring
        # mislabel and the cohort/bsm all-zero-score degeneracy.)
        trial = TrialRecord(
            trial_id=self._current_instance_id or f"trial_{self.trial_count}",
            task_type=self._current_task_type,
            trajectory=list(self._current_trajectory),
            final_outcome={"feedback": observation.content[:500]},
            goal=self._current_goal,
        )
        self._current_trajectory = []
        self._epoch_buffer.append(trial)

        if len(self._epoch_buffer) >= self.accumulation_batch_size:
            self._process_epoch_boundary()

    def _process_epoch_boundary(self) -> None:
        self._epoch_counter += 1
        if not self._skeleton_built:
            self._build_skeleton()
        if self._skeleton_built:
            self._extract_and_promote()
        self._maybe_refine()
        self._reassert_objective()
        self._epoch_buffer = []

    def _build_skeleton(self) -> None:
        """First batch: planner designs the skeleton AND tags each section's track
        in one pass (resolve_section_tracks reads the inline tags).

        With ``fewshot_plan=True`` the planner instead emits a coarse section-level
        skeleton for the file plus few-shot extraction examples routed only to the
        extractor prompts (build_fewshot_plan)."""
        objective_name = _OBJECTIVE_HEADER.replace("## ", "").strip()
        if self.fewshot_plan:
            try:
                skeleton, section_track, raw_plans, self._factual_enabled = (
                    build_fewshot_plan(
                        task_description=self._task_description,
                        trials=list(self._epoch_buffer),
                        client=self._optimizer_client,
                        prompt_dir=self.prompt_dir,
                        objective_name=objective_name,
                        max_samples=len(self._epoch_buffer),
                    )
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[tri_track] fewshot planning failed: %s", e)
                return
            if not skeleton:
                return
        else:
            try:
                skeleton = generate_skeleton_plan(
                    task_description=self._task_description,
                    trials=list(self._epoch_buffer),
                    bedrock_client=self._optimizer_client,
                    prompt_dir=self.prompt_dir,
                    max_samples=len(self._epoch_buffer),
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[tri_track] skeleton planning failed: %s", e)
                return
            if not skeleton:
                return
            try:
                section_track, self._factual_enabled, skeleton = resolve_section_tracks(
                    skeleton, self._optimizer_client, self.prompt_dir,
                    objective_name,
                    task_description=self._task_description,
                )
                raw_plans = build_track_plans(skeleton, section_track, objective_name)
            except Exception as e:  # noqa: BLE001
                logger.warning("[tri_track] track resolution failed: %s", e)
                raw_plans = {}

        self.skill_md = skeleton
        self._frozen_objective = self._extract_section(skeleton, _OBJECTIVE_HEADER)
        if not self._factual_enabled:
            raw_plans.pop("factual", None)
        pre = (self._frozen_objective + "\n\n") if self._frozen_objective else ""
        self._track_plans = {t: pre + p for t, p in raw_plans.items()}
        self._skeleton_built = True
        self._save_snapshot("skeleton_plan_init")
        logger.info(
            "[tri_track] skeleton built; factual=%s; track sizes: %s",
            self._factual_enabled,
            {t: len(p.splitlines()) for t, p in raw_plans.items()},
        )

    def _extract_and_promote(self) -> None:
        """For each active track: extract into its own aggregator (its policy), then
        promote its triggered canonicals into the shared skill.md."""
        for track in TRACKS:
            plan = self._track_plans.get(track)
            if not plan:
                continue
            cfg = self.track_cfg[track]
            agg = self.aggs[track]
            try:
                self.aggs[track] = stage_bc_batch_summarize(
                    trials=self._epoch_buffer,
                    aggregator=agg,
                    bedrock_client=self._optimizer_client,
                    current_epoch=self._epoch_counter,
                    prompt_dir=self.prompt_dir,
                    enable_match=self.enable_match,
                    use_trajectory_count=self.use_trajectory_count,
                    focus_plan=plan,
                    enable_replace=self.enable_replace,
                    authoritative_fast_track=cfg["fast_track"],
                    enable_merge=self.enable_merge,
                    prompt_name=f"extract_{track}",
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("[tri_track] %s extraction failed: %s", track, e)
                continue
            # Promote: multiplier=1.0 → fast_threshold == trigger_threshold, so every
            # triggered canonical is folded in immediately (no canary path exists).
            try:
                v_new, _canary, fast_ids = stage_d_trigger_and_update(
                    aggregator=self.aggs[track],
                    current_skill_md=self.skill_md,
                    bedrock_client=self._optimizer_client,
                    fast_promote_multiplier=1.0,
                    prompt_dir=self.prompt_dir,
                    focus_plan=plan,
                    authoritative_fast_track=cfg["fast_track"],
                )
                if v_new:
                    self.skill_md = v_new
                    if fast_ids:
                        self._save_snapshot(f"{track}_promote_{len(fast_ids)}")
            except Exception as e:  # noqa: BLE001
                logger.warning("[tri_track] %s promotion failed: %s", track, e)

    def _maybe_refine(self) -> None:
        if (
            self.trial_count > 0
            and self.refine_interval > 0
            and self.trial_count % self.refine_interval == 0
            and self.skill_md
        ):
            try:
                refined = stage_g_refine_skeleton(
                    current_skill_md=self.skill_md,
                    bedrock_client=self._optimizer_client,
                    prompt_dir=self.prompt_dir,
                )
                # Guard against a degenerate refine: at temp=1 the LLM
                # occasionally returns an empty or near-empty document, which
                # would silently wipe accumulated skills. Refine is meant to
                # reorganize/tighten, not destroy — reject any output that
                # empties the doc or collapses it to <50% of its prior length.
                prev_len = len(self.skill_md.strip())
                if refined and len(refined.strip()) >= 0.5 * prev_len:
                    self.skill_md = refined
                    self._save_snapshot("refine")
                else:
                    logger.warning(
                        "[tri_track] refine produced degenerate doc "
                        "(%d → %d chars); keeping prior skill.md",
                        prev_len,
                        len(refined.strip()),
                    )
                    self._save_snapshot("refine_rejected")
            except Exception as e:  # noqa: BLE001
                logger.warning("[tri_track] refine failed: %s", e)

    # ── objective freezing ─────────────────────────────────────────────────

    @staticmethod
    def _extract_section(md: str, header: str) -> str:
        m = re.search(
            rf"^{re.escape(header)}\b.*?(?=\n## |\Z)", md, flags=re.S | re.M
        )
        return m.group(0).strip() if m else ""

    def _reassert_objective(self) -> None:
        if not self._frozen_objective or self._frozen_objective in self.skill_md:
            return
        stripped = re.sub(
            rf"^{re.escape(_OBJECTIVE_HEADER)}\b.*?(?=\n## |\Z)",
            "", self.skill_md, flags=re.S | re.M,
        ).strip()
        self.skill_md = self._frozen_objective.rstrip() + "\n\n" + stripped

    # ── reset / metadata ───────────────────────────────────────────────────

    def reset(self) -> None:
        self._init_state()

    @property
    def name(self) -> str:
        return self._name

    def get_run_artifacts(self) -> dict[str, Any]:
        self._save_snapshot("final")
        return {
            "artifact_type": "skill_evo_tri_track",
            "skill_md": self.skill_md,
            "skill_md_length": len(self.skill_md),
            "aggregators": {t: a.to_dict() for t, a in self.aggs.items()},
            "trial_count": self.trial_count,
            "interaction_count": self.interaction_count,
            "model": self._task_client.model_id,
            "optimizer_model": self._optimizer_client.model_id,
            "track_cfg": self.track_cfg,
        }

    def _save_snapshot(self, label: str) -> None:
        out = self.output_dir
        if not out:
            return
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "skill.md"), "w", encoding="utf-8") as f:
            f.write(self.skill_md)
        snap = os.path.join(out, f"skill_t{self.trial_count:04d}_{label}.md")
        with open(snap, "w", encoding="utf-8") as f:
            f.write(self.skill_md)
        for t, a in self.aggs.items():
            with open(os.path.join(out, f"aggregator_{t}.json"), "w", encoding="utf-8") as f:
                json.dump(a.to_dict(), f, ensure_ascii=False, indent=2)

    # ── context ────────────────────────────────────────────────────────────

    def _skill_block(self) -> str:
        return (
            f"=== SKILL DOCUMENT ===\n{self.skill_md}\n=== END SKILL DOCUMENT ==="
            + _SKILL_USAGE_NOTE
        )

    def _system_messages(self) -> list[dict[str, str]]:
        return [{"role": "system", "content": self.system_prompt}] if self.system_prompt else []

    def _add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        self._truncate_context()

    def _truncate_context(self) -> None:
        max_chars = (self.context_window - self.reserve_tokens) * 4
        while len(self.messages) > 1:
            if sum(len(m["content"]) for m in self.messages) <= max_chars:
                break
            self.messages.pop(0)


# Publish an explicit signature so the CLI param resolver sees the named kwargs.
TriTrackSystem.__init__.__signature__ = inspect.signature(TriTrackSystem.__init__)
