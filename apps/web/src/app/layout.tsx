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
 * the site is served under the /project-helios base path — next/font rewrites
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
    "From permit to power-on: transparent early-warning intelligence for AI infrastructure.",
};

const NAV = [
  { href: "/", label: "Observatory" },
  { href: "/growth", label: "Growth" },
  { href: "/regions", label: "Regions" },
  { href: "/changes", label: "Changes" },
  { href: "/observatory-map", label: "National map" },
  { href: "/map", label: "Site map" },
  { href: "/sites", label: "Sites" },
  { href: "/sources", label: "Data sources" },
  { href: "/analytics", label: "Analytics" },
  { href: "/methodology", label: "Methodology" },
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
                {NAV.map((item) => (
                  <Link key={item.href} href={item.href}>
                    {item.label}
                  </Link>
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
