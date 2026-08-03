"use client";

/**
 * The interactive infrastructure map.
 *
 * Sites are coloured by development stage and substations are drawn beneath
 * them, because the question the map exists to answer is spatial: *is this
 * project near the grid capacity it would need?* Basemap tiles come from a
 * public raster source so the map has no API-key dependency and works from a
 * fresh clone.
 */

import { useCallback, useMemo, useState } from "react";
import Map, {
  Layer,
  NavigationControl,
  Popup,
  ScaleControl,
  Source,
  type MapLayerMouseEvent,
} from "react-map-gl/maplibre";
import "maplibre-gl/dist/maplibre-gl.css";

import Link from "next/link";
import type { FeatureCollection } from "@/lib/types";
import { useTheme } from "@/components/ThemeToggle";
import {
  BASEMAP_PAINT,
  MAP_PAPER,
  MAP_SUBSTATION,
  MAP_UNPLACED,
  STAGE_RAMP,
  stageColourExpression,
} from "@/lib/mapPalette";

const EAST_VALLEY_VIEW = {
  longitude: -111.72,
  latitude: 33.34,
  zoom: 9.6,
};

/**
 * The basemap follows the theme, and is retinted toward the paper it sits on.
 * CARTO's positron is near-white; dropped straight onto chart paper it read as a
 * hole punched in the page.
 */
export function basemapStyle(theme: "light" | "dark") {
  const variant = theme === "dark" ? "dark_all" : "light_all";
  return {
    version: 8 as const,
    sources: {
      carto: {
        type: "raster" as const,
        tiles: [
          `https://a.basemaps.cartocdn.com/${variant}/{z}/{x}/{y}@2x.png`,
          `https://b.basemaps.cartocdn.com/${variant}/{z}/{x}/{y}@2x.png`,
        ],
        tileSize: 256,
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      },
    },
    layers: [
      {
        id: "basemap",
        type: "raster" as const,
        source: "carto",
        paint: BASEMAP_PAINT[theme],
      },
    ],
  };
}

interface PopupState {
  longitude: number;
  latitude: number;
  kind: "site" | "substation";
  properties: Record<string, unknown>;
}

export interface InfrastructureMapProps {
  sites: FeatureCollection;
  infrastructure: FeatureCollection;
  /** Restrict the initial viewport, used on the site-detail page. */
  initialView?: { longitude: number; latitude: number; zoom: number };
  className?: string;
  /** Highlight one site by project code. */
  focusProjectCode?: string;
}

export function InfrastructureMap({
  sites,
  infrastructure,
  initialView = EAST_VALLEY_VIEW,
  className = "map-container",
  focusProjectCode,
}: InfrastructureMapProps) {
  const [popup, setPopup] = useState<PopupState | null>(null);
  const theme = useTheme();

  const interactiveLayerIds = useMemo(
    () => ["site-fill", "substation-point"],
    [],
  );

  const stageColours = useMemo(() => stageColourExpression(theme), [theme]);
  const mapStyle = useMemo(() => basemapStyle(theme), [theme]);

  const handleClick = useCallback((event: MapLayerMouseEvent) => {
    const feature = event.features?.[0];
    if (!feature) {
      setPopup(null);
      return;
    }
    setPopup({
      longitude: event.lngLat.lng,
      latitude: event.lngLat.lat,
      kind: feature.layer.id === "substation-point" ? "substation" : "site",
      properties: (feature.properties ?? {}) as Record<string, unknown>,
    });
  }, []);

  return (
    <div className={className}>
      <Map
        initialViewState={initialView}
        mapStyle={mapStyle}
        interactiveLayerIds={interactiveLayerIds}
        onClick={handleClick}
        cursor="auto"
        style={{ width: "100%", height: "100%" }}
      >
        <NavigationControl position="top-right" />
        <ScaleControl position="bottom-left" />

        {/* Substations render first so site polygons sit above them. */}
        <Source
          id="infrastructure"
          type="geojson"
          data={infrastructure as never}
        >
          <Layer
            id="substation-point"
            type="circle"
            paint={{
              "circle-radius": [
                "interpolate",
                ["linear"],
                ["coalesce", ["get", "max_voltage_kv"], 69],
                69,
                3,
                230,
                6,
                500,
                9,
              ],
              "circle-color": MAP_SUBSTATION[theme],
              "circle-opacity": 0.6,
              "circle-stroke-width": 1,
              "circle-stroke-color": MAP_PAPER[theme],
            }}
          />
        </Source>

        <Source id="sites" type="geojson" data={sites as never}>
          <Layer
            id="site-fill"
            type="fill"
            paint={{
              "fill-color": stageColours as never,
              "fill-opacity": 0.45,
            }}
          />
          <Layer
            id="site-outline"
            type="line"
            paint={{
              "line-color": stageColours as never,
              "line-width": focusProjectCode
                ? ([
                    "case",
                    ["==", ["get", "project_code"], focusProjectCode],
                    3,
                    1,
                  ] as never)
                : 1.5,
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
            {popup.kind === "site" ? (
              <SitePopup properties={popup.properties} />
            ) : (
              <SubstationPopup properties={popup.properties} />
            )}
          </Popup>
        )}
      </Map>
    </div>
  );
}

function SitePopup({ properties }: { properties: Record<string, unknown> }) {
  const confidence = Number(properties.confidence ?? 0);
  return (
    <div className="map-popup">
      <strong>{String(properties.project_code ?? "Unknown site")}</strong>
      <div>
        Stage {String(properties.stage)} &middot;{" "}
        {String(properties.stage_label)}
      </div>
      <div>Confidence {confidence.toFixed(0)}%</div>
      <div>
        {properties.total_acres
          ? `${Number(properties.total_acres).toFixed(1)} acres`
          : "—"}
        {" · "}
        {String(properties.evidence_count ?? 0)} evidence records
      </div>
      <Link href={`/sites/${String(properties.project_code)}`}>
        Open site profile
      </Link>
    </div>
  );
}

function SubstationPopup({
  properties,
}: {
  properties: Record<string, unknown>;
}) {
  const voltage = properties.max_voltage_kv;
  return (
    <div className="map-popup">
      <strong>{String(properties.name ?? "Unnamed substation")}</strong>
      <div>Operator: {String(properties.operator_name ?? "not recorded")}</div>
      <div>
        Voltage: {voltage ? `${Number(voltage).toFixed(0)} kV` : "not recorded"}
      </div>
      {typeof properties.osm_url === "string" && (
        <a href={properties.osm_url} target="_blank" rel="noreferrer">
          View in OpenStreetMap
        </a>
      )}
    </div>
  );
}

/**
 * Legend.
 *
 * Swatches are read out of STAGE_RAMP rather than restated, because the two lists
 * previously drifted: the legend claimed stage 7 was gold while the map drew it
 * amber. A legend that disagrees with the map is worse than no legend.
 */
const LEGEND_STAGES: { stage: number; label: string }[] = [
  { stage: 1, label: "Site speculation" },
  { stage: 3, label: "Regulatory commitment" },
  { stage: 4, label: "Construction initiated" },
  { stage: 6, label: "Energization" },
  { stage: 8, label: "Operational" },
];

export function MapLegend() {
  const theme = useTheme();
  const ramp = STAGE_RAMP[theme];

  return (
    <div className="legend" style={{ marginTop: "0.75rem" }}>
      <span className="legend-item muted">Stage</span>
      {LEGEND_STAGES.map((entry) => (
        <span key={entry.stage} className="legend-item">
          <span
            className="legend-swatch"
            style={{ background: ramp[entry.stage] }}
          />
          {entry.label}
        </span>
      ))}
      <span className="legend-item">
        <span
          className="legend-swatch"
          style={{ background: MAP_UNPLACED[theme] }}
        />
        Not placed on the scale
      </span>
      <span className="legend-item">
        <span
          className="legend-swatch"
          style={{ background: MAP_SUBSTATION[theme], borderRadius: "50%" }}
        />
        Substation (size by voltage)
      </span>
    </div>
  );
}
