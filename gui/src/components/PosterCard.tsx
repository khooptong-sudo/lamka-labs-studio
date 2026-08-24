"use client";

import { useMemo } from "react";
import type { CSSProperties, ReactNode } from "react";

import { CHIBI_SCENERIES } from "./posterScenery";

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
  theme?: string;
};

/** Masthead kicker above the Lamka Labs lockup. One place to rename it. */
const KICKER = "Finance Explained";

const INK = "#111111";
const MAROON = "#991b1b";
const DISPLAY = "var(--font-poster-display), 'Trebuchet MS', ui-rounded, system-ui, sans-serif";
const BODY = "var(--font-poster-body), ui-rounded, 'Segoe UI', system-ui, sans-serif";

type MarkerKind = "star" | "heart" | "check" | "arrow" | "dot" | "spark";
type PatternKind = "dots" | "grid" | "hatch" | "rule" | "none";
type LayoutKind = "grid" | "hero" | "stagger";

/**
 * A poster variant. Everything that changes between generations lives here, so
 * the look is decided once (in page state) and stays stable across re-renders —
 * html-to-image re-renders the node while capturing it.
 */
export type PosterTheme = {
  name: string;
  card: string;
  cardStyle?: CSSProperties;
  chipHeadings: boolean;
  tilt: number[];
  marker: MarkerKind;
  pattern: PatternKind;
  mascot: number;
  scenery: number;
  layout: LayoutKind;
  underline: number;
};

export const POSTER_THEMES: PosterTheme[] = [
  {
    name: "sticker",
    card: "rounded-2xl bg-white border-[3px]",
    cardStyle: { borderColor: INK, boxShadow: `6px 6px 0 ${INK}` },
    chipHeadings: true,
    tilt: [-1.1, 1.1, 0.8, -0.8, 1.2, -1.2],
    marker: "star",
    pattern: "dots",
    mascot: 0,
    scenery: 0,
    layout: "grid",
    underline: 0,
  },
  {
    name: "bubble",
    card: "rounded-[2.25rem] bg-white border-2",
    cardStyle: { borderColor: INK },
    chipHeadings: false,
    tilt: [0.9, -0.9, -0.6, 0.6, 1, -1],
    marker: "heart",
    pattern: "none",
    mascot: 1,
    scenery: 2,
    layout: "stagger",
    underline: 1,
  },
  {
    name: "notebook",
    card: "rounded-xl bg-white border-2 border-dashed",
    cardStyle: { borderColor: INK },
    chipHeadings: false,
    tilt: [0, 0, 0, 0, 0, 0],
    marker: "check",
    pattern: "rule",
    mascot: 2,
    scenery: 1,
    layout: "grid",
    underline: 2,
  },
  {
    name: "launch",
    card: "rounded-3xl bg-white border-2",
    cardStyle: { borderColor: INK, boxShadow: `4px 4px 0 ${INK}` },
    chipHeadings: true,
    tilt: [-0.7, 0.7, 0.5, -0.5, 0.9, -0.9],
    marker: "arrow",
    pattern: "hatch",
    mascot: 3,
    scenery: 4,
    layout: "hero",
    underline: 3,
  },
  {
    name: "pocket",
    card: "rounded-2xl border-0",
    cardStyle: { backgroundColor: "#f4f4f5" },
    chipHeadings: true,
    tilt: [0, 0, 0, 0, 0, 0],
    marker: "dot",
    pattern: "grid",
    mascot: 4,
    scenery: 5,
    layout: "stagger",
    underline: 0,
  },
  {
    name: "market",
    card: "rounded-[1.75rem] bg-white border-2",
    cardStyle: { borderColor: INK, outline: `2px solid ${INK}`, outlineOffset: "4px" },
    chipHeadings: false,
    tilt: [0.6, -0.6, 0.9, -0.9, 0.4, -0.4],
    marker: "spark",
    pattern: "none",
    mascot: 5,
    scenery: 3,
    layout: "hero",
    underline: 1,
  },
  {
    name: "ledger",
    card: "rounded-lg bg-white border-2",
    cardStyle: { borderColor: INK, borderTopWidth: 6 },
    chipHeadings: false,
    tilt: [0, 0, 0, 0, 0, 0],
    marker: "dot",
    pattern: "rule",
    mascot: 0,
    scenery: 6,
    layout: "grid",
    underline: 4,
  },
  {
    name: "cutout",
    card: "rounded-[1.25rem] bg-white border-[3px]",
    cardStyle: { borderColor: INK, boxShadow: `-6px 6px 0 ${INK}` },
    chipHeadings: false,
    tilt: [1.3, -1.3, -0.9, 0.9, 1.1, -1.1],
    marker: "spark",
    pattern: "dots",
    mascot: 6,
    scenery: 10,
    layout: "stagger",
    underline: 5,
  },
  {
    name: "postcard",
    card: "rounded-3xl bg-white border-2 border-dotted",
    cardStyle: { borderColor: INK },
    chipHeadings: false,
    tilt: [-0.5, 0.5, 0.7, -0.7, 0.4, -0.4],
    marker: "heart",
    pattern: "none",
    mascot: 7,
    scenery: 8,
    layout: "hero",
    underline: 6,
  },
  {
    name: "chalk",
    card: "rounded-2xl border-0",
    cardStyle: { backgroundColor: "#f1f1f2", boxShadow: `inset 0 0 0 2px ${INK}` },
    chipHeadings: true,
    tilt: [0, 0, 0, 0, 0, 0],
    marker: "star",
    pattern: "hatch",
    mascot: 2,
    scenery: 11,
    layout: "grid",
    underline: 2,
  },
];

/**
 * Patterns are rolled per poster rather than owned by a theme. "none" appears
 * twice so a plain white sheet stays the most common background.
 */
const PATTERNS: PatternKind[] = ["dots", "grid", "hatch", "rule", "none", "none"];

let lastVariant = "";
const recent: Record<string, number[]> = {};

/**
 * Pick an index, avoiding whatever the last few posters used. Keeping one
 * history per trait is what stops two consecutive posters from sharing a
 * mascot or a scene even when they land on different themes.
 */
function pickFresh(trait: string, count: number): number {
  const seen = recent[trait] ?? (recent[trait] = []);
  const all = Array.from({ length: count }, (_, i) => i);
  const pool = all.filter((i) => !seen.includes(i));
  const from = pool.length ? pool : all;
  const picked = from[Math.floor(Math.random() * from.length)];
  seen.push(picked);
  while (seen.length > Math.min(count - 1, 5)) seen.shift();
  return picked;
}

/**
 * Mascot, scenery, underline and background are rolled independently of the
 * theme. They cannot clash with a card design, so every combination is safe
 * without anyone having looked at it — which is how a dozen hand-checked
 * themes cover thousands of distinct posters. Card shape, heading style,
 * bullet marker, tilt and layout stay bundled, because those DO interact.
 */
function roll(theme: PosterTheme): PosterTheme {
  return {
    ...theme,
    scenery: pickFresh("scenery", CHIBI_SCENERIES.length),
    mascot: pickFresh("mascot", MASCOTS.length),
    underline: pickFresh("underline", UNDERLINES.length),
    pattern: PATTERNS[pickFresh("pattern", PATTERNS.length)],
  };
}

/**
 * Pick a variant. Without a name, never returns the same one twice in a row.
 * The result carries its own rolled traits, so the caller must hold on to the
 * object — re-picking on every render would re-roll the artwork mid-capture.
 */
export function getPosterTheme(name?: string): PosterTheme {
  if (name) {
    const found = POSTER_THEMES.find((t) => t.name === name);
    if (found) return roll(found);
  }
  const pool = POSTER_THEMES.filter((t) => t.name !== lastVariant);
  const picked = pool[Math.floor(Math.random() * pool.length)];
  lastVariant = picked.name;
  return roll(picked);
}

/* ---------------------------------------------------------------- mascots */

const mascotProps = {
  viewBox: "0 0 100 100",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 3.4,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  className: "w-full h-full",
};

const MASCOTS: ReactNode[] = [
  // Chibi coin
  <svg key="coin" {...mascotProps}>
    <circle cx="50" cy="54" r="32" />
    <circle cx="50" cy="54" r="25" />
    <circle cx="42" cy="50" r="3.2" fill="currentColor" stroke="none" />
    <circle cx="58" cy="50" r="3.2" fill="currentColor" stroke="none" />
    <path d="M43 60c4 4 10 4 14 0" />
    <path d="M50 16v-8M31 24l-5-7M69 24l5-7" />
  </svg>,
  // Chibi cat
  <svg key="cat" {...mascotProps}>
    <path d="M30 36l-5-18 17 9M70 36l5-18-17 9" />
    <circle cx="50" cy="54" r="28" />
    <circle cx="41" cy="50" r="3.4" fill="currentColor" stroke="none" />
    <circle cx="59" cy="50" r="3.4" fill="currentColor" stroke="none" />
    <path d="M47 59h6l-3 4z" fill="currentColor" stroke="none" />
    <path d="M44 64c2 3 4 3 6 0 2 3 4 3 6 0" />
    <path d="M18 52h12M18 61h12M70 52h12M70 61h12" />
  </svg>,
  // Chibi owl
  <svg key="owl" {...mascotProps}>
    <path d="M50 16c-16 0-27 13-27 31s11 34 27 34 27-16 27-34-11-31-27-31z" />
    <circle cx="40" cy="44" r="10" />
    <circle cx="60" cy="44" r="10" />
    <circle cx="40" cy="44" r="3.4" fill="currentColor" stroke="none" />
    <circle cx="60" cy="44" r="3.4" fill="currentColor" stroke="none" />
    <path d="M46 57l4 6 4-6z" fill="currentColor" stroke="none" />
    <path d="M25 58c-5 7-4 15 2 19M75 58c5 7 4 15-2 19" />
    <path d="M43 81v7M57 81v7" />
    <path d="M33 20l-6-8M67 20l6-8" />
  </svg>,
  // Chibi rocket
  <svg key="rocket" {...mascotProps}>
    <path d="M50 12c11 11 17 25 17 40v18H33V52c0-15 6-29 17-40z" />
    <circle cx="50" cy="44" r="10" />
    <circle cx="46" cy="42" r="2.4" fill="currentColor" stroke="none" />
    <circle cx="54" cy="42" r="2.4" fill="currentColor" stroke="none" />
    <path d="M46 49c2 2 6 2 8 0" />
    <path d="M33 56L20 72h13M67 56l13 16H67" />
    <path d="M40 70h20" />
    <path d="M44 76c2 7 4 10 6 14 2-4 4-7 6-14" />
  </svg>,
  // Chibi piggy bank
  <svg key="piggy" {...mascotProps}>
    <path d="M22 58c0-16 13-27 28-27s28 11 28 27-13 26-28 26-28-10-28-26z" />
    <path d="M31 36l-5-13 16 6M69 36l5-13-16 6" />
    <ellipse cx="50" cy="62" rx="11" ry="8" />
    <circle cx="46" cy="62" r="2.2" fill="currentColor" stroke="none" />
    <circle cx="54" cy="62" r="2.2" fill="currentColor" stroke="none" />
    <circle cx="37" cy="49" r="3" fill="currentColor" stroke="none" />
    <circle cx="63" cy="49" r="3" fill="currentColor" stroke="none" />
    <path d="M42 33h16" />
    <path d="M33 82v6M67 82v6" />
  </svg>,
  // Chibi bull
  <svg key="bull" {...mascotProps}>
    <path d="M32 40c-9-3-15-12-13-20 9 0 17 5 21 13M68 40c9-3 15-12 13-20-9 0-17 5-21 13" />
    <path d="M30 50c0-14 9-23 20-23s20 9 20 23-9 30-20 30-20-16-20-30z" />
    <circle cx="41" cy="47" r="3.2" fill="currentColor" stroke="none" />
    <circle cx="59" cy="47" r="3.2" fill="currentColor" stroke="none" />
    <ellipse cx="50" cy="65" rx="11" ry="8" />
    <circle cx="46" cy="65" r="1.8" fill="currentColor" stroke="none" />
    <circle cx="54" cy="65" r="1.8" fill="currentColor" stroke="none" />
  </svg>,
  // Chibi fox
  <svg key="fox" {...mascotProps}>
    <path d="M28 40L20 14l22 12M72 40l8-26-22 12" />
    <path d="M24 48c0-14 12-24 26-24s26 10 26 24c0 18-12 34-26 34S24 66 24 48z" />
    <circle cx="40" cy="46" r="3.4" fill="currentColor" stroke="none" />
    <circle cx="60" cy="46" r="3.4" fill="currentColor" stroke="none" />
    <path d="M46 60h8l-4 5z" fill="currentColor" stroke="none" />
    <path d="M43 68c3 4 11 4 14 0" />
    <path d="M76 74c10 2 16-6 14-16" />
  </svg>,
  // Chibi robot
  <svg key="robot" {...mascotProps}>
    <path d="M28 34h44a6 6 0 016 6v34a6 6 0 01-6 6H28a6 6 0 01-6-6V40a6 6 0 016-6z" />
    <circle cx="40" cy="52" r="4" fill="currentColor" stroke="none" />
    <circle cx="60" cy="52" r="4" fill="currentColor" stroke="none" />
    <path d="M40 64c5 5 15 5 20 0" />
    <path d="M50 34V22" />
    <circle cx="50" cy="16" r="6" />
    <path d="M22 48h-8v18h8M78 48h8v18h-8" />
    <path d="M36 80v8M64 80v8" />
  </svg>,
];

/* --------------------------------------------------------------- markers */

function Marker({ kind, className = "" }: { kind: MarkerKind; className?: string }) {
  switch (kind) {
    case "star":
      return (
        <svg viewBox="0 0 12 12" className={className} fill="currentColor" aria-hidden="true">
          <path d="M6 0l1.6 3.9L12 4.6 8.8 7.7l.9 4.3L6 9.8 2.3 12l.9-4.3L0 4.6l4.4-.7z" />
        </svg>
      );
    case "heart":
      return (
        <svg viewBox="0 0 12 12" className={className} fill="currentColor" aria-hidden="true">
          <path d="M6 11.2S.8 7.7.8 4.4A2.9 2.9 0 016 2.7a2.9 2.9 0 015.2 1.7c0 3.3-5.2 6.8-5.2 6.8z" />
        </svg>
      );
    case "check":
      return (
        <svg
          viewBox="0 0 12 12"
          className={className}
          fill="none"
          stroke="currentColor"
          strokeWidth={2.2}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="M1.2 6.4l3.2 3.4L10.8 2" />
        </svg>
      );
    case "arrow":
      return (
        <svg viewBox="0 0 12 12" className={className} fill="currentColor" aria-hidden="true">
          <path d="M2.2 0.8L9.4 6l-7.2 5.2z" />
        </svg>
      );
    case "spark":
      return (
        <svg viewBox="0 0 12 12" className={className} fill="currentColor" aria-hidden="true">
          <path d="M6 0l1.3 4.7L12 6l-4.7 1.3L6 12l-1.3-4.7L0 6l4.7-1.3z" />
        </svg>
      );
    default:
      return (
        <svg viewBox="0 0 12 12" className={className} fill="currentColor" aria-hidden="true">
          <circle cx="6" cy="6" r="3.4" />
        </svg>
      );
  }
}

/* ------------------------------------------------------------- underlines */

const UNDERLINES: string[][] = [
  ["M4 11c26-12 52 12 78 0s52-12 78 0 52 12 78 0 52-12 78 0"],
  ["M4 10c66-8 132-8 198-3s72 5 106 1"],
  ["M4 7c72-6 144-6 216 0", "M20 14c66-5 132-5 198 0"],
  ["M4 13l26-9 26 9 26-9 26 9 26-9 26 9 26-9 26 9 26-9 26 9"],
  ["M4 9q40 8 80 0t80 0 80 0 80 0 76 2"],
  ["M6 12c40-10 84 6 124-2s84-8 124 2 44 4 82-2", "M60 6c46 4 92 4 138 0"],
  ["M4 8q54 11 108 0t108 0 108 0 106 4"],
];

function Underline({ index }: { index: number }) {
  const paths = UNDERLINES[index % UNDERLINES.length];
  return (
    <svg
      viewBox="0 0 340 18"
      width={380}
      height={20}
      fill="none"
      stroke={INK}
      strokeWidth={index === 1 || index === 5 ? 6 : 3.8}
      strokeLinecap="round"
      aria-hidden="true"
    >
      {paths.map((d, i) => (
        <path key={i} d={d} />
      ))}
    </svg>
  );
}

/* --------------------------------------------------------------- patterns */

function patternStyle(kind: PatternKind): CSSProperties {
  switch (kind) {
    case "dots":
      return {
        backgroundImage: `radial-gradient(${INK} 1.6px, transparent 1.7px)`,
        backgroundSize: "26px 26px",
        opacity: 0.09,
      };
    case "grid":
      return {
        backgroundImage: `linear-gradient(${INK} 1px, transparent 1px), linear-gradient(90deg, ${INK} 1px, transparent 1px)`,
        backgroundSize: "34px 34px",
        opacity: 0.07,
      };
    case "hatch":
      return {
        backgroundImage: `repeating-linear-gradient(45deg, ${INK} 0 1.4px, transparent 1.4px 15px)`,
        opacity: 0.07,
      };
    case "rule":
      return {
        backgroundImage: `repeating-linear-gradient(180deg, transparent 0 43px, ${INK} 43px 44px)`,
        opacity: 0.07,
      };
    default:
      return { opacity: 0 };
  }
}

/* ---------------------------------------------------------------- doodles */

const DOODLE_SPOTS: Array<{
  top: number;
  left?: number;
  right?: number;
  size: number;
  rotate: number;
}> = [
  { top: 232, left: 22, size: 26, rotate: -18 },
  { top: 486, right: 26, size: 34, rotate: 12 },
  { top: 812, left: 16, size: 22, rotate: 24 },
  { top: 126, right: 296, size: 20, rotate: -8 },
];

function Doodles({ marker }: { marker: MarkerKind }) {
  return (
    <div className="absolute inset-0 pointer-events-none" aria-hidden="true" style={{ color: INK }}>
      {DOODLE_SPOTS.map((spot, index) => (
        <div
          key={index}
          className="absolute opacity-20"
          style={{
            top: spot.top,
            left: spot.left,
            right: spot.right,
            width: spot.size,
            height: spot.size,
            transform: `rotate(${spot.rotate}deg)`,
          }}
        >
          <Marker kind={marker} className="w-full h-full" />
        </div>
      ))}
    </div>
  );
}

/* ----------------------------------------------------------------- poster */

function formatGeneratedAt(): string {
  const now = new Date();
  const date = now.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
  const time = now.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${date} • ${time}`;
}

export default function PosterCard({
  poster,
  className = "",
  variant: suppliedVariant,
}: {
  poster: Poster;
  className?: string;
  /**
   * Pass the object returned by getPosterTheme() and hold on to it. Without it
   * the card picks its own, which is fine for a one-off preview but re-rolls
   * the scenery whenever the poster prop changes.
   */
  variant?: PosterTheme;
}) {
  const ownVariant = useMemo(() => getPosterTheme(poster.theme), [poster]);
  const variant = suppliedVariant ?? ownVariant;
  const generatedAt = formatGeneratedAt();
  const sections = poster.sections.slice(0, 6);

  // The poster is a fixed 1080x1350 frame, so a full summary paragraph plus
  // five sections of five bullets has to buy its space from type and padding
  // rather than from height. One step down is enough for the worst case.
  const bulletCount = sections.reduce((n, section) => n + section.bullets.length, 0);
  const dense = sections.length >= 4 || bulletCount >= 16;
  const cardClass = `${variant.card} ${dense ? "p-4" : "p-5"}`;

  const heading = (text: string) =>
    variant.chipHeadings ? (
      <span
        className="inline-block px-3 py-1.5 rounded-full border-2 text-base uppercase tracking-wide leading-none"
        style={{ borderColor: INK, color: INK, fontFamily: DISPLAY, fontWeight: 600 }}
      >
        {text}
      </span>
    ) : (
      <span className="text-lg uppercase tracking-wide leading-tight" style={{ fontFamily: DISPLAY, fontWeight: 600 }}>
        {text}
      </span>
    );

  return (
    <div
      className={`relative w-[1080px] h-[1350px] p-12 flex flex-col overflow-hidden ${className}`}
      style={{ backgroundColor: "#ffffff", color: INK, fontFamily: BODY }}
    >
      {/* Background texture */}
      <div className="absolute inset-0 pointer-events-none" style={patternStyle(variant.pattern)} />
      <Doodles marker={variant.marker} />

      {/* Header — kicker, then the Lamka Labs lockup, then the timestamp */}
      <header className={`relative z-10 ${dense ? "mb-5" : "mb-7"} flex items-center gap-4`}>
        <div
          className="w-[76px] h-[76px] rounded-2xl border-2 p-2 flex-shrink-0"
          style={{ borderColor: INK, color: INK, backgroundColor: "#ffffff" }}
        >
          {MASCOTS[variant.mascot]}
        </div>
        <div className="flex flex-col gap-1.5">
          <span
            className="text-base uppercase tracking-[0.28em] leading-none"
            style={{ fontFamily: DISPLAY, fontWeight: 600 }}
          >
            {KICKER}
          </span>
          <span className="flex items-center gap-2 leading-none">
            <img src="/logo-black.png" alt="" className="w-[18px] h-[18px] object-contain flex-shrink-0" />
            <span className="text-sm uppercase tracking-[0.2em]" style={{ fontFamily: DISPLAY, fontWeight: 600 }}>
              <span>Lamka </span>
              <span style={{ color: MAROON }}>Labs</span>
            </span>
          </span>
          <span className="text-[11px] tracking-wider opacity-60 leading-none">{generatedAt}</span>
        </div>
      </header>

      {/* Title */}
      <div className={`relative z-10 ${dense ? "mb-4" : "mb-5"}`}>
        <h1
          className={`${dense ? "text-[52px]" : "text-[62px]"} leading-[1.02] tracking-tight mb-1`}
          style={{ fontFamily: DISPLAY, fontWeight: 700 }}
        >
          {poster.title}
        </h1>
        <Underline index={variant.underline} />
        <p className={`${dense ? "text-xl" : "text-2xl"} leading-snug mt-3 opacity-75`}>{poster.subtitle}</p>
      </div>

      {/* Summary */}
      <div className={`relative z-10 ${dense ? "mb-4" : "mb-6"} ${cardClass}`} style={variant.cardStyle}>
        <div className="mb-3">{heading("At a Glance")}</div>
        <p className={`${dense ? "text-[15px] leading-[1.55]" : "text-[17px] leading-relaxed"}`}>{poster.summary}</p>
      </div>

      {/* Sections */}
      <div className={`relative z-10 grid grid-cols-2 ${dense ? "gap-4" : "gap-5"} content-start`}>
        {sections.map((section, index) => (
          <div
            key={index}
            className={`${cardClass} ${variant.layout === "hero" && index === 0 ? "col-span-2" : ""}`}
            style={{
              ...variant.cardStyle,
              transform: variant.tilt[index] ? `rotate(${variant.tilt[index]}deg)` : undefined,
              marginTop: variant.layout === "stagger" && index % 2 === 1 ? 22 : undefined,
            }}
          >
            <div className={dense ? "mb-2.5" : "mb-3"}>{heading(section.heading)}</div>
            <ul className={dense ? "space-y-1.5" : "space-y-2"}>
              {section.bullets.map((bullet, bIndex) => (
                <li key={bIndex} className={`flex items-start gap-2.5 ${dense ? "text-[13px]" : "text-sm"} leading-snug`}>
                  <Marker kind={variant.marker} className="w-3 h-3 mt-1 flex-shrink-0" />
                  {bullet}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {/* Chibi scenery — its own band, corner to corner above the footer */}
      <div
        className={`relative z-10 mt-auto ${dense ? "h-[150px]" : "h-[178px]"} w-[1080px] -mx-12 flex-shrink-0 overflow-hidden opacity-95 pointer-events-none`}
        style={{ color: INK }}
        aria-hidden="true"
      >
        {CHIBI_SCENERIES[variant.scenery]}
      </div>

      {/* Footer */}
      <footer
        className="relative z-10 -mx-12 -mb-12 px-12 pt-5 pb-6 border-t-2"
        style={{ borderColor: INK, backgroundColor: "#ffffff" }}
      >
        <div className="text-center mb-4">
          <p className="text-[11px] uppercase tracking-[0.18em]" style={{ fontFamily: DISPLAY, fontWeight: 600 }}>
            A Lamka Exchange Society Pvt Ltd Production
          </p>
          <p className="text-[10px] uppercase tracking-[0.2em] opacity-60 mt-1">
            in collaboration with Lamka Labs Studio
          </p>
        </div>
        <div className="flex items-center justify-center gap-2.5 text-xs opacity-70">
          <svg
            viewBox="0 0 16 16"
            className="w-4 h-4 flex-shrink-0 mt-0.5"
            fill="none"
            stroke={INK}
            strokeWidth={1.6}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M8 1.5l5.5 2.2v4c0 3.4-2.3 6-5.5 6.8C4.8 13.7 2.5 11.1 2.5 7.7v-4z" />
            <path d="M8 5.5v3.2M8 11h.01" />
          </svg>
          <p>{poster.footer}</p>
        </div>
      </footer>
    </div>
  );
}
