import Link from "next/link";

import { InfrastructureMap, MapLegend } from "@/components/InfrastructureMap";
import { NationalFacilityMap } from "@/components/NationalFacilityMap";
import { ApiUnavailable } from "@/components/ApiUnavailable";
import { getMapFacilities, getMapInfrastructure, getMapSites } from "@/lib/api";

export const metadata = { title: "Infrastructure map" };

export default async function MapPage() {
  let sites;
  let infrastructure;
  let facilities;
  try {
    [sites, infrastructure, facilities] = await Promise.all([
      getMapSites(),
      getMapInfrastructure(undefined, 69),
      getMapFacilities(),
    ]);
  } catch (error) {
    return <ApiUnavailable error={error} />;
  }

  const attributions = Array.from(
    new Set([...sites.attributions, ...infrastructure.attributions, ...facilities.attributions]),
  );

  return (
    <div className="stack">
      <div>
        <h1>Interactive infrastructure map</h1>
        <p className="muted" style={{ maxWidth: "62ch" }}>
          Site boundaries coloured by development stage, drawn over the electrical
          substations that could plausibly serve them. Proximity to grid capacity is a
          precondition for a large load, not evidence that a connection exists.
        </p>
      </div>

      <InfrastructureMap sites={sites} infrastructure={infrastructure} />
      <MapLegend />

      <section className="stack">
        <div>
          <h2>Reported facilities, nationwide</h2>
          <p className="muted" style={{ maxWidth: "62ch" }}>
            The map above is one Arizona valley, because sites are built from county
            parcel records and Helios reads two counties. This one is the whole country,
            because it is not showing sites. Each point is a single federal record: EPA
            lists a permitted air facility under a hosting NAICS code. Nothing here has
            been clustered into a project, staged, or scored.
          </p>
          <p className="muted" style={{ maxWidth: "62ch" }}>
            For national coverage of data centres and the transmission grid that supplies
            them, see the{" "}
            <Link href="/observatory-map">national infrastructure map</Link>, which draws
            every mapped US facility over the substations and generating plants around
            it.
          </p>
        </div>
        <NationalFacilityMap facilities={facilities} />
        <p className="small muted">
          <strong>{facilities.features.length}</strong> facilities. The density around
          Northern Virginia is the point: it is the largest concentration of data-centre
          capacity in the world, and Helios has built no sites there.
        </p>
      </section>

      <div className="grid grid-2">
        <div className="card">
          <h2 className="card-title">What is shown</h2>
          <ul className="small muted" style={{ paddingLeft: "1.1rem", margin: 0 }}>
            <li>
              <strong>{sites.features.length}</strong> site boundaries, each the union of
              its linked parcel geometries rather than a convex hull, so an irregular
              assembly is not drawn as land the project does not hold.
            </li>
            <li>
              <strong>{infrastructure.features.length}</strong> substations at 69 kV and
              above, sized by voltage.
            </li>
            <li>
              <strong>{facilities.features.length}</strong> EPA-reported hosting
              facilities nationwide, drawn as undifferentiated points because one
              reported record is all each of them carries.
            </li>
          </ul>
        </div>
        <div className="card">
          <h2 className="card-title">Attribution</h2>
          <ul className="small muted" style={{ paddingLeft: "1.1rem", margin: 0 }}>
            {attributions.map((attribution) => (
              <li key={attribution}>{attribution}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
