"use client";

export type CinematicControlState = {
  shot_scale: string;
  camera_angle: string;
  camera_movement: string;
  lens: string;
  lighting: string;
  color_treatment: string;
  pacing: string;
  motion_intent: string;
};

export const DEFAULT_CINEMATIC_CONTROLS: CinematicControlState = {
  shot_scale: "Medium close-up",
  camera_angle: "Eye level",
  camera_movement: "Slow push in",
  lens: "50mm natural perspective",
  lighting: "Soft window light",
  color_treatment: "Neutral documentary",
  pacing: "Measured",
  motion_intent: "Subject-led parallax",
};

const CONTROL_GROUPS: Array<{
  key: keyof CinematicControlState;
  label: string;
  options: string[];
}> = [
  { key: "shot_scale", label: "Shot scale", options: ["Wide establishing", "Full shot", "Medium", "Medium close-up", "Close-up", "Macro detail"] },
  { key: "camera_angle", label: "Camera angle", options: ["Eye level", "Low angle", "High angle", "Overhead", "Dutch tilt"] },
  { key: "camera_movement", label: "Camera movement", options: ["Locked frame", "Slow push in", "Pull-back reveal", "Lateral track", "Gentle orbit", "Handheld drift"] },
  { key: "lens", label: "Lens language", options: ["24mm wide perspective", "35mm environmental", "50mm natural perspective", "85mm portrait compression", "Macro optics"] },
  { key: "lighting", label: "Lighting", options: ["Soft window light", "Overcast daylight", "Sunrise rim light", "High-key studio", "Low-key practicals"] },
  { key: "color_treatment", label: "Color treatment", options: ["Neutral documentary", "Cool shadows, warm skin", "Muted earth palette", "Saturated playful color", "Monochrome"] },
  { key: "pacing", label: "Pacing", options: ["Measured", "Brisk", "Contemplative"] },
  { key: "motion_intent", label: "Frame-to-motion", options: ["Subject-led parallax", "Foreground reveal", "Environmental drift", "Locked frame, subject motion"] },
];

export default function CinematicControls({
  value,
  onChange,
  disabled = false,
}: {
  value: CinematicControlState;
  onChange: (value: CinematicControlState) => void;
  disabled?: boolean;
}) {
  return (
    <section className="border-t border-border" aria-labelledby="camera-language-heading">
      <div className="flex flex-wrap items-end justify-between gap-2 px-4 py-3">
        <div>
          <h3 id="camera-language-heading" className="text-sm font-semibold">Camera language</h3>
          <p className="mt-0.5 text-xs text-[var(--muted)]">A compact visual grammar shared by every generated scene.</p>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-primary">Continuity locked</span>
      </div>
      <div className="grid gap-px border-t border-border bg-border sm:grid-cols-2 xl:grid-cols-4">
        {CONTROL_GROUPS.map((control) => (
          <label key={control.key} className="bg-[var(--surface-deck)] p-3">
            <span className="mb-2 block font-mono text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]">{control.label}</span>
            <select
              value={value[control.key]}
              disabled={disabled}
              onChange={(event) => onChange({ ...value, [control.key]: event.target.value })}
              className="field-well min-h-10 w-full px-2 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-50"
            >
              {control.options.map((option) => <option key={option}>{option}</option>)}
            </select>
          </label>
        ))}
      </div>
    </section>
  );
}
