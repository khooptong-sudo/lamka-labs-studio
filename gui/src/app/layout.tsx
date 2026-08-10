import type { Metadata } from "next";
import "./globals.css";

import { Sidebar } from "@/components/Sidebar";
import { ThemeProvider } from "@/components/ThemeProvider";

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
      className="h-full antialiased"
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

