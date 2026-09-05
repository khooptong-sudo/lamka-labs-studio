import { Code2, Server, Terminal, Wrench } from "lucide-react";

export default function DocsPage() {
  return (
    <div className="space-y-8 max-w-5xl pb-10">
      <header className="border-b border-border pb-5">
        <h1 className="text-[27px] font-semibold leading-none tracking-[-0.025em]">Documentation & Runbook</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">Everything you need to know about The Cockpit and Fin-Content Engine.</p>
      </header>

      <div className="space-y-12">
        {/* Section 1: How to Use */}
        <section className="space-y-4">
          <div className="flex items-center gap-3">
            <Terminal className="h-6 w-6 text-[var(--muted)]" />
            <h2 className="text-xl font-semibold tracking-tight">How to Use the Pipeline</h2>
          </div>
          <div className="space-y-4 rounded-[var(--radius)] border border-border bg-[var(--surface-deck)] p-6">
            <p className="text-foreground/80 leading-relaxed">
              The GUI acts as a centralized dashboard to review and trigger video renders. Currently, generation operates in a <strong>manual-first workflow</strong>:
            </p>
            <ol className="list-decimal list-inside space-y-3 text-foreground/80 ml-2">
              <li>
                <strong>Inbox:</strong> View financial stories parsed by the Python worker.
              </li>
              <li>
                <strong>Drafts Queue:</strong> Review the auto-generated scripts and storyboards. The AI uses the <code className="field-well px-1 py-0.5 font-mono text-sm">daisy-days</code> aesthetic profile (minimal, clean, descriptive animations).
              </li>
              <li>
                <strong>Generate YouTube Video:</strong> Clicking this dispatches a job to the local <code className="field-well px-1 py-0.5 font-mono text-sm">/youtube/generate</code> endpoint on the FastAPI worker.
              </li>
              <li>
                <strong>Output:</strong> The worker orchestrates Hyperframes (rendering engine) and outputs an MP4 file into the <code className="field-well px-1 py-0.5 font-mono text-sm">../videos</code> directory on your VPS. You can then download and upload it to YouTube manually.
              </li>
            </ol>
          </div>
        </section>

        {/* Section 2: Architecture & Stack */}
        <section className="space-y-4">
          <div className="flex items-center gap-3">
            <Server className="h-6 w-6 text-[var(--muted)]" />
            <h2 className="text-xl font-semibold tracking-tight">Architecture & Stack</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="rounded-[var(--radius)] border border-border bg-[var(--surface-deck)] p-6">
              <h3 className="text-lg font-bold text-foreground mb-3 flex items-center">
                <Code2 className="w-5 h-5 mr-2 text-[var(--muted)]" />
                Frontend (GUI)
              </h3>
              <ul className="space-y-2 text-sm text-foreground/70">
                <li><strong>Framework:</strong> Next.js 16 (App Router)</li>
                <li><strong>Styling:</strong> Tailwind CSS v4</li>
                <li><strong>Theme:</strong> <code className="field-well px-1 py-0.5 font-mono">next-themes</code> (Light/Dark mode)</li>
                <li><strong>Icons:</strong> Lucide React</li>
              </ul>
            </div>
            <div className="rounded-[var(--radius)] border border-border bg-[var(--surface-deck)] p-6">
              <h3 className="text-lg font-bold text-foreground mb-3 flex items-center">
                <Server className="w-5 h-5 mr-2 text-[var(--muted)]" />
                Backend (Worker)
              </h3>
              <ul className="space-y-2 text-sm text-foreground/70">
                <li><strong>Framework:</strong> FastAPI (Python 3.12+)</li>
                <li><strong>Scheduling:</strong> APScheduler</li>
                <li><strong>Database:</strong> SQLite</li>
                <li><strong>Rendering:</strong> Hyperframes CLI (requires Node.js v20+)</li>
              </ul>
            </div>
          </div>
        </section>

        {/* Section 3: Troubleshooting */}
        <section className="space-y-4">
          <div className="flex items-center gap-3">
            <Wrench className="h-6 w-6 text-[var(--muted)]" />
            <h2 className="text-xl font-semibold tracking-tight">Troubleshooting</h2>
          </div>
          <div className="space-y-6 rounded-[var(--radius)] border border-border bg-[var(--surface-deck)] p-6">
            
            <div className="space-y-2">
              <h3 className="text-md font-bold text-destructive">Infinite Refresh Loop / ChunkLoadError (GUI)</h3>
              <p className="text-sm text-foreground/70 leading-relaxed">
                If the Next.js development server keeps reloading the page infinitely and throwing a <code className="field-well px-1 py-0.5 font-mono">ChunkLoadError</code> in the console, it is due to a caching bug in Next.js Turbopack.
              </p>
              <div className="field-well p-3 font-mono text-xs text-foreground/80">
                1. Stop the Next.js server (Ctrl+C)<br/>
                2. Run: rm -rf .next<br/>
                3. Restart: npm run dev
              </div>
            </div>

            <div className="space-y-2">
              <h3 className="text-md font-bold text-destructive">Hyperframes Rendering Fails (Worker)</h3>
              <p className="text-sm text-foreground/70 leading-relaxed">
                If the backend Python script fails while calling <code className="field-well px-1 py-0.5 font-mono">npx hyperframes render</code>, ensure your VPS is running Node v20+ and Playwright dependencies are installed:
              </p>
              <div className="field-well p-3 font-mono text-xs text-foreground/80">
                cd /opt/fce<br/>
                npx playwright install-deps
              </div>
            </div>

          </div>
        </section>

      </div>
    </div>
  );
}

