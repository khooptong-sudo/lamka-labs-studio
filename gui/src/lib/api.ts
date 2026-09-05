export const WORKER_URL = (process.env.NEXT_PUBLIC_WORKER_URL || "http://127.0.0.1:8000").trim();

export type Story = {
  id: string;
  headline: string;
  status: string;
  channel_id: string;
  created_at: string;
  score: number | null;
  angle: string | null;
  vertical: string | null;
  content_archetype: string | null;
  items: {
    id: string;
    title: string;
    url: string;
    source_name: string;
    published_at: string;
  }[];
};

export async function fetchXStories(): Promise<Story[]> {
  const res = await fetch(`${WORKER_URL}/x/stories`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch stories: ${res.status}`);
  return res.json();
}

export async function setStoryQueued(storyId: string, queued: boolean): Promise<boolean> {
  const res = await fetch(`${WORKER_URL}/stories/${storyId}/queue`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ queued }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new Error(payload.detail || `Queue toggle failed: ${res.status}`);
  }
  const data = await res.json();
  return data.queued;
}

export async function rewriteStoryToPost(storyId: string, tone?: string | null, length?: "short" | "long"): Promise<string> {
  const res = await fetch(`${WORKER_URL}/x/rewrite`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ story_id: storyId, tone: tone || null, length: length || "short" }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new Error(payload.detail || `Rewrite failed: ${res.status}`);
  }
  const data = await res.json();
  return data.post;
}

export async function suggestReply(
  comment: string,
  postContext?: string | null,
  tone?: string | null,
): Promise<string> {
  const res = await fetch(`${WORKER_URL}/x/reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      comment,
      post_context: postContext || null,
      tone: tone || null,
    }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new Error(payload.detail || `Reply failed: ${res.status}`);
  }
  const data = await res.json();
  return data.reply;
}

export type PosterSection = {
  heading: string;
  bullets: string[];
};

export type Poster = {
  title: string;
  subtitle: string;
  summary: string;
  sections: PosterSection[];
  footer: string;
  style: string;
};

export async function generatePosterFromStory(
  storyId: string,
  style?: string | null,
): Promise<Poster> {
  const res = await fetch(`${WORKER_URL}/x/poster/story`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ story_id: storyId, style: style || null }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new Error(payload.detail || `Poster failed: ${res.status}`);
  }
  return res.json();
}

export async function generatePosterFromText(
  topic: string,
  bullets: string[],
  style?: string | null,
): Promise<Poster> {
  const res = await fetch(`${WORKER_URL}/x/poster/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic, bullets, style: style || null }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new Error(payload.detail || `Poster failed: ${res.status}`);
  }
  return res.json();
}

export type RedditRight = {
  post_url: string;
  author: string;
  subreddit: string;
  state: string;
  pm_text: string;
  created_at: string;
  title?: string;
  excerpt?: string;
};

/** Mirror of the worker's PM_TEMPLATE (worker/app/reddit_outreach.py) —
 *  the default draft prefill. The worker stores the owner's edited text
 *  verbatim and the sender transmits it exactly; this never sends anything. */
export const REDDIT_PM_TEMPLATE =
  "Hi u/{author} — I run an educational YouTube channel and your post " +
  '"{title}" (r/{sub}) would make a strong segment. May I adapt it into ' +
  "a narrated video with full on-screen credit to you and a link to your " +
  "post? Reply YES and I'll send you the link when it's live, or NO and " +
  "I'll never ask again. — Min";

export function renderRedditPM(author: string, title: string, sub: string): string {
  return REDDIT_PM_TEMPLATE.split("{author}").join(author)
    .split("{title}").join(title)
    .split("{sub}").join(sub);
}

export async function fetchRedditRights(state = "candidate"): Promise<RedditRight[]> {
  const res = await fetch(`${WORKER_URL}/reddit/rights?state=${encodeURIComponent(state)}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new Error(payload.detail || `Failed to fetch rights: ${res.status}`);
  }
  return res.json();
}

export async function approveRedditPM(postUrl: string, pmText: string): Promise<RedditRight> {
  const res = await fetch(`${WORKER_URL}/reddit/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ post_url: postUrl, pm_text: pmText }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new Error(payload.detail || `Approve failed: ${res.status}`);
  }
  return res.json();
}

export async function decideReddit(
  postUrl: string,
  verdict: "granted" | "denied",
): Promise<RedditRight> {
  const res = await fetch(`${WORKER_URL}/reddit/decide`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ post_url: postUrl, verdict }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new Error(payload.detail || `Decide failed: ${res.status}`);
  }
  return res.json();
}

export async function linkDraftVideo(draftId: string, videoId: string): Promise<string> {
  const res = await fetch(`${WORKER_URL}/drafts/${draftId}/video`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId }),
  });
  if (!res.ok) {
    const payload = await res.json().catch(() => ({}));
    throw new Error(payload.detail || `Video link failed: ${res.status}`);
  }
  const data = await res.json();
  return data.youtube_video_id;
}

export type ArchetypeSummary = {
  archetype: string;
  videos: number;
  total_views: number;
  avg_views: number;
  multiplier: number;
};

export type TopVideo = {
  draft_id: string;
  video_id: string | null;
  headline: string | null;
  archetype: string | null;
  views: number;
};

export type AnalyticsSummary = {
  by_archetype: ArchetypeSummary[];
  top_videos: TopVideo[];
};

export async function fetchAnalyticsSummary(): Promise<AnalyticsSummary | null> {
  try {
    const res = await fetch(`${WORKER_URL}/analytics/summary`, { cache: "no-store" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
