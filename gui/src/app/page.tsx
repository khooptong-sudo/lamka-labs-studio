import { Calendar, TrendingUp, Users, Video, FileText, Inbox } from "lucide-react";
import AddIdeaForm from "@/components/AddIdeaForm";
import GenerateDraftButton from "@/components/GenerateDraftButton";
import QueueToggle from "@/components/QueueToggle";
import { WORKER_URL } from "@/lib/api";

export default async function Home() {
  let stories = [];
  let analytics = {};

  try {
    const res = await fetch(`${WORKER_URL}/stories`, { cache: "no-store" });
    if (res.ok) {
      stories = await res.json();
    }
    const analyticsRes = await fetch(`${WORKER_URL}/youtube/analytics`, { cache: "no-store" });
    if (analyticsRes.ok) {
      analytics = await analyticsRes.json();
    }
  } catch (error) {
    console.error("Failed to fetch data from backend:", error);
  }
  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      <header className="flex items-end justify-between border-b border-border pb-5">
        <div>
          <h1 className="text-[27px] font-semibold leading-none tracking-[-0.025em]">Inbox Overview</h1>
          <p className="mt-1 text-sm text-[var(--muted)]">Your content queue and analytics for today.</p>
        </div>
        <div className="flex items-center space-x-4">
          <span className="chip">
            <span className="font-mono">{stories.length}</span>
            Stories pending
          </span>
        </div>
      </header>

      {/* Analytics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {[
          { title: "Total Impressions", value: "2.4M", icon: Users, trend: "+12%" },
          { title: "Drafts Created", value: "12", icon: FileText, trend: "+3" },
          { title: "Videos Rendered", value: "4", icon: Video, trend: "Steady" },
          { title: "Upcoming (Scheduled)", value: "2", icon: Calendar, trend: "Next: 4pm" },
        ].map((stat, i) => (
          <div key={i} className="rounded-[var(--radius)] border border-border bg-[var(--surface-deck)] p-6">
            <div className="flex flex-col h-full">
              <div className="flex items-center justify-between mb-4">
                <span className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--muted)]">{stat.title}</span>
                <stat.icon className="h-4 w-4 text-[var(--muted)]" />
              </div>
              <div className="flex items-baseline space-x-3 mt-auto">
                <h2 className="text-[32px] font-extrabold tracking-tight">{stat.value}</h2>
                <span className="text-xs text-green-400 font-bold bg-green-400/10 px-2 py-1 rounded-md">{stat.trend}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Inbox Feed */}
      <div className="mt-10 overflow-hidden rounded-[var(--radius)] border border-border bg-[var(--surface-deck)]">
        <div className="flex items-center justify-between border-b border-border px-6 py-5">
          <h2 className="text-[17px] font-semibold tracking-tight">Pending Stories <span className="ml-2 font-normal text-[var(--muted)]">Needs Draft</span></h2>
          <AddIdeaForm />
        </div>
        
        <div className="divide-y divide-border">
          {stories.length === 0 ? (
            <div className="flex flex-col items-center justify-center space-y-4 p-12 text-center">
              <Inbox className="h-10 w-10 text-[var(--muted)]" aria-hidden="true" />
              <p className="font-medium text-[var(--muted)]">No pending stories found.</p>
            </div>
          ) : (
            stories.map((story: any) => (
              <div key={story.id} className="flex items-center justify-between p-6 transition-colors hover:bg-foreground/[0.03] group">
                <div className="flex-1 pr-8">
                  <h3 className="text-xl font-semibold leading-snug tracking-tight">{story.headline}</h3>
                  <div className="mt-3 flex items-center gap-4 text-xs font-medium text-[var(--muted)]">
                    <span className="chip">
                      {story.items && story.items.length > 0 ? story.items[0].source_name : "Unknown Source"}
                    </span>
                    <span className="flex items-center font-mono">
                      <Calendar className="mr-1.5 h-3 w-3 opacity-50" />
                      {new Date(story.created_at).toLocaleString()}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transform translate-x-4 group-hover:translate-x-0 transition-all duration-300">
                  <QueueToggle storyId={story.id} initialQueued={!!story.autopilot_queued_at} />
                  <GenerateDraftButton storyId={story.id} storyChannelId={story.channel_id} />
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Analytics Feed */}
      {Object.keys(analytics).length > 0 && (
        <div className="mt-10 overflow-hidden rounded-[var(--radius)] border border-border bg-[var(--surface-deck)]">
          <div className="flex items-center justify-between border-b border-border px-6 py-5">
            <h2 className="text-[17px] font-semibold tracking-tight">YouTube Analytics <span className="ml-2 font-normal text-[var(--muted)]">Real-time</span></h2>
          </div>
          
          <div className="divide-y divide-border">
            {Object.entries(analytics).map(([id, stats]: [string, any]) => (
              <div key={id} className="flex items-center justify-between p-6 transition-colors hover:bg-foreground/[0.03] group">
                <div className="flex-1 pr-8">
                  <h3 className="text-lg font-semibold leading-snug tracking-tight">{stats.title}</h3>
                  <div className="flex items-center space-x-6 mt-3 text-sm text-foreground/60 font-medium">
                    <span className="flex items-center text-primary/80">
                      <Users className="w-4 h-4 mr-2" />
                      {parseInt(stats.views).toLocaleString()} Views
                    </span>
                    <span className="flex items-center text-green-400">
                      <TrendingUp className="w-4 h-4 mr-2" />
                      {parseInt(stats.likes).toLocaleString()} Likes
                    </span>
                    <span className="flex items-center text-foreground/40">
                      <FileText className="w-4 h-4 mr-2" />
                      {parseInt(stats.comments).toLocaleString()} Comments
                    </span>
                  </div>
                </div>
                <div className="flex-shrink-0 text-right">
                   <a href={`https://youtube.com/watch?v=${id}`} target="_blank" rel="noreferrer" className="btn-ghost text-sm">Watch</a>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

