"use client";

/**
 * Every mapped US data centre, at its actual coordinates.
 *
 * Circles are sized by building footprint rather than drawn uniformly, because
 * footprint is the one physical quantity in the dataset and because uniform
 * dots would imply that a 12,000 m² colocation suite and a 426,000 m²
 * hyperscale campus are the same object. The area-to-radius mapping uses a
 * square root so that circle *area* tracks footprint; scaling radius directly
 * would exaggerate the largest sites by their own factor again.
 *
 * Colour carries no meaning here. There is no stage, no score and no
 * confidence in this layer - each point asserts one thing, that OpenStreetMap
 * contributors record a data centre at this location.
 */

import { useCallback, useMemo, useState } from "react";
import Map, {
  Layer,
  NavigationControl,
  Popup,
  Source,
  type MapLayerMouseEvent,
} from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";

import { basemapStyle } from "@/components/InfrastructureMap";
import { useTheme } from "@/components/ThemeToggle";
import type { FacilityCollection } from "@/lib/observatory";

const CONTINENTAL_US_VIEW = {
  longitude: -96.5,
  latitude: 38.5,
  zoom: 3.2,
};

/** One mark, one meaning. Deliberately not the stage ramp. */
const FACILITY_COLOUR = { light: "#8a5a09", dark: "#e0913f" };

interface PopupState {
  longitude: number;
  latitude: number;
  properties: Record<string, unknown>;
}

function formatArea(value: unknown): string {
  const area = typeof value === "number" ? value : 0;
  if (!area) return "footprint not mapped";
  if (area >= 1e6) return `${(area / 1e6).toFixed(2)} km² footprint`;
  return `${Math.round(area).toLocaleString()} m² footprint`;
}

export function ObservatoryMap({ facilities }: { facilities: FacilityCollection }) {
  const [popup, setPopup] = useState<PopupState | null>(null);
  const theme = useTheme();

  const mapStyle = useMemo(() => basemapStyle(theme), [theme]);
  const interactiveLayerIds = useMemo(() => ["facility-point"], []);

  const handleClick = useCallback((event: MapLayerMouseEvent) => {
    const feature = event.features?.[0];
    if (!feature) {
      setPopup(null);
      return;
    }
    setPopup({
      longitude: event.lngLat.lng,
      latitude: event.lngLat.lat,
      properties: (feature.properties ?? {}) as Record<string, unknown>,
    });
  }, []);

  return (
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

        <Source id="observatory-facilities" type="geojson" data={facilities as never}>
          <Layer
            id="facility-point"
            type="circle"
            paint={{
              // sqrt of footprint, so drawn area tracks real area. The stops are
              // in metres: 0 m² gets the floor radius, 400,000 m² the ceiling.
              "circle-radius": [
                "interpolate",
                ["linear"],
                ["zoom"],
                3,
                ["interpolate", ["linear"], ["sqrt", ["get", "footprint_m2"]], 0, 2, 640, 7],
                9,
                ["interpolate", ["linear"], ["sqrt", ["get", "footprint_m2"]], 0, 4, 640, 24],
              ],
              "circle-color": FACILITY_COLOUR[theme],
              "circle-opacity": 0.5,
              "circle-stroke-width": 0.5,
              "circle-stroke-color": theme === "dark" ? "#131210" : "#faf8f3",
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
              <strong>{String(popup.properties.name ?? "Unnamed facility")}</strong>
              {popup.properties.operator ? (
                <div>{String(popup.properties.operator)}</div>
              ) : (
                <div className="muted">operator not recorded</div>
              )}
              <div className="small">{formatArea(popup.properties.footprint_m2)}</div>
              {popup.properties.first_seen ? (
                <div className="small">
                  first mapped {String(popup.properties.first_seen)}
                </div>
              ) : null}
              <p className="small muted" style={{ marginBottom: 0 }}>
                Location reported by OpenStreetMap contributors. Any date is when the map
                recorded this facility, not when it was built.
              </p>
            </div>
          </Popup>
        )}
      </Map>
    </div>
  );
}
