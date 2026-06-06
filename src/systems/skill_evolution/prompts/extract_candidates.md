You are an expert at analyzing agent-environment interaction trajectories to extract reusable knowledge.

Given a complete trajectory (the full sequence of situations, agent decisions, and outcomes) for a task, extract **specific, reusable knowledge grounded in what actually happened** — NOT generic domain knowledge the model already knows.

## What to extract

Focus on these categories (adapt to the task at hand):

1. **Environment facts**: Concrete, stable properties of the environment that the agent had to *discover* and that future instances could reuse to avoid re-discovering. When the task implies a fixed underlying environment (e.g. a **database** with a stable schema, a fixed API, a fixed file/tool layout), capture these **verbatim and concretely** — copy the exact names, units, keys, and values. Examples:
   - Exact table/column names and what each holds (e.g. "table `fdbk_g1` holds reviews; `items_g1` holds product metadata").
   - Data formats / units / encodings (e.g. "`fdbk_g1.ts` is a Unix timestamp in **milliseconds** (÷1000); `fdbk_g2.ts` is in **seconds**; `fdbk_g3.ts` is an **ISO date string**").
   - Join keys / relationships (e.g. "join `fdbk_gN` to `items_gN` on `ref_id`").
   - Value placement (e.g. "category 'Office Products' appears in groups g1, g2 AND g3 — must sum across all three").
   ❌ vague: "check the timestamp type per group"  ✅ concrete: "`fdbk_g1.ts`=ms, `fdbk_g2.ts`=s, `fdbk_g3.ts`=ISO text".

   **An environment fact must be VERIFIED, not inferred.** Only record something as an environment fact if an *authoritative environment output* confirmed it — a tool's returned data (e.g. database metadata, column descriptions, query results), a provided response/submission schema, or an explicit error message. Do NOT record the agent's own hypotheses, intermediate groupings, assumed categorizations, or reverse-engineered structure as environment facts, **even if the agent acted on them confidently and it seemed to work**. If the agent invented a scheme (e.g. an ad-hoc way of bucketing rows, a guessed naming convention, an assumed set of categories) and no tool output or schema ever confirmed it, it is NOT a fact — at most it is a tentative strategy, and it should be labeled and worded as tentative.
   ❌ confabulated: "the cohorts follow the pattern `{sex}_{level}_{group}`" when the agent only assumed this from its own grouping queries.  ✅ verified: "the submission schema lists cohort `education_lt13_gg1` defined as `years_of_education < 13 AND genotype_group = GG-1`" — copied verbatim from the schema the environment provided.

   **When the environment itself defines a structure, copy THAT — never the agent's guess.** If the environment provides a fixed set of categories, cohorts, labels, fields, or a schema (e.g. embedded in a tool's response schema, a submission schema, or returned metadata), record it **verbatim from that authoritative source** and prefer it over any scheme the agent reverse-engineered, assumed, or built from its own intermediate queries. The agent's own ad-hoc partitions are not the environment's definitions and must never be recorded as if they were.
2. **Adversary / counterpart patterns** (only for tasks with an opponent or other agent): what the other party actually DID, and the exploitation response (e.g. "opponent never folds to river bets → bluff less on river").
3. **Effective strategies**: a specific approach the agent took that worked, described concretely enough to reuse.
4. **Agent mistakes**: a specific decision that lost value or wasted effort, with the corrective insight (NOT generic advice like "be more careful").

## What NOT to extract

- Generic domain knowledge the model already knows (e.g. "use indexes", "fold weak hands").
- Advice not grounded in specific behaviour or facts observed in THIS trajectory.
- Vague platitudes (e.g. "be more efficient", "explore carefully").

## Constraints

- Extract 1-6 candidates. Quality over quantity — skip if nothing specific was observed.
- Each candidate must reference SPECIFIC behaviour or facts observed in the trajectory.
- For any **environment fact**, the `evidence` MUST name the authoritative source that confirmed it (which tool returned it, the schema it came from, or the exact error message). If you cannot point to a confirming source, do NOT phrase it as an established environment fact — word it as a tentative hypothesis to verify.
- Classify effect: "positive" (agent did this and it worked), "negative" (agent failed to do this or did the opposite and it hurt), "unclear" (e.g. a neutral environment fact).

Respond with a JSON object:
{
  "candidates": [
    {
      "description": "<specific, reusable knowledge grounded in what was observed; for environment facts, the exact verbatim fact copied from the authoritative source — never a reverse-engineered scheme dressed up as a fact>",
      "effect": "positive" | "negative" | "unclear",
      "evidence": "<what specifically happened in the trajectory that supports this; for an environment fact, name the authoritative source that confirmed it (which tool output, schema, or error)>"
    }
  ]
}
