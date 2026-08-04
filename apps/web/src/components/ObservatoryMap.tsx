"use client";

/**
 * Every mapped US data centre, at its actual coordinates, over the grid that
 * has to carry them.
 *
 * Building circles are sized by floor plate rather than drawn uniformly,
 * because a 12,000 m² colocation suite and a 426,000 m² machine hall are not
 * the same object. Campus land boundaries and areas mapped as under
 * construction are fixed-size marks: their square metres measure a different
 * physical thing and must not enter the building scale. The area-to-radius
 * mapping uses a square root so that circle *area* tracks floor plate; scaling
 * radius directly would exaggerate the largest buildings by their own factor
 * again.
 *
 * The grid layers answer the question the data-centre layer provokes: these
 * things need hundreds of megawatts, so where can that actually be delivered?
 * Substations are sized by voltage and plants by generating capacity, both
 * ordinal quantities carried by size along a single hue each.
 *
 * The grid is fetched only when asked for. It is 62,427 points against the
 * facility layer's 1,853 - eleven megabytes - and loading it with the page
 * would make everyone pay for a layer most readers never open. Colour here is categorical - three
 * asset types, not a scale - and every colour is labelled in the legend, so
 * hue is never the only thing distinguishing them.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Map, {
  Layer,
  NavigationControl,
  Popup,
  Source,
  type MapLayerMouseEvent,
} from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";

import { basemapStyle } from "@/components/InfrastructureMap";
import {
  MAP_FACILITY,
  MAP_PAPER,
  MAP_PLANT,
  MAP_SUBSTATION,
} from "@/lib/mapPalette";
import { useTheme } from "@/components/ThemeToggle";
import {
  formatMappedArea,
  type FacilitySiteClass,
} from "@/lib/facilityPresentation";
import type { FacilityCollection } from "@/lib/observatory";
import { DATA_BASE } from "@/lib/regionPath";

const CONTINENTAL_US_VIEW = {
  longitude: -96.5,
  latitude: 38.5,
  zoom: 3.2,
};

/**
 * One mark per asset type. Declared as literals because MapLibre paint
 * expressions take colour values, not `var()` references, and a custom property
 * holding `light-dark()` does not resolve through getComputedStyle.
 *
 * These are categories rather than steps of a scale, so they take separate
 * hues - but each is labelled in the legend and named in its popup, so the hue
 * grades nothing on its own.
 */
const ASSET_COLOUR = {
  facility: MAP_FACILITY,
  substation: MAP_SUBSTATION,
  plant: MAP_PLANT,
} as const;

type LayerKey = "facilities" | "substations" | "plants";

const LAYERS: {
  key: LayerKey;
  label: string;
  asset: keyof typeof ASSET_COLOUR;
}[] = [
  { key: "facilities", label: "Data centres", asset: "facility" },
  { key: "substations", label: "Substations 69 kV+", asset: "substation" },
  { key: "plants", label: "Power plants", asset: "plant" },
];

interface GridFeatureCollection {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    geometry: { type: "Point"; coordinates: [number, number] };
    properties: Record<string, unknown>;
  }[];
}

interface PopupState {
  longitude: number;
  latitude: number;
  kind: "facility" | "substation" | "plant";
  properties: Record<string, unknown>;
}

export function ObservatoryMap({
  facilities,
}: {
  facilities: FacilityCollection;
}) {
  const [popup, setPopup] = useState<PopupState | null>(null);
  const [enabled, setEnabled] = useState<Record<LayerKey, boolean>>({
    facilities: true,
    substations: false,
    plants: false,
  });
  const [grid, setGrid] = useState<GridFeatureCollection | null>(null);
  const [gridState, setGridState] = useState<"idle" | "loading" | "failed">(
    "idle",
  );
  const theme = useTheme();

  const wantsGrid = enabled.substations || enabled.plants;

  // Guarded by a ref rather than by the state it sets.
  //
  // An earlier version depended on `gridState` and set it to "loading" on its
  // first line. That mutates a value in its own dependency array: React re-ran
  // the effect, the re-run's cleanup flipped the `cancelled` flag, and the
  // in-flight fetch's handlers all became no-ops. The layer loaded never, and
  // because the failure path was cancelled too, the map sat on "loading grid…"
  // for ever without reporting anything. A ref carries "already asked for"
  // without taking part in the dependency comparison, so the fetch is issued
  // exactly once and nothing interrupts it.
  const requested = useRef(false);

  useEffect(() => {
    if (!wantsGrid || requested.current) return;
    requested.current = true;
    setGridState("loading");
    fetch(`${DATA_BASE}/grid.geojson`)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((payload) => {
        setGrid(payload as GridFeatureCollection);
        setGridState("idle");
      })
      .catch(() => {
        // Say so rather than leaving an empty map that looks like a country
        // with no substations in it.
        setGridState("failed");
        // Release the latch on failure only. It exists to stop the effect
        // re-issuing a fetch that is already in flight; holding it after a
        // failure meant a dropped connection was permanent, and toggling the
        // layer off and on — the obvious thing to try — could never retry.
        requested.current = false;
      });
  }, [wantsGrid]);

  const mapStyle = useMemo(() => basemapStyle(theme), [theme]);

  const interactiveLayerIds = useMemo(() => {
    const ids: string[] = [];
    if (enabled.facilities) {
      ids.push("facility-building-point", "facility-other-point");
    }
    if (grid && enabled.substations) ids.push("substation-point");
    if (grid && enabled.plants) ids.push("plant-point");
    return ids;
  }, [enabled, grid]);

  const handleClick = useCallback((event: MapLayerMouseEvent) => {
    const feature = event.features?.[0];
    if (!feature) {
      setPopup(null);
      return;
    }
    const properties = (feature.properties ?? {}) as Record<string, unknown>;
    const kind =
      feature.layer?.id === "substation-point"
        ? "substation"
        : feature.layer?.id === "plant-point"
          ? "plant"
          : "facility";
    setPopup({
      longitude: event.lngLat.lng,
      latitude: event.lngLat.lat,
      kind,
      properties,
    });
  }, []);

  const gridCount = grid?.features.length ?? 0;

  return (
    <div className="stack">
      <div className="controls">
        <div className="control-group" role="group" aria-label="Map layers">
          {LAYERS.map((layer) => (
            <button
              key={layer.key}
              type="button"
              className={enabled[layer.key] ? "chip chip-active" : "chip"}
              aria-pressed={enabled[layer.key]}
              onClick={() =>
                setEnabled((prev) => ({
                  ...prev,
                  [layer.key]: !prev[layer.key],
                }))
              }
            >
              <span
                className="legend-swatch"
                style={{
                  background: ASSET_COLOUR[layer.asset][theme],
                  display: "inline-block",
                  marginRight: "0.35rem",
                  verticalAlign: "-1px",
                }}
                aria-hidden="true"
              />
              {layer.label}
            </button>
          ))}
        </div>
        <span className="card-note">
          {gridState === "loading"
            ? "loading grid…"
            : gridState === "failed"
              ? "grid layer unavailable"
              : gridCount > 0
                ? `${gridCount.toLocaleString()} grid assets loaded`
                : "grid loads when switched on"}
        </span>
      </div>

      <div className="map-container">
        <Map
          initialViewState={CONTINENTAL_US_VIEW}
          mapStyle={mapStyle}
          interactiveLayerIds={interactiveLayerIds}
          onClick={handleClick}
          cursor="auto"
          style={{ width: "100%", height: "100%" }}
        >
          <NavigationControl position="top-right" />

          {grid ? (
            <Source id="observatory-grid" type="geojson" data={grid as never}>
              {/* Drawn beneath the facilities: the grid is context for them,
                  not the subject. */}
              <Layer
                id="plant-point"
                type="circle"
                filter={["==", ["get", "kind"], "plant"]}
                layout={{ visibility: enabled.plants ? "visible" : "none" }}
                paint={{
                  "circle-radius": [
                    "interpolate",
                    ["linear"],
                    ["zoom"],
                    3,
                    [
                      "interpolate",
                      ["linear"],
                      ["sqrt", ["coalesce", ["get", "capacity_mw"], 0]],
                      0,
                      1.6,
                      45,
                      6,
                    ],
                    9,
                    [
                      "interpolate",
                      ["linear"],
                      ["sqrt", ["coalesce", ["get", "capacity_mw"], 0]],
                      0,
                      3,
                      45,
                      16,
                    ],
                  ],
                  "circle-color": ASSET_COLOUR.plant[theme],
                  "circle-opacity": 0.45,
                  "circle-stroke-width": 0.4,
                  "circle-stroke-color": MAP_PAPER[theme],
                }}
              />
              <Layer
                id="substation-point"
                type="circle"
                filter={["==", ["get", "kind"], "substation"]}
                layout={{
                  visibility: enabled.substations ? "visible" : "none",
                }}
                paint={{
                  // Voltage is ordinal, so it is carried by size along one hue.
                  // 69 kV floor, 765 kV ceiling - the highest in service.
                  "circle-radius": [
                    "interpolate",
                    ["linear"],
                    ["zoom"],
                    3,
                    [
                      "interpolate",
                      ["linear"],
                      ["get", "voltage_kv"],
                      69,
                      1.4,
                      765,
                      5,
                    ],
                    9,
                    [
                      "interpolate",
                      ["linear"],
                      ["get", "voltage_kv"],
                      69,
                      3,
                      765,
                      14,
                    ],
                  ],
                  "circle-color": ASSET_COLOUR.substation[theme],
                  "circle-opacity": 0.45,
                  "circle-stroke-width": 0.4,
                  "circle-stroke-color": MAP_PAPER[theme],
                }}
              />
            </Source>
          ) : null}

          <Source
            id="observatory-facilities"
            type="geojson"
            data={facilities as never}
          >
            <Layer
              id="facility-building-point"
              type="circle"
              // Only an explicit `building` is sized by area. A missing class is
              // an unknown, and an unknown is not a building: sizing it here
              // would let unclassified land back into the floor-plate scale.
              filter={["==", ["get", "site_class"], "building"]}
              layout={{ visibility: enabled.facilities ? "visible" : "none" }}
              paint={{
                // sqrt of floor plate, so drawn area tracks building area. The
                // stops are in metres: 0 m² gets the floor radius, 400,000 m²
                // the ceiling.
                "circle-radius": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  3,
                  [
                    "interpolate",
                    ["linear"],
                    ["sqrt", ["get", "footprint_m2"]],
                    0,
                    2,
                    640,
                    7,
                  ],
                  9,
                  [
                    "interpolate",
                    ["linear"],
                    ["sqrt", ["get", "footprint_m2"]],
                    0,
                    4,
                    640,
                    24,
                  ],
                ],
                "circle-color": ASSET_COLOUR.facility[theme],
                "circle-opacity": 0.5,
                "circle-stroke-width": 0.5,
                "circle-stroke-color": MAP_PAPER[theme],
              }}
            />
            <Layer
              id="facility-other-point"
              type="circle"
              // Everything else, including an unclassified feature: `get` on a
              // missing property yields null, which is != "building".
              filter={["!=", ["get", "site_class"], "building"]}
              layout={{ visibility: enabled.facilities ? "visible" : "none" }}
              paint={{
                // A land parcel or construction polygon is not a floor plate.
                // Fixed radii keep its mapped area out of the building scale.
                "circle-radius": [
                  "interpolate",
                  ["linear"],
                  ["zoom"],
                  3,
                  2.5,
                  9,
                  6,
                ],
                "circle-color": ASSET_COLOUR.facility[theme],
                "circle-opacity": 0.35,
                "circle-stroke-width": 1.25,
                "circle-stroke-color": ASSET_COLOUR.facility[theme],
              }}
            />
          </Source>

          {popup && (
            <Popup
              longitude={popup.longitude}
              latitude={popup.latitude}
              onClose={() => setPopup(null)}
              closeOnClick={false}
              maxWidth="320px"
            >
              <div className="map-popup">
                {popup.kind === "facility" ? (
                  <>
                    <strong>
                      {String(popup.properties.name ?? "Unnamed facility")}
                    </strong>
                    {popup.properties.operator ? (
                      <div>{String(popup.properties.operator)}</div>
                    ) : (
                      <div className="muted">operator not recorded</div>
                    )}
                    <div className="small">
                      {formatMappedArea(
                        popup.properties.footprint_m2,
                        popup.properties.site_class as
                          | FacilitySiteClass
                          | undefined,
                      )}
                    </div>
                    {popup.properties.first_seen ? (
                      <div className="small">
                        first mapped {String(popup.properties.first_seen)}
                      </div>
                    ) : null}
                    <p className="small muted" style={{ marginBottom: 0 }}>
                      Location reported by OpenStreetMap contributors. Any date
                      is when the map recorded this facility, not when it was
                      built.
                    </p>
                  </>
                ) : (
                  <>
                    <strong>
                      {String(
                        popup.properties.name ??
                          (popup.kind === "substation"
                            ? "Unnamed substation"
                            : "Unnamed power plant"),
                      )}
                    </strong>
                    <div className="small">
                      {popup.kind === "substation"
                        ? "Substation"
                        : "Generating plant"}
                      {popup.properties.source
                        ? ` · ${String(popup.properties.source)}`
                        : ""}
                    </div>
                    {popup.properties.voltage_kv ? (
                      <div className="small">
                        {String(popup.properties.voltage_kv)} kV highest level
                      </div>
                    ) : null}
                    {popup.properties.capacity_mw ? (
                      <div className="small">
                        {Number(popup.properties.capacity_mw).toLocaleString()}{" "}
                        MW rated
                      </div>
                    ) : null}
                    {popup.properties.operator ? (
                      <div className="small">
                        {String(popup.properties.operator)}
                      </div>
                    ) : null}
                    <p className="small muted" style={{ marginBottom: 0 }}>
                      Reported by OpenStreetMap contributors. Voltage and
                      capacity are whatever a mapper recorded, and neither is a
                      measurement Helios made.
                    </p>
                  </>
                )}
              </div>
            </Popup>
          )}
        </Map>
      </div>

      {gridState === "failed" ? (
        <p className="small muted">
          The grid layer could not be loaded. The data centres above are
          unaffected.
        </p>
      ) : null}
    </div>
  );
}
