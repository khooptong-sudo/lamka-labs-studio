const fs = require("fs");
const path = require("path");
const sharp = require(path.join(__dirname, "..", "gui", "node_modules", "sharp"));

const OUT_DIR = path.join(__dirname, "assets");
fs.mkdirSync(OUT_DIR, { recursive: true });

// Lamka Labs Studio — refined brand palette
const PALETTE = {
  bg: "#0A0A0A",
  gold: "#D4AF37",
  champagne: "#C9A227",
  silver: "#C0C0C0",
  charcoal: "#1A1A1A",
  ivory: "#F5F5F0",
  graphite: "#2A2A2A",
};

function svgWrapper({ width, height, content, bg = PALETTE.bg }) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <rect width="${width}" height="${height}" fill="${bg}" />
  ${content}
</svg>`;
}





function wordmarkHorizontal(x, y, size = 48, color = PALETTE.ivory) {
  return `
    <text x="${x}" y="${y}" font-size="${size}" dominant-baseline="middle">
      <tspan font-family="'Georgia','Times New Roman',serif" font-weight="400" fill="${color}" letter-spacing="0.04em">LAMKA</tspan>
      <tspan dx="${size * 0.32}" font-family="'Helvetica Neue','Arial',sans-serif" font-weight="300" fill="${color}" letter-spacing="0.12em">LABS</tspan>
      <tspan dx="${size * 0.42}" dy="-${size * 0.18}" font-family="'Georgia','Times New Roman',serif" font-size="${size * 0.52}" font-weight="400" fill="${PALETTE.gold}" letter-spacing="0.18em">STUDIO</tspan>
    </text>
  `;
}



function wordmarkCentered(cx, y, size = 48, color = PALETTE.ivory) {
  return `
    <text x="${cx}" y="${y}" font-size="${size}" text-anchor="middle" dominant-baseline="middle">
      <tspan font-family="'Georgia','Times New Roman',serif" font-weight="400" fill="${color}" letter-spacing="0.04em">LAMKA</tspan>
      <tspan dx="${size * 0.32}" font-family="'Helvetica Neue','Arial',sans-serif" font-weight="300" fill="${color}" letter-spacing="0.12em">LABS</tspan>
      <tspan x="${cx}" y="${y + size * 1.2}" font-family="'Helvetica Neue','Arial',sans-serif" font-size="${size * 0.34}" font-weight="400" fill="${PALETTE.gold}">LUXURY CONTENT STUDIO</tspan>
    </text>
  `;
}

const LOGOS = [
  {
    id: "01-aperture",
    name: "Aperture Mark",
    concept: "Focus, lens, and precision — the aperture forms a negative-space L.",
    drawIcon(size) {
      const c = size / 2;
      const r = size * 0.36;
      const blades = 6;
      let bladePaths = "";
      for (let i = 0; i < blades; i++) {
        const a1 = (i * 360) / blades;
        const a2 = ((i + 1) * 360) / blades - 6;
        const rad1 = (Math.PI / 180) * a1;
        const rad2 = (Math.PI / 180) * a2;
        const x1 = c + r * 0.35 * Math.cos(rad1);
        const y1 = c + r * 0.35 * Math.sin(rad1);
        const x2 = c + r * Math.cos(rad1);
        const y2 = c + r * Math.sin(rad1);
        const x3 = c + r * Math.cos(rad2);
        const y3 = c + r * Math.sin(rad2);
        bladePaths += `<path d="M${x1},${y1} L${x2},${y2} A${r},${r} 0 0,1 ${x3},${y3} Z" fill="${PALETTE.gold}" opacity="0.92" />`;
      }
      return `
        <circle cx="${c}" cy="${c}" r="${r + 6}" fill="none" stroke="${PALETTE.graphite}" stroke-width="2" />
        ${bladePaths}
        <path d="M${c - r * 0.55},${c + r * 0.15} L${c - r * 0.55},${c + r * 0.65} L${c + r * 0.25},${c + r * 0.65}" fill="none" stroke="${PALETTE.bg}" stroke-width="${size * 0.055}" stroke-linecap="square" />
      `;
    },
  },
  {
    id: "02-frame",
    name: "Frame Mark",
    concept: "A studio frame with an L-shaped cut — craft, composition, and clarity.",
    drawIcon(size) {
      const pad = size * 0.22;
      const w = size - pad * 2;
      const sw = size * 0.065;
      const x1 = pad;
      const y1 = pad;
      const x2 = pad + w;
      const y2 = pad + w;
      return `
        <rect x="${x1}" y="${y1}" width="${w}" height="${w}" fill="none" stroke="${PALETTE.gold}" stroke-width="${sw}" />
        <line x1="${x1}" y1="${y2 - w * 0.35}" x2="${x1 + w * 0.65}" y2="${y2 - w * 0.35}" stroke="${PALETTE.bg}" stroke-width="${sw * 1.2}" stroke-linecap="butt" />
        <line x1="${x1 + w * 0.35}" y1="${y2 - w * 0.35}" x2="${x1 + w * 0.35}" y2="${y2}" stroke="${PALETTE.bg}" stroke-width="${sw * 1.2}" stroke-linecap="butt" />
      `;
    },
  },
  {
    id: "03-prism",
    name: "Prism Mark",
    concept: "Three planes of light converge into an L — insight, refraction, and craft.",
    drawIcon(size) {
      const pad = size * 0.24;
      const s = size - pad * 2;
      const t = s * 0.38;
      const x = pad;
      const y = size - pad - s;
      return `
        <polygon points="${x},${y} ${x + t},${y} ${x},${y + s}" fill="${PALETTE.gold}" opacity="0.35" />
        <polygon points="${x + t * 0.15},${y + t * 0.15} ${x + t * 1.45},${y + t * 0.15} ${x + t * 0.15},${y + s - t * 0.15}" fill="${PALETTE.gold}" opacity="0.65" />
        <polygon points="${x + t * 0.35},${y + t * 0.35} ${x + t * 1.85},${y + t * 0.35} ${x + t * 0.35},${y + s - t * 0.35}" fill="${PALETTE.champagne}" opacity="0.95" />
      `;
    },
  },
  {
    id: "04-node",
    name: "Node Mark",
    concept: "Connected points form the L — intelligence, collaboration, and studio networks.",
    drawIcon(size) {
      const nodes = [
        [0.25, 0.28], [0.48, 0.22], [0.72, 0.30],
        [0.22, 0.52], [0.45, 0.48], [0.68, 0.52],
        [0.28, 0.75], [0.52, 0.72], [0.75, 0.78],
      ];
      const active = [0, 3, 6, 7]; // forms an L
      let circles = "";
      let lines = "";
      const r = size * 0.028;
      // connections
      const pairs = [[0, 3], [3, 6], [6, 7]];
      for (const [a, b] of pairs) {
        const x1 = nodes[a][0] * size;
        const y1 = nodes[a][1] * size;
        const x2 = nodes[b][0] * size;
        const y2 = nodes[b][1] * size;
        lines += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${PALETTE.gold}" stroke-width="${size * 0.012}" />`;
      }
      nodes.forEach((n, i) => {
        const isActive = active.includes(i);
        const cx = n[0] * size;
        const cy = n[1] * size;
        circles += `<circle cx="${cx}" cy="${cy}" r="${isActive ? r * 1.35 : r}" fill="${isActive ? PALETTE.gold : PALETTE.graphite}" />`;
      });
      return lines + circles;
    },
  },
  {
    id: "05-seal",
    name: "Monogram Seal",
    concept: "A timeless circular seal with interlocking LL initials — heritage and authority.",
    drawIcon(size) {
      const c = size / 2;
      const r = size * 0.32;
      const sw = size * 0.018;
      return `
        <circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="${PALETTE.gold}" stroke-width="${sw}" />
        <circle cx="${c}" cy="${c}" r="${r + size * 0.045}" fill="none" stroke="${PALETTE.graphite}" stroke-width="${sw * 0.6}" />
        <text x="${c}" y="${c + r * 0.42}" font-family="'Georgia','Times New Roman',serif" font-size="${r * 1.15}" font-weight="400" fill="${PALETTE.ivory}" text-anchor="middle" letter-spacing="-0.05em">LL</text>
        <path d="M${c},${c - r * 0.78} L${c},${c - r * 0.62}" stroke="${PALETTE.gold}" stroke-width="${sw}" />
        <path d="M${c - r * 0.1},${c - r * 0.78} L${c - r * 0.1},${c - r * 0.62}" stroke="${PALETTE.gold}" stroke-width="${sw}" />
      `;
    },
  },
  {
    id: "06-sovereign",
    name: "Sovereign Studio Seal",
    concept: "Hairline double-ring seal with a shared-stem LL monogram — family DNA to Lamka Equities, made distinct for the studio.",
    hasDivider: true,
    drawIcon(size) {
      const c = size / 2;
      const r = size * 0.30;
      const sw = size * 0.016;
      const strokeW = size * 0.038;
      const stemH = r * 1.15;
      const stemY = c - stemH / 2;
      return `
        <circle cx="${c}" cy="${c}" r="${r}" fill="none" stroke="${PALETTE.ivory}" stroke-width="${sw}" />
        <circle cx="${c}" cy="${c}" r="${r - size * 0.045}" fill="none" stroke="${PALETTE.gold}" stroke-width="${sw}" />
        <line x1="${c}" y1="${stemY}" x2="${c}" y2="${stemY + stemH}" stroke="${PALETTE.ivory}" stroke-width="${strokeW}" stroke-linecap="round" />
        <line x1="${c}" y1="${c + r * 0.05}" x2="${c - r * 0.55}" y2="${c + r * 0.05}" stroke="${PALETTE.ivory}" stroke-width="${strokeW}" stroke-linecap="round" />
        <line x1="${c}" y1="${c + r * 0.35}" x2="${c + r * 0.55}" y2="${c + r * 0.35}" stroke="${PALETTE.ivory}" stroke-width="${strokeW}" stroke-linecap="round" />
        <path d="M${c - r * 0.22},${c + r * 0.58} Q${c},${c + r * 0.78} ${c + r * 0.22},${c + r * 0.58}" fill="none" stroke="${PALETTE.gold}" stroke-width="${sw * 1.4}" stroke-linecap="round" />
      `;
    },
  },
];

async function render({ id, name, concept, drawIcon, hasDivider = false }) {
  const sizes = {
    icon: 512,
    wordmark: 1200,
    social: 1080,
    favicon: 64,
  };

  // 1. Icon-only SVG
  const iconSvg = svgWrapper({
    width: sizes.icon,
    height: sizes.icon,
    content: drawIcon(sizes.icon),
  });
  fs.writeFileSync(path.join(OUT_DIR, `${id}-icon.svg`), iconSvg);

  // 2. Logo with wordmark
  const wmSize = 58;
  const logoSize = 150;
  const canvasH = 320;
  const canvasW = sizes.wordmark;
  const logoX = 110;
  const logoY = (canvasH - logoSize) / 2;
  const dividerX = logoX + logoSize + 35;
  const wmX = dividerX + (hasDivider ? 40 : 0) + 25;
  const wmY = canvasH / 2;

  const dividerSvg = hasDivider
    ? `<rect x="${dividerX}" y="${canvasH * 0.18}" width="2" height="${canvasH * 0.64}" fill="${PALETTE.graphite}" />`
    : "";

  const wordmarkSvg = svgWrapper({
    width: canvasW,
    height: canvasH,
    content: `
      <g transform="translate(${logoX}, ${logoY})">${drawIcon(logoSize)}</g>
      ${dividerSvg}
      ${wordmarkHorizontal(wmX, wmY, wmSize)}
    `,
  });
  fs.writeFileSync(path.join(OUT_DIR, `${id}-logo.svg`), wordmarkSvg);

  // 3. Social square (mark + wordmark stacked)
  const socialSize = sizes.social;
  const socialIconSize = 360;
  const socialSvg = svgWrapper({
    width: socialSize,
    height: socialSize,
    content: `
      <g transform="translate(${(socialSize - socialIconSize) / 2}, ${socialSize * 0.18})">${drawIcon(socialIconSize)}</g>
      ${wordmarkCentered(socialSize / 2, socialSize * 0.72, 86, PALETTE.ivory)}
    `,
  });
  fs.writeFileSync(path.join(OUT_DIR, `${id}-social.svg`), socialSvg);

  // 4. Favicon SVG
  const favSvg = svgWrapper({
    width: sizes.favicon,
    height: sizes.favicon,
    content: drawIcon(sizes.favicon),
  });
  fs.writeFileSync(path.join(OUT_DIR, `${id}-favicon.svg`), favSvg);

  // Render PNG and JPEG
  for (const [suffix, svgBuffer] of [
    ["icon", iconSvg],
    ["logo", wordmarkSvg],
    ["social", socialSvg],
    ["favicon", favSvg],
  ]) {
    const base = path.join(OUT_DIR, `${id}-${suffix}`);
    await sharp(Buffer.from(svgBuffer))
      .png({ compressionLevel: 9 })
      .resize(suffix === "favicon" ? 64 : null)
      .toFile(`${base}.png`);

    await sharp(Buffer.from(svgBuffer))
      .jpeg({ quality: 95, background: PALETTE.bg })
      .resize(suffix === "favicon" ? 64 : null)
      .toFile(`${base}.jpg`);
  }

  console.log(`✓ ${id}: ${name}`);
}

(async () => {
  for (const logo of LOGOS) {
    await render(logo);
  }
  console.log(`\nAssets written to ${OUT_DIR}`);
})();
