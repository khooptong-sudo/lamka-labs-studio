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
      const text = await rewriteStoryToPost(selected.id, tone || null);
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
      <section className="w-1/3 min-w-[280px] max-w-md flex flex-col glass-panel rounded-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-border bg-foreground/[0.02]">
          <h2 className="text-lg font-bold tracking-wide">Inbox</h2>
          <p className="text-xs text-foreground/50 mt-1">Select a story to work with</p>
        </div>
        <div className="flex-1 overflow-y-auto divide-y divide-border/50">
          {loadingStories ? (
            <div className="p-8 text-center text-foreground/50 text-sm">Loading stories...</div>
          ) : stories.length === 0 ? (
            <div className="p-8 text-center text-foreground/50 text-sm">No pending stories.</div>
          ) : (
            stories.map((story) => (
              <button
                key={story.id}
                onClick={() => setSelected(story)}
                className={`w-full text-left p-4 transition-colors hover:bg-foreground/[0.03] ${
                  selected?.id === story.id ? "bg-primary/10 border-l-4 border-primary" : "border-l-4 border-transparent"
                }`}
              >
                <h3 className="font-semibold text-sm leading-snug line-clamp-2">{story.headline}</h3>
                <p className="text-[11px] text-foreground/40 mt-2 uppercase tracking-wider">
                  {story.items[0]?.source_name || "Manual idea"} · {story.items.length} source{story.items.length !== 1 ? "s" : ""}
                </p>
              </button>
            ))
          )}
        </div>
      </section>

      {/* Column 2: Post / Poster tabs */}
      <section className="flex-1 flex flex-col glass-panel rounded-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-border bg-foreground/[0.02] flex justify-between items-center">
          <div className="flex items-center gap-1">
            <button
              onClick={() => setActiveTab("post")}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === "post" ? "bg-primary text-primary-foreground" : "text-foreground/70 hover:bg-foreground/[0.05]"
              }`}
            >
              Post
            </button>
            <button
              onClick={() => setActiveTab("poster")}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === "poster" ? "bg-primary text-primary-foreground" : "text-foreground/70 hover:bg-foreground/[0.05]"
              }`}
            >
              Poster
            </button>
          </div>
          {activeTab === "post" && selected && (
            <button
              onClick={handleRewrite}
              disabled={rewriting}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
            >
              {rewriting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              Rewrite
            </button>
          )}
          {activeTab === "poster" && (
            <div className="flex items-center gap-2">
              <button
                onClick={downloadPoster}
                disabled={downloadingPoster || !poster}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-secondary text-secondary-foreground text-sm font-medium hover:bg-secondary/80 disabled:opacity-50"
              >
                {downloadingPoster ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                Download PNG
              </button>
              <button
                onClick={handleGeneratePoster}
                disabled={generatingPoster}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
              >
                {generatingPoster ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Image className="w-4 h-4" />}
                Generate
              </button>
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {error && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-3 text-sm text-red-400">
              {error}
            </div>
          )}

          {activeTab === "post" ? (
            selected ? (
              <>
                <div className="rounded-xl bg-foreground/[0.03] p-4 border border-border/50">
                  <h3 className="font-semibold text-foreground">{selected.headline}</h3>
                  <ul className="mt-3 space-y-2">
                    {selected.items.map((item) => (
                      <li key={item.id} className="text-sm text-foreground/70">
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:text-primary hover:underline"
                        >
                          {item.title}
                        </a>
                        <span className="text-foreground/40 ml-2 text-xs">({item.source_name})</span>
                      </li>
                    ))}
                    {selected.items.length === 0 && (
                      <li className="text-sm text-foreground/40 italic">No linked sources.</li>
                    )}
                  </ul>
                </div>

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-foreground/50 mb-2">
                    Tone
                  </label>
                  <div className="flex flex-wrap gap-2 mb-3">
                    {TONE_PRESETS.map((preset) => {
                      const active = tone === preset.value;
                      return (
                        <button
                          key={preset.value}
                          onClick={() => setTone(active ? "" : preset.value)}
                          className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                            active
                              ? "bg-primary text-primary-foreground"
                              : "bg-foreground/[0.05] text-foreground/70 hover:bg-foreground/[0.10]"
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
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                </div>

                {post && (
                  <div className="rounded-xl bg-foreground/[0.03] border border-border/50 p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold uppercase tracking-wider text-foreground/50">
                        Draft post
                      </span>
                      <span className="text-xs text-foreground/40">{post.length}/280</span>
                    </div>
                    <p className="text-foreground whitespace-pre-wrap leading-relaxed">{post}</p>
                    <button
                      onClick={copyPost}
                      className="mt-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-secondary text-secondary-foreground text-xs font-medium hover:bg-secondary/80"
                    >
                      {copiedPost ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                      {copiedPost ? "Copied" : "Copy post"}
                    </button>
                  </div>
                )}
              </>
            ) : (
              <div className="h-full flex items-center justify-center text-foreground/40 text-sm">
                Select a story from the inbox.
              </div>
            )
          ) : (
            <>
              <div className="flex items-center gap-2 mb-2">
                <button
                  onClick={() => setPosterMode("story")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
                    posterMode === "story" ? "bg-primary text-primary-foreground" : "bg-foreground/[0.05] text-foreground/70"
                  }`}
                >
                  From story
                </button>
                <button
                  onClick={() => setPosterMode("manual")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
                    posterMode === "manual" ? "bg-primary text-primary-foreground" : "bg-foreground/[0.05] text-foreground/70"
                  }`}
                >
                  Manual topic
                </button>
              </div>

              {posterMode === "story" ? (
                selected ? (
                  <div className="rounded-xl bg-foreground/[0.03] p-4 border border-border/50">
                    <h3 className="font-semibold text-foreground">{selected.headline}</h3>
                    <p className="text-xs text-foreground/50 mt-1">{selected.items.length} linked source(s)</p>
                  </div>
                ) : (
                  <div className="rounded-xl bg-foreground/[0.03] p-4 border border-border/50 text-sm text-foreground/50">
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
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                  <textarea
                    value={manualBullets}
                    onChange={(e) => setManualBullets(e.target.value)}
                    placeholder="Paste raw bullet points, one per line..."
                    rows={5}
                    className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-foreground/50 mb-2">
                  Poster style
                </label>
                <div className="flex flex-wrap gap-2">
                  {POSTER_STYLES.map((s) => {
                    const active = posterStyle === s.value;
                    return (
                      <button
                        key={s.value}
                        onClick={() => setPosterStyle(s.value)}
                        className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                          active
                            ? "bg-primary text-primary-foreground"
                            : "bg-foreground/[0.05] text-foreground/70 hover:bg-foreground/[0.10]"
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
                  <div className="flex items-center gap-2 text-xs text-foreground/50">
                    <Lightbulb className="w-3.5 h-3.5" />
                    <span>Preview is scaled down. Downloaded PNG is 1080×1350.</span>
                  </div>
                  <div className="overflow-auto rounded-xl border border-border bg-background p-4">
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
      <section className="w-1/3 min-w-[280px] max-w-md flex flex-col glass-panel rounded-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-border bg-foreground/[0.02]">
          <h2 className="text-lg font-bold tracking-wide">Reply helper</h2>
          <p className="text-xs text-foreground/50 mt-1">Paste a comment; AI suggests a reply.</p>
        </div>
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          <div>
            <label className="block text-xs font-bold uppercase tracking-wider text-foreground/50 mb-2">
              Comment
            </label>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Paste the comment here..."
              rows={4}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none"
            />
          </div>

          <button
            onClick={handleReply}
            disabled={replying || !comment.trim()}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
          >
            {replying ? <RefreshCw className="w-4 h-4 animate-spin" /> : <MessageSquare className="w-4 h-4" />}
            Suggest reply
          </button>

          {reply && (
            <div className="rounded-xl bg-foreground/[0.03] border border-border/50 p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-bold uppercase tracking-wider text-foreground/50">Suggested reply</span>
                <span className="text-xs text-foreground/40">{reply.length}/280</span>
              </div>
              <p className="text-foreground whitespace-pre-wrap leading-relaxed">{reply}</p>
              <button
                onClick={copyReply}
                className="mt-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-md bg-secondary text-secondary-foreground text-xs font-medium hover:bg-secondary/80"
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
