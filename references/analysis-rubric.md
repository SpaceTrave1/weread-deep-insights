# Analysis Rubric

Use this rubric when interpreting a user's WeRead data.

## Evidence Priority

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

- Be direct about weak signals: low completion, over-commenting, theme bias, abstraction-heavy writing, weak action transfer.
- Keep the tone witty and concise, not abusive.
- Criticize patterns and habits, not the person's worth.
- Tie every harsh claim to behavior in the data.
- Use one short disclaimer before the section; do not apologize repeatedly.

## Publishable Generalization

- Keep theme, thinking-style, and value taxonomies generic. Do not hard-code one reader's favorite books, people, or examples into the default script.
- Detect people primarily from WeRead's author/preferAuthor fields. If a deployment needs custom public-figure matching, provide it as user configuration rather than bundled defaults.
- Ensure suggestions are triggered by metrics and evidence patterns, not by assumptions about one user's background.
- Build recommendation lists from generic theme families and visible reading history. Avoid recommending a title already present in the user's shelf/notebooks when the script can detect it.
- Treat information-cocoon analysis as a concentration-risk assessment, not as a moral judgment. Pair every risk with a concrete counter-reading or writing action.
