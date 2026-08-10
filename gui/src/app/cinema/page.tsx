"use client";

import { useEffect, useState } from "react";
import { Loader2, Sparkles, Wand2 } from "lucide-react";

type FieldState = Record<string, string | string[]>;

const MODES = ["single", "frame_motion"] as const;
const LEVELS = ["simple", "complex"] as const;
const MODELS = ["universal", "veo", "sora", "kling", "seedance", "grok", "ltx", "pixverse", "luma", "wan"] as const;

function fieldDisplayValue(value: string | string[]): string {
  return Array.isArray(value) ? value.join(", ") : value;
}

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

  const [falKey, setFalKey] = useState("");
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState<
    { id: string; description: string; local_path: string; created_at: string }[]
  >([]);
  const [vocabData, setVocabData] = useState<
    Record<string, Record<string, { values: string[]; free_text: boolean }>>
  >({});

  useEffect(() => {
    const stored = window.localStorage.getItem("falrun_api_key");
    if (stored) setFalKey(stored);
    fetchHistory();
  }, []);

  useEffect(() => {
    fetch(`/api/cineprompt/vocab?mode=${mode}&level=${level}`)
      .then((res) => (res.ok ? res.json() : {}))
      .then(setVocabData)
      .catch(() => {
        // The picker is additive — Fill/Build/Generate stay usable if this fails.
      });
  }, [mode, level]);

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
    setVideoUrl(null);
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

  async function handleFill() {
    setVideoUrl(null);
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
    setVideoUrl(null);
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
      setPrompt((body.prompts as string[]).join("\n\n"));
    } catch {
      setError("Could not reach the worker.");
    } finally {
      setBuilding(false);
    }
  }

  function updateField(key: string, value: string) {
    setVideoUrl(null);
    setFields((prev) => ({ ...prev, [key]: value }));
  }

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

        {Object.keys(fields).length > 0 && (
          <section className="rounded-xl border border-border bg-[var(--surface-deck)] p-4 space-y-3">
            <h2 className="text-sm font-semibold">Fields</h2>
            <div className="grid gap-2 sm:grid-cols-2">
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
            </div>
            <div className="flex items-center gap-3">
              <label className="text-xs text-[var(--muted)]">
                Prompt format
                <select value={model} onChange={(e) => setModel(e.target.value as typeof model)} className="mt-1 block min-h-9 rounded-lg border border-border bg-[var(--surface-recessed)] px-2 text-sm">
                  {MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </label>
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

        {prompt && (
          <section className="rounded-xl border border-border bg-[var(--surface-deck)] p-4 space-y-3">
            <h2 className="text-sm font-semibold">Generate</h2>
            <p className="text-xs text-[var(--muted)]">
              Generated with Kling 2.0 via fal.run — the prompt format above does not change the generator.
            </p>
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
                <li key={row.id} className="space-y-1 text-sm text-[var(--muted)]">
                  <p>{row.description}</p>
                  <video src={`/api/videos/${row.local_path}`} controls className="w-full rounded-lg" />
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
  );
}
