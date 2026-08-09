// worker/scripts/gen_cineprompt_fixtures.mjs
// Run once, offline, to freeze oracle output:
//   npm pack cineprompt@1.2.0 && tar -xzf cineprompt-1.2.0.tgz
//   node scripts/gen_cineprompt_fixtures.mjs > tests/fixtures/cineprompt_golden.json
// Never run as part of the test suite.
import { readFileSync } from 'fs';
import { buildPromptText } from '../package/lib/prompt-builder.js';

// readFileSync resolves relative to CWD, not the script file, so it cannot
// share the '../package/...' specifier used by the import above (which
// resolves relative to this script). Resolve explicitly against the script's
// own URL instead, so this works regardless of the invoking CWD.
const VALUES = JSON.parse(readFileSync(new URL('../package/data/field-values.json', import.meta.url), 'utf8'));

// The CLI omits these four from every section, the live site has a DIALOGUE
// section for them. Fixtures must avoid them or the oracle disagrees with us.
const EXCLUDED = new Set(['dialogue', 'delivery_style', 'delivery_style_custom', 'dialogue_language']);

// 40 hand-picked states, one per merge rule plus empty-partner variants.
// Random sampling essentially never hits these branches: the brand-dedup path
// only fires when camera_body and color_science share a manufacturer.
const HANDPICKED = [
  { camera_body: 'shot on ARRI Alexa 65', color_science: 'ARRI LogC4 flat log footage, ungraded' },
  { camera_body: 'shot on RED V-Raptor', color_science: 'ARRI LogC4 flat log footage, ungraded' },
  { camera_body: 'shot on ARRI Alexa 65' },
  { color_science: 'ARRI LogC4 flat log footage, ungraded' },
  { shot_type: 'wide shot', movement: 'static' },
  { shot_type: 'wide shot', movement: 'pan' },
  { shot_type: 'wide shot' },
  { movement: 'static' },
  { movement: 'pan' },
  { focal_length: '50mm lens', lens_brand: 'ARRI Master Prime' },
  { focal_length: '50mm lens' },
  { lens_brand: 'ARRI Master Prime' },
  { lighting_style: 'soft light', lighting_type: 'daylight' },
  { lighting_style: 'soft light' },
  { lighting_type: 'daylight' },
  { hair_style: 'short hair', hair_color: 'black hair' },
  { hair_style: 'short hair' },
  { hair_color: 'black hair' },
  { env_time: 'dawn, first light', weather: 'light rain' },
  { env_time: 'dawn, first light' },
  { key_light: 'hard key from camera left', fill_light: 'soft fill from camera right' },
  { key_light: 'hard key from camera left' },
  { film_stock: 'Kodak Portra 400 film colors, warm pastels', color_grade: 'warm tones' },
  { film_stock: 'Kodak Portra 400 film colors, warm pastels' },
  { expression: 'a faint smile', body_language: 'shoulders relaxed' },
  { expression: 'a faint smile' },
  { char_label: 'a woman', age_range: 'in their 30s' },
  { char_label: 'a woman', age_range: 'a child' },
  { char_label: 'a woman' },
  { creature_category: 'wild animal', creature_label: 'the alpha' },
  { creature_category: 'wild animal' },
  { veh_type: 'car', veh_subtype: 'vintage roadster' },
  { veh_type: 'car' },
  { music_genre: 'orchestral', music_mood: 'tense, unsettling' },
  { music_genre: 'orchestral' },
  { sound_mode: 'voice-over narration', voiceover_text: 'It began quietly.' },
  { sound_mode: 'voice-over narration' },
  { setting: 'a cramped office', location_type: 'living room', custom_location: 'above a laundromat' },
  { setting: 'a cramped office', custom_location: 'above a laundromat' },
  { media_type: 'cinematic', genre: ['action', 'thriller'] },
];

// Deterministic PRNG so regeneration is reproducible.
let seed = 20260809;
function rand() {
  seed = (seed * 1103515245 + 12345) & 0x7fffffff;
  return seed / 0x7fffffff;
}

const FIELDS = Object.keys(VALUES).filter(f => !EXCLUDED.has(f) && VALUES[f].length > 0);

function randomState() {
  const fields = {};
  const count = 3 + Math.floor(rand() * 18);
  for (let i = 0; i < count; i++) {
    const f = FIELDS[Math.floor(rand() * FIELDS.length)];
    fields[f] = VALUES[f][Math.floor(rand() * VALUES[f].length)];
  }
  return fields;
}

const out = [];
for (const fields of HANDPICKED) {
  out.push({ fields, expected: buildPromptText({ fields }) });
}
for (let i = 0; i < 200; i++) {
  const fields = randomState();
  out.push({ fields, expected: buildPromptText({ fields }) });
}
process.stdout.write(JSON.stringify(out, null, 1));
