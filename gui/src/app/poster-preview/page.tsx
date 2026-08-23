"use client";

/**
 * Local harness for the poster layout. It renders every variant against a
 * worst-case poster (long summary, five sections, five bullets each) so
 * overflow past the fixed 1080x1350 frame is visible without running the
 * worker or spending an LLM call. Not linked from the app.
 */

import PosterCard, { POSTER_THEMES, type Poster } from "@/components/PosterCard";

const SAMPLE: Poster = {
  title: "Stock Picks Unveiled: Jayaswal Neco & More",
  subtitle: "Understanding Analyst Recommendations and Market Signals",
  summary:
    "Market analysts published a fresh set of short-term stock recommendations ahead of Monday trading, with Jayaswal Neco Industries among the two names singled out for attention. The calls lean on a mix of technical chart patterns and fundamental screening, and were circulated through the usual financial media channels that retail traders follow. Recommendations of this kind describe what an analyst expects, not what the market is obliged to do, and they carry no guarantee of outcome. Readers should treat them as one input among several rather than as instructions, and should check the underlying reasoning against their own research before acting on any of it.",
  sections: [
    {
      heading: "What Happened",
      bullets: [
        "Market analysts released fresh stock recommendations for Monday trading.",
        "Jayaswal Neco Industries is among the two stocks highlighted.",
        "These picks are based on technical and fundamental analysis.",
        "Such recommendations are common in financial media to guide traders.",
        "The calls were published ahead of the opening bell.",
      ],
    },
    {
      heading: "Why It Matters",
      bullets: [
        "Recommendations can influence short-term trading decisions.",
        "They reflect current market sentiment and analyst views.",
        "Understanding them helps in learning market analysis techniques.",
        "Always consider your own research before acting.",
        "Coverage volume often moves a small-cap more than the call itself.",
      ],
    },
    {
      heading: "Educational Takeaway",
      bullets: [
        "Learn how analysts use charts, patterns, and fundamentals.",
        "Recognize that recommendations are opinions, not facts.",
        "Study historical performance to see patterns, not guarantees.",
        "Focus on risk management and diversification.",
        "Track how often a given analyst's calls actually play out.",
      ],
    },
    {
      heading: "What To Watch",
      bullets: [
        "Monitor the stock's price movement relative to support and resistance.",
        "Track company news, earnings, and sector trends.",
        "Note market indices and broader economic indicators.",
        "Observe trading volumes for confirmation.",
        "Watch for revisions that quietly walk an earlier call back.",
      ],
    },
    {
      heading: "Before You Act",
      bullets: [
        "Nothing here is a recommendation to buy or sell.",
        "Position sizing matters more than entry timing for most beginners.",
        "Check whether the analyst discloses a position in the stock.",
        "Consider the tax treatment of short holding periods.",
        "Speak to a registered adviser about your own circumstances.",
      ],
    },
  ],
  footer: "For educational purposes only. Not financial advice. Always do your own research.",
  style: "light",
};

export default function PosterPreviewPage() {
  return (
    <div className="p-8 space-y-12 bg-neutral-200">
      {POSTER_THEMES.map((variant, index) => (
        <div key={variant.name} className="space-y-2">
          <p className="font-mono text-sm text-black">
            {variant.name} · layout={variant.layout} · scenery={index % 9}
          </p>
          {/* A red frame at exactly 1350px: content crossing it is overflow. */}
          <div className="relative w-[1080px] outline outline-2 outline-red-600">
            <PosterCard poster={SAMPLE} variant={{ ...variant, scenery: index % 9 }} />
          </div>
        </div>
      ))}
    </div>
  );
}
