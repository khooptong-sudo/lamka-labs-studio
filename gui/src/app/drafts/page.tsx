"use client";

import { useState, useEffect } from "react";
import { Loader2, PlayCircle, Video, FileText, PlaySquare, Download } from "lucide-react";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

function CopyField({ label, value }: { label: string; value: string }) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "unavailable">("idle");

  async function copy() {
    if (!navigator.clipboard) {
      setCopyState("unavailable");
      setTimeout(() => setCopyState("idle"), 1500);
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      setCopyState("copied");
    } catch {
      setCopyState("unavailable");
    }
    setTimeout(() => setCopyState("idle"), 1500);
  }

  return (
    <div className="mb-3">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-semibold text-[var(--muted)] uppercase tracking-[0.2em]">{label}</span>
        <button
          onClick={copy}
          disabled={!value}
          className="rounded-lg border border-transparent px-2 py-1 text-xs text-[var(--muted)] transition-colors hover:border-border hover:text-foreground disabled:opacity-40"
        >
          {copyState === "copied" ? "Copied" : copyState === "unavailable" ? "Copy unavailable" : "Copy"}
        </button>
      </div>
      <p className="whitespace-pre-wrap text-sm text-foreground/80">{value || "Not generated"}</p>
    </div>
  );
}

export default function DraftsPage() {
  const [drafts, setDrafts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/drafts", { cache: "no-store" })
      .then((res) => res.json())
      .then((data) => {
        setDrafts(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[50vh] space-y-4">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <p className="text-[var(--muted)] tracking-widest uppercase text-xs font-bold animate-pulse">Syncing Database...</p>
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      <header className="border-b border-border pb-5">
        <h1 className="text-[27px] font-semibold leading-none tracking-[-0.025em]">Drafts Queue</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">Review your AI-generated drafts and rendered videos before publishing.</p>
      </header>

      {drafts.length === 0 ? (
        <div className="flex flex-col items-center justify-center space-y-4 rounded-[var(--radius)] border border-border bg-[var(--surface-deck)] p-16 text-center">
          <FileText className="h-10 w-10 text-[var(--muted)]" aria-hidden="true" />
          <p className="text-lg font-medium text-[var(--muted)]">No drafts found. Generate a draft from the Inbox first.</p>
        </div>
      ) : (
        <div className="space-y-6 mt-8">
          {drafts.map((draft) => (
            <DraftCard key={draft.id} draft={draft} />
          ))}
        </div>
      )}
    </div>
  );
}

function DraftCard({ draft }: { draft: any }) {
  const success = draft.status === "published";
  const [activeTab, setActiveTab] = useState<"overview" | "youtube">("overview");
  const [markdownContent, setMarkdownContent] = useState<string | null>(null);
  const [loadingMarkdown, setLoadingMarkdown] = useState(false);

  const loadMarkdown = async () => {
    if (markdownContent) return;
    setLoadingMarkdown(true);
    try {
      const res = await fetch(`/api/videos/story-${draft.story_id}/STORYBOARD.md`);
      if (res.ok) {
        const text = await res.text();
        setMarkdownContent(text);
      } else {
        setMarkdownContent("Failed to load script. Either it hasn't been generated yet or the file is missing.");
      }
    } catch (e) {
      setMarkdownContent("Error fetching script.");
    } finally {
      setLoadingMarkdown(false);
    }
  };

  useEffect(() => {
    if (activeTab === "youtube") {
      loadMarkdown();
    }
  }, [activeTab]);

  const draftBody = draft.body || {};
  const filePath = draftBody.file_path || "Unknown path";

  const audioUrl = `/api/videos/story-${draft.story_id}/audio.mp3`;
  const storyboardUrl = `/api/videos/story-${draft.story_id}/STORYBOARD.md`;

  return (
    <div className="overflow-hidden rounded-[var(--radius)] border border-border bg-[var(--surface-deck)]">
      {/* Card Header */}
      <div className="flex items-start justify-between gap-4 border-b border-border p-6 md:px-8">
        <div>
          <div className="mb-3 flex items-center gap-3">
            <span className={`chip ${success ? "text-[var(--success)]" : "text-primary"}`}>
              {success ? "Published" : "Approved"}
            </span>
            <span className="font-mono text-xs text-[var(--muted)]">ID: {draft.id.substring(0, 8)}</span>
          </div>
          <h2 className="text-[17px] font-semibold tracking-tight">{draft.headline || "Untitled Story"}</h2>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border px-6 md:px-8">
        <button
          onClick={() => setActiveTab("overview")}
          className={`border-b-2 px-6 py-4 text-sm font-semibold uppercase tracking-wider transition-colors ${
            activeTab === "overview" ? "border-primary text-primary" : "border-transparent text-[var(--muted)] hover:text-foreground"
          }`}
        >
          Overview
        </button>
        <button
          onClick={() => setActiveTab("youtube")}
          className={`flex items-center gap-2 border-b-2 px-6 py-4 text-sm font-semibold uppercase tracking-wider transition-colors ${
            activeTab === "youtube" ? "border-[#ff0000] text-[#ff0000]" : "border-transparent text-[var(--muted)] hover:text-foreground"
          }`}
        >
          <PlaySquare className="h-4 w-4" />
          <span>YouTube Package</span>
        </button>
      </div>

      {/* Card Body */}
      <div className="p-6 md:p-8">
        {activeTab === "overview" && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 md:gap-12">
            {/* Draft Content (Left 2/3) */}
            <div className="md:col-span-2 space-y-6">
              <div className="field-well p-5">
                <CopyField label="Title" value={draft.title} />
                <CopyField label="Description" value={draft.description} />
              </div>

              <div>
                <h3 className="text-xs font-semibold text-[var(--muted)] uppercase tracking-[0.2em] mb-3">Video Render Details</h3>
                <div className="field-well space-y-3 p-5 text-[13px] leading-relaxed">
                  <div className="flex items-start">
                    <span className="mr-2 w-24 flex-shrink-0 text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">File</span>
                    <span className="break-all font-mono">{filePath}</span>
                  </div>
                  <div className="flex items-start">
                    <span className="mr-2 w-24 flex-shrink-0 text-xs font-semibold uppercase tracking-wider text-[var(--muted)]">Config</span>
                    <span className="font-mono">{draft.upload_preference}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Action Panel (Right 1/3) */}
            <div className="space-y-4">
              <h3 className="text-xs font-semibold text-[var(--muted)] uppercase tracking-[0.2em] mb-3">Production</h3>

              <div className="field-well flex flex-col items-center space-y-4 p-6 text-center">
                <div className="mb-2 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-primary">
                  <Video className="h-7 w-7" />
                </div>
                <div>
                  <h4 className="font-semibold tracking-wide">{success ? "Published" : "Rendered Successfully"}</h4>
                  <p className="mt-1 text-[11px] font-semibold uppercase tracking-wider text-[var(--muted)]">
                    {success ? "Live" : "Copy the metadata above to publish manually"}
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "youtube" && (
          <div className="space-y-8">
            {/* Audio Preview */}
            <div className="field-well p-6">
              <h3 className="mb-4 flex items-center text-xs font-semibold text-[var(--muted)] uppercase tracking-[0.2em]">
                <PlayCircle className="mr-2 h-4 w-4" /> Voiceover Preview
              </h3>
              <audio controls className="h-12 w-full rounded-lg" src={audioUrl}>
                Your browser does not support the audio element.
              </audio>
            </div>

            {/* Download Assets */}
            <div className="flex gap-4">
              <a href={storyboardUrl} target="_blank" rel="noreferrer" className="flex flex-1 items-center justify-between rounded-[var(--radius)] border border-border bg-[var(--surface-recessed)] p-4 font-semibold tracking-wide transition-colors hover:bg-foreground/[0.035]">
                <span className="flex items-center"><FileText className="mr-3 h-5 w-5 text-[var(--muted)]" /> Download Script</span>
                <Download className="h-5 w-5 text-[var(--muted)]" />
              </a>
              <a href={audioUrl} target="_blank" rel="noreferrer" className="flex flex-1 items-center justify-between rounded-[var(--radius)] border border-border bg-[var(--surface-recessed)] p-4 font-semibold tracking-wide transition-colors hover:bg-foreground/[0.035]">
                <span className="flex items-center"><PlayCircle className="mr-3 h-5 w-5 text-[var(--muted)]" /> Download Audio</span>
                <Download className="h-5 w-5 text-[var(--muted)]" />
              </a>
            </div>

            {/* Script Display */}
            <div className="space-y-4">
              <h3 className="text-xs font-semibold text-[var(--muted)] uppercase tracking-[0.2em]">Storyboard & Script</h3>
              <div className="max-h-[600px] overflow-y-auto rounded-[var(--radius)] border border-border bg-[var(--surface-recessed)] p-6 md:p-8">
                {loadingMarkdown ? (
                  <div className="flex flex-col items-center justify-center h-32 space-y-4">
                    <Loader2 className="w-6 h-6 animate-spin text-primary" />
                    <span className="text-[var(--muted)] text-xs font-bold uppercase tracking-widest">Loading Script...</span>
                  </div>
                ) : (
                  <article className="prose prose-sm md:prose-base dark:prose-invert max-w-none prose-headings:font-black prose-a:text-primary">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {markdownContent || ""}
                    </ReactMarkdown>
                  </article>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
