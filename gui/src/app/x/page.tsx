"use client";

import { useEffect, useRef, useState } from "react";
import { toPng } from "html-to-image";
import { Copy, Check, RefreshCw, MessageSquare, Send, Image, Download, Lightbulb } from "lucide-react";
import {
  fetchXStories,
  rewriteStoryToPost,
  suggestReply,
  generatePosterFromStory,
  generatePosterFromText,
  type Story,
  type Poster,
} from "@/lib/api";
import PosterCard, { getPosterTheme, type PosterTheme } from "@/components/PosterCard";

const TONE_PRESETS = [
  { label: "Concise", value: "concise" },
  { label: "Analyst-educator", value: "analyst-educator: clear, curious, never promotional" },
  { label: "Humorous", value: "humorous: witty, light, never mean" },
  { label: "Sarcastic", value: "sarcastic: dry, sharp, but fair" },
  { label: "Bullish", value: "bullish: optimistic, momentum-focused, no price targets" },
  { label: "Bearish", value: "bearish: skeptical, risk-focused, no panic" },
];

const POSTER_STYLES = [
  { label: "Light", value: "light" },
  { label: "Dark", value: "dark" },
];

export default function XPage() {
  const [stories, setStories] = useState<Story[]>([]);
  const [selected, setSelected] = useState<Story | null>(null);
  const [loadingStories, setLoadingStories] = useState(true);
  const [activeTab, setActiveTab] = useState<"post" | "poster">("post");

  // Post state
  const [post, setPost] = useState("");
  const [rewriting, setRewriting] = useState(false);
  const [tone, setTone] = useState("");
  const [postLength, setPostLength] = useState<"short" | "long">("short");
  const [copiedPost, setCopiedPost] = useState(false);

  // Poster state
  const [posterStyle, setPosterStyle] = useState("light");
  const [poster, setPoster] = useState<Poster | null>(null);
  const [posterTheme, setPosterTheme] = useState<PosterTheme | null>(null);
  const [generatingPoster, setGeneratingPoster] = useState(false);
  const [posterMode, setPosterMode] = useState<"story" | "manual">("story");
  const [manualTopic, setManualTopic] = useState("");
  const [manualBullets, setManualBullets] = useState("");
  const posterRef = useRef<HTMLDivElement>(null);
  const [downloadingPoster, setDownloadingPoster] = useState(false);

  // Reply state
  const [comment, setComment] = useState("");
  const [postContext, setPostContext] = useState("");
  const [reply, setReply] = useState("");
  const [replying, setReplying] = useState(false);
  const [copiedReply, setCopiedReply] = useState(false);

  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchXStories()
      .then((data) => {
        setStories(data);
        if (data.length > 0) setSelected(data[0]);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoadingStories(false));
  }, []);

  const handleRewrite = async () => {
    if (!selected) return;
    setRewriting(true);
    setError(null);
    try {
      const text = await rewriteStoryToPost(selected.id, tone || null, postLength);
      setPost(text);
      setPostContext(text);
    } catch (err: any) {
      setError(err.message || "Rewrite failed");
    } finally {
      setRewriting(false);
    }
  };

  const copyPost = async () => {
    await navigator.clipboard.writeText(post);
    setCopiedPost(true);
    setTimeout(() => setCopiedPost(false), 1500);
  };

  const handleGeneratePoster = async () => {
    setGeneratingPoster(true);
    setError(null);
    try {
      let result: Poster;
      if (posterMode === "story") {
        if (!selected) throw new Error("Select a story first");
        result = await generatePosterFromStory(selected.id, posterStyle);
      } else {
        if (!manualTopic.trim()) throw new Error("Topic is required");
        const bullets = manualBullets
          .split("\n")
          .map((b) => b.trim())
          .filter(Boolean);
        result = await generatePosterFromText(manualTopic, bullets, posterStyle);
      }
      setPoster(result);
      setPosterTheme(getPosterTheme());
    } catch (err: any) {
      setError(err.message || "Poster generation failed");
    } finally {
      setGeneratingPoster(false);
    }
  };

  const downloadPoster = async () => {
    if (!posterRef.current || !poster) return;
    setDownloadingPoster(true);
    try {
      const dataUrl = await toPng(posterRef.current, { cacheBust: true, pixelRatio: 2 });
      const link = document.createElement("a");
      link.download = `${poster.title.replace(/\s+/g, "_").toLowerCase()}_poster.png`;
      link.href = dataUrl;
      link.click();
    } catch (err: any) {
      setError(err.message || "Download failed");
    } finally {
      setDownloadingPoster(false);
    }
  };

  const handleReply = async () => {
    if (!comment.trim()) return;
    setReplying(true);
    setError(null);
    try {
      const text = await suggestReply(comment, postContext || null, tone || null);
      setReply(text);
    } catch (err: any) {
      setError(err.message || "Reply failed");
    } finally {
      setReplying(false);
    }
  };

  const copyReply = async () => {
    await navigator.clipboard.writeText(reply);
    setCopiedReply(true);
    setTimeout(() => setCopiedReply(false), 1500);
  };

  return (
    <div className="h-[calc(100vh-2rem)] flex gap-4">
      {/* Column 1: Story list */}
      <section className="w-1/3 min-w-[280px] max-w-md flex flex-col overflow-hidden rounded-[var(--radius)] border border-border bg-[var(--surface-deck)]">
        <div className="border-b border-border px-5 py-4">
          <h2 className="text-[17px] font-semibold tracking-tight">Inbox</h2>
          <p className="mt-1 text-xs text-[var(--muted)]">Select a story to work with</p>
        </div>
        <div className="flex-1 overflow-y-auto divide-y divide-border">
          {loadingStories ? (
            <div className="p-8 text-center text-sm text-[var(--muted)]">Loading stories...</div>
          ) : stories.length === 0 ? (
            <div className="p-8 text-center text-sm text-[var(--muted)]">No pending stories.</div>
          ) : (
            stories.map((story) => (
              <button
                key={story.id}
                onClick={() => setSelected(story)}
                className={`w-full border-l-2 p-4 text-left transition-colors hover:bg-foreground/[0.035] ${
                  selected?.id === story.id ? "border-primary bg-primary/[0.08]" : "border-transparent"
                }`}
              >
                <h3 className="text-sm font-semibold leading-snug line-clamp-2">{story.headline}</h3>
                <p className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-[var(--muted)]">
                  <span className="chip">{story.items[0]?.source_name || "Manual idea"}</span>
                  <span aria-hidden="true"> · </span>
                  <span className="font-mono">{story.items.length} source{story.items.length !== 1 ? "s" : ""}</span>
                </p>
              </button>
            ))
          )}
        </div>
      </section>

      {/* Column 2: Post / Poster tabs */}
      <section className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-[var(--radius)] border border-border bg-[var(--surface-deck)]">
        <div className="flex items-center justify-between gap-3 border-b border-border px-5">
          <div className="flex items-center gap-1">
            <button
              onClick={() => setActiveTab("post")}
              className={`-mb-px border-b-2 px-4 py-4 text-sm font-semibold transition-colors ${
                activeTab === "post" ? "border-primary text-primary" : "border-transparent text-[var(--muted)] hover:text-foreground"
              }`}
            >
              Post
            </button>
            <button
              onClick={() => setActiveTab("poster")}
              className={`-mb-px border-b-2 px-4 py-4 text-sm font-semibold transition-colors ${
                activeTab === "poster" ? "border-primary text-primary" : "border-transparent text-[var(--muted)] hover:text-foreground"
              }`}
            >
              Poster
            </button>
          </div>
          {activeTab === "post" && selected && (
            <button
              onClick={handleRewrite}
              disabled={rewriting}
              className="btn-primary my-2"
            >
              {rewriting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              Rewrite
            </button>
          )}
          {activeTab === "poster" && (
            <div className="flex items-center gap-2 py-2">
              <button
                onClick={downloadPoster}
                disabled={downloadingPoster || !poster}
                className="btn-ghost"
              >
                {downloadingPoster ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                Download PNG
              </button>
              <button
                onClick={handleGeneratePoster}
                disabled={generatingPoster}
                className="btn-primary"
              >
                {generatingPoster ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Image className="w-4 h-4" />}
                Generate
              </button>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {error && (
            <div role="alert" className="flex flex-wrap items-center gap-3 rounded-[var(--radius)] border border-[color-mix(in_srgb,var(--destructive)_35%,var(--border))] bg-[color-mix(in_srgb,var(--destructive)_8%,transparent)] px-4 py-3 text-sm text-[var(--destructive)]">
              <span className="chip">Error</span>
              <p className="m-0">{error}</p>
            </div>
          )}

          {activeTab === "post" ? (
            selected ? (
              <>
                <div className="field-well p-4">
                  <h3 className="text-[15px] font-semibold tracking-tight">{selected.headline}</h3>
                  <ul className="mt-3 space-y-2">
                    {selected.items.map((item) => (
                      <li key={item.id} className="text-sm text-foreground/70">
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:underline"
                        >
                          {item.title}
                        </a>
                        <span className="ml-2 text-xs text-[var(--muted)]">({item.source_name})</span>
                      </li>
                    ))}
                    {selected.items.length === 0 && (
                      <li className="text-sm italic text-[var(--muted)]">No linked sources.</li>
                    )}
                  </ul>
                </div>

                <div>
                  <label className="mb-2 block text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">
                    Length
                  </label>
                  <div className="mb-5 flex flex-wrap gap-1 rounded-[var(--radius)] border border-border bg-[var(--surface-recessed)] p-1" role="group" aria-label="Post length">
                    {([
                      { label: "Short · under 280", value: "short" },
                      { label: "Long · essay", value: "long" },
                    ] as const).map((option) => {
                      const active = postLength === option.value;
                      return (
                        <button
                          key={option.value}
                          onClick={() => setPostLength(option.value)}
                          aria-pressed={active}
                          className={`min-h-9 rounded-[calc(var(--radius)-4px)] border px-3 py-1.5 text-xs font-medium transition-colors ${
                            active
                              ? "border-border bg-[var(--surface-deck)] text-foreground"
                              : "border-transparent text-[var(--muted)] hover:bg-foreground/[0.035] hover:text-foreground"
                          }`}
                        >
                          {option.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div>
                  <label className="mb-2 block text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">
                    Tone
                  </label>
                  <div className="mb-3 flex flex-wrap gap-1 rounded-[var(--radius)] border border-border bg-[var(--surface-recessed)] p-1" role="group" aria-label="Tone presets">
                    {TONE_PRESETS.map((preset) => {
                      const active = tone === preset.value;
                      return (
                        <button
                          key={preset.value}
                          onClick={() => setTone(active ? "" : preset.value)}
                          aria-pressed={active}
                          className={`min-h-9 rounded-[calc(var(--radius)-4px)] border px-3 py-1.5 text-xs font-medium transition-colors ${
                            active
                              ? "border-border bg-[var(--surface-deck)] text-foreground"
                              : "border-transparent text-[var(--muted)] hover:bg-foreground/[0.035] hover:text-foreground"
                          }`}
                        >
                          {preset.label}
                        </button>
                      );
                    })}
                  </div>
                  <input
                    type="text"
                    value={tone}
                    onChange={(e) => setTone(e.target.value)}
                    placeholder="Or type a custom tone..."
                    className="field-well min-h-11 w-full px-3 py-2 text-sm placeholder:text-[var(--muted)] focus:outline-none"
                  />
                </div>

                {post && (
                  <div className="field-well p-4">
                    <div className="mb-2 flex items-center justify-between">
                      <span className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">
                        Draft post
                      </span>
                      <span className="font-mono text-xs text-[var(--muted)]">
                        {postLength === "short" ? `${post.length}/280` : `${post.length} / 4000`}
                      </span>
                    </div>
                    <p className="text-foreground whitespace-pre-wrap leading-relaxed">{post}</p>
                    <button
                      onClick={copyPost}
                      className="mt-4 inline-flex items-center gap-2 rounded-lg border border-transparent px-2 py-1 text-xs text-[var(--muted)] transition-colors hover:border-border hover:text-foreground disabled:opacity-40"
                    >
                      {copiedPost ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                      {copiedPost ? "Copied" : "Copy post"}
                    </button>
                  </div>
                )}
              </>
            ) : (
              <div className="flex h-full items-center justify-center p-8 text-center text-sm text-[var(--muted)]">
                Select a story from the inbox.
              </div>
            )
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-1 rounded-[var(--radius)] border border-border bg-[var(--surface-recessed)] p-1" role="group" aria-label="Poster source">
                <button
                  onClick={() => setPosterMode("story")}
                  aria-pressed={posterMode === "story"}
                  className={`min-h-9 rounded-[calc(var(--radius)-4px)] border px-3 py-1.5 text-xs font-medium transition-colors ${
                    posterMode === "story" ? "border-border bg-[var(--surface-deck)] text-foreground" : "border-transparent text-[var(--muted)] hover:bg-foreground/[0.035] hover:text-foreground"
                  }`}
                >
                  From story
                </button>
                <button
                  onClick={() => setPosterMode("manual")}
                  aria-pressed={posterMode === "manual"}
                  className={`min-h-9 rounded-[calc(var(--radius)-4px)] border px-3 py-1.5 text-xs font-medium transition-colors ${
                    posterMode === "manual" ? "border-border bg-[var(--surface-deck)] text-foreground" : "border-transparent text-[var(--muted)] hover:bg-foreground/[0.035] hover:text-foreground"
                  }`}
                >
                  Manual topic
                </button>
              </div>

              {posterMode === "story" ? (
                selected ? (
                  <div className="field-well p-4">
                    <h3 className="text-[15px] font-semibold tracking-tight">{selected.headline}</h3>
                    <p className="mt-1 font-mono text-xs text-[var(--muted)]">{selected.items.length} linked source(s)</p>
                  </div>
                ) : (
                  <div className="field-well p-4 text-sm text-[var(--muted)]">
                    Select a story from the inbox.
                  </div>
                )
              ) : (
                <div className="space-y-3">
                  <input
                    type="text"
                    value={manualTopic}
                    onChange={(e) => setManualTopic(e.target.value)}
                    placeholder="Topic, e.g. CAGR vs XIRR"
                    className="field-well min-h-11 w-full px-3 py-2 text-sm placeholder:text-[var(--muted)] focus:outline-none"
                  />
                  <textarea
                    value={manualBullets}
                    onChange={(e) => setManualBullets(e.target.value)}
                    placeholder="Paste raw bullet points, one per line..."
                    rows={5}
                    className="field-well min-h-24 w-full resize-none px-3 py-2 text-sm placeholder:text-[var(--muted)] focus:outline-none"
                  />
                </div>
              )}

              <div>
                <label className="mb-2 block text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">
                  Poster style
                </label>
                <div className="flex flex-wrap gap-1 rounded-[var(--radius)] border border-border bg-[var(--surface-recessed)] p-1" role="group" aria-label="Poster style">
                  {POSTER_STYLES.map((s) => {
                    const active = posterStyle === s.value;
                    return (
                      <button
                        key={s.value}
                        onClick={() => setPosterStyle(s.value)}
                        aria-pressed={active}
                        className={`min-h-9 rounded-[calc(var(--radius)-4px)] border px-3 py-1.5 text-xs font-medium transition-colors ${
                          active
                            ? "border-border bg-[var(--surface-deck)] text-foreground"
                            : "border-transparent text-[var(--muted)] hover:bg-foreground/[0.035] hover:text-foreground"
                        }`}
                      >
                        {s.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {poster && (
                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
                    <Lightbulb className="w-3.5 h-3.5" />
                    <span>Preview is scaled down. Downloaded PNG is 1080×1350.</span>
                  </div>
                  <div className="overflow-auto rounded-[var(--radius)] border border-border bg-[var(--surface-deck)] p-4">
                    <div className="origin-top-left scale-[0.35] sm:scale-[0.45]">
                      <PosterCard poster={poster} variant={posterTheme ?? undefined} />
                    </div>
                  </div>
                  {/* Hidden full-size element for capture — avoids scale/clip issues */}
                  <div className="fixed -left-[9999px] top-0" aria-hidden="true">
                    <div ref={posterRef}>
                      <PosterCard poster={poster} variant={posterTheme ?? undefined} />
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </section>

      {/* Column 3: Reply */}
      <section className="w-1/3 min-w-[280px] max-w-md flex flex-col overflow-hidden rounded-[var(--radius)] border border-border bg-[var(--surface-deck)]">
        <div className="border-b border-border px-5 py-4">
          <h2 className="text-[17px] font-semibold tracking-tight">Reply helper</h2>
          <p className="mt-1 text-xs text-[var(--muted)]">Paste a comment; AI suggests a reply.</p>
        </div>
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          <div>
            <label className="mb-2 block text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">
              Comment
            </label>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Paste the comment here..."
              rows={4}
              className="field-well min-h-24 w-full resize-none px-3 py-2 text-sm placeholder:text-[var(--muted)] focus:outline-none"
            />
          </div>

          <button
            onClick={handleReply}
            disabled={replying || !comment.trim()}
            className="btn-ink w-full"
          >
            {replying ? <RefreshCw className="w-4 h-4 animate-spin" /> : <MessageSquare className="w-4 h-4" />}
            Suggest reply
          </button>

          {reply && (
            <div className="field-well p-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">Suggested reply</span>
                <span className="font-mono text-xs text-[var(--muted)]">{reply.length}/280</span>
              </div>
              <p className="text-foreground whitespace-pre-wrap leading-relaxed">{reply}</p>
              <button
                onClick={copyReply}
                className="mt-4 inline-flex items-center gap-2 rounded-lg border border-transparent px-2 py-1 text-xs text-[var(--muted)] transition-colors hover:border-border hover:text-foreground disabled:opacity-40"
              >
                {copiedReply ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                {copiedReply ? "Copied" : "Copy reply"}
              </button>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
