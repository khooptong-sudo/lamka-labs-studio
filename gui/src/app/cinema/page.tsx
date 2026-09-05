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

// Minor words stay lowercase unless they open or close the string, matching
// standard title-case style (e.g. Chicago/APA). Applied only to display
// text — the underlying field/value strings sent to the worker are never
// altered.
const TITLE_CASE_MINOR_WORDS = new Set([
  "a", "an", "the", "is", "at", "of", "in", "on", "to", "for",
  "and", "or", "but", "nor", "as", "by", "with",
]);

function toTitleCase(text: string): string {
  const words = text.replace(/_/g, " ").split(" ").filter(Boolean);
  return words
    .map((word, index) => {
      // Preserve existing acronyms (ARRI, RED, DOF, ...) rather than
      // re-casing them into "Arri"/"Red"/"Dof".
      if (word.length > 1 && word === word.toUpperCase() && /[A-Z]/.test(word)) {
        return word;
      }
      const lower = word.toLowerCase();
      const isMinor = index !== 0 && index !== words.length - 1 && TITLE_CASE_MINOR_WORDS.has(lower);
      return isMinor ? lower : lower.charAt(0).toUpperCase() + lower.slice(1);
    })
    .join(" ");
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
        body: JSON.stringify({ description, mode, level, locked: fields }),
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
        <header className="border-b border-border pb-5">
          <h1 className="text-[27px] font-semibold leading-none tracking-[-0.025em]">Cinema</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Describe a scene, let CinePrompt fill in the cinematography, then generate video.
          </p>
        </header>

        <section className="space-y-3 rounded-[var(--radius)] border border-border bg-[var(--surface-deck)] p-4">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="A woman in a cramped office at dawn, wide shot, tense..."
            className="field-well min-h-24 w-full p-3 text-sm placeholder:text-[var(--muted)] focus:outline-none"
          />
          <div className="flex flex-wrap gap-3">
            <select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)} className="field-well min-h-11 px-2 text-sm">
              {MODES.map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
            <select value={level} onChange={(e) => setLevel(e.target.value as typeof level)} className="field-well min-h-11 px-2 text-sm">
              {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
            <button
              onClick={handleFill}
              disabled={filling || description.trim().length === 0}
              className="btn-ink ml-auto"
            >
              {filling ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
              Fill
            </button>
          </div>
          {error && (
            <div role="alert" className="flex flex-wrap items-center gap-3 rounded-[var(--radius)] border border-[color-mix(in_srgb,var(--destructive)_35%,var(--border))] bg-[color-mix(in_srgb,var(--destructive)_8%,transparent)] px-4 py-3 text-sm text-[var(--destructive)]">
              <span className="chip">Error</span>
              <p className="m-0">{error}</p>
            </div>
          )}
        </section>

        {Object.keys(vocabData).length > 0 && (
          <section className="space-y-4 rounded-[var(--radius)] border border-border bg-[var(--surface-deck)] p-4">
            <h2 className="text-[17px] font-semibold tracking-tight">Browse fields</h2>
            {Object.entries(vocabData).map(([section, sectionFields]) => (
              <details key={section} open className="border-t border-border pt-3">
                <summary className="cursor-pointer text-sm font-semibold tracking-tight">
                  {section}
                </summary>
                <div className="space-y-3 pt-2">
                  {Object.entries(sectionFields).map(([field, { values, free_text }]) => (
                    <div key={field} className="border-t border-border pt-3 first:border-t-0 first:pt-0">
                      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">{toTitleCase(field)}</p>
                      {free_text ? (
                        <textarea
                          value={typeof fields[field] === "string" ? (fields[field] as string) : ""}
                          onChange={(e) => updateFreeTextField(field, e.target.value)}
                          className="field-well mt-1 min-h-16 w-full p-2 text-sm focus:outline-none"
                        />
                      ) : (
                        <div className="mt-1 flex flex-wrap gap-1.5">
                          {values.map((value) => (
                            <button
                              key={value}
                              type="button"
                              aria-pressed={isChipActive(field, value)}
                              onClick={() => toggleChip(field, value)}
                              className={`chip ${
                                isChipActive(field, value)
                                  ? "border-primary bg-primary/10 text-primary"
                                  : "text-[var(--muted)]"
                              }`}
                            >
                              {toTitleCase(value)}
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
          <section className="space-y-3 rounded-[var(--radius)] border border-border bg-[var(--surface-deck)] p-4">
            <h2 className="text-[17px] font-semibold tracking-tight">Fields</h2>
            <div className="grid gap-2 sm:grid-cols-2">
              {Object.entries(fields).map(([key, value]) => (
                <label key={key} className="text-xs text-[var(--muted)]">
                  {toTitleCase(key)}
                  <input
                    value={fieldDisplayValue(value)}
                    onChange={(e) => updateField(key, e.target.value)}
                    className="field-well mt-1 min-h-11 w-full px-2 text-sm focus:outline-none"
                  />
                </label>
              ))}
            </div>
            <div className="flex items-center gap-3">
              <label className="text-xs text-[var(--muted)]">
                Prompt format
                <select value={model} onChange={(e) => setModel(e.target.value as typeof model)} className="field-well mt-1 block min-h-11 px-2 text-sm">
                  {MODELS.map((m) => <option key={m} value={m}>{m}</option>)}
                </select>
              </label>
              <button
                onClick={handleBuild}
                disabled={building}
                className="btn-ink"
              >
                {building ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                Build prompt
              </button>
            </div>
          </section>
        )}

        {prompt && (
          <section className="rounded-[var(--radius)] border border-border bg-[var(--surface-deck)] p-4">
            <h2 className="text-[17px] font-semibold tracking-tight">Prompt</h2>
            <p className="field-well mt-2 p-3 text-sm leading-relaxed">{prompt}</p>
          </section>
        )}

        {prompt && (
          <section className="space-y-3 rounded-[var(--radius)] border border-border bg-[var(--surface-deck)] p-4">
            <h2 className="text-[17px] font-semibold tracking-tight">Generate</h2>
            <p className="text-xs text-[var(--muted)]">
              Generated with Kling 2.0 via fal.run — the prompt format above does not change the generator.
            </p>
            <label className="block text-xs text-[var(--muted)]">
              fal.run API key (stored only in this browser)
              <input
                type="password"
                value={falKey}
                onChange={(e) => saveFalKey(e.target.value)}
                className="field-well mt-1 min-h-11 w-full px-2 text-sm focus:outline-none"
              />
            </label>
            <button
              onClick={handleGenerate}
              disabled={generating || falKey.trim().length === 0}
              className="btn-primary"
            >
              {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Generate
            </button>
            {videoUrl && (
              <div className="space-y-2">
                <video src={videoUrl} controls className="w-full rounded-[var(--radius)]" />
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="btn-ghost"
                >
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Save
                </button>
              </div>
            )}
          </section>
        )}

        {history.length > 0 && (
          <section className="space-y-2 rounded-[var(--radius)] border border-border bg-[var(--surface-deck)] p-4">
            <h2 className="text-[17px] font-semibold tracking-tight">History</h2>
            <ul className="divide-y divide-border">
              {history.map((row) => (
                <li key={row.id} className="space-y-2 py-3 text-sm first:pt-1 last:pb-0">
                  <p className="text-foreground">{row.description}</p>
                  <p className="font-mono text-xs text-[var(--muted)]">{row.created_at}</p>
                  <video src={`/api/videos/${row.local_path}`} controls className="w-full rounded-[var(--radius)]" />
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
  );
}
