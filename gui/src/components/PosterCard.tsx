"use client";

import { Lightbulb, ShieldAlert } from "lucide-react";

export type PosterSection = {
  heading: string;
  bullets: string[];
};

export type Poster = {
  title: string;
  subtitle: string;
  sections: PosterSection[];
  footer: string;
  style: string;
};

export default function PosterCard({
  poster,
  className = "",
}: {
  poster: Poster;
  className?: string;
}) {
  const isDark = poster.style === "dark";

  return (
    <div
      className={`relative w-[1080px] h-[1350px] p-16 flex flex-col overflow-hidden ${
        isDark
          ? "bg-slate-900 text-white"
          : "bg-gradient-to-br from-slate-50 to-white text-slate-900"
      } ${className}`}
      style={{ fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}
    >
      {/* Decorative background accent */}
      <div
        className={`absolute top-0 right-0 w-[600px] h-[600px] rounded-full blur-3xl opacity-20 pointer-events-none ${
          isDark ? "bg-blue-500" : "bg-blue-400"
        }`}
      />

      {/* Header */}
      <header className="relative z-10 mb-10">
        <div className="flex items-center gap-3 mb-4">
          <div className={`p-3 rounded-xl ${isDark ? "bg-blue-500/20" : "bg-blue-100"}`}>
            <Lightbulb className={`w-8 h-8 ${isDark ? "text-blue-300" : "text-blue-600"}`} />
          </div>
          <span className={`text-sm font-bold uppercase tracking-[0.25em] ${isDark ? "text-blue-300" : "text-blue-600"}`}>
            Finance Explained
          </span>
        </div>
        <h1 className="text-6xl font-black leading-tight tracking-tight mb-3">
          {poster.title}
        </h1>
        <p className={`text-2xl font-medium ${isDark ? "text-slate-300" : "text-slate-600"}`}>
          {poster.subtitle}
        </p>
      </header>

      {/* Sections grid */}
      <div className="relative z-10 grid grid-cols-2 gap-6 flex-1 content-start">
        {poster.sections.map((section, index) => (
          <div
            key={index}
            className={`rounded-2xl p-6 border ${
              isDark
                ? "bg-slate-800/60 border-slate-700"
                : "bg-white border-slate-200 shadow-sm"
            }`}
          >
            <div className="flex items-center gap-3 mb-4">
              <span
                className={`flex items-center justify-center w-10 h-10 rounded-full text-lg font-black ${
                  isDark
                    ? "bg-blue-500 text-white"
                    : "bg-blue-600 text-white"
                }`}
              >
                {index + 1}
              </span>
              <h2 className="text-xl font-bold leading-tight">{section.heading}</h2>
            </div>
            <ul className="space-y-3">
              {section.bullets.map((bullet, bIndex) => (
                <li key={bIndex} className="flex items-start gap-2 text-base leading-relaxed">
                  <span className={`mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${isDark ? "bg-blue-300" : "bg-blue-500"}`} />
                  {bullet}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      {/* Footer */}
      <footer className="relative z-10 mt-8 pt-6 border-t border-dashed flex items-center gap-3 text-sm opacity-80">
        <ShieldAlert className="w-5 h-5 flex-shrink-0" />
        <p>{poster.footer}</p>
      </footer>
    </div>
  );
}
