/**
 * One region: what is mapped there, when it appeared, and its share of load.
 *
 * The page has to reconcile two numbers that look like they should match and
 * do not. The facility count is what is on the map today; the growth series
 * counts only facilities whose *appearance* was observed inside the history
 * window. A building mapped before 2012, or one whose creation edit falls
 * outside what ohsome retains, is in the first and not the second. Rather than
 * quietly showing whichever is larger, the page states the gap wherever it is
 * non-zero.
 */
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { MappingGrowthChart } from "@/components/MappingGrowthChart";
import { RegionPicker } from "@/components/RegionPicker";
import { facilityClassLabel } from "@/lib/facilityPresentation";
import {
  getRegionFacilities,
  getRegionSeries,
  getRegions,
  regionIdFromSlug,
  regionSlug,
} from "@/lib/observatory";

export async function generateStaticParams() {
  const regions = await getRegions();
  return [
    { regionId: regionSlug("national:US") },
    ...regions.map((region) => ({ regionId: regionSlug(region.region_id) })),
  ];
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ regionId: string }>;
}): Promise<Metadata> {
  const { regionId } = await params;
  const regions = await getRegions();
  const region = regions.find((r) => regionSlug(r.region_id) === regionId);
  const name = region ? region.name : "United States";
  return {
    title: name,
    description: `Data centres recorded in OpenStreetMap in ${name}, over time, with the region's share of national data-centre electricity and water.`,
  };
}

export default async function RegionPage({
  params,
}: {
  params: Promise<{ regionId: string }>;
}) {
  const { regionId } = await params;
  const id = regionIdFromSlug(regionId);
  const regions = await getRegions();
  const region = regions.find((r) => r.region_id === id);
  const isNational = id === "national:US";

  if (!region && !isNational) notFound();

  const [series, facilities] = await Promise.all([
    getRegionSeries(id),
    getRegionFacilities(id),
  ]);

  const name = region ? region.name : "United States";
  const subtitle = region
    ? region.kind === "county"
      ? `County in ${region.state}`
      : "State"
    : "National";

  const mapped = facilities.length;
  const observed = series?.points.at(-1)?.count ?? 0;
  const undated = mapped - observed;

  // Facilities carrying no power estimate, because what was mapped is a land
  // parcel or a site under construction rather than a building. Reported rather
  // than absorbed: without this the megawatt figure looks like a full account of
  // the region, and in a county mapped campus-first it is nowhere near one.
  const siteCount = region?.site_count ?? 0;
  const constructionCount = region?.construction_count ?? 0;
  const unmeasured = siteCount + constructionCount;

  const named = [...facilities]
    .filter((f) => f.properties.name)
    .sort((a, b) => b.properties.footprint_m2 - a.properties.footprint_m2)
    .slice(0, 40);

  // The picker reaches everywhere; these reach the handful of places a reader
  // on this page is most likely to want next. Server-rendered, so they work
  // before hydration and without JavaScript at all.
  const peers = (
    region?.kind === "county"
      ? regions.filter(
          (r) => r.kind === "county" && r.state === region.state && r.region_id !== id,
        )
      : region?.kind === "state"
        ? regions.filter((r) => r.kind === "county" && r.state === region.state)
        : regions.filter((r) => r.kind === "county")
  )
    .sort((a, b) => b.facility_count - a.facility_count)
    .slice(0, 12);

  const peerLabel =
    region?.kind === "county"
      ? `Other counties in ${region.state}`
      : region?.kind === "state"
        ? `Counties in ${region.name}`
        : "Densest counties";

  const currentLabel = region
    ? region.kind === "county"
      ? `${region.name}, ${region.state}`
      : region.name
    : "United States — national";

  return (
    <div className="stack">
      <div className="card-header">
        <div>
          <h1>{name}</h1>
          <p className="muted small" style={{ margin: 0 }}>
            {subtitle} · {mapped.toLocaleString()} data centres recorded in
            OpenStreetMap
          </p>
        </div>
        <RegionPicker currentId={id} currentLabel={currentLabel} />
      </div>

      {peers.length > 0 ? (
        <nav className="peer-nav" aria-label={peerLabel}>
          <span className="peer-nav-label">{peerLabel}</span>
          {peers.map((peer) => (
            <Link
              key={peer.region_id}
              href={`/regions/${regionSlug(peer.region_id)}`}
              className="chip"
            >
              {peer.name}
              <span className="muted"> {peer.facility_count.toLocaleString()}</span>
            </Link>
          ))}
          {region?.kind === "county" ? (
            <Link href={`/regions/state-${region.state}`} className="chip">
              All of {region.state}
            </Link>
          ) : null}
          {!isNational ? (
            <Link href="/regions/national-US" className="chip">
              United States
            </Link>
          ) : null}
          <Link href="/regions" className="chip">
            All regions →
          </Link>
        </nav>
      ) : null}

      <div className="grid grid-4">
        <div className="metric">
          <div className="metric-label">Mapped facilities</div>
          <div className="metric-value num">{mapped.toLocaleString()}</div>
          <div className="metric-sub">on the map today</div>
        </div>
        <div className="metric">
          <div className="metric-label">Floor area</div>
          <div className="metric-value num">
            {region ? (region.footprint_m2 / 1e6).toFixed(2) : "—"}
          </div>
          <div className="metric-sub">
            km² across {(region?.building_count ?? 0).toLocaleString()} buildings
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">Share of US load</div>
          <div className="metric-value num">
            {region ? Math.round(region.est_mw).toLocaleString() : "—"}
          </div>
          <div className="metric-sub">MW, inferred upper bound</div>
        </div>
        <div className="metric">
          <div className="metric-label">Water</div>
          <div className="metric-value num">
            {region ? (region.est_gal_per_day / 1e6).toFixed(2) : "—"}
          </div>
          <div className="metric-sub">million gal/day, inferred</div>
        </div>
      </div>

      {unmeasured > 0 ? (
        <div className="notice">
          <strong>
            {unmeasured.toLocaleString()} of these {mapped.toLocaleString()} are not
            mapped as buildings, so no power figure is estimated for them.
          </strong>{" "}
          {siteCount > 0 ? (
            <>
              {siteCount.toLocaleString()}{" "}
              {siteCount === 1 ? "is a campus boundary" : "are campus boundaries"} covering{" "}
              {(region!.site_area_m2! / 1e6).toFixed(2)} km² of land
              {constructionCount > 0 ? ", and " : ". "}
            </>
          ) : null}
          {constructionCount > 0 ? (
            <>
              {constructionCount.toLocaleString()}{" "}
              {constructionCount === 1 ? "is a site" : "are sites"} mapped as under
              construction.{" "}
            </>
          ) : null}
          The megawatt figure above divides a national total by{" "}
          <em>building floor area</em>, and the area of a land parcel is not floor area.
          A site still being built consumed none of the electricity that total measures.
          Both are counted here and left out of the estimate rather than folded into it,
          so this region&apos;s load is understated by however much those{" "}
          {unmeasured === 1 ? "represents" : "represent"}.
        </div>
      ) : null}

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">When these appeared on the map</h2>
          <span className="card-note">observed, not surveyed</span>
        </div>
        {series ? (
          <MappingGrowthChart points={series.points} />
        ) : (
          <p className="muted small">No mapping history recorded for this region.</p>
        )}

        {undated > 0 ? (
          <div className="notice">
            <strong>
              {undated.toLocaleString()} of these {mapped.toLocaleString()} facilities do
              not appear in the curve.
            </strong>{" "}
            The chart counts facilities whose appearance was observed in
            OpenStreetMap&apos;s edit history; one mapped before 2012 has no creation edit
            to observe. The two numbers answer different questions — how many are on the
            map now, and how many were watched arriving — and neither is wrong.
          </div>
        ) : null}
      </section>

      {region?.substation_count !== undefined ? (
        <section className="card">
          <div className="card-header">
            <h2 className="card-title">What the grid here looks like</h2>
            <span className="card-note">reported by OSM contributors</span>
          </div>
          <div className="grid grid-4">
            <div className="metric">
              <div className="metric-label">Substations</div>
              <div className="metric-value num">
                {region.substation_count.toLocaleString()}
              </div>
              <div className="metric-sub">69 kV and above</div>
            </div>
            <div className="metric">
              <div className="metric-label">Bulk substations</div>
              <div className="metric-value num">
                {(region.bulk_substation_count ?? 0).toLocaleString()}
              </div>
              <div className="metric-sub">230 kV and above</div>
            </div>
            <div className="metric">
              <div className="metric-label">Highest voltage</div>
              <div className="metric-value num">{region.max_voltage_kv ?? "—"}</div>
              <div className="metric-sub">
                kV, present in this {region.kind === "county" ? "county" : "state"}
              </div>
            </div>
            <div className="metric">
              <div className="metric-label">Generating capacity</div>
              <div className="metric-value num">
                {Math.round(region.plant_capacity_mw ?? 0).toLocaleString()}
              </div>
              <div className="metric-sub">
                MW across {(region.plant_count ?? 0).toLocaleString()}{" "}
                {region.plant_count === 1 ? "plant" : "plants"}
              </div>
            </div>
          </div>
          <p className="small" style={{ marginTop: "0.75rem" }}>
            A facility drawing hundreds of megawatts connects at bulk transmission
            voltage, so the second figure matters more than the first: forty 69 kV yards
            are not a substitute for one 500 kV substation.
            {(region.plants_without_capacity ?? 0) > 0 ? (
              <>
                {" "}
                {region.plants_without_capacity?.toLocaleString()} of the plants here
                carry no capacity tag, so the megawatt total is a floor rather than the
                region&apos;s output.
              </>
            ) : null}
          </p>
          <p className="small muted" style={{ marginBottom: 0 }}>
            <strong>Proximity is not connection.</strong> Nothing here shows that any
            facility has contracted power from any of these substations — that is settled
            by interconnection filings Helios cannot read, and in several regions those
            queues now run for years. A county with no substations shown has not been
            shown to have none; it may simply have none mapped.
          </p>
        </section>
      ) : null}

      {named.length > 0 ? (
        <section className="card">
          <div className="card-header">
            <h2 className="card-title">Largest named mapped records</h2>
            <span className="card-note">by mapped area</span>
          </div>
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Operator</th>
                  <th>Mapped as</th>
                  <th className="num">Mapped area m²</th>
                  <th className="num">Share MW</th>
                  <th>First mapped</th>
                </tr>
              </thead>
              <tbody>
                {named.map((facility) => (
                  <tr key={facility.properties.id}>
                    <td>{facility.properties.name}</td>
                    <td>
                      {facility.properties.operator ?? (
                        <span className="muted">not recorded</span>
                      )}
                    </td>
                    <td>{facilityClassLabel(facility.properties.site_class)}</td>
                    <td className="num">
                      {facility.properties.footprint_m2 > 0
                        ? facility.properties.footprint_m2.toLocaleString()
                        : "—"}
                    </td>
                    <td className="num">
                      {facility.properties.est_mw?.toFixed(1) ?? "—"}
                    </td>
                    <td className="mono small">
                      {facility.properties.first_seen ?? (
                        <span className="muted">before 2012</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small muted" style={{ marginBottom: 0 }}>
            &ldquo;First mapped&rdquo; is when OpenStreetMap recorded the facility, not
            when it was built — OpenStreetMap carries no construction dates. Mapped area
            means a building floor plate, campus boundary, or construction polygon
            according to the &ldquo;Mapped as&rdquo; column; those quantities are never
            added together. The megawatt column appears only for buildings and is their
            floor-area share of a reported national total, not a measurement.
          </p>
        </section>
      ) : null}
    </div>
  );
}
