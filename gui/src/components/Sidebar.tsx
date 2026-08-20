"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpen, Clapperboard, FileText, Film, Inbox, Settings } from "lucide-react";
import { ThemeToggle } from "./ThemeToggle";

function XIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
    </svg>
  );
}

export function Sidebar() {
  const pathname = usePathname();

  const navItems = [
    { name: "Research", href: "/", icon: Inbox },
    { name: "Production", href: "/films", icon: Clapperboard },
    { name: "Cinema", href: "/cinema", icon: Film },
    { name: "Drafts", href: "/drafts", icon: FileText },
    { name: "X Post", href: "/x", icon: XIcon },
    { name: "Studio setup", href: "/settings", icon: Settings },
    { name: "Guide", href: "/docs", icon: BookOpen },
  ];

  return (
    <aside className="studio-sidebar">
      <div className="studio-brand">
        <span className="studio-brand-mark" aria-hidden="true">LV</span>
        <div>
          <h1>LAMKA LABS</h1>
          <p>STUDIO</p>
        </div>
      </div>

      <nav className="studio-nav" aria-label="Studio navigation">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link 
              key={item.href}
              href={item.href} 
              className={`studio-nav-link ${
                isActive 
                  ? "studio-nav-link-active"
                  : ""
              }`}
            >
              <item.icon aria-hidden="true" />
              <span>{item.name}</span>
            </Link>
          );
        })}
      </nav>

      <div className="studio-status">
        <div className="studio-status-copy">
          <span className="studio-live-indicator" aria-hidden="true" />
          <div>
            <p>Worker connected</p>
            <span>Local production</span>
          </div>
        </div>
        <div className="studio-theme-row">
          <span>Appearance</span>
          <ThemeToggle />
        </div>
      </div>
    </aside>
  );
}
