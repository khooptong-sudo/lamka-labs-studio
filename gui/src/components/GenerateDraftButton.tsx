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
      className="inline-flex items-center gap-2 rounded-xl bg-primary/10 px-4 py-2 text-sm font-semibold text-primary transition-colors hover:bg-primary hover:text-foreground"
    >
      Review research
      <ArrowRight className="h-4 w-4" />
    </Link>
  );
}
