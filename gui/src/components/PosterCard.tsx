"use client";

import { useMemo } from "react";
import type { CSSProperties, ReactNode } from "react";

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
];

let lastVariant = "";
const sceneryHistory: number[] = [];

/**
 * Scenery is picked independently of the variant so the two do not travel as a
 * fixed pair, and the recent history is excluded so consecutive posters never
 * show the same scene.
 */
function pickScenery(): number {
  const all = CHIBI_SCENERIES.map((_, i) => i);
  const fresh = all.filter((i) => !sceneryHistory.includes(i));
  const picked = (fresh.length ? fresh : all)[
    Math.floor(Math.random() * (fresh.length ? fresh.length : all.length))
  ];
  sceneryHistory.push(picked);
  while (sceneryHistory.length > CHIBI_SCENERIES.length - 2) sceneryHistory.shift();
  return picked;
}

/**
 * Pick a variant. Without a name, never returns the same one twice in a row.
 * The result carries its own scenery, so the caller must hold on to the object
 * — re-picking on every render would re-roll the artwork mid-capture.
 */
export function getPosterTheme(name?: string): PosterTheme {
  if (name) {
    const found = POSTER_THEMES.find((t) => t.name === name);
    if (found) return { ...found, scenery: pickScenery() };
  }
  const pool = POSTER_THEMES.filter((t) => t.name !== lastVariant);
  const picked = pool[Math.floor(Math.random() * pool.length)];
  lastVariant = picked.name;
  return { ...picked, scenery: pickScenery() };
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
      strokeWidth={index === 1 ? 6 : 3.4}
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

/* ---------------------------------------------------------------- scenery */

const sceneryProps = {
  viewBox: "0 0 1080 260",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  // Fill the band edge to edge and anchor to the ground line, cropping sky
  // rather than shrinking the scene to fit the band height.
  preserveAspectRatio: "xMidYMax slice",
  className: "w-full h-full",
};

const CHIBI_SCENERIES: ReactNode[] = [
  // City skyline
  <svg key="city" {...sceneryProps}>
    <path d="M0 260h1080" />
    <path d="M40 260V160h50v100M120 260V110h70v150M220 260V80h60v180M320 260V140h80v120M440 260V60h90v200M570 260V100h60v160M670 260V150h70v110M780 260V90h80v170M900 260V130h60v130M990 260V170h50v90" />
    <path d="M60 180h20v20H60zM150 140h20v20h-20zM250 110h20v20h-20zM480 90h20v20h-20zM700 170h20v20h-20zM930 150h20v20h-20z" />
    <path d="M300 60c0-22 18-40 40-40s40 18 40 40" />
    <circle cx="340" cy="55" r="8" fill="currentColor" />
    <path d="M800 40c15-15 35-15 50 0M880 50c10-10 25-10 35 0" />
    <path d="M120 70l8 8M150 50l8 8M900 60l8 8M940 45l8 8" />
  </svg>,
  // Mountain range
  <svg key="mountains" {...sceneryProps}>
    <path d="M0 260L160 60 300 200 480 40 640 180 820 30 1080 260z" />
    <path d="M180 120l20-20 20 20M500 90l25-25 25 25M840 80l20-20 20 20" />
    <path d="M160 60L140 30M160 60L180 30M480 40L455 10M480 40L505 10M820 30L800 0M820 30L840 0" />
    <circle cx="920" cy="55" r="22" />
    <circle cx="940" cy="50" r="4" fill="currentColor" />
    <path d="M60 260c40-30 90-30 130 0M260 260c50-35 110-35 160 0M560 260c45-30 100-30 145 0M820 260c40-25 85-25 125 0" />
    <path d="M100 220c10-10 25-10 35 0M620 220c10-10 25-10 35 0" />
  </svg>,
  // Forest
  <svg key="forest" {...sceneryProps}>
    <path d="M0 260h1080" />
    <path d="M60 260V180l-25-40h50l-25 40zM160 260V150l-30-55h60l-30 55zM280 260V170l-25-45h50l-25 45zM400 260V130l-35-65h70l-35 65zM540 260V160l-28-50h56l-28 50zM680 260V140l-32-60h64l-32 60zM820 260V170l-25-45h50l-25 45zM940 260V150l-30-55h60l-30 55z" />
    <circle cx="90" cy="140" r="28" /><circle cx="200" cy="110" r="32" /><circle cx="330" cy="130" r="26" />
    <circle cx="460" cy="90" r="34" /><circle cx="580" cy="120" r="28" /><circle cx="720" cy="100" r="30" />
    <circle cx="850" cy="130" r="26" /><circle cx="970" cy="110" r="32" />
    <path d="M70 200c5-5 12-5 17 0M190 190c5-5 12-5 17 0M560 195c5-5 12-5 17 0M940 185c5-5 12-5 17 0" />
    <path d="M150 60c0-8 7-15 15-15s15 7 15 15M350 50c0-10 8-18 18-18s18 8 18 18M850 55c0-9 7-16 16-16s16 7 16 16" />
  </svg>,
  // Ocean coast
  <svg key="ocean" {...sceneryProps}>
    <path d="M0 260h1080" />
    <path d="M0 220c60-20 120 20 180 0s120-20 180 0 120 20 180 0 120-20 180 0 120 20 180 0" />
    <path d="M0 245c60-20 120 20 180 0s120-20 180 0 120 20 180 0 120-20 180 0 120 20 180 0" />
    <path d="M900 260V140h60v120M880 140h100M930 110V60M910 80h40" />
    <circle cx="930" cy="45" r="16" />
    <path d="M150 120c0-25 20-45 45-45s45 20 45 45M700 100c0-20 16-36 36-36s36 16 36 36" />
    <path d="M80 60c12-8 28-8 40 0M320 50c10-7 24-7 34 0M600 65c12-8 28-8 40 0" />
  </svg>,
  // Space
  <svg key="space" {...sceneryProps}>
    <path d="M520 260V140c-30-10-50-40-50-75 0-45 35-80 80-80s80 35 80 80c0 35-20 65-50 75v120" />
    <circle cx="550" cy="65" r="14" />
    <path d="M470 200l-50 60h50M610 200l50 60h-50" />
    <path d="M500 140h120" />
    <circle cx="200" cy="60" r="20" />
    <path d="M185 60h30M200 45v30" />
    <circle cx="850" cy="80" r="16" />
    <path d="M840 80h20M850 70v20" />
    <path d="M80 100l10 10M120 50l10 10M300 120l10 10M700 40l10 10M950 130l10 10M1000 70l10 10" />
    <path d="M100 180c0-6 5-11 11-11s11 5 11 11M750 160c0-6 5-11 11-11s11 5 11 11" />
  </svg>,
  // Countryside
  <svg key="countryside" {...sceneryProps}>
    <path d="M0 260c80-60 200-60 280-20s200 20 320-30 240-40 360 10 120 40 120 40" />
    <path d="M720 260V110h80v150M760 110V70M740 90h40M720 130h80M720 170h80" />
    <path d="M760 70l-25 20M760 70l25 20M760 70l-8 30M760 70l8 30" />
    <path d="M150 260V180h60v80M170 180v-30h20v30" />
    <path d="M350 260V200h50v60M375 200v-25" />
    <circle cx="120" cy="60" r="22" />
    <path d="M100 60h40M120 40v40" />
    <path d="M60 110c0-8 7-15 15-15s15 7 15 15M280 90c0-10 8-18 18-18s18 8 18 18M920 70c0-9 7-16 16-16s16 7 16 16" />
  </svg>,
  // Railway bridge
  <svg key="railway" {...sceneryProps}>
    <path d="M0 190h1080" />
    <path d="M120 190v70M260 190v70M400 190v70M540 190v70M680 190v70M820 190v70M960 190v70" />
    <path d="M120 260c0-34 28-62 62-62M260 198c34 0 62 28 62 62M400 260c0-34 28-62 62-62M540 198c34 0 62 28 62 62M680 260c0-34 28-62 62-62M820 198c34 0 62 28 62 62" />
    <path d="M180 190V120h250v70M180 120l125-40 125 40" />
    <circle cx="240" cy="155" r="12" /><circle cx="305" cy="155" r="12" /><circle cx="370" cy="155" r="12" />
    <path d="M620 190v-60h180v60M620 130h180M680 190v-60M740 190v-60" />
    <path d="M900 90c14-12 32-12 46 0M960 70c10-9 24-9 34 0" />
    <path d="M60 120l8 8M480 70l8 8M1020 140l8 8" />
  </svg>,
  // Hot-air balloons
  <svg key="balloons" {...sceneryProps}>
    <path d="M0 250c90-24 180 24 270 8s180-40 270-16 180 40 270 16 180-32 270-8" />
    <path d="M200 120c0-32-25-58-56-58s-56 26-56 58c0 26 34 56 56 76 22-20 56-50 56-76z" />
    <path d="M126 152l18 26M162 152l-18 26M132 178h24v18h-24z" />
    <path d="M560 96c0-26-20-46-45-46s-45 20-45 46c0 21 27 45 45 61 18-16 45-40 45-61z" />
    <path d="M500 122l15 21M530 122l-15 21M506 143h19v15h-19z" />
    <path d="M900 140c0-22-17-40-38-40s-38 18-38 40c0 18 23 38 38 52 15-14 38-34 38-52z" />
    <path d="M850 162l12 18M874 162l-12 18M855 180h15v13h-15z" />
    <path d="M320 60c12-10 28-10 40 0M700 44c10-9 24-9 34 0" />
  </svg>,
  // Lantern street
  <svg key="lanterns" {...sceneryProps}>
    <path d="M0 260h1080" />
    <path d="M40 260V60M1040 260V60M40 70c180 34 360 46 500 46s320-12 500-46" />
    <path d="M170 100v26M330 118v26M500 126v26M670 122v26M840 108v26M990 86v26" />
    <path d="M150 126h40v34h-40zM310 144h40v34h-40zM480 152h40v34h-40zM650 148h40v34h-40zM820 134h40v34h-40zM970 112h40v34h-40z" />
    <path d="M170 160v12M330 178v12M500 186v12M670 182v12M840 168v12M990 146v12" />
    <path d="M120 260v-50h120v50M260 260v-64h130v64M420 260v-46h120v46M580 260v-58h130v58M740 260v-44h120v44" />
    <path d="M150 232h24M300 226h24M460 238h24M620 230h24M780 240h24" />
  </svg>,
];

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
        className="inline-block px-3 py-1.5 rounded-full text-base uppercase tracking-wide leading-none"
        style={{ backgroundColor: INK, color: "#ffffff", fontFamily: DISPLAY, fontWeight: 600 }}
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
        className={`relative z-10 mt-auto ${dense ? "h-[124px]" : "h-[164px]"} w-[1080px] -mx-12 flex-shrink-0 overflow-hidden opacity-70 pointer-events-none`}
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
