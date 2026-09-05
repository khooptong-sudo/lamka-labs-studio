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
          <div className="space-y-6 rounded-[var(--radius)] border border-border bg-[var(--surface-deck)] p-6">
            <p className="text-foreground/80 leading-relaxed">
              Think of this Studio as a <strong>robot film crew</strong>. It reads the news,
              writes scripts, speaks them out loud, draws the pictures, and edits everything
              into a video. <strong>You are the director.</strong> Nothing ever publishes
              itself. Every video waits for you to check it first.
            </p>

            <h3 className="text-lg font-semibold tracking-tight">The 7 rooms</h3>
            <ul className="list-disc list-inside space-y-2 text-foreground/80 ml-2">
              <li><strong>Research:</strong> the news inbox. New stories land here all day, best first.</li>
              <li><strong>Production:</strong> where you order a video. Pick a story, a channel, and a format, then press Build.</li>
              <li><strong>Cinema:</strong> a prompt workshop for making single AI video clips with typed movie-direction words.</li>
              <li><strong>Drafts:</strong> finished videos waiting for your review, with their titles, descriptions, and files.</li>
              <li><strong>X Post:</strong> turns a story into a short post or a long essay, plus picture posters and reply ideas.</li>
              <li><strong>Studio setup:</strong> channels, voices, and blocked words. Change with care.</li>
              <li><strong>Guide:</strong> this page.</li>
            </ul>

            <h3 className="text-lg font-semibold tracking-tight">Your first video, step by step</h3>
            <ol className="list-decimal list-inside space-y-3 text-foreground/80 ml-2">
              <li>Open <strong>Research</strong> and pick a story that looks interesting. Stories with more linked sources give better videos.</li>
              <li>Go to <strong>Production</strong>. Choose a <strong>channel</strong> (Finance, Kids, History, Science, or Mystery).</li>
              <li>Choose a <strong>format</strong>: a vertical <strong>3D Short</strong> (about a minute) or a wide <strong>Story Film</strong>.</li>
              <li>Leave the storyboard box <strong>empty</strong> so the crew writes the script for you. (Paste your own script there only when you want exact control.)</li>
              <li>Press <strong>Build video</strong>. The progress rail walks through script, voice, visuals, and render. This takes a few minutes. One video uses the graphics card at a time, so a second order waits its turn.</li>
              <li>Open <strong>Drafts</strong> when it finishes. Watch the video. Read the title and description. If anything looks wrong, throw it away and build again — that is normal.</li>
              <li>Publish it yourself on YouTube (see below). The Studio never uploads for you.</li>
            </ol>

            <h3 className="text-lg font-semibold tracking-tight">Words you will see</h3>
            <ul className="list-disc list-inside space-y-2 text-foreground/80 ml-2">
              <li><strong>Storyboard:</strong> the written plan — what is said and what is shown, scene by scene.</li>
              <li><strong>Hook:</strong> the first line. It must grab the viewer in seconds.</li>
              <li><strong>Voiceover:</strong> the spoken words over the pictures.</li>
              <li><strong>Render:</strong> the computer drawing every frame into the final <code className="field-well px-1 py-0.5 font-mono text-sm">video.mp4</code> file. The slow part.</li>
              <li><strong>Draft:</strong> a finished video waiting for your yes or no.</li>
              <li><strong>Channel:</strong> which show this is for. Each channel has its own voice and rules.</li>
              <li><strong>Thumbnail:</strong> the cover picture viewers click on. You get two to choose from.</li>
              <li><strong>Tags:</strong> search words that help people find the video.</li>
            </ul>

            <h3 className="text-lg font-semibold tracking-tight">The three video types</h3>
            <ul className="list-disc list-inside space-y-2 text-foreground/80 ml-2">
              <li><strong>3D Short:</strong> vertical, about a minute, cartoon-style 3D pictures. Best for news and explainers. Fastest to make.</li>
              <li><strong>Story Film:</strong> wide landscape, computer-drawn 3D world, slower and calmer. Best for stories and ideas.</li>
              <li><strong>Documentary:</strong> 8 to 12 minutes, built in 3 or 4 acts like a real TV documentary. Best for history, science, and mysteries. Needs a story with good sources, or your own typed notes in the brief box. Slowest and most expensive — save it for stories worth it.</li>
            </ul>

            <h3 className="text-lg font-semibold tracking-tight">Using your own voice</h3>
            <p className="text-foreground/80 leading-relaxed">
              Tired of robot voices? Record yourself reading each scene — one sound file
              per scene, in order — and send them with the <code className="field-well px-1 py-0.5 font-mono text-sm">with-voice</code> job.
              The crew skips its own voice and cuts the pictures to YOUR timing. If a file
              is missing or broken, the job stops loudly instead of guessing. (This door
              is API-only for now; the upload button comes later.)
            </p>

            <h3 className="text-lg font-semibold tracking-tight">Putting a video on YouTube</h3>
            <ol className="list-decimal list-inside space-y-3 text-foreground/80 ml-2">
              <li>In <strong>Drafts</strong>, open your video and copy the <strong>title</strong>, <strong>description</strong>, and <strong>tags</strong>. They also live in a file called <code className="field-well px-1 py-0.5 font-mono text-sm">upload.txt</code> next to the video.</li>
              <li>On YouTube, upload the <code className="field-well px-1 py-0.5 font-mono text-sm">video.mp4</code> file and paste that text in.</li>
              <li>Upload <code className="field-well px-1 py-0.5 font-mono text-sm">thumbnail-a.jpg</code> or <code className="field-well px-1 py-0.5 font-mono text-sm">thumbnail-b.jpg</code> as the cover — whichever you would click yourself.</li>
              <li>Kids channel only: tick <strong>Made for kids</strong> on YouTube. The Studio reminds you in the upload file. This is the law, not a suggestion.</li>
            </ol>

            <h3 className="text-lg font-semibold tracking-tight">Posting on X</h3>
            <ul className="list-disc list-inside space-y-2 text-foreground/80 ml-2">
              <li><strong>Short:</strong> one post under 280 letters. Works for everyone.</li>
              <li><strong>Long · essay:</strong> a hook plus a few short paragraphs and a closing question. Needs a paid X account — free accounts cannot post long text.</li>
              <li><strong>Posters:</strong> square picture cards made from a story or your own bullet points. Download and attach them to posts by hand.</li>
              <li><strong>Replies:</strong> paste a comment you received and get a suggested answer. Always read before sending.</li>
              <li>Posting itself is always copy-paste by you. Nothing here can post for you.</li>
            </ul>

            <h3 className="text-lg font-semibold tracking-tight">When something waits or says no</h3>
            <ul className="list-disc list-inside space-y-2 text-foreground/80 ml-2">
              <li><strong>Waiting:</strong> only one video can use the graphics card at a time. Others queue politely. Writing and voices happen in parallel, so the queue moves.</li>
              <li><strong>Stuck:</strong> a job sitting too long can be cancelled from the job controls. Cancelling never deletes finished work.</li>
              <li><strong>Refused:</strong> the crew says no instead of faking it. A script with invented facts, a silent voice, or a broken picture fails loudly with a reason in the log. Read the reason, fix the input, try again.</li>
            </ul>

            <h3 className="text-lg font-semibold tracking-tight">What costs money</h3>
            <ul className="list-disc list-inside space-y-2 text-foreground/80 ml-2">
              <li><strong>Free:</strong> robot voices, cutting and rendering on your own computer, everything in the Drafts queue.</li>
              <li><strong>Costs credits:</strong> AI-written words and AI-drawn pictures. Documentaries cost the most because they use the most of both.</li>
              <li>The secret keys live in a file called <code className="field-well px-1 py-0.5 font-mono text-sm">.env</code> that is never shared or uploaded anywhere. If a key ever leaks into a chat or a screenshot, replace it.</li>
            </ul>

            <h3 className="text-lg font-semibold tracking-tight">The golden rules</h3>
            <ol className="list-decimal list-inside space-y-3 text-foreground/80 ml-2">
              <li><strong>You are the boss.</strong> Check every video, post, and reply before it goes out. The crew drafts; you decide.</li>
              <li><strong>Never tell people what to do with money.</strong> Explain what happened and why it is interesting. No buy, sell, or invest advice — ever, on any channel.</li>
              <li><strong>Kids channel, kids rules.</strong> Simple words, kind pictures, nothing scary, and always tick Made for kids on upload.</li>
              <li><strong>True stories only.</strong> If the sources do not support it, it does not go in the script.</li>
              <li><strong>When in doubt, throw it out.</strong> Rebuilding is cheap. Publishing garbage is expensive.</li>
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

