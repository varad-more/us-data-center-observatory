"use client";

/**
 * Jump from one region to any other without going back to the index.
 *
 * The full list is fetched rather than embedded. Inlining 323 options into all
 * 324 region pages would put the same list in every page's HTML and again in
 * its RSC payload; fetching the already-published `regions.json` costs one
 * request that the browser then caches across every region page visited after
 * it, and keeps the pages themselves the size they are.
 *
 * Because the list arrives after paint, the select starts holding a single
 * option describing where the reader already is — supplied by the server, which
 * knows the name — rather than an empty control or a spinner. It is a working
 * label immediately and a working picker a moment later.
 */

import { useEffect, useId, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { DATA_BASE, regionSlug } from "@/lib/regionPath";

interface PickerRegion {
  region_id: string;
  kind: "county" | "state";
  name: string;
  state: string;
}

const NATIONAL_ID = "national:US";

export function RegionPicker({
  currentId,
  currentLabel,
}: {
  currentId: string;
  currentLabel: string;
}) {
  const router = useRouter();
  const selectId = useId();
  const [regions, setRegions] = useState<PickerRegion[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${DATA_BASE}/regions.json`)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((payload) => {
        if (!cancelled) setRegions(payload?.items ?? []);
      })
      .catch(() => {
        // The index page lists every region, so a failed fetch costs the reader
        // a shortcut rather than the ability to get anywhere.
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const { counties, states } = useMemo(() => {
    const list = regions ?? [];
    // Alphabetical, not by size: this is a find-the-one-I-want control, and
    // hundreds of county names are only searchable in name order. Many states
    // share county names, so the state breaks the tie in both sort and label.
    const byName = (a: PickerRegion, b: PickerRegion) =>
      a.name.localeCompare(b.name) || a.state.localeCompare(b.state);
    return {
      counties: list.filter((r) => r.kind === "county").sort(byName),
      states: list.filter((r) => r.kind === "state").sort(byName),
    };
  }, [regions]);

  if (failed) {
    return (
      <p className="small" style={{ margin: 0 }}>
        <Link href="/regions">Browse all regions &rarr;</Link>
      </p>
    );
  }

  const ready = regions !== null;

  return (
    <div className="region-switch">
      <label htmlFor={selectId} className="region-switch-label">
        Change region
      </label>
      <select
        id={selectId}
        className="control-select"
        value={currentId}
        disabled={!ready}
        onChange={(event) =>
          router.push(`/regions/${regionSlug(event.target.value)}`)
        }
      >
        {ready ? (
          <>
            <option value={NATIONAL_ID}>United States — national</option>
            <optgroup label="Counties">
              {counties.map((region) => (
                <option key={region.region_id} value={region.region_id}>
                  {region.name}, {region.state}
                </option>
              ))}
            </optgroup>
            <optgroup label="States">
              {states.map((region) => (
                <option key={region.region_id} value={region.region_id}>
                  {region.name}
                </option>
              ))}
            </optgroup>
          </>
        ) : (
          <option value={currentId}>{currentLabel}</option>
        )}
      </select>
    </div>
  );
}
