import { InfrastructureMap, MapLegend } from "@/components/InfrastructureMap";
import { ApiUnavailable } from "@/components/ApiUnavailable";
import { getMapInfrastructure, getMapSites } from "@/lib/api";

export const dynamic = "force-dynamic";

export const metadata = { title: "Infrastructure map" };

export default async function MapPage() {
  let sites;
  let infrastructure;
  try {
    [sites, infrastructure] = await Promise.all([
      getMapSites(),
      getMapInfrastructure(undefined, 69),
    ]);
  } catch (error) {
    return <ApiUnavailable error={error} />;
  }

  const attributions = Array.from(
    new Set([...sites.attributions, ...infrastructure.attributions]),
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
