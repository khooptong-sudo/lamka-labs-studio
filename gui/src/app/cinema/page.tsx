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
