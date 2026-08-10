# CinePrompt Vocabulary Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manual, category-grouped field picker to the Cinema page so a user can build a prompt by browsing and clicking vocabulary values directly, without requiring the AI Fill step.

**Architecture:** One new read-only worker route (`GET /cineprompt/vocab`) exposes the engine's existing section/field/value data, filtered through the same `fields_in_scope(mode, level)` the Fill prompt already uses. The Cinema page's `fields` state (currently `Record<string, string>`) widens to `Record<string, string | string[]>` and becomes the single source of truth for both Fill-populated and manually-picked values.

**Tech Stack:** FastAPI (worker), Next.js 16 + React 19 + TypeScript (gui) — same stack as the existing Cinema page, no new dependencies.

## Global Constraints

- No changes to `worker/app/cineprompt/vocab.py`, `assemble.py`, `resolve.py`, `fill.py`, or the vocabulary data files (`data/base.json`, `data/lamka.json`). This plan only adds a route that reads from them.
- `build_prompt`'s contract is unchanged: it already accepts a field value as either a plain string or a list (`assemble.py`'s `nl_join` handles both), so no backend change is needed to support multi-select.
- A field with zero selected values (empty array after removing the last chip) must not appear in `fields` at all — an unset field must not reach `build_prompt`, matching `assemble.py`'s existing prune-of-empty-fields behavior.
- Sections with no in-scope fields for the current `mode`/`level` are omitted from `/cineprompt/vocab`'s response entirely, not returned as empty objects.
- No visual/aesthetic design in this plan (colors, spacing, chip styling, collapse animation) — functional structure only, reusing the same Tailwind/CSS-variable tokens already in the page (`--surface-deck`, `--muted`, `--border`, matching the existing Fields/Prompt/Generate sections).

---

### Task 1: Route — `GET /cineprompt/vocab`

**Files:**
- Modify: `worker/app/routes.py`
- Test: `worker/tests/test_routes_cineprompt.py`

**Interfaces:**
- Consumes: `app.cineprompt.assemble.SECTIONS: dict[str, list[str]]`, `app.cineprompt.prompts.fields_in_scope(mode: str, level: str) -> list[str]`, `app.cineprompt.vocab.values_for(field: str) -> list[str]`, `app.cineprompt.vocab.is_free_text(field: str) -> bool`
- Produces: route `GET /cineprompt/vocab?mode=single&level=complex` → `{section_name: {field_name: {values: string[], free_text: bool}}}`

- [ ] **Step 1: Write the failing test**

Append to `worker/tests/test_routes_cineprompt.py`:

```python
def test_vocab_returns_all_eight_sections_at_defaults():
    resp = client.get("/cineprompt/vocab")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "STYLE", "SUBJECT", "ACTIONS", "ENVIRONMENT",
        "CINEMATOGRAPHY", "PALETTE", "DIALOGUE", "SOUND",
    }


def test_vocab_enum_field_lists_real_values():
    resp = client.get("/cineprompt/vocab")
    body = resp.json()
    genre = body["STYLE"]["genre"]
    assert genre["free_text"] is False
    assert "action" in genre["values"]
    assert len(genre["values"]) > 1


def test_vocab_free_text_field_is_marked():
    resp = client.get("/cineprompt/vocab")
    body = resp.json()
    dialogue = body["DIALOGUE"]["dialogue"]
    assert dialogue["free_text"] is True
    assert dialogue["values"] == []


def test_vocab_respects_mode_and_level_query_params():
    resp = client.get("/cineprompt/vocab?mode=single&level=simple")
    body = resp.json()
    # "dialogue" is not in prompts.SIMPLE_FIELDS, so at level=simple it must
    # be absent from the response (either DIALOGUE is omitted entirely, or
    # present without a "dialogue" key) — this proves the query params
    # actually reach fields_in_scope rather than always returning defaults.
    if "DIALOGUE" in body:
        assert "dialogue" not in body["DIALOGUE"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_routes_cineprompt.py -k vocab -v`
Expected: FAIL, 404 (route doesn't exist yet)

- [ ] **Step 3: Implement**

Add to `worker/app/routes.py`, directly after `cineprompt_history` (~line 469, before `__all__`):

```python
@router.get("/cineprompt/vocab")
async def cineprompt_vocab(mode: str = "single", level: str = "complex") -> dict:
    """Section -> field -> {values, free_text}, filtered to what's in scope
    for (mode, level) — the same filter Fill's system prompt catalogue uses,
    so the manual picker and the AI-fill shortcut always agree on what's
    pickable. A section with nothing in scope is omitted, not emitted empty.
    """
    from app.cineprompt import assemble, prompts, vocab

    in_scope = set(prompts.fields_in_scope(mode, level))
    result: dict[str, dict] = {}
    for section, section_fields in assemble.SECTIONS.items():
        fields_here = [f for f in section_fields if f in in_scope]
        if not fields_here:
            continue
        result[section] = {
            field: {"values": vocab.values_for(field), "free_text": vocab.is_free_text(field)}
            for field in fields_here
        }
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_routes_cineprompt.py -k vocab -v`
Expected: PASS, 4 tests

- [ ] **Step 5: Run the full cineprompt route suite**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_routes_cineprompt.py -v`
Expected: PASS, all tests (existing 15 + 4 new = 19)

- [ ] **Step 6: Commit**

```powershell
cd "F:\Content Creation Project"
git add worker/app/routes.py worker/tests/test_routes_cineprompt.py
git commit -m "feat(cineprompt): GET /cineprompt/vocab route"
```

---

### Task 2: Frontend — widen `fields` state to support multi-select

**Files:**
- Modify: `gui/src/app/cinema/page.tsx:6` (the `FieldState` type), and every call site that reads/writes `fields`

**Interfaces:**
- Produces: `type FieldState = Record<string, string | string[]>`, plus a helper `fieldDisplayValue(value: string | string[]) -> string` for rendering a field's current value as a single line of text (used by the existing per-field `<input>` editor, unchanged in this task)

This task is a type-and-render-safety task with no new UI — it makes the state shape ready for Task 3's picker without changing what's visible on screen yet. The existing Fields section (the `<input>` list Fill populates) must keep working exactly as it does today; the only change is that a field's stored value can now legitimately be an array, and the existing render code must not crash when it is.

- [ ] **Step 1: Widen the type and add the display helper**

In `gui/src/app/cinema/page.tsx`, change line 6:

```tsx
type FieldState = Record<string, string | string[]>;
```

Add a helper function near the top of the file, after the `MODELS` constant (~line 10):

```tsx
function fieldDisplayValue(value: string | string[]): string {
  return Array.isArray(value) ? value.join(", ") : value;
}
```

- [ ] **Step 2: Update the existing Fields `<input>` render to use the helper**

The existing render at lines 230-238 does `value={value}` directly on an `<input>`, which breaks if `value` is now an array (React would throw — an `<input>`'s `value` prop must be a string). Change:

```tsx
              {Object.entries(fields).map(([key, value]) => (
                <label key={key} className="text-xs text-[var(--muted)]">
                  {key}
                  <input
                    value={value}
                    onChange={(e) => updateField(key, e.target.value)}
                    className="mt-1 min-h-9 w-full rounded-lg border border-border bg-[var(--surface-recessed)] px-2 text-sm text-foreground"
                  />
                </label>
              ))}
```

to:

```tsx
              {Object.entries(fields).map(([key, value]) => (
                <label key={key} className="text-xs text-[var(--muted)]">
                  {key}
                  <input
                    value={fieldDisplayValue(value)}
                    onChange={(e) => updateField(key, e.target.value)}
                    className="mt-1 min-h-9 w-full rounded-lg border border-border bg-[var(--surface-recessed)] px-2 text-sm text-foreground"
                  />
                </label>
              ))}
```

`updateField`'s signature (`(key: string, value: string) => void`, ~line 186) is unchanged — typing into this `<input>` always sets a plain string, which is valid under the widened `FieldState` type. This preserves today's editing behavior exactly; only the *display* of an array-valued field (which can only happen after Task 3 ships) changes to a joined string.

- [ ] **Step 3: Verify it builds**

Run:
```powershell
cd "F:\Content Creation Project\gui"
npm run build
```
Expected: build succeeds, no TypeScript errors.

- [ ] **Step 4: Manual smoke check**

With the worker running, open `/cinema`, type a description, click Fill, confirm the Fields section still populates and each field is still editable exactly as before (this task changes no behavior for the Fill path — it only makes the type able to hold more).

- [ ] **Step 5: Commit**

```powershell
cd "F:\Content Creation Project"
git add gui/src/app/cinema/page.tsx
git commit -m "feat(cineprompt): widen field state to support multi-select values"
```

---

### Task 3: Frontend — vocabulary browser (picker UI)

**Files:**
- Modify: `gui/src/app/cinema/page.tsx`

**Interfaces:**
- Consumes: `GET /api/cineprompt/vocab?mode=...&level=...` → `{section: {field: {values: string[], free_text: bool}}}` (Task 1), `FieldState`, `fieldDisplayValue` (Task 2)
- Produces: new component state `vocabData: Record<string, Record<string, {values: string[], free_text: boolean}>>`, new function `toggleChip(field: string, value: string): void`

- [ ] **Step 1: Add vocab-fetching state and effect**

Add to the component's state declarations, after the existing `history` state (~line 30):

```tsx
  const [vocabData, setVocabData] = useState<
    Record<string, Record<string, { values: string[]; free_text: boolean }>>
  >({});
```

Add a new `useEffect` after the existing mount-time `useEffect` (~line 36), so it re-fetches whenever `mode` or `level` changes:

```tsx
  useEffect(() => {
    fetch(`/api/cineprompt/vocab?mode=${mode}&level=${level}`)
      .then((res) => (res.ok ? res.json() : {}))
      .then(setVocabData)
      .catch(() => {
        // The picker is additive — Fill/Build/Generate stay usable if this fails.
      });
  }, [mode, level]);
```

- [ ] **Step 2: Add the chip-toggle handler**

Add near `updateField` (~line 186):

```tsx
  function toggleChip(field: string, value: string) {
    setVideoUrl(null);
    setFields((prev) => {
      const current = prev[field];
      const currentArray = Array.isArray(current) ? current : current ? [current] : [];
      const next = currentArray.includes(value)
        ? currentArray.filter((v) => v !== value)
        : [...currentArray, value];
      const updated = { ...prev };
      if (next.length === 0) {
        delete updated[field];
      } else {
        updated[field] = next;
      }
      return updated;
    });
  }

  function isChipActive(field: string, value: string): boolean {
    const current = fields[field];
    if (Array.isArray(current)) return current.includes(value);
    return current === value;
  }

  function updateFreeTextField(field: string, value: string) {
    setVideoUrl(null);
    setFields((prev) => {
      const updated = { ...prev };
      if (value.trim().length === 0) {
        delete updated[field];
      } else {
        updated[field] = value;
      }
      return updated;
    });
  }
```

- [ ] **Step 3: Render the vocabulary browser**

Insert a new section into the JSX between the description/Fill `<section>` (ends ~line 224) and the `{Object.keys(fields).length > 0 && (...)}` Fields section (~line 226):

```tsx
        {Object.keys(vocabData).length > 0 && (
          <section className="rounded-xl border border-border bg-[var(--surface-deck)] p-4 space-y-4">
            <h2 className="text-sm font-semibold">Browse fields</h2>
            {Object.entries(vocabData).map(([section, sectionFields]) => (
              <details key={section} open className="space-y-2">
                <summary className="cursor-pointer text-xs font-semibold uppercase text-[var(--muted)]">
                  {section}
                </summary>
                <div className="space-y-3 pt-2">
                  {Object.entries(sectionFields).map(([field, { values, free_text }]) => (
                    <div key={field}>
                      <p className="text-xs text-[var(--muted)]">{field}</p>
                      {free_text ? (
                        <textarea
                          value={typeof fields[field] === "string" ? (fields[field] as string) : ""}
                          onChange={(e) => updateFreeTextField(field, e.target.value)}
                          className="mt-1 min-h-16 w-full rounded-lg border border-border bg-[var(--surface-recessed)] p-2 text-sm text-foreground"
                        />
                      ) : (
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {values.map((value) => (
                            <button
                              key={value}
                              type="button"
                              aria-pressed={isChipActive(field, value)}
                              onClick={() => toggleChip(field, value)}
                              className={`rounded-full border px-2.5 py-1 text-xs ${
                                isChipActive(field, value)
                                  ? "border-primary bg-primary/10 text-foreground"
                                  : "border-border text-[var(--muted)]"
                              }`}
                            >
                              {value}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </details>
            ))}
          </section>
        )}

```

- [ ] **Step 4: Verify it builds**

Run:
```powershell
cd "F:\Content Creation Project\gui"
npm run build
```
Expected: build succeeds, no TypeScript errors.

- [ ] **Step 5: Manual smoke check**

With the worker running (`python run_worker.py`), open `/cinema`:
1. Confirm the "Browse fields" section appears with 8 open-by-default sections (STYLE, SUBJECT, ACTIONS, ENVIRONMENT, CINEMATOGRAPHY, PALETTE, DIALOGUE, SOUND), each listing clickable value chips for its enum fields and a textarea for free-text fields (e.g. DIALOGUE's `dialogue` field).
2. Click a `media_type` chip (e.g. `cinematic`), then a `genre` chip (e.g. `thriller`). `genre` is in `assemble.py`'s `MEDIA_ABSORBED` set and only renders once `media_type` is also set, so both are needed for step 8's prompt to be non-empty. Confirm each chip visually toggles active, and the same field appears in the Fields section below (Task 2's existing render) showing `thriller`.
3. Click a second chip in the `genre` field (e.g. `drama`). Confirm the Fields section now shows `thriller, drama` (via `fieldDisplayValue`'s join).
4. Click `thriller` again to deselect it. Confirm the Fields section now shows just `drama`.
5. Deselect `drama` too (the last remaining chip for that field). Confirm the field disappears from the Fields section entirely (proves the empty-array-deletes-the-key behavior).
6. Type a scene description, click Fill, confirm a Fill-populated field's chip(s) show as pre-toggled in the browser (proves picker and Fill share state correctly).
7. Change the `level` dropdown from `complex` to `simple`. Confirm the "Browse fields" section's field list shrinks (fewer fields per section, some sections may disappear) — proves the `useEffect` re-fetches on `level` change.
8. With `media_type` still set (re-pick it if step 4/5 cleared `genre`'s section state), click Build Prompt with at least one manually-picked field (no Fill). Confirm a prompt is produced — proves the picker's output reaches `build_prompt` correctly.

- [ ] **Step 6: Commit**

```powershell
cd "F:\Content Creation Project"
git add gui/src/app/cinema/page.tsx
git commit -m "feat(cineprompt): vocabulary browser picker on the Cinema page"
git push
```

---

## Verification

After Task 3:

```powershell
cd "F:\Content Creation Project\worker"
..\.venv\Scripts\python.exe -m pytest tests -q -m "not integration"
cd "F:\Content Creation Project\gui"
npm run build
```

Then run `START_LAMKA_LABS_STUDIO.bat`, open `/cinema`, and walk Task 3 Step 5's full manual checklist end to end.
