"use client";

/**
 * Every hosting-classified facility EPA reports, drawn at national scale.
 *
 * This map deliberately looks nothing like the site map. Sites are polygons
 * assembled from parcel geometry, coloured by a development stage Helios
 * worked out; these are undifferentiated points carrying one fact each — a
 * federal agency lists this facility under a hosting NAICS code. Giving them a
 * stage colour, a confidence, or a boundary would dress a reported record up as
 * an analysed one.
 *
 * Points are drawn small and semi-transparent so that density reads as density.
 * The clustering around Northern Virginia is the single most informative thing
 * on the page and it should be visible before any label is read.
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

import type { FeatureCollection } from "@/lib/types";
import { basemapStyle } from "@/components/InfrastructureMap";
import { MAP_FACILITY, MAP_PAPER } from "@/lib/mapPalette";
import { useTheme } from "@/components/ThemeToggle";

const CONTINENTAL_US_VIEW = {
  longitude: -96.5,
  latitude: 38.5,
  zoom: 3.2,
};

/** One mark, one meaning. Not the stage ramp: nothing here carries a stage. */
const FACILITY_COLOUR = MAP_FACILITY;

interface PopupState {
  longitude: number;
  latitude: number;
  properties: Record<string, unknown>;
}

export function NationalFacilityMap({
  facilities,
}: {
  facilities: FeatureCollection;
}) {
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

        <Source id="facilities" type="geojson" data={facilities as never}>
          <Layer
            id="facility-point"
            type="circle"
            paint={{
              // Grows only slightly with zoom: at national scale the cluster
              // matters, and at state scale the individual record does.
              "circle-radius": [
                "interpolate",
                ["linear"],
                ["zoom"],
                3,
                3,
                8,
                6,
              ],
              "circle-color": FACILITY_COLOUR[theme],
              "circle-opacity": 0.55,
              "circle-stroke-width": 0.5,
              "circle-stroke-color": MAP_PAPER[theme],
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
              <strong>
                {String(popup.properties.name ?? "Unnamed facility")}
              </strong>
              <div>
                {String(
                  popup.properties.jurisdiction ?? "location not recorded",
                )}
              </div>
              <div>
                NAICS {String(popup.properties.naics ?? "not recorded")}
              </div>
              <p className="small muted" style={{ marginBottom: 0 }}>
                Reported by EPA ECHO. A permitted air facility carrying a
                hosting NAICS code — not a Helios site, and not a confirmed data
                centre.
              </p>
            </div>
          </Popup>
        )}
      </Map>
    </div>
  );
}
