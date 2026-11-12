"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Forecast map" },
  { href: "/planner/", label: "Crew planner" },
  { href: "/track-record/", label: "Track record" },
  { href: "/methods/", label: "Methods & model card" },
];

export default function Nav() {
  const path = usePathname();
  return (
    <header className="top">
      <Link className="brand" href="/">Broward sargassum forecast</Link>
      <nav aria-label="Main">
        {LINKS.map((l) => (
          <Link key={l.href} href={l.href} aria-current={path === l.href || path + "/" === l.href ? "page" : undefined}>
            {l.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
