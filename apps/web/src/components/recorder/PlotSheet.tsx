/**
 * The plot sheet: every mapped facility, over the grid it has to connect to.
 *
 * Three layers, and which pen draws each one is the whole point.
 *
 * The land is reference geography — the contiguous coastline, dissolved from
 * the same county boundaries that decided which county every facility is in. It
 * is drawn in the paper's own hairline, not in a pen, because it is not an
 * observation: it is the printed part of the sheet, the way a chart recorder's
 * paper arrives already ruled. Two earlier versions left it out and asked the
 * grid stipple to carry the country's shape instead. It cannot. A density field
 * is a measurement, and no tuning makes a measurement into a coastline — there
 * is nothing in Nevada to stipple, so Nevada simply had no edge.
 *
 * The grid — 61,983 substations and power plants — is the first real
 * measurement, binned to a cell and weighted by how much of it is in that cell.
 * Now that the land carries the shape, this layer is free to say only what it
 * knows: where the country's electrical plant actually is.
 *
 * The facilities are the subject, and they come in two marks whose difference is
 * not colour alone. A filled dot is a building: it has a floor plate, so it
 * carries a share of the national power total. An open ring is a campus mapped
 * as land, a bare point with no geometry, or a site under construction:
 * counted, located, and given no power figure at all. Rendering those as small
 * filled dots would say they draw a little power. They draw an unknown amount.
 *
 * Drawn on the server into static SVG. MapLibre already serves the interactive
 * map two clicks away; the front page does not need to ship a map engine to
 * make this point.
 */
import fs from "fs/promises";
import path from "path";

import {
  albersUsa,
  applyExtent,
  binToGrid,
  dotsToPath,
  fitExtent,
  ringsToPath,
} from "@/lib/recorder";

const VIEW_W = 1000;
const PAD = 18;

/**
 * The contiguous states, in degrees.
 *
 * The grid layer covers Alaska and Hawaii — 358 assets out past 165° west — and
 * the sheet is fitted to the lower 48, so those would land off the paper. Cut
 * them in geographic space, which says what is meant; the previous guard was a
 * magic number in projection units and dropped 121 points of the 358 it was
 * aimed at.
 */
const CONUS = { lonMin: -125, lonMax: -66.5, latMin: 24, latMax: 49.5 };

interface Facility {
  lon: number;
  lat: number;
  footprint: number;
  hasFigure: boolean;
  state: string;
}

async function readData<T>(file: string): Promise<T> {
  const raw = await fs.readFile(
    path.join(process.cwd(), "public", "data", file),
    "utf-8",
  );
  return JSON.parse(raw) as T;
}

type PointLayer = {
  features: {
    geometry: { coordinates: [number, number] };
    properties: Record<string, unknown>;
  }[];
};

export async function PlotSheet() {
  const [facilityGeo, gridGeo, basemap] = await Promise.all([
    readData<PointLayer>("facilities.geojson"),
    readData<PointLayer>("grid.geojson"),
    readData<{ rings: [number, number][][] }>("basemap.json"),
  ]);

  const facilities: Facility[] = facilityGeo.features.map((f) => ({
    lon: f.geometry.coordinates[0],
    lat: f.geometry.coordinates[1],
    footprint: Number(f.properties.footprint_m2 ?? 0),
    // Only a building carries an allocated figure; the allocation is by floor
    // area and the others have none. This mirrors the pipeline rather than
    // re-deciding it here.
    hasFigure: f.properties.site_class === "building",
    state: String(f.properties.state ?? ""),
  }));

  // Puerto Rico is projected separately into its own inset. Folding it into the
  // main extent would push the conic 900 miles southeast and shrink the country
  // to make room for two facilities; dropping it would contradict the coverage
  // this site states everywhere else.
  const mainland = facilities.filter((f) => f.state !== "PR");
  const offshore = facilities.filter((f) => f.state === "PR");

  const mainlandProjected = mainland.map((f) => albersUsa(f.lon, f.lat));

  const conusGrid = gridGeo.features
    .filter((f) => {
      const [lon, lat] = f.geometry.coordinates;
      return (
        lon >= CONUS.lonMin &&
        lon <= CONUS.lonMax &&
        lat >= CONUS.latMin &&
        lat <= CONUS.latMax
      );
    })
    .map((f) =>
      albersUsa(f.geometry.coordinates[0], f.geometry.coordinates[1]),
    );

  // The sheet is fitted to the land, and everything else is placed into that
  // same extent. Fitting to the data instead — as this did while the grid was
  // carrying the shape — makes the frame move whenever the dataset does, so a
  // new substation in Maine could shift every facility on the sheet.
  //
  // The height is derived from the projected aspect rather than hardcoded, so
  // there is no slack left over as dead ocean.
  const projectedLand = basemap.rings.map((ring) =>
    ring.map(([lon, lat]) => albersUsa(lon, lat)),
  );
  const landPoints = projectedLand.flat();
  const lx = landPoints.map((p) => p[0]);
  const ly = landPoints.map((p) => p[1]);
  const aspect =
    (Math.max(...lx) - Math.min(...lx)) / (Math.max(...ly) - Math.min(...ly));
  const VIEW_H = Math.round((VIEW_W - PAD * 2) / aspect) + PAD * 2;
  const INSET = { x: VIEW_W - 186, y: VIEW_H - 116, w: 168, h: 98 };

  const extent = fitExtent(landPoints, VIEW_W, VIEW_H, PAD);
  const landPath = ringsToPath(
    projectedLand.map((ring) => ring.map((p) => applyExtent(p, extent))),
  );

  /**
   * The bin the grid layer is drawn on, in viewBox units.
   *
   * Four rather than nine, and the reason is occupancy. Binning puts every mark
   * on a lattice, and a lattice is invisible while it is sparsely filled and
   * unmistakable once it is not. At a nine-unit cell about half the country's
   * cells hold something and the populated half holds something in nearly every
   * cell, so the marks lined up in rows and columns and the layer read as a
   * halftone screen printed over the map. At four the same 61,983 assets occupy
   * 30% of the cells, which scatters, and the quantisation stops being a
   * pattern the eye can find.
   *
   * It costs three times the marks. That is the trade being made deliberately:
   * this layer is the reason the sheet exists.
   */
  const GRID_CELL = 4;
  const gridCells = binToGrid(
    conusGrid.map((p) => applyExtent(p, extent)),
    GRID_CELL,
  ).filter(([x, y]) => x >= 0 && x <= VIEW_W && y >= 0 && y <= VIEW_H);

  /**
   * The weight of each mark is how much grid is in that cell.
   *
   * The counts run from 1 to 111 with a median of 3, so the scale is
   * logarithmic; a linear one puts nine cells in ten at the lightest weight and
   * throws away the difference between a rural substation and the Ohio valley.
   * Four weights rather than a continuous ramp because each weight is one
   * `<path>`, and four paths carry all 61,983 assets.
   *
   * The heaviest mark is a little wider than the cell, so that neighbouring
   * dense cells run together into continuous tone instead of staying separate
   * dots. The ceiling is still deliberately low: this is the ground the
   * facilities are plotted on, and it is no longer being asked to draw the
   * country as well.
   */
  const GRID_WEIGHTS = 4;
  const busiestCell = Math.max(...gridCells.map((c) => c[2]), 1);
  const gridBuckets = new Map<number, [number, number][]>();
  for (const [x, y, count] of gridCells) {
    const weight = Math.min(
      GRID_WEIGHTS - 1,
      Math.floor((Math.log1p(count) / Math.log1p(busiestCell)) * GRID_WEIGHTS),
    );
    const list = gridBuckets.get(weight);
    if (list) list.push([x, y]);
    else gridBuckets.set(weight, [[x, y]]);
  }

  const placed = mainland.map((f, i) => ({
    facility: f,
    point: applyExtent(mainlandProjected[i], extent),
  }));

  const insetExtent = fitExtent(
    offshore.map((f) => albersUsa(f.lon, f.lat)),
    INSET.w,
    INSET.h,
    36,
  );

  const buildings = placed.filter((p) => p.facility.hasFigure);
  const others = placed.filter((p) => !p.facility.hasFigure);
  const maxFootprint = Math.max(
    ...buildings.map((p) => p.facility.footprint),
    1,
  );

  /**
   * Buildings are drawn as zero-length strokes with a round cap, bucketed by
   * size, rather than as fifteen hundred `<circle>` elements.
   *
   * A round cap on a path that goes nowhere paints a disc of the stroke's
   * width, so one path carries every building in its size bucket at about a
   * fifth of the bytes. That matters more than it looks: this markup is emitted
   * twice, once as HTML and once into the hydration payload, so the circles
   * were costing a quarter of a megabyte between them.
   */
  const BUCKETS = 7;
  const radiusFor = (footprint: number) =>
    1.7 + 4.6 * Math.sqrt(footprint / maxFootprint);
  const minR = 1.7;
  const maxR = radiusFor(maxFootprint);
  const bucketed = new Map<number, [number, number][]>();
  for (const { facility, point } of buildings) {
    const r = radiusFor(facility.footprint);
    const step = Math.min(
      BUCKETS - 1,
      Math.floor(((r - minR) / (maxR - minR || 1)) * BUCKETS),
    );
    const key = Number(
      (minR + (step + 0.5) * ((maxR - minR) / BUCKETS)).toFixed(2),
    );
    const list = bucketed.get(key);
    if (list) list.push(point);
    else bucketed.set(key, [point]);
  }

  return (
    <svg
      className="pp-map"
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      role="img"
      aria-label={`A map of the contiguous United States. ${facilities.length.toLocaleString()} mapped data centres plotted over ${conusGrid.length.toLocaleString()} substations and power plants. ${buildings.length.toLocaleString()} are buildings and carry an allocated power figure; ${others.length.toLocaleString()} are campuses, bare points or sites under construction and carry none.`}
    >
      {/* Reference geography, drawn in the paper's hairline rather than in a
          pen: the coastline is where the measurements sit, not one of them. */}
      <path d={landPath} className="pp-map-land" fillRule="evenodd" />

      {[...gridBuckets.entries()]
        .sort(([a], [b]) => a - b)
        .map(([weight, cells]) => (
          <path
            key={weight}
            d={dotsToPath(cells)}
            className="pp-map-grid-mark"
            strokeWidth={0.8 + weight * 1.25}
            strokeOpacity={0.26 + weight * 0.13}
          />
        ))}

      {others.map(({ point }, i) => (
        <circle
          key={`o${i}`}
          cx={point[0].toFixed(1)}
          cy={point[1].toFixed(1)}
          r={2.6}
          className="pp-map-nofigure"
        />
      ))}

      {/* Area-proportional, square-rooted, so that a facility ten times the
          floor plate draws ten times the ink and not a hundred times. */}
      {[...bucketed.entries()].map(([r, points]) => (
        <path
          key={r}
          d={dotsToPath(points, 1)}
          className="pp-map-building-mark"
          strokeWidth={r * 2}
        />
      ))}

      {offshore.length > 0 && (
        <g>
          <rect
            x={INSET.x}
            y={INSET.y}
            width={INSET.w}
            height={INSET.h}
            className="pp-map-neatline"
          />
          <text x={INSET.x + 6} y={INSET.y + 14} className="pp-map-inset-label">
            Puerto Rico
          </text>
          {offshore.map((f, i) => {
            const [px, py] = applyExtent(albersUsa(f.lon, f.lat), insetExtent);
            return (
              <circle
                key={`p${i}`}
                cx={INSET.x + px}
                cy={INSET.y + py}
                r={f.hasFigure ? 3 : 2.6}
                className={f.hasFigure ? "pp-map-building" : "pp-map-nofigure"}
              />
            );
          })}
        </g>
      )}
    </svg>
  );
}
