"use client";

import { useEffect, useState } from "react";
import { Check, RefreshCw, Send, ShieldCheck, XCircle } from "lucide-react";
import {
  approveRedditPM,
  decideReddit,
  fetchRedditRights,
  renderRedditPM,
  type RedditRight,
} from "@/lib/api";

const STATES = [
  "candidate",
  "pm_approved",
  "sent",
  "review",
  "granted",
  "denied",
  "expired",
] as const;

export default function RedditPage() {
  const [state, setState] = useState<string>("candidate");
  const [rights, setRights] = useState<RedditRight[]>([]);
  const [selected, setSelected] = useState<RedditRight | null>(null);
  const [loading, setLoading] = useState(true);
  const [pmText, setPmText] = useState("");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = async (s: string) => {
    setLoading(true);
    setError(null);
    try {
      const rows = await fetchRedditRights(s);
      setRights(rows);
      setSelected((prev) => rows.find((r) => r.post_url === prev?.post_url) ?? null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load queue");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(state);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  useEffect(() => {
    if (!selected) {
      setPmText("");
      return;
    }
    setPmText(
      selected.pm_text && selected.pm_text.trim()
        ? selected.pm_text
        : renderRedditPM(
            selected.author,
            selected.title || "your post",
            selected.subreddit,
          ),
    );
  }, [selected]);

  const refresh = () => load(state);

  const handleApprove = async () => {
    if (!selected || !pmText.trim()) return;
    setWorking(true);
    setError(null);
    setNotice(null);
    try {
      await approveRedditPM(selected.post_url, pmText.trim());
      setNotice("PM approved. The sender transmits this exact text.");
      setSelected(null);
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Approve failed");
    } finally {
      setWorking(false);
    }
  };

  const handleDecide = async (verdict: "granted" | "denied") => {
    if (!selected) return;
    setWorking(true);
    setError(null);
    setNotice(null);
    try {
      await decideReddit(selected.post_url, verdict);
      setNotice(
        verdict === "denied"
          ? "Denied. This author is opted out — their posts stay candidate forever."
          : "Granted. This post may now enter story evidence.",
      );
      setSelected(null);
      await refresh();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Decide failed");
    } finally {
      setWorking(false);
    }
  };

  return (
    <div className="h-[calc(100vh-2rem)] flex gap-4">
      {/* Column 1: queue */}
      <section className="w-1/3 min-w-[280px] max-w-md flex flex-col overflow-hidden rounded-[var(--radius)] border border-border bg-[var(--surface-deck)]">
        <div className="border-b border-border px-5 py-4">
          <h2 className="text-[17px] font-semibold tracking-tight">Reddit permissions</h2>
          <p className="mt-1 text-xs text-[var(--muted)]">
            Nothing sends without your per-PM approval. Dry-run unless the kill switch is live.
          </p>
          <div className="mt-3 flex flex-wrap gap-1" role="group" aria-label="Rights state filter">
            {STATES.map((s) => {
              const active = state === s;
              return (
                <button
                  key={s}
                  onClick={() => setState(s)}
                  aria-pressed={active}
                  className={`min-h-8 rounded-[calc(var(--radius)-4px)] border px-2.5 py-1 font-mono text-[11px] transition-colors ${
                    active
                      ? "border-border bg-[var(--surface-recessed)] text-foreground"
                      : "border-transparent text-[var(--muted)] hover:bg-foreground/[0.035] hover:text-foreground"
                  }`}
                >
                  {s}
                </button>
              );
            })}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto divide-y divide-border">
          {loading ? (
            <div className="p-8 text-center text-sm text-[var(--muted)]">Loading queue...</div>
          ) : rights.length === 0 ? (
            <div className="p-8 text-center text-sm text-[var(--muted)]">
              No {state} posts. <button onClick={refresh} className="underline">Reload</button>
            </div>
          ) : (
            rights.map((row) => (
              <button
                key={row.post_url}
                onClick={() => setSelected(row)}
                className={`w-full border-l-2 p-4 text-left transition-colors hover:bg-foreground/[0.035] ${
                  selected?.post_url === row.post_url
                    ? "border-primary bg-primary/[0.08]"
                    : "border-transparent"
                }`}
              >
                <h3 className="text-sm font-semibold leading-snug line-clamp-2">
                  {row.title || row.post_url}
                </h3>
                <p className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-[var(--muted)]">
                  <span className="chip">u/{row.author}</span>
                  <span className="chip">r/{row.subreddit}</span>
                </p>
              </button>
            ))
          )}
        </div>
      </section>

      {/* Column 2: exact-text review */}
      <section className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-[var(--radius)] border border-border bg-[var(--surface-deck)]">
        <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-4">
          <div>
            <h2 className="text-[17px] font-semibold tracking-tight">Review PM</h2>
            <p className="mt-1 text-xs text-[var(--muted)]">
              What you approve here is transmitted exactly — never reworded.
            </p>
          </div>
          <button onClick={refresh} disabled={loading} className="btn-ghost" aria-label="Reload queue">
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {error && (
            <div role="alert" className="flex flex-wrap items-center gap-3 rounded-[var(--radius)] border border-[color-mix(in_srgb,var(--destructive)_35%,var(--border))] bg-[color-mix(in_srgb,var(--destructive)_8%,transparent)] px-4 py-3 text-sm text-[var(--destructive)]">
              <span className="chip">Error</span>
              <p className="m-0">{error}</p>
            </div>
          )}
          {notice && (
            <div role="status" className="flex flex-wrap items-center gap-3 rounded-[var(--radius)] border border-border bg-[var(--surface-recessed)] px-4 py-3 text-sm">
              <Check className="w-4 h-4" />
              <p className="m-0">{notice}</p>
            </div>
          )}

          {!selected ? (
            <div className="flex h-full items-center justify-center p-8 text-center text-sm text-[var(--muted)]">
              Select a post from the queue.
            </div>
          ) : (
            <>
              <div className="field-well p-4">
                <h3 className="text-[15px] font-semibold tracking-tight">
                  {selected.title || "Untitled post"}
                </h3>
                <p className="mt-1 font-mono text-xs text-[var(--muted)]">
                  u/{selected.author} on r/{selected.subreddit} · {selected.state}
                </p>
                <a
                  href={selected.post_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 block break-all text-sm hover:underline"
                >
                  {selected.post_url}
                </a>
                {selected.excerpt && (
                  <p className="mt-3 text-sm text-foreground/70 line-clamp-4">{selected.excerpt}</p>
                )}
              </div>

              <div>
                <label
                  htmlFor="reddit-pm-text"
                  className="mb-2 block text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted)]"
                >
                  Exact PM text
                </label>
                <textarea
                  id="reddit-pm-text"
                  value={pmText}
                  onChange={(e) => setPmText(e.target.value)}
                  rows={7}
                  className="field-well min-h-32 w-full px-3 py-2 font-mono text-[13px] leading-relaxed focus:outline-none"
                />
                <p className="mt-1 font-mono text-xs text-[var(--muted)]">{pmText.length} chars</p>
              </div>

              <div className="flex flex-wrap gap-2">
                {(state === "candidate" || selected.state === "candidate") && (
                  <button
                    onClick={handleApprove}
                    disabled={working || !pmText.trim()}
                    className="btn-primary"
                  >
                    {working ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                    Approve this text
                  </button>
                )}
                {(state === "review" || selected.state === "review") && (
                  <>
                    <button
                      onClick={() => handleDecide("granted")}
                      disabled={working}
                      className="btn-primary"
                    >
                      <ShieldCheck className="w-4 h-4" />
                      Granted
                    </button>
                    <button
                      onClick={() => handleDecide("denied")}
                      disabled={working}
                      className="btn-ghost"
                    >
                      <XCircle className="w-4 h-4" />
                      Denied (opts author out)
                    </button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
