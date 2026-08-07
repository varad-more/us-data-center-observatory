/**
 * The facilities OpenStreetMap currently marks as under construction.
 *
 * This is a forward signal, but only a weak one. The status and geometry are
 * reported by contributors; the date is when the record first appeared in the
 * retained map history, not when construction began. No mapped area on this
 * page enters the operating-load allocation.
 */
import type { Metadata } from "next";
import Link from "next/link";

import { ScrollArea } from "@/components/ScrollArea";
import { openStreetMapElementUrl } from "@/lib/facilityPresentation";
import { routeMeta } from "@/lib/site";
import {
  getFacilities,
  getObservatoryMeta,
  getRegions,
  regionSlug,
} from "@/lib/observatory";

export const metadata: Metadata = {
  title: "Mapped construction",
  description:
    "US data-centre records that OpenStreetMap contributors currently mark as under construction, kept separate from operating-load estimates.",
  ...routeMeta("/construction/"),
};

export default async function ConstructionPage() {
  const [collection, regions, meta] = await Promise.all([
    getFacilities(),
    getRegions(),
    getObservatoryMeta(),
  ]);

  const construction = collection.features
    .filter((feature) => feature.properties.site_class === "construction")
    .sort(
      (a, b) => b.properties.footprint_m2 - a.properties.footprint_m2,
    );

  const counties = regions
    .filter(
      (region) =>
        region.kind === "county" && (region.construction_count ?? 0) > 0,
    )
    .sort(
      (a, b) =>
        (b.construction_count ?? 0) - (a.construction_count ?? 0) ||
        (b.construction_area_m2 ?? 0) - (a.construction_area_m2 ?? 0),
    );

  const countyByFips = new Map(
    regions
      .filter((region) => region.kind === "county")
      .map((region) => [region.fips, region]),
  );

  const states = new Set(
    construction
      .map((feature) => feature.properties.state)
      .filter((state): state is string => Boolean(state)),
  );
  const named = construction.filter((feature) =>
    Boolean(feature.properties.name),
  ).length;
  const dated = construction.filter((feature) =>
    Boolean(feature.properties.first_seen),
  ).length;
  const mappedAreaM2 = construction.reduce(
    (sum, feature) => sum + feature.properties.footprint_m2,
    0,
  );

  return (
    <div className="stack">
      <div className="card-header">
        <div>
          <h1>Mapped as under construction</h1>
          <p className="muted small" style={{ margin: 0 }}>
            {construction.length.toLocaleString()} data-centre records that contributors
            currently tag as being built, across {counties.length.toLocaleString()}{" "}
            counties in {states.size.toLocaleString()} states.
          </p>
        </div>
      </div>

      <div className="grid grid-4">
        <div className="metric">
          <div className="metric-label">Construction records</div>
          <div className="metric-value num">{construction.length.toLocaleString()}</div>
          <div className="metric-sub">
            {meta.construction_count?.toLocaleString() ?? "—"} in dataset metadata
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">Counties</div>
          <div className="metric-value num">{counties.length.toLocaleString()}</div>
          <div className="metric-sub">across {states.size} states</div>
        </div>
        <div className="metric">
          <div className="metric-label">Named records</div>
          <div className="metric-value num">{named.toLocaleString()}</div>
          <div className="metric-sub">named by OSM contributors</div>
        </div>
        <div className="metric">
          <div className="metric-label">Mapped area</div>
          <div className="metric-value num">{(mappedAreaM2 / 1e6).toFixed(2)}</div>
          <div className="metric-sub">km² of construction geometry, not floor area</div>
        </div>
      </div>

      <div className="notice">
        <strong>This is a forward mapping signal, not a construction census.</strong>{" "}
        A contributor has applied a construction tag to each record in the latest
        snapshot. Helios has not verified that work is active, when it began, what
        capacity is planned, or when it will finish. The {dated.toLocaleString()} dates
        available below are when the records first appeared in the retained OpenStreetMap
        history — never construction-start dates.
      </div>

      <div className="notice">
        <strong>No power or water figure is assigned to these records.</strong>{" "}
        Their mapped square metres describe construction geometry, not an operating
        building floor plate. Folding that area into the allocation would give unbuilt
        sites a share of electricity measured in 2024, so Helios carries the area and
        leaves consumption unknown.
      </div>

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Where construction is mapped</h2>
          <span className="card-note">counties, not added to their states</span>
        </div>
        <ScrollArea className="table-scroll" label="Where construction is mapped, scrollable">
          <table className="table">
            <thead>
              <tr>
                <th>County</th>
                <th className="num">Records</th>
                <th className="num">Mapped area km²</th>
                <th className="num">All mapped facilities</th>
              </tr>
            </thead>
            <tbody>
              {counties.map((county) => (
                <tr key={county.region_id}>
                  <td>
                    <Link href={`/regions/${regionSlug(county.region_id)}`}>
                      {county.name}
                    </Link>
                    <span className="muted small">, {county.state}</span>
                  </td>
                  <td className="num">
                    {(county.construction_count ?? 0).toLocaleString()}
                  </td>
                  <td className="num">
                    {((county.construction_area_m2 ?? 0) / 1e6).toFixed(2)}
                  </td>
                  <td className="num">{county.facility_count.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollArea>
        <p className="small muted" style={{ marginBottom: 0 }}>
          States and counties overlap, so this table uses counties only. A county absent
          from it has no construction <em>mapped</em>, which is a weaker statement than
          having none.
        </p>
      </section>

      <section className="card">
        <div className="card-header">
          <h2 className="card-title">The mapped records</h2>
          <span className="card-note">largest mapped area first</span>
        </div>
        <ScrollArea className="table-scroll" label="The mapped records, scrollable">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>County</th>
                <th>Operator</th>
                <th className="num">Mapped area m²</th>
                <th>First mapped</th>
                <th>Record</th>
              </tr>
            </thead>
            <tbody>
              {construction.map((feature) => {
                const properties = feature.properties;
                const county = properties.county_fips
                  ? countyByFips.get(properties.county_fips)
                  : undefined;
                const osmUrl = openStreetMapElementUrl(properties.id);

                return (
                  <tr key={properties.id}>
                    <td>
                      {properties.name ?? (
                        <span className="muted">unnamed record</span>
                      )}
                    </td>
                    <td>
                      {county ? (
                        <>
                          <Link href={`/regions/${regionSlug(county.region_id)}`}>
                            {county.name}
                          </Link>
                          <span className="muted small">, {county.state}</span>
                        </>
                      ) : (
                        <span className="muted">
                          {properties.state ?? "not placed"}
                        </span>
                      )}
                    </td>
                    <td>
                      {properties.operator ?? (
                        <span className="muted">not recorded</span>
                      )}
                    </td>
                    <td className="num">
                      {properties.footprint_m2.toLocaleString()}
                    </td>
                    <td className="mono small">
                      {properties.first_seen ?? (
                        <span className="muted">before retained history</span>
                      )}
                    </td>
                    <td>
                      {osmUrl ? (
                        <a href={osmUrl}>OpenStreetMap</a>
                      ) : (
                        <span className="muted">unavailable</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </ScrollArea>
        <p className="small muted" style={{ marginBottom: 0 }}>
          “First mapped” is observed history for the data-centre record. A record can be
          edited into or out of the construction class later, so the date does not
          establish when building work began.
        </p>
      </section>
    </div>
  );
}
