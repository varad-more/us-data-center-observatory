"use client";

/**
 * Every county and state holding a mapped data centre, sortable.
 *
 * The two power columns are the ones most likely to be misread, so they are
 * labelled as shares rather than as measurements. A county's megawatt figure is
 * its footprint's slice of a national total that Lawrence Berkeley National
 * Laboratory reported; nobody metered these buildings, and the number would be
 * an upper bound even if they had, because the national total is spread across
 * only the facilities OpenStreetMap knows about.
 */

import { useMemo, useState } from "react";
import Link from "next/link";

import type { Region } from "@/lib/observatory";
import { ScrollArea } from "@/components/ScrollArea";
import {
  formatRegionFootprintKm2,
  formatRegionMw,
} from "@/lib/facilityPresentation";

type SortKey = "name" | "facility_count" | "footprint_m2" | "est_mw";
type Scope = "all" | "county" | "state";

const COLUMNS: { key: SortKey; label: string; numeric: boolean }[] = [
  { key: "name", label: "Region", numeric: false },
  { key: "facility_count", label: "Facilities", numeric: true },
  { key: "footprint_m2", label: "Footprint km²", numeric: true },
  { key: "est_mw", label: "Share of US load MW", numeric: true },
];

export function RegionTable({ regions }: { regions: Region[] }) {
  const [scope, setScope] = useState<Scope>("county");
  const [sort, setSort] = useState<SortKey>("facility_count");
  const [query, setQuery] = useState("");

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return regions
      .filter((r) => (scope === "all" ? true : r.kind === scope))
      .filter(
        (r) =>
          !needle ||
          r.name.toLowerCase().includes(needle) ||
          r.state.toLowerCase().includes(needle),
      )
      .sort((a, b) => {
        if (sort === "name") return a.name.localeCompare(b.name);
        return (b[sort] as number) - (a[sort] as number);
      });
  }, [regions, scope, sort, query]);

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title">Regions</h2>
        <span className="card-note">{rows.length} shown</span>
      </div>

      <div className="controls">
        <div className="control-group" role="group" aria-label="Region type">
          {(["county", "state", "all"] as Scope[]).map((value) => (
            <button
              key={value}
              type="button"
              className={scope === value ? "chip chip-active" : "chip"}
              aria-pressed={scope === value}
              onClick={() => setScope(value)}
            >
              {value === "all"
                ? "Both"
                : value === "county"
                  ? "Counties"
                  : "States"}
            </button>
          ))}
        </div>
        <label className="control-search">
          <span className="sr-only">Filter regions by name</span>
          <input
            type="search"
            placeholder="Filter by name or state…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
      </div>

      <ScrollArea
        className="table-scroll"
        label="Regions by facility count, scrollable"
      >
        <table className="table">
          <thead>
            <tr>
              {COLUMNS.map((column) => (
                <th
                  key={column.key}
                  className={column.numeric ? "num" : undefined}
                  // aria-sort belongs to the header cell, not the control inside
                  // it. "name" sorts ascending; every numeric column sorts
                  // descending, because the question is always "where is the most".
                  aria-sort={
                    sort === column.key
                      ? column.key === "name"
                        ? "ascending"
                        : "descending"
                      : "none"
                  }
                >
                  <button
                    type="button"
                    className={
                      sort === column.key ? "th-sort th-sort-active" : "th-sort"
                    }
                    onClick={() => setSort(column.key)}
                  >
                    {column.label}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((region) => (
              <tr key={region.region_id}>
                <td>
                  <Link href={`/regions/${region.region_id.replace(":", "-")}`}>
                    {region.name}
                  </Link>
                  {region.kind === "county" && region.state ? (
                    <span className="muted small">, {region.state}</span>
                  ) : null}
                </td>
                <td className="num">
                  {region.facility_count.toLocaleString()}
                </td>
                <td className="num">{formatRegionFootprintKm2(region)}</td>
                <td className="num">{formatRegionMw(region)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollArea>

      {rows.length === 0 ? (
        <p className="muted small">No region matches that filter.</p>
      ) : null}

      <p className="small muted" style={{ marginBottom: 0 }}>
        Counties and states both appear, and they overlap — a county&apos;s
        facilities are also counted in its state. Never add the two together.
        The megawatt column is a share of a reported national total allocated by
        building footprint, not a measurement of these buildings. An em dash
        means nothing was measured to allocate from: every facility there is a
        point or a campus boundary with no building footprint, which is not the
        same as a footprint of zero.
      </p>
    </section>
  );
}
