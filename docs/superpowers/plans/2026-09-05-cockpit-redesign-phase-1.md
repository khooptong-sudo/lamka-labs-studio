# Cockpit Redesign Phase 1 (Tokens + Shell + Films + Drafts) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reskin the production path (shell, films, drafts, shared controls) in the Editorial Dual system with zero behavior change.

**Architecture:** Tokens first (everything keys off CSS vars), then shell, then pages top-down; each task ends with `tsc` clean and the dev server rendering. No new dependencies except the Inter font (build-time `next/font`, same precedent as the poster fonts). No API, worker, or behavior changes — classNames, copy, and component props stay meaning-compatible unless the task says otherwise.

**Tech Stack:** Next.js 16 + React 19 + Tailwind v4 (CSS-first, no config file) + next-themes + lucide-react. Verification is `npx tsc --noEmit`, `npm run build`, and Playwright screenshots in both themes — there is no GUI unit-test runner and this plan does not add one.

**Spec:** `docs/superpowers/specs/2026-09-05-cockpit-redesign-editorial-dual-design.md`

## Global Constraints

- FROZEN (never touch): `PosterCard.tsx`, `posterScenery.tsx`, poster font loading in `layout.tsx`, `poster-preview` export logic, `ChannelSelect` no-default semantics, all worker API contracts. Page chrome around frozen components may reskin.
- Keep `defaultTheme="dark"`, keep both themes, keep all breakpoints (1100px dock, 768px top bar, 44px targets).
- `prefers-reduced-motion` block in globals.css stays and still covers everything new.
- Dead `animate-in`/`fade-in`/`slide-in-*` classes (no animation plugin installed — they do nothing today) are removed where touched, never added to.
- PowerShell 5.1 for shells (no `&&`). GUI commands run with workdir `gui/`.
- The working tree may hold unrelated uncommitted work: stage ONLY your files/hunks. Do NOT push (Task 4 pushes once).

---

### Task 1: Tokens, fonts, shell

**Files:**
- Modify: `gui/src/app/globals.css`, `gui/src/app/layout.tsx`, `gui/src/components/Sidebar.tsx`
- Restyle (no logic): `gui/src/components/ThemeToggle.tsx`

**Interfaces:**
- Consumes: nothing (foundation task).
- Produces: Editorial Dual CSS vars, Inter display/body faces, 192px rail, coral-tick active states. Every later task builds on these exact var names.

- [ ] **Step 1: Rewrite the token blocks**

In `globals.css`, replace the `:root` and `.dark` blocks with the spec values
(light: paper `#FAFAF7`, deck `#FFFFFF`, well `#F0EEE9`, ink `#17191D`,
muted `#5D646E`, hairline `#E4E2DC`, coral `#D84F45` with white text,
success `#23875A`, warning `#B87816`, destructive `#C43E3E`,
surface-recessed `#F0EEE9` (new var for wells — the current light block
lacks it; dark keeps its existing value);
dark: bg `#0D1218`, deck `#121922`, raised `#18212B`, recessed `#0A1016`,
ink `#E8EEF3`, muted `#8D9AA8`, hairline `#242F3A`, coral `#FF6259` with
`#11161C` text, success `#58B982`, warning `#D9A24D`, destructive `#FF6D68`,
sidebar `#0A1016`, active `#17212B`; radius `0.65rem`). Keep every existing
var NAME (`--background`, `--foreground`, `--card`, `--primary`,
`--secondary`, `--accent`, `--destructive`, `--border`, `--input`, `--ring`,
`--muted`, `--surface-deck`, `--surface-raised`, `--surface-recessed`,
`--sidebar`, `--sidebar-active`, `--success`, `--warning`, `--radius`) —
pages reference them; renaming would balloon the diff. Add one overlay shadow
token `--shadow-overlay` used only for transient surfaces.

- [ ] **Step 2: Update base rules**

`.studio-main`: `margin-left: 192px`, remove the radial-wash background
(plain `var(--background)`). `.studio-sidebar`: `width: 192px`.
`.studio-brand-logo`: 32px. Nav link radius 10px; active state keeps its
structure but the tick uses 2px coral (already coral — keep). Remove
`.glass`/`.glass-panel` ambient leftovers? No — pages still use them; leave
the classes (redefine `.glass-panel` as flat deck: `background:
var(--surface-raised); border: 1px solid var(--border);` no shadow).
Delete `.premium-hover` translate rule (keep the class name as a no-op color
transition so callers don't break: `transition: background-color 150ms ease,
border-color 150ms ease`). Keep the mobile block, updating 216px→192px
references (margin-left, sidebar width). Keep the reduced-motion block verbatim.

- [ ] **Step 3: Load Inter, keep poster fonts byte-identical**

In `layout.tsx`, add:

```tsx
import { Inter } from "next/font/google";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});
```

Add `inter.variable` to the `<html>` className. Do NOT touch the Fredoka /
Nunito blocks. In `globals.css` `@theme inline`, set `--font-sans:
var(--font-inter), "Segoe UI Variable", "Segoe UI", system-ui, sans-serif;`
Keep `--font-mono` exactly as-is.

- [ ] **Step 4: Sidebar reskin (structure untouched)**

Same items, same order, same active logic, same ThemeToggle row, same status
block. Changes: 192px rail padding rhythm (nav `padding: 14px 10px`),
13px/590 nav type, section caption "STUDIO" stays, brand h1 Inter 700.
No prop or route changes.

- [ ] **Step 5: Verify**

Run: `cd gui; npx tsc --noEmit`
Expected: clean. Then: `cd gui; npm run build`
Expected: success. Then eyeball: `npm run dev`, open `/films` in both themes —
unstyled pages are expected (they still reference old patterns); this task
only proves the shell + tokens compile and render.

- [ ] **Step 6: Commit**

```bash
git add gui/src/app/globals.css gui/src/app/layout.tsx gui/src/components/Sidebar.tsx gui/src/components/ThemeToggle.tsx
git commit -m "Reskin shell in Editorial Dual tokens and Inter"
```

---

### Task 2: Shared controls

**Files:**
- Modify: `gui/src/components/FilmProgress.tsx`, `GenerateDraftButton.tsx`, `ChannelSelect.tsx`, `CinematicControls.tsx`, `AddIdeaForm.tsx`
- Test: none (no runner) — verification is tsc + screenshots in Task 4.

**Interfaces:**
- Consumes: Task 1 tokens.
- Produces: one button hierarchy, recessed wells, pill chips, light/dark progress rail. Props and semantics byte-identical.

- [ ] **Step 1: Buttons, inputs, chips**

Establish (in globals.css, additive classes — pages adopt them in Tasks 3–4):
`.btn-primary` (coral solid, spec text color per theme), `.btn-ink`
(ink solid), `.btn-ghost` (transparent, hairline on hover), `.field-well`
(recessed `var(--surface-recessed)`), `.chip` (pill, 11px semibold uppercase).
`.chip` (pill, 11px semibold uppercase). Focus-visible and 44px rules ride
the existing base. Then swap Films/Drafts/shared components onto them as
those files are touched — do NOT global-find-replace classNames blindly.

- [ ] **Step 2: FilmProgress restyle**

Keep stages array, labels, polling, skipped-film logic, done/error panels.
Replace `glass-panel rounded-3xl` wrapper with flat deck + hairline;
stage pills keep shape language but use `.chip` tones; remove glow shadows
(`shadow-[0_0_...]`); spinner stays (transport, not decoration). The
`Record<typeof STAGES[number], string>` type is the drift guard — tsc must
stay clean.

- [ ] **Step 3: Form controls**

`ChannelSelect`, `CinematicControls`, `AddIdeaForm`, `GenerateDraftButton`:
same props, same options, same no-default semantics; wells for inputs,
hierarchy buttons, hairline dividers between groups. `CinematicControls`
keeps every field (piece-3 motion intent included).

- [ ] **Step 4: Verify**

Run: `cd gui; npx tsc --noEmit`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add gui/src/app/globals.css gui/src/components/FilmProgress.tsx gui/src/components/GenerateDraftButton.tsx gui/src/components/ChannelSelect.tsx gui/src/components/CinematicControls.tsx gui/src/components/AddIdeaForm.tsx
git commit -m "Restyle shared controls in Editorial Dual"
```

---

### Task 3: Films page

**Files:**
- Modify: `gui/src/app/films/page.tsx`

**Interfaces:**
- Consumes: Tasks 1–2 (tokens, controls).
- Produces: three hairline-separated zones, segmented provider control, quieter dock. Zero logic change: same state, same fetches, same payloads, same validation gates.

- [ ] **Step 1: Restructure**

Keep every hook, fetch, payload shape, and gate (`canGenerate`,
`needsReviewedBoard`, provider `configured` gating, storyboard override
semantics). Changes, top to bottom: route header → Display 27px semibold +
one muted subline; zones separated by hairlines and baseline alignment
(remove `rounded-3xl`/`glass-panel`/glow wrappers, keep DOM order);
provider radio group → segmented control bound to the same
`imageProvider` state (options and disabled-when-unconfigured behavior
identical); storyboard textarea keeps mono + rows, well background;
cinematic controls keep fields (Task 2 component); sticky dock keeps its
grid and content, flat raised surface, coral only on the generate action;
warning/error panels keep copy, pill-chipped.

- [ ] **Step 2: Verify**

Run: `cd gui; npx tsc --noEmit`
Expected: clean. Dev-render `/films` light + dark; every control from the
old page present and ordered identically (compare against `git show
HEAD:gui/src/app/films/page.tsx` side by side — same fields, same order).

- [ ] **Step 3: Commit**

```bash
git add gui/src/app/films/page.tsx
git commit -m "Restructure films page in Editorial Dual"
```

---

### Task 4: Drafts page, screenshots, record, push

**Files:**
- Modify: `gui/src/app/drafts/page.tsx`, `PROGRESS.md` (decision #82)

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: contact-strip drafts, reviewed screenshots, decision row, push.

- [ ] **Step 1: Restructure drafts**

Keep data flow (`/api/drafts`, tabs, storyboard/audio fetches, copy
buttons): header → Display title + subline; empty state keeps copy, flat
deck, no glow disc; `DraftCard` becomes a flat row stack — header row
(status pill `.chip`, mono ID, headline Title 17px), tab row (hairline
underline tabs, coral active), body keeps the 2/3 + 1/3 grid with wells
instead of `bg-black/60` inset boxes (that class is near-black in both
themes — replace with `var(--surface-recessed)`); remove `shadow-2xl`,
glow `shadow-[0_0_...]`, `group-hover` border theatrics, and dead
`animate-in` classes; YouTube red tab accent stays (brand color, not
decoration); CopyField keeps behavior, ghost copy buttons.

- [ ] **Step 2: Screenshots**

`cd gui; npm run dev` (leave running), then for `/`, `/films`, `/drafts`
in light + dark: `npx playwright screenshot --viewport-size=1600,900
--wait-for-timeout=3000 <url> <out>.png`. Pages needing a live worker show
honest empty/error states — that is what gets reviewed. Save under
`C:\Users\MIN K\AppData\Local\Temp\opencode\gui-review\` (never in the repo).
Review each: one coral action per viewport, hairlines not boxes, mono only
on values, no glow, text contrast AA in both themes, visible focus order
sane, one 768px-width shot per page for the single-column fallback. Fix and
re-shoot before proceeding.

- [ ] **Step 3: Full verification**

Run: `cd gui; npx tsc --noEmit` then `cd gui; npm run build`
Expected: both clean. Worker suite untouched by this plan — skip it (no
worker files change; note that in the commit message if asked).

- [ ] **Step 4: Record and push**

`PROGRESS.md` append:

```
| 82 | Editorial Dual Phase 1: tokens, shell, films, drafts | gui-redesign | Light porcelain + refined dark, Inter, hairline structure, frozen poster/export path. Verified by tsc + build + screenshots. |
```

```bash
git add gui/src/app/drafts/page.tsx PROGRESS.md
git commit -m "Restructure drafts page in Editorial Dual"
git push
```
