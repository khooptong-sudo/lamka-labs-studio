/**
 * Hand-drawn chibi scenery for the poster footer band.
 *
 * Three rules hold the style together, and breaking any one of them is what
 * made the first pass read as a technical diagram instead of a cartoon:
 *
 * 1. Authored at the band's own aspect ratio (1080x178). The band paints with
 *    `slice`, so anything drawn above y=32 is cropped on a dense poster. Sky
 *    only up there.
 * 2. Weight varies. Silhouettes at 5.5, structure at 4, detail at 2.6, and a
 *    few solid-black masses. Uniform stroke is what makes line art look CAD.
 * 3. Every scene is inhabited. A chibi character with the same face grammar
 *    (big head, dot eyes, small smile) anchors each one — that is the part
 *    that reads as "cartoon" at a glance.
 */

import type { ReactNode } from "react";

const sceneryProps = {
  viewBox: "0 0 1080 178",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 5.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  // Anchor to the ground line and crop sky, never shrink the scene to fit.
  preserveAspectRatio: "xMidYMax slice",
  className: "w-full h-full",
};

/** The shared chibi face: big dot eyes, small smile. One grammar everywhere. */
function Face({ x, y, r }: { x: number; y: number; r: number }) {
  return (
    <>
      <circle cx={x - r * 0.34} cy={y - r * 0.08} r={r * 0.15} fill="currentColor" stroke="none" />
      <circle cx={x + r * 0.34} cy={y - r * 0.08} r={r * 0.15} fill="currentColor" stroke="none" />
      <path
        d={`M${x - r * 0.26} ${y + r * 0.34}q${r * 0.26} ${r * 0.3} ${r * 0.52} 0`}
        strokeWidth={2.8}
      />
    </>
  );
}

/** A wobbly ground line. Straight `h` strokes are the fastest tell of a machine. */
function Ground({ y = 168 }: { y?: number }) {
  return (
    <path
      d={`M-10 ${y}q90 -5 180 1t180 -2 180 3 180 -3 180 2 190 -1`}
      strokeWidth={5.5}
    />
  );
}

export const CHIBI_SCENERIES: ReactNode[] = [
  // 1. City rooftops, with a cat who owns the tallest one
  <svg key="city" {...sceneryProps}>
    <Ground />
    <path d="M28 168q-4-46 0-74 32-5 64 0 4 28 0 74" strokeWidth={5.5} />
    <path d="M112 168q-5-72 0-108 36-6 72 0 5 36 0 108" strokeWidth={5.5} />
    <path d="M206 168q-4-58 0-88 30-5 60 0 4 30 0 88" strokeWidth={5.5} />
    <path d="M700 168q-5-64 0-96 34-6 68 0 5 32 0 96" strokeWidth={5.5} />
    <path d="M790 168q-4-44 0-70 30-5 60 0 4 26 0 70" strokeWidth={5.5} />
    <path d="M872 168q-6-88 0-124 38-6 76 0 6 36 0 124" strokeWidth={5.5} />
    <path d="M962 168q-4-52 0-80 32-5 64 0 4 28 0 80" strokeWidth={5.5} />
    <g fill="currentColor" stroke="none">
      <rect x="44" y="112" width="14" height="16" rx="3" />
      <rect x="68" y="112" width="14" height="16" rx="3" />
      <rect x="130" y="80" width="15" height="17" rx="3" />
      <rect x="156" y="80" width="15" height="17" rx="3" />
      <rect x="130" y="114" width="15" height="17" rx="3" />
      <rect x="716" y="94" width="15" height="17" rx="3" />
      <rect x="742" y="94" width="15" height="17" rx="3" />
      <rect x="890" y="66" width="16" height="18" rx="3" />
      <rect x="918" y="66" width="16" height="18" rx="3" />
      <rect x="890" y="102" width="16" height="18" rx="3" />
      <rect x="978" y="106" width="15" height="17" rx="3" />
      <rect x="1002" y="106" width="15" height="17" rx="3" />
    </g>
    {/* Chibi cat sitting on the middle roof */}
    <path d="M470 168q-2-30 14-40" strokeWidth={4} />
    <path d="M418 168q-6-34 10-52 20-22 48-16 26 6 28 34 2 22-10 34" strokeWidth={5.5} fill="#ffffff" />
    <path d="M432 106l-8-24 24 12M486 104l10-22-24 10" strokeWidth={4.5} />
    <Face x={458} y={112} r={26} />
    <path d="M446 126q6 7 12 0" strokeWidth={2.6} />
    <path d="M410 116h-24M410 128h-24M508 116h24M508 128h24" strokeWidth={2.6} />
    <path d="M498 168q22-4 24-26 2-18-14-20" strokeWidth={4} />
    {/* Steam puffs and a couple of birds */}
    <path d="M300 96q10-14 24-6t8 24" strokeWidth={4} />
    <path d="M596 74q9-12 21-5t6 21" strokeWidth={4} />
    <path d="M636 46q12-11 24 0M676 60q10-9 20 0" strokeWidth={4} />
  </svg>,

  // 2. Mountains, with a chibi climber planting a flag
  <svg key="mountains" {...sceneryProps}>
    <path
      d="M-10 176q64-14 128-104 66 12 78 66 60-2 140-84 72 14 112 90 66-4 136-96 76 16 128 100 68-6 122-80 74 12 126 84"
      strokeWidth={5.5}
    />
    <path d="M118 72l-26 32 24-8 20 10 22-8zM336 54l-28 34 26-8 22 10 22-8zM834 68l-26 32 24-8 20 10 22-8z" strokeWidth={4} />
    <Ground y={174} />
    {/* Chibi climber on the tallest summit */}
    <path d="M640 58V10" strokeWidth={4} />
    <path d="M640 12q28 2 32 14-20 10-32 6z" fill="currentColor" stroke="none" />
    <path d="M588 88q-4-30 22-32 28-2 26 30" strokeWidth={5} fill="#ffffff" />
    <circle cx="610" cy="48" r="24" strokeWidth={5.5} fill="#ffffff" />
    <Face x={610} y={50} r={24} />
    <path d="M586 34q24-16 48 0" strokeWidth={4} />
    <path d="M634 70l14-8M586 70l-16 8" strokeWidth={4.5} />
    {/* Pines at the base, apex up, and two birds */}
    <path d="M44 122l-30 50h60zM44 94l-24 40h48zM44 66l-18 32h36z" strokeWidth={4} fill="#ffffff" />
    <path d="M44 178v-14" strokeWidth={4} />
    <path d="M1010 130l-26 42h52zM1010 102l-20 36h40zM1010 178v-12" strokeWidth={4} fill="#ffffff" />
    <path d="M240 34q12-11 24 0M282 48q10-9 20 0" strokeWidth={4} />
  </svg>,

  // 3. Forest, with a bear peeking between the trunks
  <svg key="forest" {...sceneryProps}>
    <Ground />
    <path d="M96 168v-40M96 128q-38 2-38-30 0-30 38-28 38-2 38 28 0 32-38 30z" strokeWidth={5.5} />
    <path d="M226 168v-34M226 134q-32 2-32-26 0-26 32-24 32-2 32 24 0 28-32 26z" strokeWidth={5.5} />
    <path d="M868 168v-40M868 128q-36 2-36-30 0-30 36-28 36-2 36 28 0 32-36 30z" strokeWidth={5.5} />
    <path d="M990 168v-32M990 136q-30 2-30-24 0-24 30-22 30-2 30 22 0 26-30 24z" strokeWidth={5.5} />
    <path d="M344 116l-32 52h64zM344 84l-26 44h52zM344 52l-20 36h40z" strokeWidth={4.5} />
    <path d="M746 120l-28 48h56zM746 90l-22 38h44z" strokeWidth={4.5} />
    {/* Chibi bear */}
    <path d="M470 168q-6-40 20-58 24-16 50 0 26 18 20 58" strokeWidth={5.5} />
    <circle cx="510" cy="90" r="32" strokeWidth={5.5} />
    <circle cx="484" cy="62" r="11" strokeWidth={4.5} />
    <circle cx="536" cy="62" r="11" strokeWidth={4.5} />
    <Face x={510} y={88} r={32} />
    <ellipse cx="510" cy="102" rx="13" ry="9" strokeWidth={3} />
    <circle cx="510" cy="98" r="4" fill="currentColor" stroke="none" />
    <path d="M478 168q4-18 14-22M542 168q-4-18-14-22" strokeWidth={4} />
    {/* Mushrooms and grass tufts */}
    <path d="M614 168v-14M600 154q14-20 28 0z" strokeWidth={4} />
    <path d="M642 168v-10M632 158q10-14 20 0z" strokeWidth={4} />
    <path d="M180 168q6-16 12 0M292 168q6-14 12 0M816 168q6-16 12 0M934 168q6-14 12 0" strokeWidth={3.4} />
  </svg>,

  // 4. Coast, with a spouting whale
  <svg key="ocean" {...sceneryProps}>
    <path d="M-10 150q70-18 140 0t140 0 140 0 140 0 140 0 140 0 150 0" strokeWidth={5.5} />
    <path d="M-10 172q70-18 140 0t140 0 140 0 140 0 140 0 140 0 150 0" strokeWidth={4} />
    {/* Chibi whale */}
    <path d="M392 148q-8-46 36-56 56-12 92 20 20 18 16 36" strokeWidth={5.5} fill="#ffffff" />
    <path d="M520 148q26-10 40-34 6 34-10 44" strokeWidth={5} />
    <Face x={432} y={112} r={26} />
    <path d="M452 74q-2-24 16-32M452 74q10-22 34-22" strokeWidth={4} />
    <path d="M418 130q22 8 44 0" strokeWidth={2.6} />
    {/* Lighthouse and a small sailboat */}
    <path d="M894 150l14-96h32l14 96" strokeWidth={5.5} fill="#ffffff" />
    <path d="M904 118h44M908 90h36" strokeWidth={4} />
    <path d="M902 54h44M914 54V34h20v20" strokeWidth={4} fill="#ffffff" />
    <path d="M912 24h24" strokeWidth={4} />
    <path d="M896 44l-22-8M952 44l22-8" strokeWidth={3} />
    <path d="M132 128q60 7 128 0l-22 28q-42 5-84 0z" strokeWidth={5} />
    <path d="M196 128V56" strokeWidth={4.5} />
    <path d="M202 62l44 56h-44z" strokeWidth={4.5} />
    <path d="M190 62l-30 56h30z" strokeWidth={4.5} />
    <path d="M300 48q12-11 24 0M660 58q10-9 20 0" strokeWidth={4} />
  </svg>,

  // 5. Space, with a floating astronaut
  <svg key="space" {...sceneryProps}>
    <path d="M-10 178q60-38 150-38 96 0 150 38" strokeWidth={5.5} />
    <path d="M700 178q52-34 132-34 84 0 136 34" strokeWidth={5.5} />
    <path d="M118 132q26-8 52 0M812 138q24-8 48 0" strokeWidth={3} />
    {/* Chibi astronaut */}
    <path d="M486 172q-6-52 34-54 40-2 34 54" strokeWidth={5.5} fill="#ffffff" />
    <path d="M478 130l-30 14M562 130l30 14" strokeWidth={5} />
    <path d="M486 150h68" strokeWidth={3} />
    <circle cx="520" cy="80" r="38" strokeWidth={5.5} fill="#ffffff" />
    <circle cx="520" cy="80" r="27" strokeWidth={3} />
    <Face x={520} y={80} r={27} />
    <path d="M550 58q14-6 20 6" strokeWidth={3} />
    {/* Rocket, ringed planet, stars */}
    <path d="M270 168q-14-52 14-84 28 32 14 84" strokeWidth={5} />
    <circle cx="284" cy="98" r="10" strokeWidth={3.4} />
    <path d="M270 138l-18 24h18M298 138l18 24h-18" strokeWidth={4} />
    <path d="M276 172q8 14 8 6t8-6" strokeWidth={4} fill="currentColor" />
    <circle cx="862" cy="70" r="30" strokeWidth={5} />
    <path d="M814 78q48 22 96-4" strokeWidth={4} />
    <g fill="currentColor" stroke="none">
      <path d="M108 62l5 12 12 5-12 5-5 12-5-12-12-5 12-5z" />
      <path d="M420 40l4 9 9 4-9 4-4 9-4-9-9-4 9-4z" />
      <path d="M690 52l4 9 9 4-9 4-4 9-4-9-9-4 9-4z" />
      <path d="M980 118l3 8 8 3-8 3-3 8-3-8-8-3 8-3z" />
    </g>
  </svg>,

  // 6. Countryside, with a cow that has opinions
  <svg key="countryside" {...sceneryProps}>
    <path d="M-10 168q90-46 190-18 90 26 170-16 84-44 176-2 92 42 180-10 76-46 184 8 76 38 190 0" strokeWidth={5.5} />
    {/* Barn */}
    <path d="M150 168v-56h96v56M144 112l54-30 54 30" strokeWidth={5.5} />
    <path d="M182 168v-32h32v32M198 92v-14" strokeWidth={4} />
    {/* Windmill */}
    <path d="M902 168l14-76h20l14 76" strokeWidth={5.5} fill="#ffffff" />
    <path d="M926 92l-6-26 40-14-6 28zM926 92l26 6 14 40-28-6zM926 92l6 26-40 14 6-28zM926 92l-26-6-14-40 28 6z" strokeWidth={4} fill="#ffffff" />
    <circle cx="926" cy="92" r="6" fill="currentColor" stroke="none" />
    {/* Chibi cow. Body and head are opaque, or the hill runs straight through. */}
    <path d="M508 150v18M552 152v16M604 152v16M640 150v18" strokeWidth={5} />
    <path d="M496 118q0-22 78-22t74 22q4 34-74 34t-78-34z" strokeWidth={5.5} fill="#ffffff" />
    <ellipse cx="556" cy="120" rx="15" ry="9" fill="currentColor" stroke="none" />
    <ellipse cx="612" cy="134" rx="11" ry="7" fill="currentColor" stroke="none" />
    <path d="M648 112q22-2 22 22" strokeWidth={3.4} />
    <circle cx="486" cy="106" r="30" strokeWidth={5.5} fill="#ffffff" />
    <path d="M462 86l-16-20 26 6M510 86l16-20-26 6" strokeWidth={4.5} />
    <Face x={484} y={100} r={28} />
    <ellipse cx="486" cy="120" rx="16" ry="10" strokeWidth={3} fill="#ffffff" />
    <circle cx="480" cy="118" r="3.4" fill="currentColor" stroke="none" />
    <circle cx="493" cy="118" r="3.4" fill="currentColor" stroke="none" />
    {/* Fence and grass */}
    <path d="M660 168v-30M700 168v-32M740 168v-30M652 146h96M652 158h96" strokeWidth={4} />
    <path d="M320 168q6-16 12 0M840 158q6-16 12 0" strokeWidth={3.4} />
  </svg>,

  // 7. Railway bridge, with a train that has a face
  <svg key="railway" {...sceneryProps}>
    <path d="M-10 122h1090" strokeWidth={5.5} />
    <path d="M40 122v56M180 122v56M320 122v56M760 122v56M900 122v56M1040 122v56" strokeWidth={5} />
    <path d="M40 178q0-38 70-38t70 38M180 178q0-38 70-38t70 38M760 178q0-38 70-38t70 38M900 178q0-38 70-38t70 38" strokeWidth={4.5} />
    {/* Chibi locomotive */}
    <path d="M420 118V64q0-10 12-10h84q12 0 12 10v54" strokeWidth={5.5} />
    <path d="M528 118V80h58q10 0 10 12v26" strokeWidth={5.5} />
    <path d="M446 40q-4-16 12-16t12 16z" strokeWidth={4.5} />
    <Face x={474} y={84} r={30} />
    <circle cx="450" cy="118" r="14" strokeWidth={4.5} />
    <circle cx="512" cy="118" r="14" strokeWidth={4.5} />
    <circle cx="566" cy="118" r="11" strokeWidth={4.5} />
    <path d="M604 118V86h74v32M690 118V90h64v28" strokeWidth={5} />
    {/* Smoke and hills behind */}
    <path d="M444 28q10-18 26-8t4 26" strokeWidth={4} />
    <path d="M392 42q9-14 21-6t3 20" strokeWidth={4} />
    <path d="M60 122q40-40 90-40t90 40M820 122q42-44 94-44t94 44" strokeWidth={4} />
  </svg>,

  // 8. Balloons over hills, one crew visible
  <svg key="balloons" {...sceneryProps}>
    <path d="M-10 178q100-44 200-14 96 28 180-10 88-40 180 4 92 44 180-8 84-44 180 28" strokeWidth={5.5} />
    {/* Big balloon with a chibi passenger */}
    <path d="M604 78q0-46-46-46t-46 46q0 30 46 62 46-32 46-62z" strokeWidth={5.5} />
    <path d="M534 32q10 42 0 76M582 32q-10 42 0 76" strokeWidth={3} />
    <path d="M540 122l10 18M576 122l-10 18M544 140h28v26h-28z" strokeWidth={4.5} />
    <circle cx="558" cy="132" r="13" strokeWidth={4} />
    <Face x={558} y={132} r={13} />
    {/* Two smaller balloons */}
    <path d="M244 96q0-34-34-34t-34 34q0 22 34 46 34-24 34-46z" strokeWidth={5} />
    <path d="M194 132l8 14M226 132l-8 14M198 146h24v20h-24z" strokeWidth={4} />
    <path d="M902 110q0-28-28-28t-28 28q0 18 28 38 28-20 28-38z" strokeWidth={5} />
    <path d="M860 142l6 12M888 142l-6 12M864 154h20v16h-20z" strokeWidth={4} />
    <path d="M340 44q13-12 26 0M700 34q11-10 22 0M736 52q9-8 18 0" strokeWidth={4} />
  </svg>,

  // 9. Lantern street, with a kid carrying one
  <svg key="lanterns" {...sceneryProps}>
    <Ground />
    <path d="M24 168V36M1056 168V36" strokeWidth={5} />
    <path d="M24 40q140 58 250 62 156 6 266 4 200-4 260-16 130-26 256-50" strokeWidth={4.5} />
    <g strokeWidth={4.5}>
      <path d="M150 72v14M126 86h48v40h-48zM150 126v12" />
      <path d="M330 100v14M306 114h48v40h-48zM330 154v10" />
      <path d="M746 102v14M722 116h48v40h-48zM746 156v10" />
      <path d="M930 62v14M906 76h48v40h-48zM930 116v12" />
    </g>
    <path d="M126 106h48M306 134h48M722 136h48M906 96h48" strokeWidth={2.6} />
    {/* Stalls */}
    <path d="M60 168v-40h120v40M52 128l68-24 68 24" strokeWidth={5} />
    <path d="M900 168v-36h130v36M892 132l65-22 65 22" strokeWidth={5} />
    {/* Chibi kid with a lantern */}
    <path d="M500 168q-4-40 22-50 30-12 52 4 20 12 16 46" strokeWidth={5.5} fill="#ffffff" />
    <circle cx="534" cy="82" r="30" strokeWidth={5.5} fill="#ffffff" />
    <Face x={534} y={82} r={30} />
    <path d="M506 60q28-20 56 0" strokeWidth={4} />
    <path d="M574 120q22-2 32-10" strokeWidth={4.5} />
    <path d="M614 98v12M596 110h36v32h-36zM614 142v10" strokeWidth={4} fill="#ffffff" />
    <path d="M420 148q8-18 16 0M660 152q8-18 16 0" strokeWidth={3.4} />
  </svg>,

  // 10. Harbour, with a crab on the dock
  <svg key="harbour" {...sceneryProps}>
    <path d="M-10 152q70-16 140 0t140 0 140 0 140 0 140 0 140 0 150 0" strokeWidth={5} />
    <path d="M0 122h420M60 122v30M180 122v30M300 122v30M400 122v30" strokeWidth={5.5} />
    {/* Boats */}
    <path d="M548 126q68 7 144 0l-24 28q-48 5-96 0z" strokeWidth={5.5} />
    <path d="M614 126V52" strokeWidth={4.5} />
    <path d="M620 58l46 58h-46z" strokeWidth={4.5} />
    <path d="M608 58l-32 58h32z" strokeWidth={4.5} />
    <path d="M816 134q46 6 98 0l-18 22q-32 4-62 0z" strokeWidth={5} />
    <path d="M862 134V78" strokeWidth={4} />
    <path d="M868 84l32 42h-32z" strokeWidth={4} />
    {/* Crates */}
    <path d="M100 122V86h56v36M100 104h56M128 86v36" strokeWidth={4.5} />
    <path d="M300 122V94h44v28M300 108h44" strokeWidth={4.5} />
    {/* Chibi crab */}
    <path d="M196 116q0-22 40-22t40 22q0 20-40 20t-40-20z" strokeWidth={5.5} fill="#ffffff" />
    <path d="M220 96V84M252 96V84" strokeWidth={4} />
    <circle cx="220" cy="80" r="5" fill="currentColor" stroke="none" />
    <circle cx="252" cy="80" r="5" fill="currentColor" stroke="none" />
    <path d="M224 118q12 10 24 0" strokeWidth={3} />
    <path d="M196 110l-24-6q-14 10-6 22 10 10 22 0z" strokeWidth={4.5} />
    <path d="M276 110l24-6q14 10 6 22-10 10-22 0z" strokeWidth={4.5} />
    <path d="M206 134l-10 14M228 138v12M244 138v12M266 134l10 14" strokeWidth={4} />
    {/* Gulls */}
    <path d="M420 46q13-12 26 0M470 60q11-10 22 0M740 40q13-12 26 0" strokeWidth={4} />
  </svg>,

  // 11. Camp at night, with a fox at the fire
  <svg key="campfire" {...sceneryProps}>
    <Ground />
    <path d="M96 110l-34 58h68zM96 72l-26 44h52zM96 40l-20 34h40z" strokeWidth={4.5} />
    <path d="M986 114l-32 54h64zM986 80l-24 40h48z" strokeWidth={4.5} />
    {/* Tent */}
    <path d="M200 168l64-84 64 84z" strokeWidth={5.5} />
    <path d="M264 168V96M264 96l-26 72M264 96l26 72" strokeWidth={4} />
    {/* Fire */}
    <path d="M540 168q-30-6-30-32 0-24 22-38 4 16 14 18 6-20-4-34 34 16 34 54 0 26-30 32z" strokeWidth={5} />
    <path d="M494 168l92-16M586 168l-92-16" strokeWidth={4.5} />
    {/* Chibi fox */}
    <path d="M700 168q-6-38 22-50 30-12 52 4 20 12 16 46" strokeWidth={5.5} />
    <circle cx="736" cy="88" r="30" strokeWidth={5.5} />
    <path d="M712 68l-8-24 26 12M760 68l8-24-26 12" strokeWidth={4.5} />
    <Face x={736} y={88} r={30} />
    <path d="M726 100q10 8 20 0" strokeWidth={2.6} />
    <path d="M782 156q30 6 34-22 2-16-12-18" strokeWidth={4.5} />
    <g fill="currentColor" stroke="none">
      <path d="M400 54l4 9 9 4-9 4-4 9-4-9-9-4 9-4z" />
      <path d="M860 44l4 9 9 4-9 4-4 9-4-9-9-4 9-4z" />
      <circle cx="620" cy="48" r="4" />
      <circle cx="316" cy="40" r="4" />
    </g>
  </svg>,

  // 12. Market stalls, with a vendor and a dog
  <svg key="market" {...sceneryProps}>
    <Ground />
    <path d="M70 168v-52h180v52" strokeWidth={5.5} />
    <path d="M56 116q22-30 52 0 22-30 52 0 22-30 52 0 22-30 52 0" strokeWidth={5} />
    <path d="M160 168v-52" strokeWidth={4} />
    <path d="M830 168v-46h170v46" strokeWidth={5.5} />
    <path d="M818 122q20-28 48 0 20-28 48 0 20-28 48 0" strokeWidth={5} />
    {/* Crates of round produce */}
    <path d="M300 168v-34h74v34M300 148h74" strokeWidth={4.5} />
    <circle cx="318" cy="126" r="10" strokeWidth={3.4} />
    <circle cx="340" cy="122" r="11" strokeWidth={3.4} />
    <circle cx="362" cy="127" r="9" strokeWidth={3.4} />
    {/* Chibi vendor behind the counter */}
    <path d="M500 168q-4-46 26-56 34-12 58 6 20 14 16 50" strokeWidth={5.5} />
    <circle cx="540" cy="76" r="32" strokeWidth={5.5} />
    <Face x={540} y={76} r={32} />
    <path d="M506 54q34-24 68 0M540 44v-14" strokeWidth={4} />
    <path d="M584 122l30 10" strokeWidth={4.5} />
    <path d="M456 168v-24h180v24" strokeWidth={5} />
    {/* Chibi dog */}
    <path d="M690 168q-4-28 16-36 22-10 38 2 14 10 12 34" strokeWidth={5} />
    <circle cx="714" cy="112" r="22" strokeWidth={5} />
    <path d="M696 96q-14-12-6-24 12 2 18 12M732 96q14-12 6-24-12 2-18 12" strokeWidth={4} />
    <Face x={714} y={112} r={22} />
    <path d="M748 146q22 2 24-16" strokeWidth={4} />
    <path d="M420 168q6-16 12 0M796 168q6-14 12 0" strokeWidth={3.4} />
  </svg>,
];
