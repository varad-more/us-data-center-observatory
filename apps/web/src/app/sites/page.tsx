import Link from "next/link";

import { AssertionBadge, ConfidenceBadge } from "@/components/AssertionBadge";
import { ApiUnavailable } from "@/components/ApiUnavailable";
import { listSites, sitesCsvUrl, sitesGeoJsonUrl } from "@/lib/api";

export const metadata = { title: "Sites" };

export default async function SitesPage() {
  let sites;
  try {
    sites = await listSites({ limit: 200, sort: "-confidence" });
  } catch (error) {
    return <ApiUnavailable error={error} />;
  }

  return (
    <div className="stack">
      <div className="card-header">
        <div>
          <h1>Site register</h1>
          <p className="muted small" style={{ margin: 0 }}>
            {sites.meta.total} sites in the East Valley study area.
          </p>
        </div>
        <div className="button-row">
          <a className="button" href={sitesCsvUrl()}>
            Download CSV
          </a>
          <a className="button" href={sitesGeoJsonUrl()}>
            Download GeoJSON
          </a>
        </div>
      </div>

      <table className="table">
        <thead>
          <tr>
            <th>Project code</th>
            <th>City</th>
            <th>Classification</th>
            <th>Stage</th>
            <th className="num">Parcels</th>
            <th className="num">Acres</th>
            <th className="num">Evidence</th>
            <th>First signal</th>
            <th>Identity Conf.</th>
            <th>Operator</th>
          </tr>
        </thead>
        <tbody>
          {sites.items.map((site) => (
            <tr key={site.id}>
              <td>
                <Link href={`/sites/${site.project_code}`} className="mono">
                  {site.project_code}
                </Link>
              </td>
              <td>{site.jurisdiction ?? "—"}</td>
              <td>
                {site.site_kind.replace(/_/g, " ")}{" "}
                <AssertionBadge assertion={site.site_kind_assertion} />
              </td>
              <td>
                <span className="mono muted">{site.current_stage}</span>{" "}
                {site.current_stage_label}
              </td>
              <td className="num">{site.parcel_count}</td>
              <td className="num">
                {site.total_acres ? site.total_acres.toFixed(1) : "—"}
              </td>
              <td className="num">{site.evidence_count}</td>
              <td className="mono small">{site.first_signal_date ?? "—"}</td>
              <td>
                <ConfidenceBadge
                  confidence={site.current_confidence}
                  band={site.confidence_band}
                />
              </td>
              <td className="small muted">
                {site.operator_status === "not_established"
                  ? "Not established"
                  : site.operator_status}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
