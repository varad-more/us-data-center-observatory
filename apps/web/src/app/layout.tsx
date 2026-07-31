import type { Metadata } from "next";
import localFont from "next/font/local";
import Link from "next/link";

import { DemoDataBanner } from "@/components/DemoDataBanner";
import { SiteFooter } from "@/components/SiteFooter";
import { THEME_INIT_SCRIPT, ThemeToggle } from "@/components/ThemeToggle";
import "./globals.css";

/**
 * Fraunces carries the display voice; the interface stays on the system sans.
 *
 * Loaded through next/font/local rather than a hand-written @font-face because
 * the site may be served under a base path — next/font rewrites
 * the URL and fingerprints the file, where a raw url() in globals.css would have
 * to hardcode the prefix and would break the moment the path changed.
 */
const fraunces = localFont({
  src: "./fonts/fraunces-latin-var.woff2",
  variable: "--font-fraunces",
  display: "swap",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: {
    default: "Helios Open AI Infrastructure Observatory",
    template: "%s | Helios",
  },
  description:
    "Where US data centres are, how fast they are arriving, and what they draw in electricity and water — counted from public records.",
};

/**
 * Grouped rather than flat, because the site serves two different datasets and
 * a single ten-item strip gave a reader no way to tell which was which. The
 * groups are the actual division in the data: what OpenStreetMap reports
 * nationally, what Helios infers about one Arizona valley, and the reference
 * material explaining both.
 *
 * The two map entries used to read "National map" and "Site map" side by side.
 * "Site map" meant the Arizona parcel view, but it reads as a sitemap; both are
 * now named after the thing they actually draw.
 */
const NAV_GROUPS = [
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
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={fraunces.variable} suppressHydrationWarning>
      <head>
        {/* Runs before first paint so a dark-mode reader never sees the ivory
            ground flash. Must be inline and blocking; see THEME_INIT_SCRIPT. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body>
        <div className="shell">
          <a href="#main" className="skip-link">
            Skip to content
          </a>
          <header className="site-header">
            <div className="site-header-inner">
              <Link href="/" className="brand">
                <span className="brand-mark">HELIOS</span>
                <span className="brand-tag">Open AI Infrastructure Observatory</span>
              </Link>
              <nav className="nav" aria-label="Primary">
                {NAV_GROUPS.map((group) => (
                  <ul key={group.label} className="nav-group" aria-label={group.label}>
                    {group.items.map((item) => (
                      <li key={item.href}>
                        <Link href={item.href}>{item.label}</Link>
                      </li>
                    ))}
                  </ul>
                ))}
                <ThemeToggle />
              </nav>
            </div>
          </header>

          <DemoDataBanner />

          <main id="main" className="container">
            {children}
          </main>

          <SiteFooter />
        </div>
      </body>
    </html>
  );
}
