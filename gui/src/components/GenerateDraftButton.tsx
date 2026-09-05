"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";

export default function GenerateDraftButton({
  storyId,
  storyChannelId,
}: {
  storyId: string;
  storyChannelId?: string | null;
}) {
  const params = new URLSearchParams({ story: storyId });
  if (storyChannelId) params.set("channel", storyChannelId);

  return (
    <Link
      href={`/films?${params.toString()}`}
      className="btn-ghost"
    >
      Review research
      <ArrowRight className="h-4 w-4" />
    </Link>
  );
}
