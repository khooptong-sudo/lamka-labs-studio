"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import {
  Check,
  Clapperboard,
  Cpu,
  ExternalLink,
  FileCheck2,
  ImagePlay,
  Loader2,
  Mic2,
  Play,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import ChannelSelect, { readErrorDetail, useChannels } from "@/components/ChannelSelect";
import CinematicControls, { DEFAULT_CINEMATIC_CONTROLS } from "@/components/CinematicControls";
import FilmProgress from "@/components/FilmProgress";
import ShotInspector from "@/components/ShotInspector";

type SourceItem = {
  id: string;
  title: string;
  url: string;
  source_name: string;
  published_at: string;
};

type Story = {
  id: string;
  headline: string;
  created_at: string;
  items: SourceItem[];
};

type ImageProvider = {
  id: "openai" | "comfyui";
  label: string;
  detail: string;
  configured: boolean;
};
type Mode = "short" | "film";
type VoiceKey = "adult_female" | "teenage_girl";

const FEMALE_VOICES: { id: VoiceKey; label: string; detail: string }[] = [
  { id: "adult_female", label: "Jenny", detail: "Warm, clear delivery. Edge Neural." },
  { id: "teenage_girl", label: "Aria", detail: "Bright, expressive delivery. Edge Neural." },
];

function storyboardTitle(storyboard: string): string {
  const title = storyboard.match(/^\s*title\s*:\s*(.+)$/im)?.[1]?.trim();
  return title?.slice(0, 180) || "Manual storyboard";
}

const MODES: { id: Mode; label: string; detail: string; icon: typeof ImagePlay }[] = [
  {
    id: "short",
    label: "3D Short",
    detail: "Image-led, 1080 x 1920 portrait",
    icon: ImagePlay,
  },
  {
    id: "film",
    label: "Story Film",
    detail: "Code-authored, 1920 x 1080 landscape",
    icon: Clapperboard,
  },
];

export default function FilmsPage() {
  const { channels, error: channelsError } = useChannels();
  const [stories, setStories] = useState<Story[]>([]);
  const [storyId, setStoryId] = useState("");
  const [channelId, setChannelId] = useState("");
  const [mode, setMode] = useState<Mode>("short");
  const [imageProviders, setImageProviders] = useState<ImageProvider[]>([]);
  const [imageProvider, setImageProvider] = useState<ImageProvider["id"]>("comfyui");
  const [voiceKey, setVoiceKey] = useState<VoiceKey>("adult_female");
  const [storyboard, setStoryboard] = useState("");
  const [cinematicControls, setCinematicControls] = useState(DEFAULT_CINEMATIC_CONTROLS);
  const [jobId, setJobId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const hasHydrated = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false,
  );
  const selectedStory = stories.find((story) => story.id === storyId);
  const hasStoryboard = Boolean(storyboard.trim());
  const needsReviewedBoard = Boolean(selectedStory && selectedStory.items.length === 0 && !storyboard.trim());
  const selectedImageProvider = imageProviders.find((provider) => provider.id === imageProvider);
  const imageProviderReady = selectedImageProvider?.configured ?? false;
  const canGenerate =
    hasHydrated &&
    Boolean(channelId) &&
    Boolean(storyId || hasStoryboard) &&
    !busy &&
    !needsReviewedBoard &&
    (mode !== "short" || imageProviderReady);

  useEffect(() => {
    fetch("/api/stories", { cache: "no-store" })
      .then((res) => res.json())
      .then((data) => {
        const nextStories: Story[] = Array.isArray(data) ? data : [];
        setStories(nextStories);
        const params = new URLSearchParams(window.location.search);
        const selectedId = params.get("story");
        const selectedChannel = params.get("channel");
        if (selectedId && nextStories.some((story) => story.id === selectedId)) {
          setStoryId(selectedId);
        }
        if (selectedChannel) setChannelId(selectedChannel);
      })
      .catch(() => setStories([]));
  }, []);

  useEffect(() => {
    fetch("/api/youtube/image-providers", { cache: "no-store" })
      .then((res) => res.json())
      .then((data) => setImageProviders(Array.isArray(data.providers) ? data.providers : []))
      .catch(() => setImageProviders([]));
  }, []);

  if (!hasHydrated) {
    return (
      <div className="min-h-[100dvh] p-4 lg:p-6" aria-busy="true">
        <header className="mb-6 border-b border-border pb-5">
          <div className="h-7 w-40 animate-pulse rounded bg-foreground/10" />
          <div className="mt-3 h-4 w-72 max-w-full animate-pulse rounded bg-foreground/5" />
        </header>
        <section className="space-y-3" aria-label="Loading production workspace">
          <div className="h-32 animate-pulse rounded-xl bg-foreground/5" />
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_22rem]">
            <div className="h-96 animate-pulse rounded-xl bg-foreground/5" />
            <div className="h-96 animate-pulse rounded-xl bg-foreground/5" />
          </div>
        </section>
      </div>
    );
  }

  const generate = async () => {
    setBusy(true);
    setError("");
    setJobId("");
    try {
      const board = storyboard.trim();
      let activeStoryId = storyId;

      if (!activeStoryId && board) {
        const headline = storyboardTitle(board);
        const manualStoryRes = await fetch("/api/stories/manual", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ headline, channel_id: channelId }),
        });
        if (!manualStoryRes.ok) {
          setError(await readErrorDetail(manualStoryRes, "Could not create the manual story"));
          return;
        }
        const manualStory = await manualStoryRes.json() as { id?: string };
        if (!manualStory.id) {
          setError("The worker did not return an ID for the manual story.");
          return;
        }
        activeStoryId = manualStory.id;
        setStoryId(activeStoryId);
        setStories((current) => [
          { id: activeStoryId, headline, created_at: "", items: [] },
          ...current,
        ]);
      }

      const res = await fetch("/api/youtube/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          story_id: activeStoryId,
          channel_id: channelId,
          mode,
          storyboard: board || undefined,
          image_provider: mode === "short" ? imageProvider : undefined,
          voice_key: voiceKey,
          cinematic_controls: cinematicControls,
        }),
      });
      if (!res.ok) {
        setError(await readErrorDetail(res, "Could not start the run"));
        return;
      }
      const data = await res.json();
      setJobId(data.job_id);
    } catch {
      setError("Could not reach the worker. Is it running on port 8000?");
    } finally {
      setBusy(false);
    }
  };

  const evidenceReady = Boolean(selectedStory?.items.length);
  const productionLabel = selectedStory?.headline || (hasStoryboard ? storyboardTitle(storyboard) : "Untitled production");

  return (
    <div className="min-h-[100dvh] pb-4">
      {/*
        THESIS: One production bench connects evidence, continuity, controls, and render state without a wizard.
        OWN-WORLD: Cool graphite deck, porcelain type, coral transport action, sparse rails, no decorative glass.
        STORY: Select evidence, configure the run, verify readiness, then build and monitor one accountable draft.
        FIRST VIEWPORT: Evidence ledger above a two-zone setup, with the production dock visible at the bottom.
        FORM: Contact-sheet production bench with a persistent transport dock; direction seed 6c12a7ff.
      */}
      <header className="sticky top-0 z-30 flex min-h-[82px] flex-wrap items-center justify-between gap-4 border-b border-border bg-background/95 px-4 py-4 backdrop-blur-md lg:px-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold tracking-[-0.025em]">Production</h1>
            <span className="rounded-md border border-border bg-secondary px-2 py-1 font-mono text-[10px] text-secondary-foreground">
              {mode === "short" ? "PORTRAIT" : "LANDSCAPE"}
            </span>
          </div>
          <p className="mt-1 max-w-[64ch] truncate text-sm text-[var(--muted)]">{productionLabel}</p>
        </div>
        <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
          <ShieldCheck className="h-4 w-4 text-[var(--success)]" aria-hidden="true" />
          Human-reviewed, manual publish
        </div>
      </header>

      <div className="space-y-3 p-3 lg:p-4">
        <section className="overflow-hidden rounded-xl border border-border bg-[var(--surface-deck)]" aria-labelledby="evidence-heading">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
            <div>
              <h2 id="evidence-heading" className="text-sm font-semibold">Evidence ledger</h2>
              <p className="mt-0.5 text-xs text-[var(--muted)]">The source packet that constrains automatic scripting.</p>
            </div>
            <span className="font-mono text-xs text-[var(--muted)]">
              {selectedStory?.items.length ?? 0} linked source{selectedStory?.items.length === 1 ? "" : "s"}
            </span>
          </div>

          <div className="grid gap-3 p-3 lg:grid-cols-[minmax(18rem,0.8fr)_minmax(0,1.7fr)]">
            <div className="space-y-2">
              <label htmlFor="production-story" className="text-xs font-medium text-[var(--muted)]">Research story</label>
              <select
                id="production-story"
                value={storyId}
                onChange={(event) => setStoryId(event.target.value)}
                className="min-h-11 w-full rounded-lg border border-border bg-[var(--surface-recessed)] px-3 text-sm text-foreground transition-colors focus:border-primary focus:outline-none"
              >
                <option value="">Select a story</option>
                {stories.map((story) => (
                  <option key={story.id} value={story.id}>{story.headline}</option>
                ))}
              </select>
              <p className="text-xs leading-5 text-[var(--muted)]">
                {stories.length === 0
                  ? "No stories are available. Ingest a feed or use a reviewed storyboard."
                  : "Choose a dated research story, or leave this empty and supply a reviewed storyboard."}
              </p>
            </div>

            <div className="min-w-0 border-t border-border pt-2 lg:border-l lg:border-t-0 lg:pl-3 lg:pt-0">
              {selectedStory ? (
                selectedStory.items.length > 0 ? (
                  <div className="divide-y divide-border">
                    {selectedStory.items.slice(0, 4).map((item, index) => (
                      <a
                        key={item.id}
                        href={item.url}
                        target="_blank"
                        rel="noreferrer"
                        className="grid min-h-12 grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-3 rounded-lg px-2 text-sm transition-colors hover:bg-foreground/[0.035]"
                      >
                        <span className="font-mono text-xs text-[var(--muted)]">{String(index + 1).padStart(2, "0")}</span>
                        <span className="min-w-0">
                          <span className="block truncate font-medium">{item.title}</span>
                          <span className="block truncate text-xs text-[var(--muted)]">{item.source_name}</span>
                        </span>
                        <ExternalLink className="h-4 w-4 text-[var(--muted)]" aria-label="Open source" />
                      </a>
                    ))}
                  </div>
                ) : (
                  <div className="flex min-h-28 items-center gap-3 px-3 text-sm text-[var(--warning)]">
                    <FileCheck2 className="h-5 w-5 shrink-0" aria-hidden="true" />
                    <p>This manual idea has no evidence packet. Paste a reviewed storyboard before building.</p>
                  </div>
                )
              ) : (
                <div className="flex min-h-28 items-center gap-3 px-3 text-sm text-[var(--muted)]">
                  <FileCheck2 className="h-5 w-5 shrink-0" aria-hidden="true" />
                  <p>Select a research story to inspect its sources here.</p>
                </div>
              )}
            </div>
          </div>
        </section>

        <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(22rem,0.62fr)]">
          <section className="rounded-xl border border-border bg-[var(--surface-deck)]" aria-labelledby="continuity-heading">
            <div className="border-b border-border px-4 py-3">
              <h2 id="continuity-heading" className="text-sm font-semibold">Production setup</h2>
              <p className="mt-0.5 text-xs text-[var(--muted)]">The choices that alter the generated artifact.</p>
            </div>

            <div className="grid gap-5 p-4 md:grid-cols-2">
              <fieldset className="space-y-2">
                <legend className="mb-2 text-xs font-medium text-[var(--muted)]">Channel</legend>
                <ChannelSelect
                  value={channelId}
                  onChange={setChannelId}
                  channels={channels}
                  disabled={busy}
                  className="min-h-11 w-full px-3 text-sm"
                />
                {channelsError && <p className="text-xs text-[var(--destructive)]">{channelsError}</p>}
              </fieldset>

              <fieldset className="space-y-2">
                <legend className="mb-2 text-xs font-medium text-[var(--muted)]">Format</legend>
                <div className="grid grid-cols-2 gap-2">
                  {MODES.map((option) => {
                    const active = mode === option.id;
                    return (
                      <button
                        key={option.id}
                        type="button"
                        aria-pressed={active}
                        onClick={() => setMode(option.id)}
                        className={`min-h-[72px] rounded-lg border p-3 text-left transition-colors active:translate-y-px ${active ? "border-primary bg-primary/10" : "border-border bg-[var(--surface-recessed)] hover:bg-secondary"}`}
                      >
                        <span className="flex items-center gap-2 text-sm font-semibold">
                          <option.icon className={`h-4 w-4 ${active ? "text-primary" : "text-[var(--muted)]"}`} aria-hidden="true" />
                          {option.label}
                        </span>
                        <span className="mt-1 block font-mono text-[10px] leading-4 text-[var(--muted)]">{option.detail}</span>
                      </button>
                    );
                  })}
                </div>
              </fieldset>

              <fieldset className="space-y-2">
                <legend className="mb-2 text-xs font-medium text-[var(--muted)]">Narrator</legend>
                <div className="grid grid-cols-2 gap-2">
                  {FEMALE_VOICES.map((voice) => {
                    const active = voiceKey === voice.id;
                    return (
                      <button
                        key={voice.id}
                        type="button"
                        aria-pressed={active}
                        onClick={() => setVoiceKey(voice.id)}
                        className={`min-h-[72px] rounded-lg border p-3 text-left transition-colors active:translate-y-px ${active ? "border-primary bg-primary/10" : "border-border bg-[var(--surface-recessed)] hover:bg-secondary"}`}
                      >
                        <span className="flex items-center gap-2 text-sm font-semibold">
                          <Mic2 className={`h-4 w-4 ${active ? "text-primary" : "text-[var(--muted)]"}`} aria-hidden="true" />
                          {voice.label}
                        </span>
                        <span className="mt-1 block text-[11px] leading-4 text-[var(--muted)]">{voice.detail}</span>
                      </button>
                    );
                  })}
                </div>
              </fieldset>

              {mode === "short" && (
                <fieldset className="space-y-2">
                  <legend className="mb-2 text-xs font-medium text-[var(--muted)]">Image provider</legend>
                  <div className="grid grid-cols-2 gap-2">
                    {imageProviders.map((provider) => {
                      const active = provider.id === imageProvider;
                      return (
                        <button
                          key={provider.id}
                          type="button"
                          aria-pressed={active}
                          onClick={() => setImageProvider(provider.id)}
                          className={`min-h-[72px] rounded-lg border p-3 text-left transition-colors active:translate-y-px ${active ? "border-primary bg-primary/10" : "border-border bg-[var(--surface-recessed)] hover:bg-secondary"}`}
                        >
                          <span className="flex items-center gap-2 text-sm font-semibold">
                            <Cpu className={`h-4 w-4 ${active ? "text-primary" : "text-[var(--muted)]"}`} aria-hidden="true" />
                            {provider.label}
                          </span>
                          <span className={`mt-1 flex items-center gap-1.5 text-[11px] ${provider.configured ? "text-[var(--success)]" : "text-[var(--warning)]"}`}>
                            {provider.configured && <Check className="h-3 w-3" aria-hidden="true" />}
                            {provider.configured ? "Ready" : "Setup needed"}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                  {imageProviders.length === 0 && <p className="text-xs text-[var(--warning)]">Provider status is unavailable. Check the worker.</p>}
                </fieldset>
              )}
            </div>
            <CinematicControls
              value={cinematicControls}
              onChange={setCinematicControls}
              disabled={busy}
            />
          </section>

          <section className="flex min-h-[28rem] flex-col rounded-xl border border-border bg-[var(--surface-deck)]" aria-labelledby="storyboard-heading">
            <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
              <div>
                <h2 id="storyboard-heading" className="text-sm font-semibold">Storyboard control</h2>
                <p className="mt-0.5 text-xs text-[var(--muted)]">Optional exact production script.</p>
              </div>
              <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
            </div>
            <textarea
              value={storyboard}
              onChange={(event) => setStoryboard(event.target.value)}
              rows={16}
              placeholder="Paste a reviewed storyboard for exact control. Include YAML title, description and preset, followed by 4-8 scenes with Voiceover and Scene lines. Leave blank to script from linked evidence."
              className="min-h-80 flex-1 resize-y border-0 bg-[var(--surface-recessed)] p-4 font-mono text-xs leading-6 text-foreground placeholder:text-[var(--muted)] focus:outline-none"
            />
            <div className="border-t border-border px-4 py-3 text-xs leading-5 text-[var(--muted)]">
              A pasted board overrides automatic scripting but still passes narration, visual, render, and quality checks.
            </div>
          </section>
        </div>

        {(selectedImageProvider && !selectedImageProvider.configured) && mode === "short" && (
          <div className="rounded-lg border border-[color-mix(in_srgb,var(--warning)_35%,var(--border))] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] px-4 py-3 text-sm text-[var(--warning)]">
            {imageProvider === "comfyui"
              ? "Start ComfyUI and configure its URL and checkpoint, then restart the worker."
              : "Set a funded OpenAI API key, then restart the worker."}
          </div>
        )}

        {error && (
          <div role="alert" className="rounded-lg border border-[color-mix(in_srgb,var(--destructive)_35%,var(--border))] bg-[color-mix(in_srgb,var(--destructive)_8%,transparent)] px-4 py-3 text-sm text-[var(--destructive)]">
            {error}
          </div>
        )}

        <section className="sticky bottom-3 z-20 grid overflow-hidden rounded-xl border border-border bg-[var(--surface-raised)] shadow-[0_18px_45px_rgba(0,0,0,0.28)] md:grid-cols-[1fr_1fr_1fr_1.2fr_auto]" aria-label="Production dock">
          <div className="flex min-h-[76px] items-center gap-3 border-b border-border px-4 md:border-b-0 md:border-r">
            <Clapperboard className="h-5 w-5 text-[var(--muted)]" aria-hidden="true" />
            <div>
              <p className="text-[10px] text-[var(--muted)]">FORMAT</p>
              <p className="mt-1 text-sm font-medium">{mode === "short" ? "3D Short" : "Story Film"}</p>
            </div>
          </div>
          <div className="flex min-h-[76px] items-center gap-3 border-b border-border px-4 md:border-b-0 md:border-r">
            <Cpu className="h-5 w-5 text-[var(--muted)]" aria-hidden="true" />
            <div className="min-w-0">
              <p className="text-[10px] text-[var(--muted)]">PROVIDER</p>
              <p className="mt-1 truncate text-sm font-medium">{mode === "film" ? "Local Three.js" : selectedImageProvider?.label || "Not available"}</p>
            </div>
          </div>
          <div className="flex min-h-[76px] items-center gap-3 border-b border-border px-4 md:border-b-0 md:border-r">
            <Mic2 className="h-5 w-5 text-[var(--muted)]" aria-hidden="true" />
            <div>
              <p className="text-[10px] text-[var(--muted)]">NARRATOR</p>
              <p className="mt-1 text-sm font-medium">{FEMALE_VOICES.find((voice) => voice.id === voiceKey)?.label}</p>
            </div>
          </div>
          <div className="flex min-h-[76px] items-center gap-3 border-b border-border px-4 md:border-b-0 md:border-r">
            {canGenerate ? <Check className="h-5 w-5 text-[var(--success)]" aria-hidden="true" /> : <ShieldCheck className="h-5 w-5 text-[var(--warning)]" aria-hidden="true" />}
            <div>
              <p className="text-[10px] text-[var(--muted)]">READINESS</p>
              <p className="mt-1 text-sm font-medium">{canGenerate ? "Ready to build" : evidenceReady || hasStoryboard ? "Complete setup" : "Evidence or storyboard required"}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={generate}
            disabled={!canGenerate}
            className="m-2 inline-flex min-h-[60px] min-w-48 items-center justify-center gap-2 rounded-lg bg-primary px-5 font-semibold text-primary-foreground transition-[transform,filter] hover:brightness-105 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-35"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Play className="h-4 w-4 fill-current" aria-hidden="true" />}
            {busy ? "Starting run" : "Build video"}
          </button>
        </section>

        {jobId && <FilmProgress jobId={jobId} />}
        {jobId && <ShotInspector jobId={jobId} />}
      </div>
    </div>
  );
}
