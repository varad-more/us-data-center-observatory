/**
 * The national map of mapped data centres.
 *
 * Kept separate from `/map`, which shows the Arizona site model - parcels,
 * stages and inferred boundaries. These are different kinds of claim and
 * putting them on one canvas would invite the reader to treat a reported point
 * and an inferred polygon as the same sort of thing.
 */
import type { Metadata } from "next";

import { ObservatoryMap } from "@/components/ObservatoryMap";
import { getFacilities, getObservatoryMeta } from "@/lib/observatory";

export const metadata: Metadata = {
  title: "National map",
  description:
    "Every US data centre recorded in OpenStreetMap, at its mapped coordinates, sized by building footprint.",
};

export default async function ObservatoryMapPage() {
  const [facilities, meta] = await Promise.all([getFacilities(), getObservatoryMeta()]);

  const withFootprint = facilities.features.filter(
    (feature) => feature.properties.footprint_m2 > 0,
  ).length;
  const withOperator = facilities.features.filter(
    (feature) => Boolean(feature.properties.operator),
  ).length;

  return (
    <div className="stack">
      <div className="card-header">
        <div>
          <h1>National map</h1>
          <p className="muted small" style={{ margin: 0 }}>
            {meta.facility_count.toLocaleString()} data centres recorded in
            OpenStreetMap, drawn at their mapped coordinates and sized by building
            footprint.
          </p>
        </div>
      </div>

      <ObservatoryMap facilities={facilities} />

      <div className="grid grid-4">
        <div className="metric">
          <div className="metric-label">Facilities</div>
          <div className="metric-value num">{meta.facility_count.toLocaleString()}</div>
          <div className="metric-sub">all with coordinates</div>
        </div>
        <div className="metric">
          <div className="metric-label">With footprint</div>
          <div className="metric-value num">
            {Math.round((100 * withFootprint) / facilities.features.length)}%
          </div>
          <div className="metric-sub">building outline mapped</div>
        </div>
        <div className="metric">
          <div className="metric-label">With operator</div>
          <div className="metric-value num">
            {Math.round((100 * withOperator) / facilities.features.length)}%
          </div>
          <div className="metric-sub">named by a contributor</div>
        </div>
        <div className="metric">
          <div className="metric-label">Total footprint</div>
          <div className="metric-value num">
            {(meta.total_footprint_m2 / 1e6).toFixed(0)}
          </div>
          <div className="metric-sub">km² of building</div>
        </div>
      </div>

      <div className="notice">
        <strong>Absence on this map is not evidence of absence.</strong> OpenStreetMap is
        mapped by volunteers, and coverage is uneven: Northern Virginia is mapped in
        detail because people there have mapped it. An empty area may hold no data
        centres, or may simply hold no mappers. This layer can tell you what has been
        recorded; it cannot tell you what exists.
      </div>
    </div>
  );
}
