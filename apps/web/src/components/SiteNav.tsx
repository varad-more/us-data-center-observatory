"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { ThemeToggle } from "./ThemeToggle";

/**
 * The primary rail: an identity line, then three labelled banks of links.
 *
 * Grouped rather than flat, because the site serves two different datasets and
 * a single thirteen-item strip gave a reader no way to tell which was which.
 * The groups are the actual division in the data: what OpenStreetMap reports
 * nationally, what Helios infers about one Arizona valley, and the reference
 * material explaining both.
 *
 * The group names are printed. They used to live only in an `aria-label` on the
 * list, which meant the distinction the grouping exists to draw was invisible to
 * everyone looking at the screen — thirteen identical links and two hairlines
 * that, at this type size, read as decoration. A bank label above each row is
 * how a labelled instrument panel says the same thing, and it costs no width.
 *
 * The two map entries used to read "National map" and "Site map" side by side.
 * "Site map" meant the Arizona parcel view, but it reads as a sitemap; both are
 * now named after the thing they actually draw.
 */
export const NAV_GROUPS = [
  {
    label: "Observatory",
    items: [
      { href: "/", label: "Overview" },
      { href: "/growth", label: "Growth" },
      { href: "/regions", label: "Regions" },
      { href: "/construction", label: "Construction" },
      { href: "/large-load-filings", label: "Large loads" },
      { href: "/observatory-map", label: "US infrastructure" },
      { href: "/changes", label: "Changes" },
    ],
  },
  {
    label: "Arizona study",
    items: [
      { href: "/sites", label: "Sites" },
      { href: "/map", label: "Parcel map" },
      { href: "/analytics", label: "Analytics" },
    ],
  },
  {
    label: "Reference",
    items: [
      { href: "/understand", label: "Basics" },
      { href: "/methodology", label: "Methods" },
      { href: "/sources", label: "Sources" },
    ],
  },
] as const;

/**
 * The site exports with `trailingSlash: true`, so the router reports "/growth/"
 * while the hrefs are written "/growth". Comparing them raw marks nothing as
 * current, which is how the rule for it sat in the stylesheet unused.
 */
export function normalisePath(value: string): string {
  const trimmed = value.replace(/\/+$/, "");
  return trimmed === "" ? "/" : trimmed;
}

const PANEL_ID = "site-nav-panel";

export function SiteNav() {
  const pathname = normalisePath(usePathname() || "/");
  const [open, setOpen] = useState(false);

  // A menu left open across a navigation covers the page the reader just asked
  // for. Closing on the path change also covers the browser's back button.
  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  // The panel covers most of a phone screen, so it needs the way out that every
  // other overlay has. Bound only while open, so the page carries no key
  // listener the rest of the time.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <header className="site-header">
      <div className="site-header-inner">
        <Link href="/" className="brand">
          <span className="brand-mark">HELIOS</span>
          <span className="brand-tag">US AI Infrastructure Observatory</span>
        </Link>

        <div className="header-tools">
          <button
            type="button"
            className="nav-toggle"
            aria-expanded={open}
            aria-controls={PANEL_ID}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? "Close" : "Menu"}
          </button>
          <ThemeToggle />
        </div>

        <nav
          id={PANEL_ID}
          className="nav"
          aria-label="Primary"
          data-open={open ? "true" : "false"}
        >
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="nav-bank">
              {/* Hidden from assistive technology because the list below carries
                  the same string as its accessible name; printed twice it would
                  be announced twice. */}
              <span className="nav-bank-label" aria-hidden="true">
                {group.label}
              </span>
              <ul className="nav-bank-items" aria-label={group.label}>
                {group.items.map((item) => {
                  const href = normalisePath(item.href);
                  const isPage = pathname === href;
                  // "/regions" is not the page a reader is on when they are deep
                  // in "/regions/county-51107", but it is the section, and
                  // saying so is the difference between a rail that orients and
                  // one that goes blank on every detail page. Marked with a
                  // weaker signal than the page itself, and not with
                  // aria-current, which means this page and nothing looser.
                  const isSection =
                    !isPage && href !== "/" && pathname.startsWith(`${href}/`);
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        aria-current={isPage ? "page" : undefined}
                        data-section={isSection ? "true" : undefined}
                      >
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>
      </div>
    </header>
  );
}
