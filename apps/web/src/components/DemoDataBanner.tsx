/**
 * States what the published deployment actually is.
 *
 * Helios exists to keep reported facts distinguishable from derived ones, so a
 * static snapshot that looked like a live feed would break the product's own
 * rule at the outermost layer. The banner names the snapshot as a snapshot and
 * dates it. It renders nothing when `meta.json` is absent, which is the case
 * when the UI is pointed at a live API.
 */
import Link from "next/link";

import fs from "fs/promises";
import path from "path";

import { API_BASE } from "@/lib/api";

interface ExportMeta {
  generated_at: string;
  site_count: number;
}

interface ObservatoryMeta {
  facility_count: number;
}

async function readJson<T>(...segments: string[]): Promise<T | null> {
  // Read from disk at build time; a static export has no server at runtime.
  try {
    const raw = await fs.readFile(
      path.join(process.cwd(), ...segments),
      "utf-8",
    );
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function formatExportDate(iso: string): string | null {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}

export async function DemoDataBanner() {
  const [meta, observatory] = await Promise.all([
    readJson<ExportMeta>("public", "api", "meta.json"),
    readJson<ObservatoryMeta>("public", "data", "meta.json"),
  ]);
  if (!meta) return null;

  const exportedOn = formatExportDate(meta.generated_at);

  return (
    <div className="demo-banner" role="note">
      <strong>Static snapshot.</strong> This site serves two different things:{" "}
      {observatory ? `${observatory.facility_count.toLocaleString()} ` : ""}data
      centres reported by OpenStreetMap contributors nationwide, and{" "}
      {meta.site_count}
      {exportedOn
        ? ` sites Helios infers from Arizona parcel records, exported on ${exportedOn}.`
        : " sites Helios infers from Arizona parcel records."}{" "}
      The first is a map of what has been recorded; the second is an argued
      hypothesis with an evidence chain. This is a point-in-time export, not a
      live view. See <a href={`${API_BASE}/meta.json`}>meta.json</a> or the{" "}
      <Link href="/methodology">methodology</Link>.
    </div>
  );
}
