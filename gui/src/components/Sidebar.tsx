"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpen, Clapperboard, FileText, Film, Inbox, Settings } from "lucide-react";
import { ThemeToggle } from "./ThemeToggle";

export function Sidebar() {
  const pathname = usePathname();

  const navItems = [
    { name: "Research", href: "/", icon: Inbox },
    { name: "Production", href: "/films", icon: Clapperboard },
    { name: "Cinema", href: "/cinema", icon: Film },
    { name: "Drafts", href: "/drafts", icon: FileText },
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
