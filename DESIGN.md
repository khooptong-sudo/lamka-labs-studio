---
name: Lamka Labs Studio
description: A motion-control production console for evidence-backed video creation.
---

<!-- SEED: established with the user before implementation; re-run $impeccable document once there's code to capture the actual tokens and components. -->

# Design System: Lamka Labs Studio

## Overview

**Creative North Star: "The Motion-Control Bench"**

Lamka Labs Studio borrows its discipline from a motion-control camera bench: calibrated tracks, cue sheets, transport controls, and a clear separation between setup, execution, and review. It refuses both the generic glowing AI dashboard and the black-and-gold screenplay aesthetic. The interface should feel engineered for repeated production work, with the operator always able to locate the active input, costly choice, pipeline state, and finished artifact.

The world is cool, precise, and tactile. Dense areas use alignment and tonal layering rather than nested cards. A single warm signal color marks actions and live focus. Motion appears once as transport behavior: stages advance along a production rail and controls depress physically when committed.

**Key Characteristics:**

- Cool graphite surfaces with porcelain text and one warm signal accent.
- Edit-decision rows, contact-strip thumbnails, and motion-control rails as functional structure.
- Compact workhorse typography with mono reserved for time, dimensions, counts, and machine state.
- Flat by default, lifted only for transient overlays or an actively manipulated object.
- Desktop-first density with a strict single-column mobile fallback.

## Colors

The palette uses cool near-black metal and blue graphite, avoiding CinePrompt's warm film-stock neutrals and gold controls.

### Primary

- **Signal Coral:** the only non-semantic accent, used for primary actions, active focus, and the live transport position. Exact value will be resolved during implementation.

### Neutral

- **Night Housing:** the application background, close to black but visibly blue-cool.
- **Graphite Deck:** working surfaces and fixed navigation.
- **Raised Rail:** selected rows, inputs, and active production bands.
- **Porcelain Type:** primary text without pure white glare.
- **Cadet Type:** secondary text and machine annotations.

**The Signal Discipline Rule.** Signal Coral marks at most one primary action and one active focus region in a viewport. Semantic success, warning, and failure colors are reserved for real state.

## Typography

**Display Font:** Geist Sans with system sans-serif fallback
**Body Font:** Geist Sans with system sans-serif fallback
**Label/Mono Font:** Geist Mono with monospace fallback

**Character:** The pairing is neutral enough for long operating sessions, but its tight geometry suits calibrated production tooling. Hierarchy comes from size, weight, and alignment rather than decorative type changes.

### Hierarchy

- **Display:** compact route titles only, never oversized.
- **Headline:** panel and production titles with tight line height.
- **Title:** control-group and item titles.
- **Body:** readable operational copy with a maximum measure near 70 characters.
- **Label:** concise machine-state labels; mono is reserved for values, not used as a technical costume.

**The Measured Mono Rule.** If a value can be measured, counted, timed, sized, or addressed, mono may own it. Narrative copy remains sans-serif.

## Layout

The desktop application uses a fixed navigation rail and a wide working canvas. The Production route uses three coordinated zones: source and continuity on the left, construction controls in the center, and an always-visible run summary on the right. Horizontal rules and aligned baselines separate dense groups; boxes appear only when an element genuinely moves above the deck.

At widths below 1100px the summary becomes a bottom production dock. Below 768px the navigation condenses to a top bar and every work zone becomes one column. Touch targets remain at least 44px high even when information density is high.

## Elevation & Depth

Depth is tonal and mechanical. Fixed surfaces differ by one luminance step. Inputs appear recessed; active controls rise by a small shadow and one-pixel highlight. Large ambient glows, decorative glass, and persistent drop shadows do not belong in this world.

**The Flat Deck Rule.** Resting content stays flat. Elevation communicates manipulation, focus, or temporary layering.

## Shapes

Panels and fields use restrained 10-12px corners. Small status chips may be pill-shaped because they are compact indicators, while action buttons and work surfaces remain gently rectangular. Dividers are sparse and structural. No nested rounded containers.

## Do's and Don'ts

### Do:

- **Do** make source provenance, provider readiness, cost-bearing choices, and pipeline state visible before generation.
- **Do** use a single production rail to connect setup, execution, and completion.
- **Do** keep mobile structure explicit and preserve familiar form semantics.
- **Do** let real thumbnails and generated shots carry visual energy.

### Don't:

- **Don't** copy CinePrompt's black, parchment, gold, screenplay, or hardware-switch visual treatment.
- **Don't** use purple gradients, generic glass panels, neon halos, or animated decoration.
- **Don't** hide essential configuration behind hover, color alone, or unlabeled icons.
- **Don't** place cards inside cards or turn every group into a bordered box.
