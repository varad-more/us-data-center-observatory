import Link from "next/link";
import { notFound } from "next/navigation";

import {
  AssertionBadge,
  ConfidenceBadge,
  OperatorStatus,
  StatusPill,
} from "@/components/AssertionBadge";
import { ApiUnavailable } from "@/components/ApiUnavailable";
import { InfrastructureMap } from "@/components/InfrastructureMap";
import { ScoreExplanation, Metric } from "@/components/ScoreExplanation";
import { SatelliteComparison } from "@/components/SatelliteComparison";
import { Timeline } from "@/components/Timeline";
import {
  ApiError,
  evidenceBundleUrl,
  evidenceJsonUrl,
  getMapInfrastructure,
  getMapSites,
  getSite,
  getTimeline,
  listSites,
} from "@/lib/api";
import type { Dependency, Parcel, SiteDetail } from "@/lib/types";

export async function generateStaticParams() {
  try {
    const sites = await listSites({ limit: 200 });
    return sites.items.map((site) => ({ siteId: site.id }));
  } catch {
    return [
      { siteId: "AZ-MESA-001" },
      { siteId: "f272c49f-e2d2-4975-9aa8-0077384ede69" },
      { siteId: "AZ-CHANDLER-001" },
      { siteId: "3822e5b6-60f4-4e89-8da2-c33907a89140" },
    ];
  }
}

const STAGE_COUNT = 9;

interface PageProps {
  params: Promise<{ siteId: string }>;
}

export default async function SiteDetailPage({ params }: PageProps) {
  const { siteId } = await params;

  let site: SiteDetail;
  let timeline;
  let mapSites;
  let infrastructure;
  try {
    [site, timeline] = await Promise.all([getSite(siteId), getTimeline(siteId)]);
    const bbox = boundingBoxFor(site);
    [mapSites, infrastructure] = await Promise.all([
      getMapSites(bbox),
      getMapInfrastructure(bbox),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      notFound();
    }
    return <ApiUnavailable error={error} />;
  }

  const centroid = site.centroid ?? [-111.72, 33.34];

  return (
    <div className="stack">
      <header>
        <div className="card-header" style={{ marginBottom: "0.25rem" }}>
          <div>
            <h1 style={{ marginBottom: "0.25rem" }}>
              <span className="mono">{site.project_code}</span>
            </h1>
            <p className="muted" style={{ margin: 0 }}>
              {site.jurisdiction ?? "Unknown jurisdiction"}, {site.county} County,
              Arizona &middot; {site.site_kind.replace(/_/g, " ")}{" "}
              <AssertionBadge assertion={site.site_kind_assertion} />
            </p>
          </div>
          <div className="button-row">
            <a className="button" href={evidenceBundleUrl(site.id)}>
              Download evidence bundle
            </a>
            <a className="button" href={evidenceJsonUrl(site.id)}>
              Evidence JSON
            </a>
          </div>
        </div>

        <StageTrack stage={site.current_stage} label={site.current_stage_label} />
      </header>

      <div className="grid grid-4">
        <Metric
          label="Confidence (Id. / Stage)"
          value={`${site.current_confidence.toFixed(0)}% / ${site.stage_confidence.toFixed(0)}%`}
          sub={site.confidence_band.replace("_", " ")}
        />
        <Metric
          label="Site area"
          value={site.total_acres ? `${site.total_acres.toFixed(1)}` : "—"}
          sub={`acres across ${site.parcel_count} parcel${site.parcel_count === 1 ? "" : "s"}`}
        />
        <Metric
          label="Evidence records"
          value={String(site.evidence_count)}
          sub={
            site.first_signal_date
              ? `first signal ${site.first_signal_date}`
              : "no dated signals"
          }
        />
        <Metric
          label="Estimated load"
          value={(() => {
            const powerEst = site.estimates?.find((e) => e.estimate_type === "power_capacity");
            return powerEst && powerEst.likely_value !== null
              ? `${powerEst.likely_value} ${powerEst.unit}`
              : "Not established";
          })()}
          sub={(() => {
            const powerEst = site.estimates?.find((e) => e.estimate_type === "power_capacity");
            const waterEst = site.estimates?.find((e) => e.estimate_type === "water_usage");
            if (powerEst && waterEst && waterEst.likely_value !== null) {
              return `+ ~${waterEst.likely_value.toLocaleString()} ${waterEst.unit} water (heuristic)`;
            }
            return "requires a utility filing Helios cannot yet read";
          })()}
        />
      </div>

      {site.summary && (
        <div className="notice">
          <strong>Summary.</strong> {site.summary}
        </div>
      )}

      <div className="split">
        <div className="stack">
          <section className="card">
            <div className="card-header">
              <h2 className="card-title">Evidence timeline</h2>
              <span className="card-note">
                {timeline.entries.length} chronological entries
              </span>
            </div>
            <Timeline entries={timeline.entries} />
          </section>

          {site.latest_prediction && (
            <section className="card">
              <div className="card-header">
                <h2 className="card-title">Why Helios believes this</h2>
                <ConfidenceBadge
                  confidence={site.current_confidence}
                  band={site.confidence_band}
                />
              </div>
              <ScoreExplanation prediction={site.latest_prediction} />
            </section>
          )}

          {/* SATELLITE COMPARISON */}
          <section className="card">
            <div className="card-header">
              <h2 className="card-title">Remote Sensing (Copernicus)</h2>
            </div>
            <SatelliteComparison projectCode={site.project_code} />
          </section>
        </div>

        <div className="stack">
          <section className="card">
            <div className="card-header">
              <h2 className="card-title">Location</h2>
            </div>
            <InfrastructureMap
              sites={mapSites}
              infrastructure={infrastructure}
              className="map-container map-container--detail"
              initialView={{
                longitude: centroid[0],
                latitude: centroid[1],
                zoom: 13.2,
              }}
              focusProjectCode={site.project_code}
            />
          </section>

          <section className="card">
            <div className="card-header">
              <h2 className="card-title">Operator and ownership</h2>
              <OperatorStatus status={site.operator_status} />
            </div>
            <OrganizationList site={site} />
          </section>

          <section className="card">
            <div className="card-header">
              <h2 className="card-title">Parcels</h2>
            </div>
            <ParcelTable parcels={site.parcels} />
          </section>

          <section className="card">
            <div className="card-header">
              <h2 className="card-title">Infrastructure dependencies</h2>
            </div>
            <DependencyList dependencies={site.dependencies} />
          </section>

          {site.attributions.length > 0 && (
            <section className="card">
              <h2 className="card-title">Attribution</h2>
              <ul className="small muted" style={{ paddingLeft: "1.1rem", margin: 0 }}>
                {site.attributions.map((attribution) => (
                  <li key={attribution}>{attribution}</li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>

      <p className="small muted">
        <Link href="/sites">&larr; Back to all sites</Link>
      </p>
    </div>
  );
}

function StageTrack({ stage, label }: { stage: number; label: string }) {
  return (
    <div>
      <div className="stage-track" role="img" aria-label={`Development stage ${stage}: ${label}`}>
        {Array.from({ length: STAGE_COUNT }, (_, index) => (
          <span
            key={index}
            className={`stage-step ${index <= stage ? "reached" : ""}`}
          />
        ))}
      </div>
      <div className="stage-label-row">
        <span>0 No known development</span>
        <span style={{ color: "var(--accent)", fontWeight: 600 }}>
          Stage {stage}: {label}
        </span>
        <span>8 Expansion</span>
      </div>
    </div>
  );
}

function OrganizationList({ site }: { site: SiteDetail }) {
  if (site.organizations.length === 0) {
    return (
      <p className="muted small">
        No organization is recorded as holding title. Owner names classified as private
        individuals are redacted before storage and produce no organization record.
      </p>
    );
  }
  return (
    <div className="stack">
      {site.organizations.map((organization) => (
        <div key={organization.id}>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
            <strong>{organization.canonical_name}</strong>
            {organization.organization_type && (
              <StatusPill>{organization.organization_type}</StatusPill>
            )}
            {organization.is_suspected_shell && (
              <StatusPill
                tone="caution"
                title="Name characteristics typical of a single-purpose entity. This is a flag for human review, not an attribution to any parent company."
              >
                Possible single-purpose entity
              </StatusPill>
            )}
          </div>
          {organization.shell_indicators.length > 0 && (
            <ul className="small muted" style={{ paddingLeft: "1.1rem", margin: "0.25rem 0" }}>
              {organization.shell_indicators.map((indicator) => (
                <li key={indicator}>{indicator}</li>
              ))}
            </ul>
          )}
          <p className="small muted" style={{ margin: "0.25rem 0 0" }}>
            {organization.attribution_note}
          </p>
        </div>
      ))}
    </div>
  );
}

function ParcelTable({ parcels }: { parcels: Parcel[] }) {
  if (parcels.length === 0) {
    return <p className="muted small">No parcels are linked to this site.</p>;
  }
  return (
    <table className="table">
      <thead>
        <tr>
          <th>APN</th>
          <th>Address</th>
          <th className="num">Acres</th>
          <th>Deed</th>
        </tr>
      </thead>
      <tbody>
        {parcels.map((parcel) => (
          <tr key={parcel.id}>
            <td>
              {parcel.assessor_url ? (
                <a
                  className="mono"
                  href={parcel.assessor_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {parcel.apn_formatted ?? parcel.apn}
                </a>
              ) : (
                <span className="mono">{parcel.apn_formatted ?? parcel.apn}</span>
              )}
            </td>
            <td className="small">
              {parcel.situs_address ?? "—"}
              {parcel.owner_is_redacted && (
                <div className="muted" style={{ fontSize: "0.72rem" }}>
                  Owner withheld (private individual)
                </div>
              )}
            </td>
            <td className="num">
              {parcel.lot_size_acres ? parcel.lot_size_acres.toFixed(2) : "—"}
            </td>
            <td className="small">
              {parcel.last_deed_url ? (
                <a href={parcel.last_deed_url} target="_blank" rel="noreferrer">
                  {parcel.last_deed_date ?? "View"}
                </a>
              ) : (
                (parcel.last_deed_date ?? "—")
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DependencyList({ dependencies }: { dependencies: Dependency[] }) {
  if (dependencies.length === 0) {
    return (
      <p className="muted small">
        No infrastructure dependencies have been matched. This means none were found within
        the search radius, not that the site has no grid connection.
      </p>
    );
  }

  const shown = dependencies.slice(0, 6);
  return (
    <div className="stack">
      {shown.map((dependency) => (
        <div key={dependency.id}>
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
            <strong className="small">{dependency.label}</strong>
            <AssertionBadge assertion={dependency.assertion_class} />
            {dependency.is_blocking && (
              <StatusPill tone="caution" title="Close enough that a dedicated connection is plausible.">
                Likely dedicated
              </StatusPill>
            )}
          </div>
          <div className="small muted">
            {dependency.distance_meters !== null &&
              `${dependency.distance_meters.toFixed(0)} m away`}
            {dependency.voltage_kv && ` · ${dependency.voltage_kv.toFixed(0)} kV`}
            {dependency.operator_name && ` · ${dependency.operator_name}`}
            {` · match confidence ${(dependency.confidence * 100).toFixed(0)}%`}
          </div>
        </div>
      ))}
      {dependencies.length > shown.length && (
        <p className="small muted" style={{ margin: 0 }}>
          {dependencies.length - shown.length} further dependencies not shown.
        </p>
      )}
      <p className="card-note">
        Dependencies are inferred from spatial proximity. A nearby substation makes a
        connection practical; it is not evidence that one exists.
      </p>
    </div>
  );
}

function boundingBoxFor(site: SiteDetail): string | undefined {
  if (!site.centroid) return undefined;
  const [lon, lat] = site.centroid;
  const pad = 0.05;
  return [lon - pad, lat - pad, lon + pad, lat + pad].join(",");
}
