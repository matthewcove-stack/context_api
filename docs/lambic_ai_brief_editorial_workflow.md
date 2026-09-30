# Lambic AI Brief editorial workflow

## Purpose

The Brief must read like a short reported note written by an editor who has inspected the sources. It must not read like a model filling a newsletter template.

This workflow adapts the house style and review method in the separate `writing_repo`: UK English, restrained operational prose, mechanism before implication, distinct structural and anti-AI passes, and removal of any sentence written to impress.

## Audit that triggered the change

The ten daily issues from 2026-08-15 through 2026-08-24 showed repeated system-level failures:

- 10 of 10 used the same `This issue is most useful as a decision surface...` editorial frame.
- 10 of 10 ended with the same generic `Watch whether ... signals turn into repeatable production patterns.` construction.
- 10 of 10 copied `topThings[0]` unchanged into `builderImplication`.
- 53 of 60 engineering takeaways began as commands.
- Intros repeatedly began with `This issue`, `A practical look`, or another newsletter scaffold instead of a reported fact.
- Several items stacked abstract nouns such as governance, provenance, infrastructure, controls, pressure, and signals without naming a mechanism.
- The 2026-08-20 issue contained an unfinished sentence, and the 2026-08-24 watch line contained `agents signals`.

The problem was not that a particular model chose a few awkward words. The generator required the same rhetorical jobs on every issue, created the Lambic View from deterministic boilerplate, and checked only completeness and source diversity before publication.

## Publication workflow

Every new daily issue now passes these stages:

1. **Evidence packet** — candidate source metadata, extracted facts, support snippets, metrics, and clean quotations are assembled before drafting.
2. **Reported draft** — the first editor writes factual copy and a specific Lambic view. The prompt requires named entities and mechanisms before implications.
3. **Structural review** — a separate model pass checks that the title, introduction, summary, top points, editorial view, and each item do different work. `what happened`, `why it matters`, and `engineering takeaway` cannot paraphrase one another.
4. **Anti-AI review** — the same independent pass removes vague abstraction, generic transitions, rhetorical symmetry, consultancy language, repeated sentence shapes, and prose that could fit an unrelated LinkedIn post.
5. **Recent-issue comparison** — the candidate is compared with the previous ten issues. Reusing a five-word top-level opening that already recurred twice is a blocking finding.
6. **Deterministic style gate** — phrase, duplication, length, completeness, specificity, and sentence-shape checks run over the revised JSON.
7. **Bounded repair** — if the gate still finds a problem, the reviewer receives the exact findings and can make up to two further rewrites.
8. **Fail closed** — an issue that still fails is skipped. It is not written, committed, pushed, or published.
9. **Review record** — a passing issue stores `editorialReview` metadata with the workflow version, review time, revision count, checked-field count, findings, and material edits.

## House rules enforced by the generator

### Lead with evidence

- Name the company, product, paper, benchmark, measurement, incident, release, or policy early.
- Report what happened before interpreting it.
- Use examples and mechanisms to reduce abstraction.
- Do not claim that unrelated stories have converged on a single lesson merely to make the issue feel coherent.
- Do not force unrelated stories into a control-plane, audit or governance theme. Separate factual sentences are preferable when there is no evidenced connection.

### Keep each field distinct

- `intro` establishes why the specific edition is worth reading.
- `summary` connects only items that share a real mechanism.
- `issueSummary` states one plain editorial judgement.
- `topThings` records the most useful facts or consequences and cannot duplicate another field.
- `editorialFrame` states Lambic's view of named evidence, not how the reader should use the issue.
- `builderImplication` identifies one concrete change to a design or operating decision.
- `watchSignal` names observable evidence that could confirm or weaken the view.

### Remove synthetic prose

The gate rejects recurring phrases such as:

- `decision surface`
- `the signal is in`
- `signals turn into repeatable patterns`
- `This issue covers...`
- `a practical look at...`
- `operationalize`
- `first-class`
- `not just X but Y`

These are examples, not the full test. The reviewer also checks abstract-noun stacks, repeated openings, copied fields, excessive command-style takeaways, and incomplete sentences.

### Make recommendations earned and specific

- Not every item needs to tell the reader to build something.
- A concrete limitation, missing comparison or unanswered question may be the most useful takeaway. Do not invent thresholds, checklists or first-hand Lambic experiments to manufacture an action.
- A recommendation should identify an action, test, threshold, owner, or trade-off supported by the source.
- No more than half of the takeaways should begin as commands.
- A watch item must name observable evidence from the issue. `Watch what happens next` is not a watch item.

### Weekly collections

The current weekly output is an archive collection, not an independently reported
weekly essay. It uses the latest issue's complete summary and, where available,
complete reviewed editorial copy with a link to its source issue. No character
trimming, generic weekly thesis or unreviewed fallback commentary is allowed.
Original weekly analysis remains a separately reviewed future capability.

## Revising published issues

Existing issues can be run through the same workflow without changing their source URLs, dates, categories, document IDs, metrics, or quotations:

```bash
python -m scripts.revise_lambic_ai_briefs \
  --website-repo /path/to/lambic_labs_website \
  --last 10
```

Use `--dry-run` to complete both review passes without writing files. The command is transactional: it holds revised issues in memory and writes only after every selected issue passes.
