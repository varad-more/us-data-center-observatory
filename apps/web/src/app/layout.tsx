import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

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
  { href: "/map", label: "Map" },
  { href: "/sites", label: "Sites" },
  { href: "/sources", label: "Data sources" },
  { href: "/methodology", label: "Methodology" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
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
              </nav>
            </div>
          </header>

          <main id="main" className="container">
            {children}
          </main>

          <footer className="site-footer">
            <p>
              Helios infers development activity from public records. Confidence scores are
              model output, not fact. Helios does not assert the identity of any facility
              operator unless a direct filing establishes it.
            </p>
            <p>
              Parcel data courtesy of Maricopa County Assessor / Maricopa County GIS. Power
              infrastructure data &copy; OpenStreetMap contributors, ODbL. Owner names
              classified as belonging to private individuals are redacted before storage.
            </p>
          </footer>
        </div>
      </body>
    </html>
  );
}
