/**
 * Chart primitives for the recorder world.
 *
 * Every chart on the front page is a channel on one strip of paper, so the
 * things they share — a time base, a gain, a path builder, a projection — live
 * here rather than being re-derived in each component. That is the whole reason
 * this file exists: three components drawing three subtly different month scales
 * is how a shared crosshair stops lining up with the traces underneath it.
 *
 * Pure functions only. Nothing here imports React, touches the DOM or reads a
 * file, which is what lets the maths be tested without rendering anything and
 * lets the same code run in a server component and in a client one.
 *
 * No charting dependency, deliberately and for the second time: a stepped line
 * is a polyline and an Albers conic is nine lines of trigonometry. Neither is a
 * reason to ship a library to a reader.
 */

/**
 * The shared time base: months since 2014-01, the earliest year any channel
 * carries.
 *
 * This lives here rather than beside the chart because the server page builds
 * the channels and the client chart draws them, and both have to agree on what
 * month a given x position is. When it lived in the client module the server
 * could not call it at all, which is the useful version of that mistake.
 */
export const EPOCH_YEAR = 2014;

export function monthIndex(period: string): number {
  const [year, month] = period.split("-").map(Number);
  return (year - EPOCH_YEAR) * 12 + (month - 1);
}

export function periodFromIndex(index: number): string {
  const year = EPOCH_YEAR + Math.floor(index / 12);
  const month = (index % 12) + 1;
  return `${year}-${String(month).padStart(2, "0")}`;
}

/** A linear scale: a value in the domain to a coordinate in the range. */
export interface Scale {
  (value: number): number;
  domain: readonly [number, number];
  range: readonly [number, number];
}

export function scaleLinear(
  domain: readonly [number, number],
  range: readonly [number, number],
): Scale {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  // A zero-width domain would divide by zero and put every point at NaN, which
  // renders as an empty chart rather than as an error. A single-valued series is
  // a real case here — a county with one facility that never moved — so it is
  // pinned to the middle of the range instead.
  const span = d1 - d0;
  const fn = ((value: number) =>
    span === 0 ? (r0 + r1) / 2 : r0 + ((value - d0) / span) * (r1 - r0)) as Scale;
  fn.domain = domain;
  fn.range = range;
  return fn;
}

/**
 * Tick values at 1/2/5×10ⁿ intervals covering the domain.
 *
 * The instrument reading this borrows is a chart recorder's printed grid: the
 * divisions are round numbers a human can count in their head, not whatever
 * falls out of dividing the range into equal parts.
 */
export function niceTicks(min: number, max: number, target = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) return [min];
  const raw = (max - min) / Math.max(1, target);
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const normalised = raw / magnitude;
  // Geometric-mean boundaries rather than the integers, so each candidate wins
  // the range it is genuinely closest to. Rounding 6 up to 10 is what left the
  // 1,800-element axis labelled 0 and 1,000 and nothing else.
  const step =
    (normalised >= Math.sqrt(50)
      ? 10
      : normalised >= Math.sqrt(10)
        ? 5
        : normalised >= Math.sqrt(2)
          ? 2
          : 1) * magnitude;
  const first = Math.ceil(min / step) * step;
  const ticks: number[] = [];
  for (let v = first; v <= max + step / 1e6; v += step) {
    // Re-rounded because repeated addition of a fractional step accumulates
    // float error and prints ticks like 0.30000000000000004.
    ticks.push(Number(v.toFixed(10)));
  }
  return ticks;
}

/**
 * A stepped path through the points.
 *
 * Stepped rather than interpolated because these series change on discrete
 * months. A straight line between two months would draw facilities arriving on
 * dates no edit supports, which is a small lie the diagonal makes very easy to
 * tell.
 */
export function stepPath<T>(
  points: readonly T[],
  x: (d: T, i: number) => number,
  y: (d: T, i: number) => number,
): string {
  if (points.length === 0) return "";
  const parts: string[] = [`M ${r(x(points[0], 0))} ${r(y(points[0], 0))}`];
  for (let i = 1; i < points.length; i += 1) {
    const px = r(x(points[i], i));
    parts.push(`L ${px} ${r(y(points[i - 1], i - 1))}`, `L ${px} ${r(y(points[i], i))}`);
  }
  return parts.join(" ");
}

/** A straight polyline through the points, for series that really are continuous. */
export function linePath<T>(
  points: readonly T[],
  x: (d: T, i: number) => number,
  y: (d: T, i: number) => number,
): string {
  return points
    .map((d, i) => `${i === 0 ? "M" : "L"} ${r(x(d, i))} ${r(y(d, i))}`)
    .join(" ");
}

/** A closed band between an upper and a lower edge, for a scenario range. */
export function bandPath<T>(
  points: readonly T[],
  x: (d: T, i: number) => number,
  yTop: (d: T, i: number) => number,
  yBottom: (d: T, i: number) => number,
): string {
  if (points.length === 0) return "";
  const top = points.map((d, i) => `${i === 0 ? "M" : "L"} ${r(x(d, i))} ${r(yTop(d, i))}`);
  const bottom = points
    .map((d, i) => `L ${r(x(d, i))} ${r(yBottom(d, i))}`)
    .reverse();
  return `${top.join(" ")} ${bottom.join(" ")} Z`;
}

/**
 * Drop the interior of flat runs.
 *
 * Lossless for a stepped path: a run of identical values only needs its first
 * and last reading, because everything between them is drawn as the same
 * horizontal line either way. It matters because most of these series are
 * mostly flat — a county with 39 facilities for four years is 48 points that
 * draw one line — and the markup is emitted twice, once as HTML and once into
 * the payload that hydrates the page.
 */
export function dropFlatRuns<T>(
  points: readonly T[],
  valueOf: (d: T) => number,
): T[] {
  if (points.length <= 2) return [...points];
  const out: T[] = [points[0]];
  for (let i = 1; i < points.length - 1; i += 1) {
    const prev = valueOf(points[i - 1]);
    const here = valueOf(points[i]);
    const next = valueOf(points[i + 1]);
    // Keep anything that is not the middle of a flat stretch, so both ends of
    // every run survive and the step lands on the right month.
    if (here !== prev || here !== next) out.push(points[i]);
  }
  out.push(points[points.length - 1]);
  return out;
}

/** Coordinates are rounded to a tenth of a unit: past that, SVG only gets heavier. */
function r(n: number): number {
  return Math.round(n * 10) / 10;
}

/**
 * Albers equal-area conic, the projection the US Census and USGS publish in.
 *
 * Equal-area matters more than it looks: the alternative on hand is plotting
 * degrees straight onto the axes, which stretches the north of the country
 * sideways and would make the same number of facilities occupy more paper in
 * Washington than in Texas. Returns unnormalised projection units; fit them to
 * a viewBox with `fitExtent`.
 */
export function albersUsa(lon: number, lat: number): [number, number] {
  const rad = Math.PI / 180;
  const phi1 = 29.5 * rad;
  const phi2 = 45.5 * rad;
  const lam0 = -96 * rad;
  const phi0 = 37.5 * rad;
  const n = 0.5 * (Math.sin(phi1) + Math.sin(phi2));
  const c = Math.cos(phi1) ** 2 + 2 * n * Math.sin(phi1);
  const rho0 = Math.sqrt(c - 2 * n * Math.sin(phi0)) / n;
  const theta = n * (lon * rad - lam0);
  const rho = Math.sqrt(c - 2 * n * Math.sin(lat * rad)) / n;
  // Y is negated so that north is up once the result lands in SVG's
  // downward-growing coordinate space.
  return [rho * Math.sin(theta), -(rho0 - rho * Math.cos(theta))];
}

export interface Extent {
  scale: number;
  dx: number;
  dy: number;
}

/**
 * The scale and offset that fit projected points into a box, preserving aspect.
 *
 * Kept separate from the projection so that a map and its insets can be
 * projected identically and only then placed differently — which is what makes
 * the Puerto Rico inset show real relative area rather than a blown-up guess.
 */
export function fitExtent(
  projected: readonly (readonly [number, number])[],
  width: number,
  height: number,
  padding = 0,
): Extent {
  if (projected.length === 0) return { scale: 1, dx: 0, dy: 0 };
  const xs = projected.map((p) => p[0]);
  const ys = projected.map((p) => p[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const scale = Math.min(
    (width - padding * 2) / (maxX - minX || 1),
    (height - padding * 2) / (maxY - minY || 1),
  );
  return {
    scale,
    dx: padding + (width - padding * 2 - (maxX - minX) * scale) / 2 - minX * scale,
    dy: padding + (height - padding * 2 - (maxY - minY) * scale) / 2 - minY * scale,
  };
}

export function applyExtent(
  point: readonly [number, number],
  extent: Extent,
): [number, number] {
  return [point[0] * extent.scale + extent.dx, point[1] * extent.scale + extent.dy];
}

/**
 * Bin points onto a grid and return each occupied cell with how many landed in
 * it: `[x, y, count]`.
 *
 * The grid layer under the plot sheet is 61,983 assets. Drawing each one is
 * 2 MB of markup for a picture in which most of them land on the same pixel, so
 * the cell is the honest unit.
 *
 * The count is what makes the cell a measurement rather than a mesh. Occupied
 * or not, drawn at one weight, 3,900 cells produce a regular lattice with a
 * ragged edge — graph paper, not a country, and on a sheet that is itself ruled
 * it disappears into the ruling entirely. Carrying the count lets the mark be
 * weighted by how much grid is actually in the cell, which is what draws the
 * eastern seaboard, the Ohio valley and the California coast. The counts are
 * heavily skewed (median 9, maximum 278), so the caller is expected to put them
 * through a compressive scale rather than a linear one.
 */
export function binToGrid(
  points: readonly (readonly [number, number])[],
  cell: number,
): [number, number, number][] {
  const cells = new Map<string, [number, number, number]>();
  for (const [x, y] of points) {
    const gx = Math.round(x / cell);
    const gy = Math.round(y / cell);
    const key = `${gx}:${gy}`;
    const hit = cells.get(key);
    if (hit) hit[2] += 1;
    else cells.set(key, [gx * cell, gy * cell, 1]);
  }
  return [...cells.values()];
}

/**
 * Closed rings to one SVG path, in relative commands.
 *
 * The coastline is 958 points and this markup is emitted twice — once as HTML
 * and once into the payload that hydrates the page — so the encoding is worth
 * choosing. Absolute four-digit coordinates cost about 12 bytes a point;
 * relative deltas between neighbouring vertices are almost always one or two
 * digits, which is 36 kB down to 9 kB for the same line.
 *
 * The position is tracked as the sum of the deltas actually written rather than
 * as the ideal coordinate. Rounding each delta independently and letting the
 * error accumulate over 867 vertices walks the end of the ring visibly away
 * from its start, and on a closed coastline that shows up as a notch.
 */
export function ringsToPath(
  rings: readonly (readonly (readonly [number, number])[])[],
  decimals = 1,
): string {
  const q = 10 ** decimals;
  const round = (n: number) => Math.round(n * q) / q;
  const parts: string[] = [];
  for (const ring of rings) {
    if (ring.length < 2) continue;
    let x = round(ring[0][0]);
    let y = round(ring[0][1]);
    parts.push(`M${x} ${y}`);
    for (let i = 1; i < ring.length; i += 1) {
      const dx = round(round(ring[i][0]) - x);
      const dy = round(round(ring[i][1]) - y);
      // A vertex that rounds onto the one before it draws nothing; emitting it
      // would be two bytes for a zero-length line.
      if (dx === 0 && dy === 0) continue;
      parts.push(`l${dx} ${dy}`);
      x = round(x + dx);
      y = round(y + dy);
    }
    parts.push("Z");
  }
  return parts.join("");
}

/**
 * Points to one SVG path of discs: round-capped strokes that go nowhere.
 *
 * `h0` draws a horizontal line of zero length, which a round cap paints as a
 * disc of the stroke's width, so one path carries a whole layer of dots at a
 * fraction of the elements.
 *
 * Sorted into row-major order and written as relative moves, which is worth
 * more than it sounds. The grid layer is 12,091 marks; as unsorted absolute
 * coordinates that is 120 kB and 35 kB gzipped, and sorting alone takes the
 * compressed size to 30 kB because neighbouring marks then share long prefixes.
 * Emitting the gaps instead of the positions takes it to 10 kB, because in
 * row-major order almost every gap is a one- or two-digit number.
 */
export function dotsToPath(
  points: readonly (readonly [number, number])[],
  decimals = 0,
): string {
  const q = 10 ** decimals;
  const round = (n: number) => Math.round(n * q) / q;
  const sorted = [...points].sort((a, b) => a[1] - b[1] || a[0] - b[0]);
  const parts: string[] = [];
  let px = 0;
  let py = 0;
  for (const point of sorted) {
    const x = round(point[0]);
    const y = round(point[1]);
    parts.push(
      parts.length === 0
        ? `M${x} ${y}h0`
        : `m${round(x - px)} ${round(y - py)}h0`,
    );
    px = x;
    py = y;
  }
  return parts.join("");
}

/** `2026-06` to a readable `Jun 2026`, for readouts and captions. */
const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function formatPeriod(period: string): string {
  const [year, month] = period.split("-");
  const index = Number(month) - 1;
  return index >= 0 && index < 12 ? `${MONTHS[index]} ${year}` : period;
}

/** Compact figures for margin readouts, where the column is narrow by design. */
export function formatCompact(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${(value / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (abs >= 10_000) return `${Math.round(value / 1000)}k`;
  return value.toLocaleString("en-US");
}
