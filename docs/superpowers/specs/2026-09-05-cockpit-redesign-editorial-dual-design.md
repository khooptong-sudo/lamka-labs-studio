# Cockpit Redesign — Editorial Dual — Design

**Date:** 2026-09-05
**Status:** Approved, awaiting implementation plan
**Scope:** Whole cockpit, two phases. Phase 1 (tokens + shell + films + drafts,
the production path). Phase 2 (dashboard, X, cinema, settings, docs). IA,
routes, and behavior unchanged throughout — this is look, type, and structure
only.

## Direction

Editorial Dual: a light porcelain cockpit with a retained, refined dark mode.
Voice comes from scale, spacing, hairlines, and one signal color — never
decoration. Inter for display and UI (self-hosted, same `next/font` precedent
as the poster fonts); system mono kept for measured values. No serif: this is
an eight-hour operating tool.

## Tokens

Light (`:root`): paper `#FAFAF7`, deck `#FFFFFF`, well `#F0EEE9` (recessed
inputs), ink `#17191D`, muted `#5D646E`, hairline `#E4E2DC`, coral `#D84F45`
(primary/ring/accent, dark-ink text on it `#FFFFFF`), success `#23875A`,
warning `#B87816`, destructive `#C43E3E`, radius `0.65rem`, one overlay shadow
token (transient surfaces only).

Dark (`.dark`): keep the current graphite bones with quieter borders —
background `#0D1218`, deck `#121922`, raised `#18212B`, recessed `#0A1016`,
ink `#E8EEF3`, muted `#8D9AA8`, hairline `#242F3A`, coral `#FF6259` (dark-ink
text `#11161C` on it), success `#58B982`, warning `#D9A24D`, destructive
`#FF6D68`. Sidebar `#0A1016`, active `#17212B` + coral tick.

Signal discipline: coral marks at most one primary action and one live region
per viewport. Semantic colors are state only. Flat decks; elevation only for
overlays and actively manipulated objects.

## Typography

Display (route titles): Inter 600, 26–28px, tight leading, never oversized.
Headline (panel titles): Inter 600 17–20px. Title (groups/items): Inter 600
14–15px. Body: Inter 400 14px/1.55, max ~65ch. Labels: 12px semibold for
control labels; mono (existing Cascadia stack) for anything measured, counted,
timed, sized, or addressed. Poster faces (Fredoka/Nunito) stay exactly as-is.

## Shell

Sidebar narrows 216px → 192px: product mark, section labels, quiet items,
active item gets tinted background + 2px coral tick. `ThemeProvider` and
`defaultTheme="dark"` stay (no behavior change). `.studio-main` keeps its
offset math updated to the rail width; the ambient radial wash goes away
(decoration, and it fights paper).

## Pages — Phase 1

Films: same three zones, separated by hairlines and aligned baselines instead
of boxes; provider choice becomes a segmented control (same options, same
no-default semantics where they exist); sticky production dock kept, quieter;
cinematic controls keep every field, regrouped with hairline dividers.
Drafts: contact-strip rows — state dot, title, channel/mode/duration meta in
mono, actions right-aligned; no cards-in-cards. Shared: one button hierarchy
(coral solid / ink solid / ghost), recessed wells, pill status chips, progress
rail restyled for both modes (order-driven, labels unchanged).

## Frozen (do not touch)

`PosterCard.tsx`, `posterScenery.tsx`, poster font loading in `layout.tsx`,
`poster-preview` export logic, `ChannelSelect` no-default semantics, all
worker API contracts. Page chrome around frozen components may reskin; the
components and their props may not change.

## Motion

150ms ease-out on hover/press/expand; progress states get transport feel
(advancing rail, never spinners-for-decoration); `prefers-reduced-motion`
collapses everything to instant. No ambient animation, no glass, no glows.

## Guardrails

Contrast AA both modes; keyboard order and visible focus preserved; 44px
minimum targets; single-column fallback under 768px, docked summary under
1100px (existing breakpoints honored). `npx tsc --noEmit` and `next build`
green per phase; screenshots of every touched route (light + dark) reviewed
before merge.

## Rollout

Phase 1 plan next: tokens → fonts/shell → films → drafts → FilmProgress +
shared controls. Phase 2 gets its own plan after Phase 1 merges. DESIGN.md
stays as the rejected alternative, marked superseded — history, not guidance.

## Files touched (Phase 1)

- `gui/src/app/globals.css` (tokens, base, rail offset, wash removal)
- `gui/src/app/layout.tsx` (Inter loading; poster fonts untouched)
- `gui/src/components/Sidebar.tsx`, `ThemeToggle.tsx` (kept, restyled)
- `gui/src/app/films/page.tsx`, `gui/src/app/drafts/page.tsx`
- `gui/src/components/FilmProgress.tsx`, `GenerateDraftButton.tsx`,
  `ChannelSelect.tsx`, `CinematicControls.tsx`, `AddIdeaForm.tsx`
  (reskin within frozen semantics)
