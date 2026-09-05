# Cockpit Redesign Phase 2 (Dashboard, X, Cinema, Settings, Docs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the remaining five routes into Editorial Dual with zero behavior or copy change.

**Architecture:** Same method as Phase 1: classNames and structure only, DOM order and copy byte-identical, frozen components untouched. Static pages first (dashboard, docs), then interactive cockpits (X, cinema), then settings (live form state — extra care), closing with screenshots, build, decision, push.

**Tech Stack:** Next.js 16 + React 19 + Tailwind v4 + next-themes + lucide-react. Verification is `npx tsc --noEmit`, `npm run build`, Playwright screenshots both themes. No GUI unit-test runner; none added.

**Spec:** `docs/superpowers/specs/2026-09-05-cockpit-redesign-editorial-dual-design.md`

## Global Constraints

- FROZEN: `PosterCard.tsx` (+ its props/theme system), poster fonts, export logic, `ChannelSelect` semantics, all worker API contracts, ALL user-facing copy (buttons, labels, empty states, settings compliance wording — even where it reads oddly; copy changes belong to their owners, not this reskin).
- After each file edit, run `git diff` and confirm zero changed lines outside `className` strings (and pure structural wrappers with identical text content). Any text change aborts the task for review.
- Keep `defaultTheme="dark"`, breakpoints, 44px targets, reduced-motion coverage.
- Dead `animate-in`/`fade-in`/`slide-in-*` classes removed where touched, never added.
- PowerShell 5.1 (no `&&`). GUI commands with workdir `gui/`.
- The working tree holds unrelated uncommitted work (worker teardown, settings copy may be part of it, favicon, brand-kit/, logos): stage ONLY your files, and within `settings/page.tsx` ONLY className hunks. Do NOT push (Task 3 pushes once).

---

### Task 1: Dashboard + docs (static pages)

**Files:**
- Modify: `gui/src/app/page.tsx`, `gui/src/app/docs/page.tsx`

**Interfaces:**
- Consumes: Phase-1 tokens/classes (`.btn-*`, `.field-well`, `.chip`, decks, hairlines).
- Produces: Display headers, flat stat band, hairline-divided feeds, docs sections on wells. Same fetches, same data shapes, same links.

- [ ] **Step 1: Dashboard (`page.tsx`, server component — no state to preserve, but keep fetches)**

Header → Display 27px + subline; pending-count pill → `.chip` with mono count
(keep the fetch + `stories.length` logic). Stat cards: flat deck, hairline,
icon chip muted (remove giant `opacity-10` watermark icon + `drop-shadow-*`
+ `premium-hover` lift); value Inter 800 32px (mono only if it were measured
live — these are display stats, keep sans); trend pill keeps success tint.
Inbox + analytics panels: flat deck, hairline header rows, `divide-y`
retained, hover wash only (no `group-hover:text-primary` recolor on
headlines — color-shifting text on hover is decoration; keep text ink).
Source badge → `.chip`; date stays mono muted; GenerateDraftButton already
restyled (Task 2 component, no change here); Watch link → `.btn-ghost`.
Empty states keep copy, flat deck.

- [ ] **Step 2: Docs (`docs/page.tsx`, static)**

Header → Display + subline. Section icon headers keep order/icons; panels
flat deck + hairline; `code` chips → well background + mono (keep both
`bg-black/10 dark:bg-foreground/10` → single well class that themes);
troubleshooting wells → `.field-well` readout styling (read-only).
Copy byte-identical (runbook commands especially).

- [ ] **Step 3: Verify**

Run: `cd gui; npx tsc --noEmit`
Expected: clean. `git diff` on both files: classNames/structure only, zero
copy changes.

- [ ] **Step 4: Commit**

```bash
git add gui/src/app/page.tsx gui/src/app/docs/page.tsx
git commit -m "Reskin dashboard and docs in Editorial Dual"
```

---

### Task 2: X + cinema (interactive cockpits)

**Files:**
- Modify: `gui/src/app/x/page.tsx`, `gui/src/app/cinema/page.tsx`

**Interfaces:**
- Consumes: Phase-1 tokens/classes.
- Produces: same three-column X cockpit and same cinema picker flow, reskinned. All state machines, tone presets, poster styles/modes, download logic, and `PosterCard` usage identical.

- [ ] **Step 1: X page (448 lines — read whole file first, then edit surgically)**

Keep: all `useState`, TONE_PRESETS/POSTER_STYLES values, tab logic
(post/poster), rewrite/reply/poster/download handlers, `posterRef` export
flow, error handling, `PosterCard` + `getPosterTheme` usage (frozen).
Change: header → Display + subline; story list → hairline rows with `.chip`
source + mono date (mirror dashboard feed); tone preset buttons → segmented
control bound to same `tone` state; textareas/outputs → wells (mono kept
where it already is); action buttons onto the hierarchy (Rewrite primary
coral; copy/download ghost); tabs → hairline underline tabs; poster preview
frame flat deck (the POSTER ITSELF untouched — only its frame); error panel
→ destructive pill styling, same copy.

- [ ] **Step 2: Cinema page (411 lines — read whole file first)**

Keep: description state, fill/picker flow, all ~130 field groups and
multi-select semantics, build/save/history calls, fal.run BYOK handling
(key never leaves the browser), generation grid. Change: header → Display +
subline; picker groups → hairline sections with Title labels; chips onto
`.chip` selected/unselected tones (coral only for the Generate action);
history list → hairline rows with mono timestamps; output grid frames flat.
The deferred visual pass from MEMORY.md is exactly this task — no new
deferrals after it.

- [ ] **Step 3: Verify**

Run: `cd gui; npx tsc --noEmit`
Expected: clean. `git diff --stat` sanity: expect className-heavy diffs, no
deleted handlers/state. Grep both files for `bg-black/60`, `shadow-2xl`,
`shadow-[0_0`, `animate-in ` — zero hits (the YouTube-red tab accent and
`animate-spin` loaders stay: brand color and transport, respectively).

- [ ] **Step 4: Commit**

```bash
git add gui/src/app/x/page.tsx gui/src/app/cinema/page.tsx
git commit -m "Reskin X and cinema cockpits in Editorial Dual"
```

---

### Task 3: Settings, screenshots, record, push

**Files:**
- Modify: `gui/src/app/settings/page.tsx`, `PROGRESS.md` (decision #83)

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: reskinned settings with identical form semantics, reviewed screenshots, decision row, push.

- [ ] **Step 1: Settings (live form — highest care)**

Keep EVERYTHING behavioral: channel fetch/switch/save flow (including the
stash-unsaved-on-switch logic), blocklist add/remove, loading/saving states,
and ALL copy byte-identical (including the compliance wording — it may read
oddly; it belongs to another workstream, and this task must not adjudicate
it). Change only: header → Display + subline; save button → `.btn-primary`;
cards → flat deck + hairline (remove hover-border theatrics +
`border-primary/0` ghosts); icon chips muted (Mic/Save/X keep icons, drop
tinted disco backgrounds — keep `success`/`destructive` ONLY on the
compliance icon + word pills where they already are); select/textarea/input
→ `.field-well` (mono kept on the prompt textarea); Add-Word button ghost.
Verify with `git diff -U0` that every changed line is a className line or a
pure wrapper: `git diff -- gui/src/app/settings/page.tsx | Select-String
"^[-+]" | Select-String -NotMatch "^[-+]{3}" | Select-String -NotMatch
"className|class=|<div|<span|<section|<header|<button|<label" ` must return
nothing. If anything else changed, revert those hunks before proceeding.

- [ ] **Step 2: Screenshots**

`cd gui; npm run dev` (leave running), then for `/`, `/x`, `/cinema`,
`/settings`, `/docs` in light + dark @1600 (+ one @768 per page):
`npx playwright screenshot --viewport-size=1600,900
--wait-for-timeout=3000 <url> <out>.png` under
`C:\Users\MIN K\AppData\Local\Temp\opencode\gui-review\phase2\` (create it;
never the repo). Light theme via the stored-theme method proven in Phase 1
(`--load-storage`); do not invent URL params. Worker-down empty states are
honest subjects. Review checklist per shot: one coral action, hairlines not
boxes, mono on values only, AA contrast eyeball both themes, copy identical
to `git show HEAD:gui/src/app/<page>/page.tsx` text content, mobile shots
single-column. Fix and re-shoot on failure.

- [ ] **Step 3: Full verification**

Run: `cd gui; npx tsc --noEmit` then `cd gui; npm run build`
Expected: both clean (the `/` prerender worker-fetch note is pre-existing
noise, exit 0).

- [ ] **Step 4: Record and push**

`PROGRESS.md` append:

```
| 83 | Editorial Dual Phase 2: dashboard, X, cinema, settings, docs | gui-redesign | ClassNames/structure only; copy, state, and API contracts untouched. Verified by tsc + build + screenshots. Redesign complete. |
```

```bash
git add gui/src/app/settings/page.tsx PROGRESS.md
git commit -m "Reskin settings page in Editorial Dual"
git push
```

Push gate: `git log origin/main..HEAD --oneline` must show ONLY Phase-2
commits (plus any of my own earlier commits already noted); `git status`
must show no other staged changes. If the range contains anything foreign,
stop and report instead of pushing.
