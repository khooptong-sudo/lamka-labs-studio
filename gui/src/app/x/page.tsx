"use client";

import { useEffect, useState } from "react";
import { Copy, Check, RefreshCw, MessageSquare, Send } from "lucide-react";
import { fetchXStories, rewriteStoryToPost, suggestReply, type Story } from "@/lib/api";

export default function XPage() {
  const [stories, setStories] = useState<Story[]>([]);
  const [selected, setSelected] = useState<Story | null>(null);
  const [loadingStories, setLoadingStories] = useState(true);
  const [post, setPost] = useState("");
  const [rewriting, setRewriting] = useState(false);
  const [tone, setTone] = useState("");
  const [copiedPost, setCopiedPost] = useState(false);

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
          <p className="text-xs text-foreground/50 mt-1">Select a story to rewrite</p>
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

      {/* Column 2: Rewrite */}
      <section className="flex-1 flex flex-col glass-panel rounded-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-border bg-foreground/[0.02] flex justify-between items-center">
          <div>
            <h2 className="text-lg font-bold tracking-wide">Rewrite for X</h2>
            <p className="text-xs text-foreground/50 mt-1">Kimi drafts the post; you copy-paste it.</p>
          </div>
          {selected && (
            <button
              onClick={handleRewrite}
              disabled={rewriting}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
            >
              {rewriting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              Rewrite
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {error && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-3 text-sm text-red-400">
              {error}
            </div>
          )}

          {selected ? (
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
                  Tone (optional)
                </label>
                <input
                  type="text"
                  value={tone}
                  onChange={(e) => setTone(e.target.value)}
                  placeholder="e.g. concise, analyst-educator"
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
          )}
        </div>
      </section>

      {/* Column 3: Reply */}
      <section className="w-1/3 min-w-[280px] max-w-md flex flex-col glass-panel rounded-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-border bg-foreground/[0.02]">
          <h2 className="text-lg font-bold tracking-wide">Reply helper</h2>
          <p className="text-xs text-foreground/50 mt-1">Paste a comment; Kimi suggests a reply.</p>
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
