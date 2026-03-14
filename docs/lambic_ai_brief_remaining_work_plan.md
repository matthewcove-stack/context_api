# Lambic AI Brief — Remaining Work Plan

## Scope and current state

This plan is based on the current implementation across:

- `context_api`
  - daily digest generation lives in `app/research/digest_generator.py`
  - the generator writes static JSON artifacts into the website repo at `apps/web/content/research-digests/`
  - there is already a lightweight weekly clustering API at `GET /v2/research/topics/{topic_key}/weekly`
- `lambic_labs_website`
  - the public digest is a static Next.js export with canonical routes at `/brief` and `/brief/[date]`
  - `/research` and `/research/[date]` are currently continuity aliases
  - digest pages are rendered from JSON files loaded from `apps/web/content/research-digests/`

Important constraints:

- the website is static export only; there is no runtime database or authenticated admin surface
- the digest generator currently auto-commits generated daily issue files into the website repo
- the current digest schema supports issue copy and item-level summaries, but not conversion, distribution, or analytics metadata
- phase 5 is partially started already because the main site header and homepage already link to `/brief`

## Key findings

1. The product is split across two repos, not one surface.
   - `context_api` owns source selection, enrichment, digest drafting, and structured output.
   - `lambic_labs_website` owns routes, metadata, archive UX, and conversion UI.

2. The current weekly capability is not yet a publishable weekly product.
   - `context_api` exposes grouped weekly clusters for editorial synthesis.
   - the website has no weekly roundup route, loader, or artifact type.

3. Conversion and sharing are currently minimal.
   - `/brief` has a descriptive hero and archive listing, but no real subscription surface, newcomer path, or topic navigation.
   - issue metadata is limited to page `title` and `description`; there is no robust Open Graph/Twitter metadata model, RSS feed, or social card pipeline.

4. Distribution assets are not modeled yet.
   - generated issue JSON contains editorial issue content only.
   - there is no structured storage for founder/company posts, email teaser copy, or review-ready derivative assets.

5. Measurement is absent.
   - there is no analytics integration in the website repo.
   - the generator does not emit any publish-side metadata that would support campaign attribution or performance reporting.

## Recommended architecture decisions

### 1. Keep source-of-truth content generation in `context_api`

Do not move digest synthesis into the website repo. The website should stay a static consumer of generated artifacts.

### 2. Add a versioned artifact layer for digest publication metadata

Extend the generated issue artifact rather than baking new copy into route code. The next schema version should support:

- issue-level presentation metadata
  - `slug`
  - `shareTitle`
  - `shareDescription`
  - `socialImage`
  - `canonicalPath`
  - `readingTimeMinutes`
- conversion metadata
  - `primaryCta`
  - `secondaryCta`
  - `startHereLinks`
- classification metadata
  - `topics`
  - `themes`
  - `series`
  - `featured`
- distribution metadata
  - `distributionAssets` as a nested object or a parallel artifact
- linkage metadata
  - `relatedIssueDates`
  - `weeklyRoundupId`

Recommendation: keep public issue content and derivative distribution assets in separate but linked artifacts.

- `research-digests/YYYY-MM-DD.json`
  - public issue payload used by the website
- `research-digest-assets/YYYY-MM-DD.json`
  - channel variants, campaign copy, editorial notes, review status

This avoids brittle coupling between web presentation and promotional copy.

### 3. Treat weekly roundups as first-class generated artifacts

Do not render weekly pages directly from the current weekly API response. That endpoint is a discovery primitive, not a final publication format.

Add a weekly generation path in `context_api` that consumes:

- daily digest artifacts
- recent research documents
- weekly cluster candidates from `/v2/research/topics/{topic_key}/weekly` or direct shared internals

Emit a dedicated weekly artifact with its own schema and route.

Recommendation:

- route: `/brief/weekly/[week]`
- artifact directory: `apps/web/content/research-weekly/`
- canonical share target for promotion: weekly pages

### 4. Keep subscription capture simple and static-compatible

Because the website is static export, the initial subscription design should be one of:

- external newsletter platform form or hosted subscribe page
- a lightweight static form POST to a provider endpoint

Do not introduce a bespoke subscription backend inside the website unless there is a separate operational reason to own subscriber data directly.

### 5. Add analytics with a low-friction, static-compatible stack

Recommendation:

- add a privacy-light site analytics tool suitable for static export
- capture pageview plus a small event set only:
  - CTA click
  - subscription submit/click-through
  - social share click
  - topic click
  - weekly vs daily entry

Avoid a custom event ingestion service in `context_api` for this phase.

## Proposed rollout order

1. Phase 3: conversion layer and audience capture
2. Phase 4: distribution asset generation
3. Phase 6: weekly roundup layer
4. Phase 8: information architecture and SEO structure
5. Phase 7: authority and point-of-view layer
6. Phase 10: analytics and feedback loop
7. Phase 5: distribution readiness and launch surfaces
8. Phase 9: paid amplification readiness

Adjustment from the brief:

- keep phase 5 after phases 3, 4, 6, 8, and 10 because most of its remaining work depends on the new conversion, weekly, metadata, and analytics surfaces existing first

## Implementation plan by phase

## Phase 3 — Conversion layer and audience capture

### Product goal

Turn `/brief` and `/brief/[date]` into intentional reader journeys instead of archive pages.

### Implementation breakdown

Website:

- add a primary CTA block to `/brief`
- add a bottom-of-issue CTA module to `/brief/[date]`
- add a newcomer entry surface on `/brief`
  - “Start here”
  - “Best recent issues”
  - “What the brief covers”
- improve archive browsing
  - featured latest issue
  - recent issue groups
  - filters or curated topic entry points once topic metadata lands
- add explicit social share links per issue
- add richer metadata generation in page `generateMetadata`

`context_api`:

- extend issue schema with CTA-ready and metadata-ready fields
- add artifact validation for the new fields
- optionally generate fallback share title/description automatically when absent

External integration:

- select a newsletter provider or hosted subscription endpoint
- add env-driven subscription config in the website repo

### Dependencies

- schema extension for issue artifacts
- decision on subscription provider
- design decision on whether newcomer content is generated, curated, or hand-authored

### Design notes

- keep CTA copy restrained and utility-focused
- use two CTA intents only in v1:
  - subscribe
  - browse best issues

### Acceptance criteria

- `/brief` has an above-the-fold primary CTA
- every issue page has a bottom CTA with a clear next step
- every issue page has share-friendly metadata beyond plain title/description
- a new reader can find a curated starting path within one click from `/brief`
- route continuity for `/research` remains intact

## Phase 4 — Distribution asset generation from each issue

### Product goal

Each issue should produce reusable distribution material with light editorial review.

### Implementation breakdown

`context_api`:

- add a derivative asset generator stage after daily issue generation
- emit a separate `research-digest-assets/YYYY-MM-DD.json`
- generate:
  - founder LinkedIn post
  - company LinkedIn post
  - 1 to 3 short social variants
  - email teaser
  - top-takeaways block
  - share metadata defaults
  - optional community post variant
- add editorial status fields:
  - `draft`
  - `approved`
  - `rejected`
  - `override`
- support manual override files or checked-in edits without regenerating the public issue artifact

Website:

- none required for first pass unless selected takeaways are surfaced on issue pages

Ops/editorial:

- define lightweight review workflow
  - generated
  - reviewed
  - published externally

### Dependencies

- stable issue artifact schema
- decision on whether derivative assets are produced during daily generation or via a separate CLI command

### Design notes

Recommendation:

- implement asset generation as a separate command that runs after issue generation, not inline with the public publish step

Reason:

- public issue publication should remain robust even if social copy generation fails
- editorial teams need the ability to regenerate distribution assets without rewriting the issue itself

### Acceptance criteria

- each published issue can produce a structured asset bundle
- derivative assets can be regenerated independently of the issue page artifact
- review overrides do not require editing generator code
- public issue rendering does not depend on derivative asset approval

## Phase 6 — Weekly hero asset / roundup layer

### Product goal

Make weekly pages the primary share target and daily pages the retention/archive layer.

### Implementation breakdown

`context_api`:

- add weekly artifact schema and generator
- use daily issues plus source-level evidence to build:
  - weekly title
  - editorial overview
  - top themes
  - strongest developments
  - selected linked daily issues
  - optional “what builders should do differently” block
- add command support:
  - `--mode weekly`
  - `--week-start YYYY-MM-DD`
  - or a dedicated weekly script
- store weekly artifacts into website repo content

Website:

- add `/brief/weekly`
- add `/brief/weekly/[week]`
- add weekly archive/listing modules on `/brief`
- link daily issues to their parent weekly roundup

### Dependencies

- artifact versioning
- weekly schema design
- decision on curation model

### Design notes

Recommendation:

- use a hybrid model
  - automated candidate clustering and draft generation
  - human review for title, framing, and final selected items

The current weekly endpoint is useful as input to this stage but should not be treated as the final publication payload.

### Acceptance criteria

- a weekly roundup can be generated for a completed week
- weekly pages have dedicated routes and archive presence
- daily issues can link to the relevant weekly roundup where available
- weekly pages are coherent enough to use as the default external share target

## Phase 8 — Information architecture and SEO structure

### Product goal

Improve discoverability by topic and intent without creating thin pages.

### Implementation breakdown

Website:

- add topic landing pages only for sufficiently populated topics
- add topic chips that link to those pages
- add related-issue modules
- add structured archive groupings
  - by topic
  - by week
  - by “start here”
- add canonical, Open Graph, and structured metadata per route
- add RSS feed generation for:
  - latest issues
  - optionally weekly roundups only

`context_api`:

- enrich digest artifacts with stable topic/theme metadata suitable for static route generation
- add optional related-issue computation

### Dependencies

- weekly artifacts
- stable taxonomy rules
- threshold rules to avoid low-volume topic pages

### Design notes

Recommendation:

- treat `topics` and `themes` separately
  - `topics`: stable navigational taxonomy used for routes
  - `themes`: looser issue-level labels used for display and clustering

Do not generate pages for every tag. Start with a small fixed taxonomy already implicit in current output:

- agents
- tooling
- infrastructure
- evals
- voice
- enterprise
- open source
- research

### Acceptance criteria

- users can navigate issues by topic, not only date
- weekly and daily pages interlink coherently
- route metadata supports previews and indexing
- no thin topic pages are emitted below the defined threshold

## Phase 7 — Authority and point-of-view layer

### Product goal

Increase judgment without turning the brief into opinion blogging.

### Implementation breakdown

`context_api`:

- extend issue and weekly schemas with commentary fields
  - `editorialFrame`
  - `builderImplication`
  - `watchSignal`
- support generation with explicit separation from source summary fields
- allow manual editorial overrides at issue and weekly level

Website:

- render commentary in visually distinct modules
- label Lambic commentary clearly to preserve source/editor separation

### Dependencies

- stable issue and weekly schemas
- editorial review workflow from phase 4

### Design notes

Recommendation:

- daily issue item structure remains:
  - what happened
  - why it matters
  - engineering takeaway
- authority layer is added at:
  - issue header
  - weekly header
  - optional item annotation only where justified

### Acceptance criteria

- readers can distinguish source-grounded summary from Lambic commentary
- commentary is lightweight and consistent in tone
- editorial framing can be reviewed or overridden without editing source ingestion data

## Phase 10 — Measurement, analytics, and operating feedback loop

### Product goal

Make distribution and conversion performance observable with minimal instrumentation.

### Implementation breakdown

Website:

- add page analytics for:
  - `/brief`
  - `/brief/[date]`
  - `/brief/weekly/[week]`
  - topic pages
  - newcomer pages
- add event tracking for:
  - subscribe CTA clicks
  - external subscribe completion redirect if supported
  - social share clicks
  - topic navigation clicks
  - weekly-to-daily and daily-to-weekly clicks

Ops:

- define a weekly review loop
  - traffic by entry surface
  - subscription conversion by page type
  - weekly vs daily performance
  - top topics by return traffic

`context_api`:

- none required initially except optional publish manifest metadata

### Dependencies

- CTA and weekly routes must exist first
- analytics vendor selection

### Acceptance criteria

- page and CTA performance can be measured by route type
- weekly vs daily performance can be compared
- traffic source quality can be reviewed in a lightweight weekly operating rhythm

## Phase 5 — Distribution readiness and launch surfaces

### Product goal

Use the newly improved product surfaces coherently across founder, company, email, and community channels.

### Implementation breakdown

Website:

- decide the main promotion target
  - likely weekly roundup page
  - with `/brief` as evergreen archive/onboarding page
- add stronger homepage and nav promotion if needed
- add a newcomer or subscribe landing page if `/brief` proves too archive-heavy

Ops/editorial:

- define which channels map to which surfaces
  - founder LinkedIn -> weekly roundup
  - company LinkedIn -> weekly roundup or explicit landing page
  - newsletter -> weekly roundup or hosted email archive
  - communities -> issue or weekly deep link depending specificity

### Dependencies

- phases 3, 4, 6, 8, and 10

### Acceptance criteria

- there is a clearly chosen public share target for each main channel
- homepage/nav linking is aligned with that target
- channel copy and landing experience are consistent

## Phase 9 — Optional paid amplification readiness

### Product goal

Be ready for paid testing later without building paid-only surfaces now.

### Implementation breakdown

Website:

- optionally add a dedicated campaign landing template only after organic conversion paths are proven

Analytics:

- ensure UTM and campaign attribution conventions are documented
- ensure subscription conversion can be attributed by campaign source

### Dependencies

- phases 3, 5, and 10 must be complete first

### Acceptance criteria

- paid traffic could be sent to a conversion-aware surface without immediate redesign
- campaign attribution can distinguish paid vs organic performance

## Cross-repo work breakdown

### `context_api`

- issue artifact schema versioning
- derivative asset artifact generation
- weekly roundup artifact generation
- taxonomy and related-link enrichment
- editorial override support
- generator validation updates
- publish commands separated by concern
  - daily issue generation
  - derivative asset generation
  - weekly roundup generation

### `lambic_labs_website`

- CTA modules
- newcomer/start-here surfaces
- weekly routes and loaders
- topic routes and loaders
- richer `generateMetadata`
- RSS feed/static feed generation
- analytics client integration
- route-level interlinking and archive improvements

### shared operational work

- subscription provider selection
- analytics stack selection
- editorial review workflow
- promotion channel mapping

## Route and content model changes

### Route additions

- `/brief/start-here`
- `/brief/weekly`
- `/brief/weekly/[week]`
- `/brief/topics/[topic]`
- optional `/brief/subscribe`

### Route continuity

- keep `/brief` as canonical digest root
- keep `/research` and `/research/[date]` as continuity routes until external links and indexing have fully shifted
- add canonical metadata pointing legacy paths to `/brief` equivalents where technically appropriate

### Content artifacts

- keep `research-digests/YYYY-MM-DD.json`
- add `research-digest-assets/YYYY-MM-DD.json`
- add `research-weekly/YYYY-Www.json` or `YYYY-MM-DD.json`
- add optional generated feed outputs during static build

## Migration and backwards-compatibility notes

1. Do not break existing daily digest rendering.
   - new fields in digest JSON must be additive first
   - website loaders should tolerate older artifacts during transition

2. Do not remove `/research` immediately.
   - preserve aliases and redirects until search/indexing and inbound links are reviewed

3. Introduce artifact validation before relying on new fields.
   - build should fail on malformed new weekly or distribution asset files

4. Keep weekly and derivative generation decoupled from daily publish success.
   - a daily issue should still publish if weekly regeneration or social copy generation fails

## Risks

- cross-repo coordination risk because the generator and presentation layer are deployed separately
- static export constraints may limit provider integrations unless they support hosted forms or static POST flows
- taxonomy sprawl could create thin pages if topic routing is added without thresholds
- automated promotional copy can drift into hype unless review boundaries are explicit
- weekly generation quality may be weak if it relies only on naive clustering instead of curated promotion logic

## Open questions

1. Which newsletter platform should own subscription capture and list management?
2. Should weekly roundups become the primary email edition immediately, or only after a trial period?
3. Does Lambic Labs want topic pages to be strictly generated from existing taxonomy, or partially curated?
4. Should social cards use a single template family or topic-specific variants?
5. Where should editorial overrides live?
   - checked-in JSON beside generated artifacts
   - a hand-authored YAML overlay
   - a separate non-public artifact directory

## Immediate next implementation slice

The best first implementation slice is:

1. Extend the digest artifact schema additively for share metadata and CTA config.
2. Update the website loaders to accept the new fields without requiring them.
3. Add `/brief` primary CTA, `/brief/[date]` bottom CTA, and improved page metadata.
4. Integrate a subscription provider using a static-compatible approach.
5. Add a minimal analytics layer for pageviews and CTA clicks.

That sequence creates a usable conversion foundation without blocking on weekly generation or topic architecture.
