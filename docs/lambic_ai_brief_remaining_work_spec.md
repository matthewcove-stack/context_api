# Lambic AI Brief — Remaining Work Specification

## Purpose
This document describes the remaining work for the Lambic Labs digest product after the completion of the initial tidy-up and reframing work.

The first two stages are already complete:
- Phase 1: repositioning, renaming, and reframing the section
- Phase 2: cleanup, presentation improvements, and content-quality fixes

This document covers the rest of the recommended work and is intended to be given to Codex as the basis for a planning pass.

Codex should use this document to inspect the existing codebase and automation, identify where the relevant systems live, and produce a concrete implementation plan with dependencies, sequencing, acceptance criteria, and any necessary technical design notes.

This is a planning brief, not an implementation recipe.

---

## Product context
The product is now positioned as **Lambic AI Brief**: a practical AI engineering digest for people building real systems.

It should function as both:
1. a genuinely useful publication for engineers, founders, product teams, and technical operators working with AI systems
2. a trust-building authority asset for Lambic Labs

The remaining work is about turning the cleaned-up digest into a proper distribution engine, audience asset, and long-term brand surface.

---

## What Codex should do with this brief
Codex should:
- inspect the current site, routes, data flow, generation pipeline, and content model
- determine which parts of the remaining work belong in the website, the content-generation pipeline, the editorial pipeline, or supporting automation
- produce a phased implementation plan for the work described below
- identify dependencies and sensible sequencing
- identify anything that must be designed before implementation starts
- note any backwards-compatibility issues or migration requirements
- keep solutions aligned with the Lambic Labs tone: technical, restrained, practical, not hype-driven

Codex should not treat this brief as a request to blindly implement everything immediately. The immediate output should be a strong implementation plan.

---

# Remaining work

## Phase 3 — Conversion layer and audience capture
### Goal
Turn the digest from a browsable archive into a product that can capture and retain audience attention.

### Desired outcomes
The site should give readers clear next steps rather than leaving them at a dead end after reading an issue.

### Scope
Plan for the addition of:
- a clear primary CTA near the top of the digest landing page
- a secondary CTA at the bottom of issue pages
- email subscription capability or a clearly prepared subscription surface
- RSS or equivalent syndication surface if appropriate within the architecture
- a stronger archive browsing experience for returning readers
- a new-reader onboarding path, such as a “start here” or “best of” entry point
- social sharing support, including issue metadata suitable for sharing
- issue pages that look deliberate when shared externally

### Planning considerations
Codex should determine:
- whether subscription capture belongs inside the main site, a newsletter platform integration, or both
- what information architecture changes are needed to support reader journeys
- whether there should be dedicated landing pages for newcomers versus archive readers
- how issue metadata should be structured to support sharing and subscription surfaces
- what can be implemented now versus staged later

### Acceptance intent
At the end of this phase, readers should have a clear route to subscribe, return, or explore further.

---

## Phase 4 — Distribution asset generation from each issue
### Goal
Extend the digest pipeline so each issue becomes source material for distribution across channels.

### Desired outcomes
Each published issue should yield reusable promotional and distribution assets without requiring heavy manual work.

### Scope
Plan for the generation of channel-ready derivative assets such as:
- a founder-style LinkedIn post
- a company-page LinkedIn post
- one or more short-form social variants
- teaser copy for email distribution
- a compact “top takeaways” summary block
- metadata suitable for social cards or preview surfaces
- optional community-posting variants for strong issues or weekly roundups

### Planning considerations
Codex should determine:
- whether these assets are generated at issue build time, post-processing time, or on demand
- where these assets should be stored
- whether they belong in frontmatter, structured JSON, a database, or separate generated artifacts
- how tone should differ between channels while remaining consistent with Lambic Labs
- how to avoid brittle coupling between the public issue content and the derivative promotional content
- what review hooks or editorial overrides are needed

### Acceptance intent
At the end of this phase, each issue should function as a content source for social and email distribution rather than existing only as a web page.

---

## Phase 5 — Distribution readiness and launch surfaces
### Goal
Prepare the digest to be promoted through the most relevant channels without awkwardness, inconsistency, or low-conversion landing experiences.

### Desired outcomes
The product should be ready for regular promotion via founder channels, company channels, email, and technical communities.

### Scope
Plan for the work needed to support:
- founder-led promotion on LinkedIn
- company-led promotion on LinkedIn
- newsletter distribution
- selective use in technical communities or forums
- clear linking from Lambic Labs primary surfaces to the digest
- promotional consistency across channels

### Planning considerations
Codex should determine:
- whether the main digest landing page is sufficient as a promotion target or whether a more explicitly audience-facing landing page is needed
- how the digest should be linked from the main site navigation and homepage
- whether there should be a weekly roundup page that is more suitable for sharing than individual daily issues
- how issue and roundup pages should differ in structure and purpose

### Acceptance intent
At the end of this phase, there should be one or more clearly promotable surfaces that are coherent, credible, and conversion-aware.

---

## Phase 6 — Weekly “hero asset” or roundup layer
### Goal
Create a higher-level weekly product that is more shareable and more useful for growth than daily issue pages alone.

### Desired outcomes
The digest should support both:
- daily issues for retention and continuity
- weekly roundups for promotion, discovery, and broader sharing

### Scope
Plan for a weekly layer that:
- selects or summarises the most important items from the week
- presents them with stronger narrative coherence
- includes a short editorial frame or overview
- can act as the primary email edition if needed
- can serve as the main share target in public promotion

### Planning considerations
Codex should determine:
- how weekly aggregation should work relative to daily issue generation
- whether the weekly layer is derived automatically, editorially curated, or hybrid
- what data model or content relationships are needed between daily items and weekly roundups
- whether weekly issues need a different layout or route structure
- whether weekly pages should become the canonical promotional asset while daily pages remain archive/retention assets

### Acceptance intent
At the end of this phase, the digest should have a strong weekly surface suitable for broad sharing and repeat readership.

---

## Phase 7 — Authority and point-of-view layer
### Goal
Make the digest feel like expert curation rather than a neutral content dump.

### Desired outcomes
The publication should surface judgment, not just summarisation.

### Scope
Plan for the addition of lightweight editorial framing such as:
- “why this matters” signals
- practical implications for builders
- short engineering takeaways
- optional issue-level commentary or thematic framing
- stronger publication voice without turning it into a personal essay product

### Planning considerations
Codex should determine:
- where this commentary belongs in the issue structure
- how much of it should be generated versus explicitly authored or reviewed
- how to keep the voice restrained and technically credible
- how to preserve a clear distinction between summarised source content and Lambic Labs commentary

### Acceptance intent
At the end of this phase, the digest should feel meaningfully curated and recognisably useful to practitioners.

---

## Phase 8 — Information architecture and SEO structure
### Goal
Make the digest archive more discoverable, navigable, and useful over time.

### Desired outcomes
The site should support discovery by topic and intent, not just by date.

### Scope
Plan for the introduction of stronger information architecture such as:
- topic or category pages
- structured archive navigation beyond date-based browsing
- improved internal linking between issue pages, topic pages, and roundup pages
- route structures that support long-term discoverability
- metadata and page structure that better support indexing and previews

### Planning considerations
Codex should determine:
- which taxonomy model is appropriate for the existing content volume and generation style
- how topic pages should be generated and populated
- whether tags, categories, and issue themes should be separate concepts
- what metadata model is needed for robust internal linking and page previews
- whether existing routes need migration or augmentation
- how to avoid SEO bloat from thin or repetitive pages

### Acceptance intent
At the end of this phase, the digest should be easier to browse, easier to discover, and better structured for long-term growth.

---

## Phase 9 — Optional paid amplification readiness
### Goal
Prepare the product for selective paid amplification only once the organic and conversion foundations are sound.

### Desired outcomes
Paid promotion, if used later, should point to surfaces that are actually designed to convert and retain attention.

### Scope
Plan for what would be needed to support later experiments with:
- sponsored promotion of roundups or landing pages
- retargeting-friendly entry points
- campaign-specific landing surfaces if needed
- performance attribution for paid versus organic channels

### Planning considerations
Codex should determine:
- what product and analytics prerequisites should exist before any paid testing is attempted
- whether any dedicated landing templates should be prepared in advance
- what instrumentation is needed to evaluate channel quality

### Acceptance intent
This phase is mainly about readiness and architecture, not immediate paid marketing execution.

---

## Phase 10 — Measurement, analytics, and operating feedback loop
### Goal
Ensure the digest can be measured as a publication and as a brand-building asset.

### Desired outcomes
The team should be able to understand:
- what readers engage with
- which channels bring quality traffic
- which topics drive return visits or subscriptions
- whether weekly assets outperform daily assets for growth

### Scope
Plan for instrumentation and reporting around:
- issue views
- landing page performance
- subscription conversion
- return readership
- engagement by issue type or topic
- traffic source quality
- internal promotion versus external distribution performance
- weekly versus daily asset performance

### Planning considerations
Codex should determine:
- what analytics stack is already present and whether it is sufficient
- what events and page-level metrics should be added
- how success should be measured without over-instrumenting the site
- how to structure a lightweight reporting loop so the product can improve over time

### Acceptance intent
At the end of this phase, the digest should have an observable operating loop rather than relying on intuition alone.

---

# Cross-cutting requirements

## Brand and tone
All planning should stay aligned with Lambic Labs brand characteristics:
- practical
- technical
- restrained
- useful
- anti-hype
- signal-over-noise

The digest should feel credible to engineers and founders, not like generic AI marketing content.

## Continuity and backwards compatibility
Codex should identify any route, archive, metadata, or content migrations required by the above work and plan them carefully.

The digest already exists and already has published content. Future work should preserve continuity where sensible.

## Automation awareness
This product is already heavily automated.

The planning work should therefore pay particular attention to:
- where automation outputs should be enriched rather than replaced
- what should be generated as structured data versus rendered copy
- how to keep the system robust when no issue is published on a given day
- how to prevent the distribution layer from becoming fragile or over-coupled

## Human review boundaries
Codex should identify where human review or override is desirable, especially for:
- public promotional copy
- issue-level commentary
- weekly editorial framing
- any assets that might benefit from discretionary judgment

---

# Suggested implementation sequencing for planning purposes
Codex does not need to follow this exactly, but should use it as a sensible default ordering when designing the implementation plan:

1. Phase 3 — conversion layer and audience capture
2. Phase 4 — distribution asset generation
3. Phase 6 — weekly roundup / hero asset
4. Phase 8 — information architecture and SEO structure
5. Phase 7 — authority and point-of-view layer
6. Phase 10 — analytics and feedback loop
7. Phase 5 — distribution readiness and launch surfaces (if separate work remains after the above)
8. Phase 9 — optional paid amplification readiness

Rationale:
- capture and retention need to exist before promotion matters
- distribution assets are needed before regular social/email use becomes efficient
- a weekly hero asset is likely to be the best promotional unit
- stronger information architecture improves usability and discoverability
- commentary/authority is more valuable once the core surfaces are stable
- measurement should be added early enough to observe outcomes
- paid readiness should come last

Codex should adjust this sequencing if inspection of the current implementation suggests a better order.

---

# Deliverable expected from Codex
Codex should produce a planning document that includes:
- a proposed implementation breakdown by phase
- technical and product dependencies
- any route/content/model changes required
- automation changes required
- analytics and instrumentation considerations
- rollout order
- migration or backwards-compatibility notes
- risks and open questions
- acceptance criteria for each phase

That planning output should be specific enough that implementation can begin from it without needing the strategy restated.

---

# Summary
The product is no longer just an archive of generated daily issues. The remaining work is about turning **Lambic AI Brief** into:
- a credible publication
- a reusable distribution source
- an audience capture surface
- a weekly shareable asset
- a long-term authority engine for Lambic Labs

Codex should plan the remaining work accordingly.
