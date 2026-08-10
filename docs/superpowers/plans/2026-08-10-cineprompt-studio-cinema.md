# Studio Cinema Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `/cinema` Studio page where a user types a scene description, the CinePrompt engine turns it into an editable cinematography prompt, and the user generates video against fal.run with their own API key — with results saved locally and browsable as history.

**Architecture:** Four new FastAPI routes wrap the existing `app.cineprompt` engine (fill/build, both stateless) and a new Postgres table (save/history, stateful). The fal.run video call is entirely client-side in the browser — the worker never receives the user's API key, only the resulting video URL, which it downloads and persists.

**Tech Stack:** FastAPI + psycopg (worker), Next.js 16 + React 19 + Tailwind (gui), Postgres (`cineprompt_generations` table), `httpx` for the server-side video download.

## Global Constraints

- The worker never receives, logs, or stores the user's fal.run API key. It is read from `localStorage` in the browser and sent only to `queue.fal.run`.
- No task in this plan modifies `worker/app/cineprompt/` — the engine (297 passing tests) is consumed as-is via `fill_from_scene`, `build_prompt`.
- `FillError` from the engine surfaces as HTTP 422 with the error message verbatim — no fabricated field-state ever reaches the client.
- A `/cineprompt/save` call that fails to download the video must not leave a DB row with a broken `local_path`, and must not leave a partial file on disk.
- Tests for `/cineprompt/fill` and `/cineprompt/build` never reach Ollama, DeepSeek, or a network — `fill_from_scene`/`build_prompt` are patched directly, per this repo's existing rule (`test_routes_channel.py`'s pattern: `unittest.mock.patch` + `AsyncMock` on a `fastapi.testclient.TestClient`).
- DB-touching tests are integration tests (`pytestmark = pytest.mark.integration`, the `db` fixture from `tests/conftest.py`) and require local Postgres — consistent with the rest of `tests/test_db.py`. Do not run these while an end-to-end render is in flight (truncates tables).

---

### Task 1: Migration — `cineprompt_generations` table

**Files:**
- Create: `supabase/migrations/011_cineprompt_generations.sql`

**Interfaces:**
- Produces: table `cineprompt_generations(id uuid pk, description text, mode text, model text, fields jsonb, prompt text, video_url text, local_path text, created_at timestamptz)`

- [ ] **Step 1: Write the migration**

```sql
-- supabase/migrations/011_cineprompt_generations.sql
-- Studio Cinema page: one row per saved CinePrompt + fal.run generation.
-- video_url is the original fal.run source, kept only for provenance — it
-- may 404 later since fal.run retention isn't guaranteed. local_path is
-- authoritative for playback.

CREATE TABLE IF NOT EXISTS cineprompt_generations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    description TEXT NOT NULL,
    mode TEXT NOT NULL,
    model TEXT NOT NULL,
    fields JSONB NOT NULL,
    prompt TEXT NOT NULL,
    video_url TEXT NOT NULL,
    local_path TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cineprompt_generations_created_at
    ON cineprompt_generations (created_at DESC);
```

- [ ] **Step 2: Apply it to the local database**

Run:
```powershell
cd "F:\Content Creation Project"
docker exec -i fce-db psql -U postgres -d fce -f - < supabase/migrations/011_cineprompt_generations.sql
```
Expected: `CREATE TABLE`, `CREATE INDEX` (or `NOTICE: relation already exists, skipping` on a re-run — the `IF NOT EXISTS` guards make this idempotent).

Note: no `-p` flag — `docker exec` runs `psql` inside the container, where Postgres always listens on its own internal 5432 regardless of the host-side port mapping in `docker-compose.yml`. (5433 is a VPS-deploy-only convention from a different Postgres instance on that host; it does not apply here.) If the container name differs from `fce-db`, check `docker ps` first — don't guess.

- [ ] **Step 3: Verify the schema**

Run:
```powershell
docker exec -i fce-db psql -U postgres -d fce -c "\d cineprompt_generations"
```
Expected: lists all 8 columns and the `idx_cineprompt_generations_created_at` index.

- [ ] **Step 4: Commit**

```powershell
cd "F:\Content Creation Project"
git add supabase/migrations/011_cineprompt_generations.sql
git commit -m "feat(cineprompt): add cineprompt_generations table"
```

---

### Task 2: DB layer — save and fetch generations

**Files:**
- Modify: `worker/app/db.py` (append near `get_drafts`, ~line 634)
- Test: `worker/tests/test_db.py` (append)

**Interfaces:**
- Consumes: `get_pool()`, `_fetchone(conn, query, *params)`, `_fetchall(conn, query, *params)` — all already defined in `db.py`
- Produces: `async def save_cineprompt_generation(description: str, mode: str, model: str, fields: dict, prompt: str, video_url: str, local_path: str) -> uuid.UUID`, `async def get_cineprompt_history(limit: int = 50) -> list[dict]`

- [ ] **Step 1: Write the failing tests**

Append to `worker/tests/test_db.py`:

```python
class TestCinepromptGenerations:
    @pytest.mark.asyncio
    async def test_save_returns_a_new_id(self, db):
        from app.db import save_cineprompt_generation

        gen_id = await save_cineprompt_generation(
            description="a woman in a cramped office at dawn",
            mode="single",
            model="veo",
            fields={"genre": "thriller", "shot_type": "wide shot"},
            prompt="Wide shot. A woman in a cramped office. Dawn.",
            video_url="https://fal.media/files/abc/output.mp4",
            local_path="videos/cineprompt/abc.mp4",
        )
        assert isinstance(gen_id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_history_returns_newest_first(self, db):
        from app.db import get_cineprompt_history, save_cineprompt_generation

        first = await save_cineprompt_generation(
            description="first", mode="single", model="veo", fields={},
            prompt="first prompt", video_url="https://fal.media/1.mp4",
            local_path="videos/cineprompt/1.mp4",
        )
        second = await save_cineprompt_generation(
            description="second", mode="single", model="veo", fields={},
            prompt="second prompt", video_url="https://fal.media/2.mp4",
            local_path="videos/cineprompt/2.mp4",
        )

        history = await get_cineprompt_history()
        ids = [row["id"] for row in history]
        assert ids.index(second) < ids.index(first)

    @pytest.mark.asyncio
    async def test_history_respects_limit(self, db):
        from app.db import get_cineprompt_history, save_cineprompt_generation

        for i in range(3):
            await save_cineprompt_generation(
                description=f"gen {i}", mode="single", model="veo", fields={},
                prompt=f"prompt {i}", video_url=f"https://fal.media/{i}.mp4",
                local_path=f"videos/cineprompt/{i}.mp4",
            )

        history = await get_cineprompt_history(limit=2)
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_saved_fields_round_trip_as_dict(self, db):
        from app.db import get_cineprompt_history, save_cineprompt_generation

        await save_cineprompt_generation(
            description="x", mode="single", model="veo",
            fields={"genre": "thriller", "dof": "deep focus"},
            prompt="p", video_url="https://fal.media/x.mp4",
            local_path="videos/cineprompt/x.mp4",
        )
        history = await get_cineprompt_history()
        assert history[0]["fields"] == {"genre": "thriller", "dof": "deep focus"}
```

Add `pytestmark = pytest.mark.integration` is already present at module level in `test_db.py` — no change needed there. Add `import uuid` if not already imported (it already is, per the file's existing `_seed_source` helper).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_db.py -k Cineprompt -v`
Expected: FAIL, `ImportError: cannot import name 'save_cineprompt_generation'`

- [ ] **Step 3: Implement**

Append to `worker/app/db.py` after `get_drafts` (~line 634):

```python
async def save_cineprompt_generation(
    description: str, mode: str, model: str, fields: dict,
    prompt: str, video_url: str, local_path: str,
) -> uuid.UUID:
    """Persist one CinePrompt + fal.run generation. Called only after the
    video has already been downloaded to `local_path` — this never runs
    for a failed download."""
    pool = await get_pool()
    async with pool.connection() as conn:
        row = await _fetchone(
            conn,
            """
            INSERT INTO cineprompt_generations
                (description, mode, model, fields, prompt, video_url, local_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            description, mode, model, json.dumps(fields), prompt, video_url, local_path,
        )
        return row["id"]


async def get_cineprompt_history(limit: int = 50) -> list[dict[str, Any]]:
    """Most recent saved generations, newest first. No pagination in v1."""
    pool = await get_pool()
    async with pool.connection() as conn:
        return await _fetchall(
            conn,
            """
            SELECT id, description, mode, model, fields, prompt,
                   video_url, local_path, created_at
            FROM cineprompt_generations
            ORDER BY created_at DESC
            LIMIT %s
            """,
            limit,
        )
```

Check the top of `worker/app/db.py` for an existing `import json` — `create_manual_story`'s neighbors in this file already serialize JSONB elsewhere (grep `json.dumps` in `db.py`); add the import only if it is missing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_db.py -k Cineprompt -v`
Expected: PASS, 4 tests. Requires local Postgres — if it errors with a connection failure, that's the expected "no local Postgres" case from `worker/CLAUDE.md`, not a code bug; verify with `docker ps` first.

- [ ] **Step 5: Commit**

```powershell
cd "F:\Content Creation Project"
git add worker/app/db.py worker/tests/test_db.py
git commit -m "feat(cineprompt): db layer for saving and listing generations"
```

---

### Task 3: Route — `POST /cineprompt/fill`

**Files:**
- Modify: `worker/app/routes.py`
- Test: `worker/tests/test_routes_cineprompt.py` (new file)

**Interfaces:**
- Consumes: `app.cineprompt.fill_from_scene(description, mode, level, locked=None, escalate=True) -> dict`, `app.cineprompt.FillError`
- Produces: route `POST /cineprompt/fill`, request/response shape below

- [ ] **Step 1: Write the failing test**

```python
# worker/tests/test_routes_cineprompt.py
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.cineprompt import FillError
from app.main import app

client = TestClient(app)


def test_fill_returns_field_state():
    fake_fields = {"genre": "action", "mood": "nostalgic", "pacing": "slow motion"}
    with patch("app.cineprompt.fill_from_scene", AsyncMock(return_value=fake_fields)):
        resp = client.post(
            "/cineprompt/fill",
            json={"description": "a woman in a cramped office at dawn", "mode": "single", "level": "complex"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"fields": fake_fields}


def test_fill_error_returns_422_with_message():
    with patch(
        "app.cineprompt.fill_from_scene",
        AsyncMock(side_effect=FillError("scene-to-prompt failed: too few fields: 2 < 6")),
    ):
        resp = client.post(
            "/cineprompt/fill",
            json={"description": "x", "mode": "single", "level": "complex"},
        )
    assert resp.status_code == 422
    assert "too few fields" in resp.json()["detail"]


def test_fill_requires_description():
    resp = client.post("/cineprompt/fill", json={"mode": "single", "level": "complex"})
    assert resp.status_code == 422


def test_fill_passes_locked_fields_through():
    with patch("app.cineprompt.fill_from_scene", AsyncMock(return_value={})) as mock_fill:
        client.post(
            "/cineprompt/fill",
            json={
                "description": "a scene", "mode": "single", "level": "complex",
                "locked": {"camera_body": "shot on RED V-Raptor"},
            },
        )
    mock_fill.assert_awaited_once_with(
        "a scene", mode="single", level="complex", locked={"camera_body": "shot on RED V-Raptor"},
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_routes_cineprompt.py -v`
Expected: FAIL, 404 (route doesn't exist yet)

- [ ] **Step 3: Implement**

Add to `worker/app/routes.py`, after the `/config/{key}` routes (~line 362, before `__all__`):

```python
class CinepromptFillRequest(BaseModel):
    description: str = Field(min_length=1, max_length=5000)
    mode: str = "single"
    level: str = "complex"
    locked: dict | None = None


@router.post("/cineprompt/fill")
async def cineprompt_fill(req: CinepromptFillRequest) -> dict:
    """Scene description -> snapped field-state, via the CinePrompt engine."""
    from app.cineprompt import FillError, fill_from_scene

    try:
        fields = await fill_from_scene(
            req.description, mode=req.mode, level=req.level, locked=req.locked,
        )
    except FillError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"fields": fields}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_routes_cineprompt.py -v`
Expected: PASS, 4 tests

- [ ] **Step 5: Commit**

```powershell
cd "F:\Content Creation Project"
git add worker/app/routes.py worker/tests/test_routes_cineprompt.py
git commit -m "feat(cineprompt): POST /cineprompt/fill route"
```

---

### Task 4: Route — `POST /cineprompt/build`

**Files:**
- Modify: `worker/app/routes.py`
- Test: `worker/tests/test_routes_cineprompt.py`

**Interfaces:**
- Consumes: `app.cineprompt.build_prompt(state: dict) -> list[str]` (returns one string per resolved shot; `single` mode yields exactly one)
- Produces: route `POST /cineprompt/build`

- [ ] **Step 1: Write the failing test**

Append to `worker/tests/test_routes_cineprompt.py`:

```python
def test_build_returns_assembled_prompt():
    with patch("app.cineprompt.build_prompt", return_value=["Wide shot. A woman in a cramped office."]):
        resp = client.post(
            "/cineprompt/build",
            json={"mode": "single", "model": "veo", "fields": {"shot_type": "wide shot"}},
        )
    assert resp.status_code == 200
    assert resp.json() == {"prompt": "Wide shot. A woman in a cramped office."}


def test_build_requires_fields():
    resp = client.post("/cineprompt/build", json={"mode": "single", "model": "veo"})
    assert resp.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_routes_cineprompt.py -k build -v`
Expected: FAIL, 404

- [ ] **Step 3: Implement**

Add to `worker/app/routes.py`, directly after `cineprompt_fill`:

```python
class CinepromptBuildRequest(BaseModel):
    mode: str = "single"
    model: str = "universal"
    fields: dict


@router.post("/cineprompt/build")
async def cineprompt_build(req: CinepromptBuildRequest) -> dict:
    """Field-state -> assembled cinematography prompt text.

    `build_prompt` returns one string per resolved shot (multi/grid modes
    fan out); `single` mode — the only one Cinema v1 exposes — always
    resolves to exactly one, so [0] is safe.
    """
    from app.cineprompt import build_prompt

    prompts = build_prompt({"mode": req.mode, "model": req.model, "fields": req.fields})
    return {"prompt": prompts[0]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_routes_cineprompt.py -k build -v`
Expected: PASS, 2 tests

- [ ] **Step 5: Commit**

```powershell
cd "F:\Content Creation Project"
git add worker/app/routes.py worker/tests/test_routes_cineprompt.py
git commit -m "feat(cineprompt): POST /cineprompt/build route"
```

---

### Task 5: Route — `POST /cineprompt/save`

**Files:**
- Modify: `worker/app/routes.py`
- Test: `worker/tests/test_routes_cineprompt.py`

**Interfaces:**
- Consumes: `app.db.save_cineprompt_generation(...)` (Task 2), `_VIDEOS_DIR` (already defined in `routes.py:269`)
- Produces: route `POST /cineprompt/save`

This is the one route that touches the network (downloading the fal.run video) and the filesystem. Both are mocked in tests — no real HTTP call, no real file ever written by the test suite.

- [ ] **Step 1: Write the failing tests**

Append to `worker/tests/test_routes_cineprompt.py`:

```python
import uuid as uuid_module

import httpx


def test_save_downloads_video_and_returns_the_db_id(tmp_path, monkeypatch):
    """The response id must be the DB row's id, not the filename UUID.

    They are deliberately different values here — a real regression (routing
    the response through the filename UUID instead of the DB's returned id)
    would fail the `body["id"] == str(db_id)` assertion while still passing
    the file-write assertion, so this only catches the bug if the two are
    kept distinct.
    """
    monkeypatch.setattr("app.routes._VIDEOS_DIR", tmp_path)
    file_id = uuid_module.uuid4()
    db_id = uuid_module.uuid4()
    assert file_id != db_id

    async def fake_get(self, url, **kwargs):
        return httpx.Response(200, content=b"fake video bytes", request=httpx.Request("GET", url))

    with (
        patch("httpx.AsyncClient.get", fake_get),
        patch("app.db.save_cineprompt_generation", AsyncMock(return_value=db_id)),
        patch("uuid.uuid4", return_value=file_id),
    ):
        resp = client.post(
            "/cineprompt/save",
            json={
                "description": "a scene", "mode": "single", "model": "veo",
                "fields": {"genre": "action"}, "prompt": "A scene.",
                "video_url": "https://fal.media/files/abc/output.mp4",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(db_id)
    saved_path = tmp_path / "cineprompt" / f"{file_id}.mp4"
    assert saved_path.read_bytes() == b"fake video bytes"


def test_save_returns_502_on_download_failure_and_writes_no_row(tmp_path, monkeypatch):
    monkeypatch.setattr("app.routes._VIDEOS_DIR", tmp_path)

    async def fake_get(self, url, **kwargs):
        raise httpx.ConnectTimeout("timed out", request=httpx.Request("GET", url))

    with (
        patch("httpx.AsyncClient.get", fake_get),
        patch("app.db.save_cineprompt_generation", AsyncMock()) as mock_save,
    ):
        resp = client.post(
            "/cineprompt/save",
            json={
                "description": "a scene", "mode": "single", "model": "veo",
                "fields": {}, "prompt": "A scene.",
                "video_url": "https://fal.media/files/abc/output.mp4",
            },
        )
    assert resp.status_code == 502
    mock_save.assert_not_awaited()
    assert not (tmp_path / "cineprompt").exists() or not any((tmp_path / "cineprompt").iterdir())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_routes_cineprompt.py -k save -v`
Expected: FAIL, 404

- [ ] **Step 3: Implement**

Add to `worker/app/routes.py`, directly after `cineprompt_build`:

```python
class CinepromptSaveRequest(BaseModel):
    description: str = Field(min_length=1, max_length=5000)
    mode: str = "single"
    model: str = "universal"
    fields: dict
    prompt: str = Field(min_length=1)
    video_url: str = Field(min_length=1)


@router.post("/cineprompt/save")
async def cineprompt_save(req: CinepromptSaveRequest) -> dict:
    """Download the fal.run result and persist it.

    Write-then-insert, in that order: a DB row must never point at a file
    that doesn't exist. Any download failure cleans up the partial file
    and leaves no row at all, rather than a half-saved generation.

    The filename uses a locally-generated UUID chosen before the insert
    (the file must exist before the row can reference it). That UUID is
    NOT the row's primary key — `cineprompt_generations.id` defaults to
    `gen_random_uuid()`, generated independently inside Postgres. The
    response's `id` must be the value `save_cineprompt_generation`
    returns, not the filename UUID, or a later `GET /cineprompt/history`
    lookup by this id would never match the row this call just created.
    """
    from app.db import save_cineprompt_generation

    file_id = uuid.uuid4()
    dest_dir = _VIDEOS_DIR / "cineprompt"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{file_id}.mp4"

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(req.video_url)
            response.raise_for_status()
        dest_path.write_bytes(response.content)
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail=f"could not download video: {exc}") from exc

    gen_id = await save_cineprompt_generation(
        description=req.description,
        mode=req.mode,
        model=req.model,
        fields=req.fields,
        prompt=req.prompt,
        video_url=req.video_url,
        local_path=str(dest_path.relative_to(_VIDEOS_DIR.parent)),
    )
    return {"id": str(gen_id), "local_path": str(dest_path.relative_to(_VIDEOS_DIR.parent))}
```

Add `import httpx` to the top of `worker/app/routes.py` if it isn't already imported (check the existing import block at the top of the file — `youtube.py` already imports it, `routes.py` may not).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_routes_cineprompt.py -k save -v`
Expected: PASS, 2 tests

- [ ] **Step 5: Commit**

```powershell
cd "F:\Content Creation Project"
git add worker/app/routes.py worker/tests/test_routes_cineprompt.py
git commit -m "feat(cineprompt): POST /cineprompt/save route with atomic download"
```

---

### Task 6: Route — `GET /cineprompt/history`

**Files:**
- Modify: `worker/app/routes.py`
- Test: `worker/tests/test_routes_cineprompt.py`

**Interfaces:**
- Consumes: `app.db.get_cineprompt_history(limit: int = 50) -> list[dict]` (Task 2)
- Produces: route `GET /cineprompt/history`

- [ ] **Step 1: Write the failing test**

Append to `worker/tests/test_routes_cineprompt.py`:

```python
def test_history_returns_saved_generations():
    fake_row = {
        "id": uuid_module.uuid4(), "description": "a scene", "mode": "single",
        "model": "veo", "fields": {"genre": "action"}, "prompt": "A scene.",
        "video_url": "https://fal.media/x.mp4", "local_path": "videos/cineprompt/x.mp4",
        "created_at": "2026-08-10T00:00:00Z",
    }
    with patch("app.db.get_cineprompt_history", AsyncMock(return_value=[fake_row])):
        resp = client.get("/cineprompt/history")
    assert resp.status_code == 200
    assert resp.json()[0]["description"] == "a scene"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_routes_cineprompt.py -k history -v`
Expected: FAIL, 404

- [ ] **Step 3: Implement**

Add to `worker/app/routes.py`, directly after `cineprompt_save`:

```python
@router.get("/cineprompt/history")
async def cineprompt_history() -> list[dict]:
    """Most recent saved Cinema generations, newest first. No pagination in v1."""
    from app.db import get_cineprompt_history

    rows = await get_cineprompt_history()
    return [
        {**row, "id": str(row["id"]) if isinstance(row["id"], uuid.UUID) else row["id"]}
        for row in rows
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests/test_routes_cineprompt.py -v`
Expected: PASS, all 11 tests in the file

- [ ] **Step 5: Run the full worker test suite (non-DB)**

Run: `cd worker; ..\.venv\Scripts\python.exe -m pytest tests -q -m "not integration"`
Expected: no new failures beyond the pre-existing unrelated ones (`test_youtube_channel.py`'s research-sources guard, which predates this plan)

- [ ] **Step 6: Commit and push**

```powershell
cd "F:\Content Creation Project"
git add worker/app/routes.py worker/tests/test_routes_cineprompt.py
git commit -m "feat(cineprompt): GET /cineprompt/history route"
git push
```

Backend is now complete and independently testable end-to-end via curl/Postman against `python run_worker.py`, with no frontend required.

---

### Task 7: Frontend — Sidebar nav entry

**Files:**
- Modify: `gui/src/components/Sidebar.tsx`

**Interfaces:**
- Produces: a `/cinema` link in the nav, active-state highlighted like the other four

This task needs no visual-design pass — it's one array entry following the exact existing pattern of the other four.

- [ ] **Step 1: Add the nav item**

In `gui/src/components/Sidebar.tsx`, add `Clapperboard`'s sibling icon `Film` to the `lucide-react` import (line 5) and insert a new entry into `navItems` (line 11-17), between "Production" and "Drafts":

```tsx
import { BookOpen, Clapperboard, FileText, Film, Inbox, Settings } from "lucide-react";
```

```tsx
  const navItems = [
    { name: "Research", href: "/", icon: Inbox },
    { name: "Production", href: "/films", icon: Clapperboard },
    { name: "Cinema", href: "/cinema", icon: Film },
    { name: "Drafts", href: "/drafts", icon: FileText },
    { name: "Studio setup", href: "/settings", icon: Settings },
    { name: "Guide", href: "/docs", icon: BookOpen },
  ];
```

- [ ] **Step 2: Verify it renders**

Run: `cd gui; npm run build`
Expected: build succeeds (this is a static array change; there's no `/cinema` page yet, so the link will 404 until Task 8 — that's expected and fine for this task's scope).

- [ ] **Step 3: Commit**

```powershell
cd "F:\Content Creation Project"
git add gui/src/components/Sidebar.tsx
git commit -m "feat(cineprompt): add Cinema nav entry"
```

---

### Task 8: Frontend — Cinema page, fill/edit/build flow

**Files:**
- Create: `gui/src/app/cinema/page.tsx`

**Interfaces:**
- Consumes: `POST /api/cineprompt/fill` → `{fields: Record<string, string>}` or `{detail: string}` on 422; `POST /api/cineprompt/build` → `{prompt: string}` (both proxied to the worker by `next.config.ts`'s existing `/api/:path* -> 127.0.0.1:8000/:path*` rewrite)
- Produces: a working, functionally-complete but visually **unstyled-beyond-existing-tokens** page — Tailwind utility classes reusing the CSS variables already defined in `globals.css` (`--surface-deck`, `--muted`, `--border`, `--destructive`, matching `films/page.tsx`'s pattern), not a bespoke visual system. A dedicated visual-design pass is Task 10, gated on the `frontend-design` skill being active.

This task covers steps 1-3 of the design doc's 6-step interaction flow: description → fill → edit fields → build prompt. Steps 4-6 (BYOK generate, save, history) are Task 9.

- [ ] **Step 1: Write the page**

```tsx
// gui/src/app/cinema/page.tsx
"use client";

import { useState } from "react";
import { Loader2, Sparkles, Wand2 } from "lucide-react";

type FieldState = Record<string, string>;

const MODES = ["single", "fm_image"] as const;
const LEVELS = ["simple", "complex"] as const;
const MODELS = ["universal", "veo", "sora", "kling", "seedance", "grok", "ltx", "pixverse", "luma", "wan"] as const;

export default function CinemaPage() {
  const [description, setDescription] = useState("");
  const [mode, setMode] = useState<(typeof MODES)[number]>("single");
  const [level, setLevel] = useState<(typeof LEVELS)[number]>("complex");
  const [model, setModel] = useState<(typeof MODELS)[number]>("veo");

  const [fields, setFields] = useState<FieldState>({});
  const [prompt, setPrompt] = useState("");
  const [filling, setFilling] = useState(false);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFill() {
    setFilling(true);
    setError(null);
    try {
      const res = await fetch("/api/cineprompt/fill", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description, mode, level }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.detail ?? "Fill failed.");
        return;
      }
      setFields(body.fields);
      setPrompt("");
    } catch {
      setError("Could not reach the worker.");
    } finally {
      setFilling(false);
    }
  }

  async function handleBuild() {
    setBuilding(true);
    setError(null);
    try {
      const res = await fetch("/api/cineprompt/build", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, model, fields }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.detail ?? "Build failed.");
        return;
      }
      setPrompt(body.prompt);
    } catch {
      setError("Could not reach the worker.");
    } finally {
      setBuilding(false);
    }
  }

  function updateField(key: string, value: string) {
    setFields((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4 p-6">
        <header>
          <h1 className="text-lg font-semibold">Cinema</h1>
          <p className="text-sm text-[var(--muted)]">
            Describe a scene, let CinePrompt fill in the cinematography, then generate video.
          </p>
        </header>

        <section className="rounded-xl border border-border bg-[var(--surface-deck)] p-4 space-y-3">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="A woman in a cramped office at dawn, wide shot, tense..."
            className="min-h-24 w-full rounded-lg border border-border bg-[var(--surface-recessed)] p-3 text-sm text-foreground focus:border-primary focus:outline-none"
          />
          <div className="flex flex-wrap gap-3">
            <select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)} className="min-h-9 rounded-lg border border-border bg-[var(--surface-recessed)] px-2 text-sm">
              {MODES.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
            <select value={level} onChange={(e) => setLevel(e.target.value as typeof level)} className="min-h-9 rounded-lg border border-border bg-[var(--surface-recessed)] px-2 text-sm">
              {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
            <button
              onClick={handleFill}
              disabled={filling || description.trim().length === 0}
              className="ml-auto inline-flex min-h-9 items-center gap-2 rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {filling ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
              Fill
            </button>
          </div>
          {error && <p className="text-xs text-[var(--destructive)]">{error}</p>}
        </section>

        {Object.keys(fields).length > 0 && (
          <section className="rounded-xl border border-border bg-[var(--surface-deck)] p-4 space-y-3">
            <h2 className="text-sm font-semibold">Fields</h2>
            <div className="grid gap-2 sm:grid-cols-2">
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
            </div>
            <div className="flex items-center gap-3">
              <select value={model} onChange={(e) => setModel(e.target.value as typeof model)} className="min-h-9 rounded-lg border border-border bg-[var(--surface-recessed)] px-2 text-sm">
                {MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
              <button
                onClick={handleBuild}
                disabled={building}
                className="inline-flex min-h-9 items-center gap-2 rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-50"
              >
                {building ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                Build prompt
              </button>
            </div>
          </section>
        )}

        {prompt && (
          <section className="rounded-xl border border-border bg-[var(--surface-deck)] p-4">
            <h2 className="text-sm font-semibold">Prompt</h2>
            <p className="mt-2 text-sm">{prompt}</p>
          </section>
        )}
    </div>
  );
}
```

- [ ] **Step 2: Verify it builds and runs**

Run:
```powershell
cd "F:\Content Creation Project\gui"
npm run build
```
Expected: build succeeds with no TypeScript errors.

Then, with the worker running (`START_LAMKA_LABS_STUDIO.bat` or `cd worker; ..\.venv\Scripts\python.exe run_worker.py`), run `npm run dev` and open `http://localhost:3000/cinema`. Type a description, click Fill, confirm fields populate (or an error shows if Ollama/DeepSeek are unavailable — that's the engine's real gate behaving correctly, not a bug), edit a field, click Build prompt, confirm the assembled sentence appears.

- [ ] **Step 3: Commit**

```powershell
cd "F:\Content Creation Project"
git add gui/src/app/cinema/page.tsx
git commit -m "feat(cineprompt): Cinema page fill/edit/build flow"
```

---

### Task 9: Frontend — BYOK generate, save, and history

**Files:**
- Modify: `gui/src/app/cinema/page.tsx`

**Interfaces:**
- Consumes: `queue.fal.run`'s async queue API directly (client-side). Verified contract (docs.fal.ai, 2026-08-10): `POST https://queue.fal.run/{model_id}` with header `Authorization: Key $FAL_KEY` returns `{request_id, status_url, response_url, cancel_url, queue_position}`; poll `GET {status_url}?logs=1` until `{"status": "COMPLETED", ...}`; then `GET {response_url}` for the result, whose video-model output is `{"video": {"url": "..."}}` (model-specific — confirmed as the standard fal.run video-model shape, but re-check the specific `model_id` chosen at implementation time). `POST /api/cineprompt/save` → `{id: string, local_path: string}`, `GET /api/cineprompt/history` → array of saved-generation rows

This completes steps 4-6 of the design doc's interaction flow. **The fal.run key never appears in any `fetch` call to `/api/*`** — that's the one hard constraint this task must not violate.

- [ ] **Step 1: Add BYOK state, generate, save, and history to the page**

Add to `gui/src/app/cinema/page.tsx`, inside the `CinemaPage` component, after the existing state declarations:

```tsx
  const [falKey, setFalKey] = useState("");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState<
    { id: string; description: string; local_path: string; created_at: string }[]
  >([]);

  useEffect(() => {
    const stored = window.localStorage.getItem("falrun_api_key");
    if (stored) setFalKey(stored);
    fetchHistory();
  }, []);

  function saveFalKey(value: string) {
    setFalKey(value);
    window.localStorage.setItem("falrun_api_key", value);
  }

  async function fetchHistory() {
    try {
      const res = await fetch("/api/cineprompt/history");
      if (res.ok) setHistory(await res.json());
    } catch {
      // History is a convenience view; a failed fetch here isn't fatal to the page.
    }
  }

  // Verified against fal.ai's own docs (2026-08-10): "fal-ai/kling-video/v2/master/text-to-video"
  // is a live Kling 2.0 Master text-to-video endpoint. Swap this for whichever
  // model the `model` picker should target once more than one provider matters —
  // v1 hardcodes the one BYOK provider this plan scoped (fal.run, Kling).
  const FAL_MODEL_ID = "fal-ai/kling-video/v2/master/text-to-video";

  // 100 attempts * 3s = 5 minutes. A Kling generation typically completes in
  // under a minute; 5 minutes is generous headroom without hanging the page
  // indefinitely on a stuck or abandoned fal.run job.
  const MAX_POLL_ATTEMPTS = 100;
  const POLL_INTERVAL_MS = 3000;

  async function pollUntilComplete(statusUrl: string): Promise<void> {
    const headers = { Authorization: `Key ${falKey}` };
    for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      const statusRes = await fetch(`${statusUrl}?logs=1`, { headers });
      const statusBody = await statusRes.json();
      if (statusBody.status === "COMPLETED") return;
      if (statusBody.status === "ERROR") {
        throw new Error(statusBody.error ?? "fal.run generation failed.");
      }
      // IN_QUEUE / IN_PROGRESS: keep polling.
    }
    throw new Error("fal.run generation timed out after 5 minutes.");
  }

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      const submit = await fetch(`https://queue.fal.run/${FAL_MODEL_ID}`, {
        method: "POST",
        headers: {
          Authorization: `Key ${falKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ prompt }),
      });
      const submitBody = await submit.json();
      if (!submit.ok) {
        setError(submitBody.detail ?? "fal.run submission failed.");
        return;
      }

      await pollUntilComplete(submitBody.status_url);

      const resultRes = await fetch(submitBody.response_url, {
        headers: { Authorization: `Key ${falKey}` },
      });
      const resultBody = await resultRes.json();
      if (!resultRes.ok) {
        setError(resultBody.detail ?? "Could not fetch fal.run result.");
        return;
      }
      setVideoUrl(resultBody.video?.url ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach fal.run.");
    } finally {
      setGenerating(false);
    }
  }

  async function handleSave() {
    if (!videoUrl) return;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/cineprompt/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description, mode, model, fields, prompt, video_url: videoUrl }),
      });
      const body = await res.json();
      if (!res.ok) {
        setError(body.detail ?? "Save failed.");
        return;
      }
      await fetchHistory();
    } catch {
      setError("Could not reach the worker.");
    } finally {
      setSaving(false);
    }
  }
```

Add `useEffect` to the `react` import at the top of the file:

```tsx
import { useEffect, useState } from "react";
```

Add the generate/save UI and history list to the JSX, after the existing `{prompt && (...)}` block:

```tsx
        {prompt && (
          <section className="rounded-xl border border-border bg-[var(--surface-deck)] p-4 space-y-3">
            <h2 className="text-sm font-semibold">Generate</h2>
            <label className="block text-xs text-[var(--muted)]">
              fal.run API key (stored only in this browser)
              <input
                type="password"
                value={falKey}
                onChange={(e) => saveFalKey(e.target.value)}
                className="mt-1 min-h-9 w-full rounded-lg border border-border bg-[var(--surface-recessed)] px-2 text-sm"
              />
            </label>
            <button
              onClick={handleGenerate}
              disabled={generating || falKey.trim().length === 0}
              className="inline-flex min-h-9 items-center gap-2 rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Generate
            </button>
            {videoUrl && (
              <div className="space-y-2">
                <video src={videoUrl} controls className="w-full rounded-lg" />
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-border px-3 text-sm font-medium disabled:opacity-50"
                >
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Save
                </button>
              </div>
            )}
          </section>
        )}

        {history.length > 0 && (
          <section className="rounded-xl border border-border bg-[var(--surface-deck)] p-4 space-y-2">
            <h2 className="text-sm font-semibold">History</h2>
            <ul className="space-y-1">
              {history.map((row) => (
                <li key={row.id} className="text-sm text-[var(--muted)]">
                  {row.description} — <span className="font-mono text-xs">{row.local_path}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
```

- [ ] **Step 2: Verify it builds**

Run:
```powershell
cd "F:\Content Creation Project\gui"
npm run build
```
Expected: build succeeds. This step verifies the page compiles and the key never leaves the browser (confirm by reading the diff: no `falKey` variable appears anywhere in a `fetch("/api/...")` call) — it does not exercise a real fal.run generation, which needs a funded fal.run account and is a manual smoke test, not part of this plan's automated checks.

- [ ] **Step 3: Confirm the key-isolation constraint by inspection**

Run: `grep -n "falKey" "F:\Content Creation Project\gui\src\app\cinema\page.tsx"`
Expected: every match is either the `falKey` state declaration/setter, the password input, or the `Authorization` header on the `queue.fal.run` call — never inside a `fetch("/api/...")` call. This is the plan's one hard security check; if any `/api/*` call includes `falKey`, stop and fix before committing.

- [ ] **Step 4: Commit and push**

```powershell
cd "F:\Content Creation Project"
git add gui/src/app/cinema/page.tsx
git commit -m "feat(cineprompt): BYOK fal.run generation, save, and history"
git push
```

---

### Task 10: Visual design pass (blocked on session restart)

**Not implemented in this plan.** Tasks 8-9 ship a functionally complete page reusing existing Tailwind tokens (`--surface-deck`, `--muted`, `--border`, `--primary`, matching `films/page.tsx`'s conventions) — it is deliberately not a bespoke visual treatment.

Once the session has restarted and the `frontend-design` skill (re-enabled in `.claude/settings.local.json` this session) is active, invoke it against `gui/src/app/cinema/page.tsx` for aesthetic direction: layout, typography, spacing, and any component extraction the design calls for. That is a separate brainstorming/plan cycle, not a task to fold into this one — this plan's scope ends at "Cinema works," not "Cinema looks considered."

---

## Verification

After Task 9:

```powershell
cd "F:\Content Creation Project\worker"
..\.venv\Scripts\python.exe -m pytest tests -q -m "not integration"
..\.venv\Scripts\python.exe -m pytest tests/test_db.py -k Cineprompt -v   # requires local Postgres
cd "F:\Content Creation Project\gui"
npm run build
```

Then run `START_LAMKA_LABS_STUDIO.bat`, open `/cinema`, and walk the full flow: description → Fill → edit a field → Build prompt → (with a real fal.run key) Generate → Save → confirm the entry appears in History and the file exists under `videos/cineprompt/`.
