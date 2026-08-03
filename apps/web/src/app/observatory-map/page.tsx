/**
 * The national map of mapped data centres.
 *
 * Kept separate from `/map`, which shows the Arizona site model - parcels,
 * stages and inferred boundaries. These are different kinds of claim and
 * putting them on one canvas would invite the reader to treat a reported point
 * and an inferred polygon as the same sort of thing.
 */
import type { Metadata } from "next";
import Link from "next/link";

import { ObservatoryMap } from "@/components/ObservatoryMap";
import { getFacilities, getObservatoryMeta } from "@/lib/observatory";

export const metadata: Metadata = {
  title: "National infrastructure map",
  description:
    "Every US data centre recorded in OpenStreetMap, drawn over the transmission substations and generating plants that have to supply them.",
};

export default async function ObservatoryMapPage() {
  const [facilities, meta] = await Promise.all([
    getFacilities(),
    getObservatoryMeta(),
  ]);

  const buildings = facilities.features.filter(
    (feature) => feature.properties.site_class === "building",
  ).length;
  const withOperator = facilities.features.filter((feature) =>
    Boolean(feature.properties.operator),
  ).length;

  // The grid layer is fetched by a separate stage that takes far longer than
  // the rest of the pipeline, so the page has to read correctly before it has
  // ever run rather than announcing zero substations as though that were a
  // finding about the United States.
  const substations = meta.substation_count ?? 0;
  const plants = meta.plant_count ?? 0;
  const hasGrid = substations + plants > 0;

  return (
    <div className="stack">
      <div className="card-header">
        <div>
          <h1>National infrastructure map</h1>
          <p className="muted small" style={{ margin: 0 }}>
            {meta.facility_count.toLocaleString()} data centres recorded in
            OpenStreetMap
            {hasGrid
              ? `, over the ${substations.toLocaleString()} transmission substations and ${plants.toLocaleString()} generating plants that would have to supply them.`
              : ", drawn at their mapped coordinates and sized by building footprint."}
          </p>
        </div>
      </div>

      <ObservatoryMap facilities={facilities} />

      <div className="grid grid-4">
        <div className="metric">
          <div className="metric-label">Facilities</div>
          <div className="metric-value num">
            {meta.facility_count.toLocaleString()}
          </div>
          <div className="metric-sub">all with coordinates</div>
        </div>
        <div className="metric">
          <div className="metric-label">Mapped as buildings</div>
          <div className="metric-value num">
            {Math.round((100 * buildings) / facilities.features.length)}%
          </div>
          <div className="metric-sub">
            {buildings.toLocaleString()} with a floor plate
          </div>
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
        <strong>A blank patch here is not a finding.</strong> OpenStreetMap is
        mapped by volunteers, and coverage follows them: Northern Virginia is
        drawn in detail because people there have drawn it. An empty area may
        hold no data centres. It may equally hold no mappers. What you are
        looking at is the record, not the country.
      </div>

      {(meta.construction_count ?? 0) > 0 ? (
        <div className="notice">
          <strong>
            {meta.construction_count?.toLocaleString()} records are mapped as
            under construction.
          </strong>{" "}
          They use fixed-size marks here because construction area is not
          building floor area, and they receive no operating-load estimate.{" "}
          <Link href="/construction">See the construction signal</Link>.
        </div>
      ) : null}

      {hasGrid ? (
        <section className="card">
          <div className="card-header">
            <h2 className="card-title">Reading the grid layers</h2>
            <span className="card-note">switched off until asked for</span>
          </div>
          <p className="small">
            A large data centre needs a transmission connection, not a
            distribution feeder, and that is the constraint that decides where
            one can go at all. The substation layer is therefore cut at{" "}
            <strong>69 kV</strong> — below that is local distribution, which
            would bury the signal under two orders of magnitude of pole-mounted
            yards. Substations are sized by their highest voltage and plants by
            rated capacity, both recorded by mappers rather than measured here.
          </p>
          <p className="small">
            The layers load only when switched on. Together they are{" "}
            {(substations + plants).toLocaleString()} points against the
            facility layer&apos;s {meta.facility_count.toLocaleString()}, and
            making every reader download them to look at data centres would be a
            poor trade.
          </p>
          <p className="small" style={{ marginBottom: 0 }}>
            Proximity is not connection. A data centre sitting beside a 500 kV
            substation may have no agreement to draw a single watt from it, and
            interconnection queues in several regions now run for years. These
            layers place things near each other. Read nothing further into it.
          </p>
        </section>
      ) : null}
    </div>
  );
}
