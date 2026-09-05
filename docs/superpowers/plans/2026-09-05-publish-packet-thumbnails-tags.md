# Publish Packet (Thumbnails + Tags) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every render ships two Gemini-art thumbnail variants and validated search tags in the manual-upload packet.

**Architecture:** Pure helpers first (tag parse/validate, art-prompt builder, HTML layouts), thin I/O wrappers behind the existing patch seams, wiring that preserves both standing rules — metadata fails loud pre-render, thumbnails never fail at all post-render. No migration: tags ride frontmatter → draft body jsonb → `upload.txt`.

**Tech Stack:** Python worker, `google-genai` (already a dependency), Playwright screenshot path (existing), pytest with seam patching (never the network).

**Spec:** `docs/superpowers/specs/2026-09-05-publish-packet-thumbnails-tags-design.md`

## Global Constraints

- Tests must not touch the network; patch `app.youtube.*` / `app.scene3d.backend.*` seams, never providers or subprocesses.
- Never fabricate metadata; `_require_metadata` raises pre-render, thumbnails degrade post-render.
- Nothing auto-publishes; no new publish path in this plan.
- PowerShell 5.1 for shells (no `&&`); pytest as `cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q`.
- The working tree may hold unrelated uncommitted work: stage ONLY your hunks (filtered patch / selective staging, never whole-file `git add` on mixed files). Do NOT push (Task 4 pushes once).

---

### Task 1: Shared Gemini byte-extraction helper

**Files:**
- Modify: `worker/app/scene3d/backend.py` (add helper, refactor `_generate_gemini_cinematic_image` to use it)
- Test: `worker/tests/test_scene3d_backend.py` (append)

**Interfaces:**
- Consumes: `google-genai` response object (duck-typed).
- Produces: `extract_gemini_image_bytes(response: object) -> bytes` — first `image/*` inline part; `str` data is base64-decoded; raises `RuntimeError("cinematic image provider returned no image data")` when absent.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_gemini_helper_decodes_base64_string_data():
    from types import SimpleNamespace

    from app.scene3d.backend import extract_gemini_image_bytes
    import base64

    part = SimpleNamespace(
        inline_data=SimpleNamespace(mime_type="image/png", data=base64.b64encode(b"png").decode())
    )
    response = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])
    assert extract_gemini_image_bytes(response) == b"png"


def test_gemini_helper_skips_non_image_parts():
    from types import SimpleNamespace

    from app.scene3d.backend import extract_gemini_image_bytes

    text = SimpleNamespace(text="hello")
    img = SimpleNamespace(inline_data=SimpleNamespace(mime_type="image/jpeg", data=b"jpg"))
    response = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[text, img]))])
    assert extract_gemini_image_bytes(response) == b"jpg"


def test_gemini_helper_raises_with_no_image_part():
    from types import SimpleNamespace

    import pytest

    from app.scene3d.backend import extract_gemini_image_bytes

    response = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[]))])
    with pytest.raises(RuntimeError, match="no image data"):
        extract_gemini_image_bytes(response)
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_scene3d_backend.py -q -k "gemini_helper"`
Expected: FAIL with `ImportError` / `AttributeError: extract_gemini_image_bytes`

- [ ] **Step 3: Implement the helper and refactor the keyframe path**

```python
def extract_gemini_image_bytes(response: object) -> bytes:
    """Return the first image part's bytes from a generate_content response."""
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        for part in getattr(candidates[0].content, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline is not None and str(getattr(inline, "mime_type", "")).startswith("image/"):
                data = inline.data
                return data if isinstance(data, bytes) else base64.b64decode(data)
    raise RuntimeError("cinematic image provider returned no image data")
```

Refactor `_generate_gemini_cinematic_image` to replace its inline loop with:

```python
    response = await asyncio.to_thread(call)
    destination.write_bytes(extract_gemini_image_bytes(response))
```

Nothing else in that function changes.

- [ ] **Step 4: Run backend tests green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_scene3d_backend.py -q`
Expected: PASS (pre-existing Gemini keyframe tests exercise the refactored path)

- [ ] **Step 5: Commit**

```bash
git add worker/app/scene3d/backend.py worker/tests/test_scene3d_backend.py
git commit -m "Share Gemini image-byte extraction between keyframes and thumbnails"
```

---

### Task 2: Tags plumbing (frontmatter to upload packet)

**Files:**
- Modify: `worker/app/youtube.py` (helpers, `_require_metadata`, prompt FORMAT, line-222 unpacking, `_write_upload_txt`, `_record_youtube_draft` body, generate-path call)
- Test: `worker/tests/test_publish_packet.py` (new), `worker/tests/test_upload_metadata.py` (update `test_valid_metadata_returns_both` to the 3-tuple)

**Interfaces:**
- Consumes: `frontmatter: dict[str, str]`, `channels.find_blocked_terms`.
- Produces: `parse_tags(frontmatter: dict) -> list[str]`; `validate_tags(tags: list[str], blocklist: tuple[str, ...]) -> list[str]` (violations, empty means pass); `_require_metadata(frontmatter, blocklist=()) -> tuple[str, str, list[str]]` — absent tags default to `[]` on every path; present-but-invalid tags raise pre-render.

- [ ] **Step 1: Write the failing tests** (new file `worker/tests/test_publish_packet.py`)

```python
"""Tags: pure parse/validate plus metadata integration. No network, no DB."""

import pytest

from app.youtube import parse_tags, validate_tags


def test_parse_tags_splits_and_cleans():
    assert parse_tags({"tags": "  markets, ETFs,markets ,"}) == ["markets", "ETFs"]


def test_parse_tags_absent_means_empty():
    assert parse_tags({}) == []
    assert parse_tags({"tags": "   "}) == []


def test_validate_tags_rejects_too_many():
    tags = [f"t{i}" for i in range(13)]
    assert any("12" in v for v in validate_tags(tags, ()))


def test_validate_tags_rejects_an_oversized_tag():
    assert validate_tags(["a" * 61], [])


def test_validate_tags_rejects_duplicates_case_insensitively():
    assert any("duplicate" in v for v in validate_tags(["Markets", "markets"], []))


def test_validate_tags_rejects_a_blocked_term():
    from app.channels import Channel

    finance = Channel(
        id="finance", display_name="Finance", voice_key="adult_male",
        script_prompt="A prompt.", extra_blocklist=("buy",),
    )
    violations = validate_tags(["buy signals"], finance.effective_blocklist)
    assert violations


def test_validate_tags_accepts_a_clean_list():
    assert validate_tags(["markets", "ETFs", "budget 2026"], ()) == []


def test_require_metadata_returns_tags():
    from app.youtube import _require_metadata

    title, description, tags = _require_metadata(
        {"title": "T", "description": "D", "tags": "a, b"}, ()
    )
    assert (title, description, tags) == ("T", "D", ["a", "b"])


def test_require_metadata_defaults_missing_tags_to_empty():
    from app.youtube import _require_metadata

    assert _require_metadata({"title": "T", "description": "D"})[2] == []


def test_require_metadata_raises_on_invalid_tags():
    from app.youtube import _require_metadata

    with pytest.raises(ValueError, match="tags"):
        _require_metadata({"title": "T", "description": "D", "tags": "buy signals"}, ("buy",))
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_publish_packet.py -q`
Expected: FAIL with `ImportError` (no `parse_tags` in `app.youtube` yet)

- [ ] **Step 3: Implement tag helpers and extend `_require_metadata`**

```python
MAX_TAGS = 12
MAX_TAG_LENGTH = 60


def parse_tags(frontmatter: dict[str, str]) -> list[str]:
    """Split the frontmatter `tags:` line into clean tags. Absent means []."""
    raw = (frontmatter.get("tags") or "")
    seen: set[str] = set()
    tags: list[str] = []
    for chunk in raw.split(","):
        tag = " ".join(chunk.split())
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            tags.append(tag)
    return tags
```

Note: `parse_tags` dedupes silently (a model repeating a tag is sloppy, not a
crime); `validate_tags` still flags duplicates for boards that bypass parsing.
Keep both behaviours exactly as written.

```python
def validate_tags(tags: list[str], blocklist: tuple[str, ...]) -> list[str]:
    """Return violations for a tag list. Empty means shippable."""
    violations: list[str] = []
    if len(tags) > MAX_TAGS:
        violations.append(f"expected at most {MAX_TAGS} tags, found {len(tags)}")
    lowered = [t.lower() for t in tags]
    if len(set(lowered)) != len(tags):
        violations.append("duplicate tags")
    for tag in tags:
        if len(tag) > MAX_TAG_LENGTH:
            violations.append(f"tag {tag!r} exceeds {MAX_TAG_LENGTH} characters")
        blocked = [
            term
            for term in blocklist
            if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", tag, re.IGNORECASE)
        ]
        if blocked:
            violations.append(f"tag {tag!r} contains blocked term(s): {', '.join(blocked)}")
    return violations
```

(Matching is deliberately the same `(?<!\w)…(?!\w)` rule `_blocked_storyboard_terms`
uses — and deliberately local: `channels.find_blocked_terms` exists only in
uncommitted work, so depending on it would ImportError on a clean checkout.)

Extend `_require_metadata`:

```python
def _require_metadata(
    frontmatter: dict[str, str], blocklist: tuple[str, ...] = ()
) -> tuple[str, str, list[str]]:
    ...
    tags = parse_tags(frontmatter)
    tag_violations = validate_tags(tags, blocklist)
    if tag_violations:
        raise ValueError(f"storyboard tags invalid: {'; '.join(tag_violations)}")
    return title, description, tags
```

(Keep the existing title/description logic byte-identical; append the tags block
before the return.)

- [ ] **Step 4: Wire tags through the pipeline**

a) Generation prompt FORMAT in `_generate_script_for_story`: after the
`description:` example line, add:

```
tags: "comma, separated, search, tags (at most 12)"
```

b) Line-222 unpacking plus blocklist:

```python
    title, description, tags = _require_metadata(frontmatter, channel.effective_blocklist)
```

c) `_write_upload_txt` gains keyword-only `tags: tuple[str, ...] | list[str] = ()`
and, after the DESCRIPTION block:

```python
    if tags:
        lines += [
            "TAGS",
            "----",
            ", ".join(tags),
            "",
        ]
```

d) `_record_youtube_draft` gains keyword-only `tags: tuple[str, ...] | list[str] = ()`
and the body dict gains `"tags": list(tags)`. The generate-path call passes
`tags=tags`.

e) Update `test_valid_metadata_returns_both` in `test_upload_metadata.py` to the
3-tuple:

```python
def test_valid_metadata_returns_all_three():
    from app.youtube import _require_metadata

    assert _require_metadata({"title": "T", "description": "D"}) == ("T", "D", [])
```

f) Extend the prompt-content test in `test_youtube.py`
(`test_script_prompt_carries_the_hook_and_chapter_contract`) with:

```python
    assert "tags" in source.lower()
```

- [ ] **Step 5: Run tag suites green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_publish_packet.py tests/test_upload_metadata.py tests/test_youtube.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add worker/app/youtube.py worker/tests/test_publish_packet.py worker/tests/test_upload_metadata.py worker/tests/test_youtube.py
git commit -m "Plumb validated search tags from frontmatter to upload packet"
```

---

### Task 3: A/B Gemini-art thumbnails

**Files:**
- Modify: `worker/app/youtube.py` (replace `_generate_thumbnail` with the variant pipeline + wiring)
- Test: `worker/tests/test_publish_packet.py` (append), `worker/tests/test_youtube.py` + `worker/tests/test_generation_resilience.py` (rename `_generate_thumbnail` patches)

**Interfaces:**
- Consumes: `extract_gemini_image_bytes` (Task 1), `GEMINI_IMAGE_MODEL`, parsed board (title, Scene-1 voiceover, direction).
- Produces: `build_thumbnail_art_prompt(*, title, hook, bible, mood) -> str` (pure); `_thumbnail_html(*, layout, title, background: Path | None) -> str` (pure); `build_thumbnail_variants(*, title, hook, bible, video_dir) -> dict[str, Path]` — never raises; returns whichever of `thumbnail-a.jpg` / `thumbnail-b.jpg` got built (possibly neither).

- [ ] **Step 1: Write the failing tests** (append to `worker/tests/test_publish_packet.py`)

```python
def test_art_prompt_carries_title_hook_and_bible_and_bans_text():
    from app.youtube import build_thumbnail_art_prompt

    prompt = build_thumbnail_art_prompt(title="T", hook="H", bible="B", mood="calm")
    assert "T" in prompt and "H" in prompt and "B" in prompt
    assert "no words" in prompt.lower()
    assert "16:9" in prompt


def test_art_prompt_moods_differ_between_variants():
    from app.youtube import build_thumbnail_art_prompt

    a = build_thumbnail_art_prompt(title="T", hook="H", bible="B", mood="calm daylight")
    b = build_thumbnail_art_prompt(title="T", hook="H", bible="B", mood="dramatic dusk")
    assert a != b


def test_thumbnail_layouts_differ():
    from app.youtube import _thumbnail_html

    assert _thumbnail_html(layout="top-band", title="T", background=None) != _thumbnail_html(
        layout="bottom-band", title="T", background=None
    )


def test_thumbnail_html_embeds_the_title():
    from app.youtube import _thumbnail_html

    assert "My Title" in _thumbnail_html(layout="top-band", title="My Title", background=None)
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_publish_packet.py -q -k "art_prompt or thumbnail_layouts or embeds_the_title"`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement the pure builders**

```python
def build_thumbnail_art_prompt(*, title: str, hook: str, bible: str, mood: str) -> str:
    """Background-art prompt for one thumbnail variant. Never any text."""
    return f"""Create one original 16:9 landscape YouTube thumbnail background for a finance education video.

VIDEO TITLE: {title}
HOOK: {hook}
WORLD BIBLE: {bible or "Warm stylized 3D animated-feature look, miniature-scale finance world."}
MOOD: {mood}

One decisive cinematic moment, premium stylized 3D render, strong readable silhouette, uncluttered
negative space across the full upper third for a title band. Absolutely no words, letters, numbers,
tickers, logos, watermarks, UI, or subtitles anywhere in the image."""
```

`_thumbnail_html(*, layout: str, title: str, background: Path | None) -> str`:
two 1280×720 templates. `top-band`: title band across the top third over the
background (or legacy gradient when `background is None`); `bottom-band`:
title low-third plus badge. When `background` is given, emit
`<img src="file:///{background.as_posix()}">` full-bleed beneath the band;
`{title}` HTML-escaped via `html.escape`. Raise `ValueError` on any other layout.

- [ ] **Step 4: Implement art generation, composition, and the builder**

```python
async def _generate_gemini_thumbnail_art(*, prompt: str, destination: Path) -> None:
    """Paint one thumbnail background with the keyframe image model."""
    from google import genai
    from google.genai import types

    from app.scene3d.backend import GEMINI_IMAGE_MODEL, extract_gemini_image_bytes

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    def call():
        return client.models.generate_content(
            model=GEMINI_IMAGE_MODEL,
            contents=[prompt],
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )

    response = await asyncio.to_thread(call)
    destination.write_bytes(extract_gemini_image_bytes(response))
```

Reuse the existing Playwright screenshot helper shape for composition:
`_compose_thumbnail(*, layout, title, background, output)` writes
`_thumbnail_html(...)` to a temp file and screenshots it to `output`
(mirror `_generate_thumbnail`'s current body, swapping the inline HTML for
the `_thumbnail_html` call).

```python
_THUMBNAIL_VARIANTS = (
    ("a", "top-band", "calm daylight"),
    ("b", "bottom-band", "dramatic dusk"),
)


async def build_thumbnail_variants(*, title: str, hook: str, bible: str, video_dir: Path) -> dict[str, Path]:
    """Build thumbnail-a/b.jpg. Best-effort per variant: art failure falls back
    to the legacy card, and a variant that still fails is skipped. Never raises."""
    built: dict[str, Path] = {}
    for suffix, layout, mood in _THUMBNAIL_VARIANTS:
        output = video_dir / f"thumbnail-{suffix}.jpg"
        try:
            try:
                art = video_dir / f"thumbnail-{suffix}-art.png"
                await _generate_gemini_thumbnail_art(
                    prompt=build_thumbnail_art_prompt(title=title, hook=hook, bible=bible, mood=mood),
                    destination=art,
                )
                background: Path | None = art
            except Exception as exc:  # noqa: BLE001 — one bad variant must not kill the other
                log.warning("thumbnail_art_failed", variant=suffix, error=str(exc))
                background = None
            await _compose_thumbnail(layout=layout, title=title, background=background, output=output)
            built[suffix] = output
        except Exception as exc:  # noqa: BLE001 — thumbnails never block the draft
            log.warning("thumbnail_variant_failed", variant=suffix, error=str(exc))
    if not built:
        log.warning("thumbnail_generation_failed", reason="no variant built")
    return built
```

`os`, `asyncio`, `log`, `Path` are already imported in `youtube.py`. Delete
`_generate_thumbnail` (its body moves into `_compose_thumbnail`).

- [ ] **Step 5: Wire the variants into the pipeline and update old patches**

Replace the `thumbnail_path` block (`youtube.py`, the `if not thumbnail_path.exists()`
best-effort section) with:

```python
    await build_thumbnail_variants(
        title=title,
        hook=(board.frames[0].voiceover if board.frames else title),
        bible=board.direction,
        video_dir=video_dir,
    )
```

`board` is in scope (parsed pre-render). No `if not exists` guard: variants are
cheap metadata, and a re-run should refresh them. No return-value check: the
builder never raises and the draft records regardless.

Rename every `app.youtube._generate_thumbnail` patch to
`app.youtube.build_thumbnail_variants` (7 decorators in `test_youtube.py`,
2 context managers in `test_generation_resilience.py`); keep parameter names
(`mock_thumb`, `thumb`) untouched. Rewrite
`test_thumbnail_failure_still_records_the_draft` to exercise the real builder:

```python
    thumb = AsyncMock(side_effect=RuntimeError("gemini down"))

    with patch("app.youtube.VIDEOS_DIR", tmp_path), \
            patch("app.channels.resolve", AsyncMock(return_value=FINANCE)), \
            patch("app.youtube._generate_gemini_thumbnail_art", thumb), \
            patch("app.youtube._compose_thumbnail", AsyncMock(side_effect=FileNotFoundError("npx playwright not found"))):
        draft_id = await youtube.generate_youtube_video(
            story_id=story_id, channel_id="finance", upload_preference="manual"
        )

    assert draft_id is not None
    mock_record.assert_called_once()
    assert (tmp_path / f"story-{story_id}" / "upload.txt").exists()
```

(Drop the old `thumb.assert_awaited_once()` — with two variants the art seam
is awaited twice. Assert `thumb.await_count == 2` instead.)

- [ ] **Step 6: Append variant-fallback tests** (to `worker/tests/test_publish_packet.py`)

```python
@pytest.mark.asyncio
async def test_variant_falls_back_to_legacy_card_when_art_fails(tmp_path):
    from unittest.mock import AsyncMock, patch

    from app.youtube import build_thumbnail_variants

    composed = []

    async def fake_compose(*, layout, title, background, output):
        composed.append((layout, background))
        output.write_bytes(b"jpg")

    with patch("app.youtube._generate_gemini_thumbnail_art", AsyncMock(side_effect=RuntimeError("down"))), \
            patch("app.youtube._compose_thumbnail", AsyncMock(side_effect=fake_compose)):
        built = await build_thumbnail_variants(title="T", hook="H", bible="B", video_dir=tmp_path)

    assert set(built) == {"a", "b"}
    assert all(background is None for _, background in composed)


@pytest.mark.asyncio
async def test_builder_never_raises_when_everything_fails(tmp_path):
    from unittest.mock import AsyncMock, patch

    from app.youtube import build_thumbnail_variants

    with patch("app.youtube._generate_gemini_thumbnail_art", AsyncMock(side_effect=RuntimeError("down"))), \
            patch("app.youtube._compose_thumbnail", AsyncMock(side_effect=FileNotFoundError("no playwright"))):
        assert await build_thumbnail_variants(title="T", hook="H", bible="B", video_dir=tmp_path) == {}
```

(`tmp_path` here is the real pytest fixture — these tests never touch the pipeline.)

- [ ] **Step 7: Run thumbnail suites green**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_publish_packet.py tests/test_youtube.py tests/test_generation_resilience.py tests/test_upload_metadata.py tests/test_scene3d_backend.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add worker/app/youtube.py worker/app/scene3d/backend.py worker/tests/test_publish_packet.py worker/tests/test_youtube.py worker/tests/test_generation_resilience.py
git commit -m "Add A-B Gemini-art thumbnails and tag validation to publish packet"
```

---

### Task 4: Full verification + record + push

**Files:**
- Modify: `PROGRESS.md` (decision #77 + anything the run surfaced)

**Interfaces:** none (verification + docs).

- [ ] **Step 1: Run the affected suites**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_publish_packet.py tests/test_youtube.py tests/test_generation_resilience.py tests/test_upload_metadata.py tests/test_scene3d_backend.py tests/test_storyboard.py tests/test_score.py tests/test_channels.py tests/test_llm_router.py tests/test_script_quality.py -q`
Expected: PASS. (DB-backed tests need local Postgres; without it they error — pre-existing and expected, unrelated to this plan. Do not run the full DB suite mid-render.)

- [ ] **Step 2: Record the decision in PROGRESS.md**

```
| 77 | Publish packet carries A-B thumbnails + validated tags; thumbnails best-effort, tags fail-loud | piece-2 | Model paints backgrounds only, title stays in template overlay; per-variant fallback, never blocks the draft. Tags: frontmatter → draft body jsonb → upload.txt, no migration. |
```

- [ ] **Step 3: Commit and push**

```bash
git add PROGRESS.md
git commit -m "Record publish-packet decision"
git push
```
