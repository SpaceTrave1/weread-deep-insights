# Analysis Rubric

Use this rubric when interpreting a user's WeRead data.

For model-assisted interpretation, follow [the versioned evidence protocol](llm-analysis.md). Local statistics remain authoritative; semantic findings must carry original references, scope, rationale, limitations and any counter-evidence. Structural validation does not certify semantic support. Do not reinstate unsupported personality labels or fixed scores through the model.

## Evidence Priority

For longitudinal reading questions, use [reading-evolution.md](reading-evolution.md). Personal expressions must be comparable in question, object and conditions; edits are versions of one note, not independent evidence. Preserve chronology uncertainty, unresolved tension and attributed user feedback. Stable viewpoints and deepening are meaningful; do not force a reversal or a growth narrative.

1. Personal reviews and thoughts from `/review/list/mine`.
2. The user's underline choices from `/book/bookmarklist`.
3. Reading behavior: time, categories, completion, notebook distribution, repeated authors/books.
4. Shelf intent: recently opened books, unfinished clusters, private/public flags only as counts.

Prefer personal reviews for quoted evidence. Underlines may contain copyrighted book text, so quote them sparingly and only when the user asked for evidence from notes.

## Interpretation Style

- Explain patterns, not labels.
- Use "可能", "倾向于", and "只能初步推测" when evidence is limited.
- Separate data facts from inference.
- Avoid diagnostic language and deterministic personality typing.
- Do not infer sensitive traits such as politics, religion, health conditions, or identity beyond what the user explicitly wrote.
- If public issues appear in notes, frame them as "关注公共议题/制度运行/社会变化", not as a fixed political identity.

## Recommended Report Structure

1. Data basis and coverage.
2. Reading map: time, books, categories, authors, years, notes.
3. Themes and recurring questions.
4. People/authors and why they matter.
5. Thinking style.
6. Values, anxieties, interests, long-term directions.
7. Concise reader-archetype summary and tentative reader portrait.
8. Information-cocoon assessment: concentration signals, risks, and antidotes.
9. Personalized recommendation book list, preferably skipping books already visible in the user's records.
10. Suggestions: reading, writing, thinking, personal growth.
11. Strict diagnosis: blunt but evidence-based blind spots, dimension scores, and execution advice.

## Strict Diagnosis Mode

- Describe observed completion or text concentration with explicit denominators. Completion does not prove discipline, review proportion does not prove expression quality, and growth keywords do not prove action transfer.
- Keep the tone witty and concise, not abusive.
- Criticize patterns and habits, not the person's worth.
- Tie every harsh claim to behavior in the data.
- Use one short disclaimer before the section; do not apologize repeatedly.

## v0.2 Phase 1 Evidence Gates

- Profile summary requires at least 5 valid personal reviews across at least 2 book IDs. Each named thinking signal additionally requires at least 3 matched personal reviews across 2 books. Title-only and underline-only signals cannot produce a personal profile.
- Profile theme names require at least 3 matched personal reviews across 2 books. Theme tables may still expose title/text keyword signals, labeled as such.
- Value tables require at least 3 matched personal reviews across 2 books and weighted keyword score at least 15; these are vocabulary attention signals, not confirmed values, anxieties, or long-term plans.
- Category concentration requires positive category time and at least 5 books in the returned category counts. Its denominator is only the API's returned categories, whose completeness is not guaranteed.
- Theme concentration requires a completed notebook directory, successful or empty requests for every known book and note stream, valid text totals matching the directory counts, no sampling option, at least 5 matched texts for the leading theme, and texts across at least 2 books.
- Cocoon score is the arithmetic mean of available leading category/theme percentages. Levels retain heuristic cutoffs 42/68 for continuity; neither cutoffs nor sample minimums are scientifically validated. No evidence means `None`, never a low-risk conclusion. Concentration cannot confirm information cocoon without viewpoint/exposure data.
- Expression metric is reviews / (reviews + underlines) × 100, only with completed note coverage and at least 5 valid texts. Completion metric is official finished / read × 100, only with at least 5 read books and valid counts. Balance metric is 100 minus the leading returned category percentage, only with sufficient categories. All are observed proxies, not ability evaluations.
- Question quality, real-world sensitivity and action execution have no supported quantitative measurements and remain unscored. Blind-spot output is limited to conditional, checkable coverage/unfinished-record risks; no emotional or motivational diagnosis.
- Successful partial-page records may be used as observed evidence, but their stream remains failed/incomplete. Every inference is limited to the fetched sample, and missing data must not be replaced with a confident conclusion.

## Publishable Generalization

- Keep theme, thinking-style, and value taxonomies generic. Do not hard-code one reader's favorite books, people, or examples into the default script.
- Detect people primarily from WeRead's author/preferAuthor fields. If a deployment needs custom public-figure matching, provide it as user configuration rather than bundled defaults.
- Ensure suggestions are triggered by metrics and evidence patterns, not by assumptions about one user's background.
- Build recommendation lists from generic theme families and visible reading history. Avoid recommending a title already present in the user's shelf/notebooks when the script can detect it.
- Treat information-cocoon analysis as a concentration-risk assessment, not as a moral judgment. Pair every risk with a concrete counter-reading or writing action.
