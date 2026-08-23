import type { Metadata } from "next";
import { Fredoka, Nunito } from "next/font/google";
import "./globals.css";

import { Sidebar } from "@/components/Sidebar";
import { ThemeProvider } from "@/components/ThemeProvider";

// Rounded, friendly faces used by the generated posters (self-hosted by
// next/font, so html-to-image can inline them without a cross-origin fetch).
const posterDisplay = Fredoka({
  subsets: ["latin"],
  variable: "--font-poster-display",
  display: "swap",
});

const posterBody = Nunito({
  subsets: ["latin"],
  variable: "--font-poster-body",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Lamka Labs Studio",
  description: "Research-to-video production cockpit",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`h-full antialiased ${posterDisplay.variable} ${posterBody.variable}`}
    >
      <body className="min-h-[100dvh]">
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem disableTransitionOnChange>
          <Sidebar />
          <main className="studio-main">
            {children}
          </main>
        </ThemeProvider>
      </body>
    </html>
  );
}

