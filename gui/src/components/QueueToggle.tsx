"use client";

import { useState } from "react";
import { Moon } from "lucide-react";
import { setStoryQueued } from "@/lib/api";

export default function QueueToggle({
  storyId,
  initialQueued,
}: {
  storyId: string;
  initialQueued: boolean;
}) {
  const [queued, setQueued] = useState(initialQueued);
  const [busy, setBusy] = useState(false);

  async function toggle() {
    if (busy) return;
    const next = !queued;
    setQueued(next);
    setBusy(true);
    try {
      await setStoryQueued(storyId, next);
    } catch {
      setQueued(!next);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      onClick={toggle}
      disabled={busy}
      aria-pressed={queued}
      title={queued ? "Queued for tonight — click to unqueue" : "Queue for tonight's autopilot run"}
      className={`flex min-h-11 min-w-11 items-center justify-center rounded-[var(--radius)] border transition-colors disabled:opacity-40 ${
        queued
          ? "border-primary/40 bg-primary/10 text-primary"
          : "border-transparent text-[var(--muted)] hover:border-border hover:text-foreground"
      }`}
    >
      <Moon className="h-5 w-5" aria-hidden="true" />
    </button>
  );
}
