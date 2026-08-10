# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The primary user is the owner-operator running a private content studio on a Windows workstation. The operator researches stories, selects evidence, configures a production, monitors generation, reviews drafts, and publishes manually. Future collaborators may use the same cockpit, but the current workflow is optimized for one accountable editor.

## Product Purpose

The Content Creation Project turns source-backed finance news and reviewed kids concepts into complete video drafts. It coordinates scripting, narration, visual generation, rendering, metadata, and review without auto-publishing. Success means a production can move from an auditable source or storyboard to a reviewable video and upload packet without losing provenance or quality gates.

## Positioning

This is a research-first production engine, not only a prompt composer. One operator can move from dated sources to an evidence-bounded script, cinematic visuals, narration, rendered video, and manual upload packet while retaining human approval at the consequential boundaries.

## Operating Context

The studio runs locally by default with a Next.js cockpit, a Python worker, local Postgres, ComfyUI on an RTX 3070, local rendering, and optional cloud providers where quality requires them. The recurring workflow is Inbox review, production setup, live job monitoring, draft inspection, and manual publication. Finance and kids are separate channels with their own voice and compliance constraints.

## Capabilities and Constraints

- Research Inbox with dated, linked source packets.
- Manual ideas and reviewed storyboard overrides.
- Image-led portrait Shorts and code-authored landscape Story Films.
- Selectable image and narration providers.
- Script, narration, visual, render, metadata, and verification stages.
- Quality guards reject truncated, silent, placeholder-heavy, or unverified output.
- Nothing auto-publishes; a human reviews every draft and uploads manually.
- Local-first operation avoids unnecessary quota and billing dependencies.
- The target capability class includes cinematic prompt controls, frame-to-motion planning, multi-shot continuity, model/provider routing, and reusable production presets.

## Brand Commitments

The product identity is **Lamka Labs Studio** within the Content Creation Project and the wider Lamka Labs product family. The interface may learn from professional filmmaking and prompt-building tools, including CinePrompt, but must not copy their proprietary branding, code, assets, or distinctive visual treatment. Capability parity is welcome; visual imitation is not. The voice is direct, operational, technically literate, and occasionally playful.

## Evidence on Hand

- Current GUI routes under `gui/src/app/`.
- Worker pipeline and quality gates under `worker/app/`.
- Canonical project state in `PROGRESS.md`, `MEMORY.md`, and `docs/youtube/YT-HANDOFF.md`.
- Completed and interrupted local video runs under `videos/` for validating real states.
- No customer testimonials, public usage metrics, or commercial performance claims are available and none should be fabricated.

## Product Principles

1. Evidence before automation.
2. A partial run is never presented as a draft.
3. The operator can see and control every expensive or consequential stage.
4. Local by default, cloud by deliberate choice.
5. The interface serves production clarity before visual spectacle.

## Accessibility & Inclusion

The web cockpit must remain keyboard-operable, responsive, readable at common desktop zoom levels, and usable with reduced motion. Status, readiness, and failure states cannot rely on color alone.
