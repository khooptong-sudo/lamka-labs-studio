"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Check, Loader2 } from "lucide-react";

// Mirrors STAGES in worker/app/jobs.py. Order is what the bar draws.
const STAGES = ["queued", "script", "fact_check", "narration", "world", "shots", "render", "thumbnails", "done"] as const;

// "world" is unique to the code-authored Story Film. Both formats create
// visuals at the "shots" stage; the user-facing label is clearer than the
// shared backend name.
const FILM_ONLY = new Set(["world"]);
const STAGE_LABELS: Record<(typeof STAGES)[number], string> = {
  queued: "queued",
  script: "script",
  fact_check: "fact check",
  narration: "narration",
  world: "world",
  shots: "visuals",
  render: "render",
  thumbnails: "thumbnails",
  done: "done",
};

type Job = {
  stage: string;
  done: number;
  total: number;
  error: string | null;
  draft_id: string | null;
  kind: string;
};

export default function FilmProgress({ jobId }: { jobId: string }) {
  const [job, setJob] = useState<Job | null>(null);
  const [gone, setGone] = useState(false);

  useEffect(() => {
    if (!jobId) return;
    let stop = false;

    const tick = async () => {
      try {
        const res = await fetch(`/api/youtube/jobs/${jobId}`, { cache: "no-store" });
        if (!res.ok) {
          if (res.status === 404) setGone(true);
          return;
        }
        const next: Job = await res.json();
        if (stop) return;
        setJob(next);
        // Stop polling once the run has settled, either way.
        if (next.stage === "done" || next.error) stop = true;
      } catch {
        // A dropped poll is not a failed render. Keep trying.
      }
    };

    void tick();
    const timer = setInterval(() => {
      if (stop) {
        clearInterval(timer);
        return;
      }
      void tick();
    }, 2000);

    return () => {
      stop = true;
      clearInterval(timer);
    };
  }, [jobId]);

  if (gone) {
    return <p className="text-sm text-[var(--destructive)]">Job not found.</p>;
  }

  if (!job) {
    return (
      <div className="flex items-center space-x-3 text-foreground/50">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-xs font-bold uppercase tracking-widest">Starting run…</span>
      </div>
    );
  }

  const current = STAGES.indexOf(job.stage as (typeof STAGES)[number]);
  const isFilm = job.kind === "film";
  const failed = Boolean(job.error);

  return (
    <div className="rounded-[var(--radius)] border border-border bg-[var(--surface-deck)] p-6 space-y-5">
      <ol className="flex flex-wrap gap-2">
        {STAGES.map((stage, i) => {
          const skipped = !isFilm && FILM_ONLY.has(stage);
          const complete = i < current && !skipped;
          const active = i === current && !failed;

          return (
            <li
              key={stage}
              className={`flex items-center space-x-2 rounded-xl px-3 py-2 text-xs font-bold uppercase tracking-wider transition-colors ${
                complete
                  ? "border border-[var(--success)] bg-[color-mix(in_srgb,var(--success)_10%,transparent)] text-[var(--foreground)]"
                  : active
                    ? "border border-[color-mix(in_srgb,var(--primary)_45%,transparent)] bg-[color-mix(in_srgb,var(--primary)_8%,transparent)] text-[var(--foreground)]"
                    : "border border-transparent bg-[var(--surface-recessed)] text-[var(--muted)]"
              }`}
            >
              {complete && <Check className="w-3 h-3 text-[var(--success)]" />}
              {active && <Loader2 className="w-3 h-3 animate-spin text-[var(--primary)]" />}
              <span>{STAGE_LABELS[stage]}</span>
              {active && job.total > 0 && (
                <span className="font-mono normal-case">
                  {job.done}/{job.total}
                </span>
              )}
            </li>
          );
        })}
      </ol>

      {failed && (
        <div className="flex items-start space-x-3 rounded-[var(--radius)] border border-[color-mix(in_srgb,var(--destructive)_30%,transparent)] bg-[color-mix(in_srgb,var(--destructive)_6%,transparent)] p-4">
          <AlertTriangle className="w-4 h-4 text-[var(--destructive)] mt-0.5 flex-shrink-0" />
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-[var(--destructive)]">
              Stopped at “{job.stage}”
            </p>
            <p className="mt-1 text-sm text-foreground/60">{job.error}</p>
          </div>
        </div>
      )}

      {job.stage === "done" && job.draft_id && (
        <a
          href="/drafts"
          className="inline-flex items-center space-x-2 rounded-[var(--radius)] bg-[color-mix(in_srgb,var(--success)_12%,transparent)] px-4 py-2 text-sm font-semibold text-[var(--success)] hover:bg-[color-mix(in_srgb,var(--success)_20%,transparent)] transition-colors"
        >
          <Check className="w-4 h-4" />
          <span>Done — open in Drafts Queue</span>
        </a>
      )}
    </div>
  );
}
