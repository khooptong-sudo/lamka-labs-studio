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
