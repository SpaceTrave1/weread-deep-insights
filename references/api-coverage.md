# WeRead API Coverage

This skill focuses on personal reading records. It intentionally keeps public book reviews, search, and discovery separate because those are not the user's own reading behavior.

## Default Personal Export

The report generator collects:

- `/readdata/detail`
  - `overall`: total reading days, total reading/listening time, read stats, category preferences, author/publisher preferences, top books, time distribution when available.
  - `annually`: each natural year from registration year to current year.
  - `monthly` and `weekly`: current period snapshots for recent context.
- `/shelf/sync`
  - Books, albums/audiobooks, article collection entry, categories, public/private flags, finish state, recent reading order.
- `/book/getprogress`
  - Progress, record reading time, update time, finish time for each shelf book when available.
- `/book/info`
  - Detailed metadata for shelf and notebook books when available: author, category, publisher, ISBN, word count, ratings, intro, and related fields returned by the API.
- `/user/notebooks`
  - All pages using `count` + `lastSort`.
  - Total note count per book is `reviewCount + noteCount + bookmarkCount`.
- `/book/bookmarklist`
  - Per-book underline/highlight text and chapter metadata.
  - Bookmarks are counted in notebook overview but not exported as text by this endpoint.
- `/review/list/mine`
  - Per-book personal thoughts, underline comments, chapter comments, and whole-book reviews.

## Optional Non-Profile Endpoints

Model enhancement adds no WeRead endpoints. `--analysis-input` reuses a validated local bundle without WeRead requests or `.env` loading. Model HTTP attempts and declared text coverage are separate from the collection units described here; see [model analysis](llm-analysis.md). Default reporting never invokes a model endpoint.

Do not include these in the personal profile by default:

- `/store/search`: useful for resolving a title to `bookId`.
- `/book/chapterinfo`: useful for full chapter navigation when a task requires it. The default profile report does not fetch every chapter list because `/book/bookmarklist` already returns chapter metadata for exported notes.
- `/review/list`: public reviews by other users.
- `/book/bestbookmarks`, `/book/underlines`, `/book/readreviews`: community highlights and comments.
- Discovery/recommendation APIs: useful for recommendation tasks, not for the user's historical reading profile.

## Field Rules

- All reading time values from reading statistics and progress are seconds.
- `/readdata/detail` supports fixed natural periods only: weekly, monthly, annually, overall.
- `preferTime` is ordered from 06:00 through next-day 05:00.
- `/user/notebooks` pagination uses `lastSort`, not offset.
- If an API response contains `upgrade_info`, stop and surface the upgrade message.

## v0.2 Phase 1 Collection Status

- Per-book note results keep `underlines`/`reviews` for text and separate `fetchStatus`/`fetchErrors` for metadata. States are `success` (nonempty), `empty` (request succeeded without text), `failed`, and `not_requested` (derived for unselected/skipped/missing-ID entries). Legacy records without status are `unknown`, not assumed successful.
- Progress and metadata rows also carry `fetchStatus`; empty and failed rows are excluded from successful export counts. Error metadata uses exception class names, not server error bodies or arbitrary exception messages.
- Top-level `collectionStatus` tracks overall/weekly/monthly/shelf/notebook directory and annual requests. Non-upgrade failures keep other available data usable. Failed annual data is not rendered as zero reading time. Missing registration date means earlier years are unrequested and unknown in number.
- Notebook/review pagination detects absent, repeated or cycling cursors and page-limit exhaustion. Interrupted pages retain already fetched rows and mark the stream failed. Repeated explicit book/review IDs are deduplicated. An upgrade response stops collection immediately without retries, including optional per-book calls.
- Report `coverage.groups` counts logical endpoint/book/year units, not HTTP attempts or retry counts. Success, empty, failure, unrequested and unknown are separate. Skipped per-book endpoints have known denominators only when the parent directory is available; failed directories leave undiscovered counts unknown.
- Text coverage compares valid exported underlines/reviews against the fetched notebook directory's `noteCount`/`reviewCount`. Bookmarks are excluded. A completed set of visible calls cannot guarantee all account records or semantic completeness; reports always describe the observed scope.
