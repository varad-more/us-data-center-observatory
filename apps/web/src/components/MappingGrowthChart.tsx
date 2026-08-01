/**
 * Data centres on the map over time, with the unreliable stretch shaded.
 *
 * The single most important thing this chart does is refuse to let its own
 * early years be read as history. `telecom=data_center` was barely used before
 * 2017; the near-zero start is a missing convention, not an empty country, and
 * the jump when the tag caught on is a mapping event rather than a building
 * boom. That stretch is therefore drawn behind a hatched band and labelled,
 * instead of being cropped away - cropping would hide the artefact, and hiding
 * it would let the remaining curve imply a precision it does not have.
 *
 * Drawn as inline SVG for the same reason as `GrowthChart`: the published site
 * makes a point of shipping no third-party requests, and a step line is a
 * polyline, not a reason to take a dependency.
 */
import type { SeriesPoint } from "@/lib/observatory";

const VIEW_W = 760;
const VIEW_H = 260;
const PAD_L = 46;
const PAD_B = 30;
const PAD_T = 14;
const PAD_R = 12;

/**
 * Where the tagging convention became common enough for counts to mean
 * something. Before this, absence of a data centre in the data says more about
 * mappers than about the world.
 */
const RELIABLE_FROM = "2017-01";

export function MappingGrowthChart({ points }: { points: SeriesPoint[] }) {
  if (points.length < 2) {
    return <p className="muted small">Not enough history to draw a series.</p>;
  }

  const max = Math.max(...points.map((p) => p.count), 1);
  const plotW = VIEW_W - PAD_L - PAD_R;
  const plotH = VIEW_H - PAD_T - PAD_B;

  const x = (i: number) => PAD_L + (i / (points.length - 1)) * plotW;
  const y = (v: number) => PAD_T + plotH - (v / max) * plotH;

  // Stepped: the series changes on discrete months, and interpolating between
  // them would draw facilities appearing on dates no edit supports.
  const steps: string[] = [];
  points.forEach((point, i) => {
    const px = x(i);
    if (i === 0) {
      steps.push(`M ${px} ${y(point.count)}`);
    } else {
      steps.push(`L ${px} ${y(points[i - 1].count)}`, `L ${px} ${y(point.count)}`);
    }
  });
  const line = steps.join(" ");
  const area = `${line} L ${x(points.length - 1)} ${y(0)} L ${x(0)} ${y(0)} Z`;

  const unreliableUntil = points.findIndex((p) => p.period >= RELIABLE_FROM);
  const shadeWidth = unreliableUntil > 0 ? x(unreliableUntil) - PAD_L : 0;

  const ticks = [0, Math.round(max / 2), max].filter((v, i, a) => a.indexOf(v) === i);
  const labelEvery = Math.max(1, Math.ceil(points.length / 8));
  const first = points[0];
  const last = points[points.length - 1];

  return (
    <figure className="chart">
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        className="chart-svg"
        role="img"
        aria-label={`Data centres recorded in OpenStreetMap, rising from ${first.count} in ${first.period} to ${last.count} in ${last.period}. Values before ${RELIABLE_FROM} are unreliable because the tagging convention was not yet in common use.`}
      >
        <defs>
          <pattern
            id="unreliable-hatch"
            width="6"
            height="6"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <line x1="0" y1="0" x2="0" y2="6" className="chart-hatch" />
          </pattern>
        </defs>

        {shadeWidth > 0 && (
          <g>
            <rect
              x={PAD_L}
              y={PAD_T}
              width={shadeWidth}
              height={plotH}
              fill="url(#unreliable-hatch)"
            />
            <rect
              x={PAD_L}
              y={PAD_T}
              width={shadeWidth}
              height={plotH}
              className="chart-shade"
            />
          </g>
        )}

        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={PAD_L}
              x2={VIEW_W - PAD_R}
              y1={y(tick)}
              y2={y(tick)}
              className="chart-grid"
            />
            <text x={PAD_L - 7} y={y(tick) + 3.5} className="chart-tick" textAnchor="end">
              {tick.toLocaleString()}
            </text>
          </g>
        ))}

        <path d={area} className="chart-area" />
        <path d={line} className="chart-line" />

        {/* Names what the band does to the numbers, not just what caused it.
            "tag not yet in use" left a reader to work out which tag, and whether
            that made the count too high or too low; the answer is that it is too
            low, which is the only thing they need before reading the curve. */}
        {shadeWidth > 24 && (
          <text x={PAD_L + 6} y={PAD_T + 14} className="chart-tick">
            <tspan x={PAD_L + 6}>undercounted:</tspan>
            <tspan x={PAD_L + 6} dy="12">
              the tag was new
            </tspan>
          </text>
        )}

        {points.map((point, i) =>
          i % labelEvery === 0 || i === points.length - 1 ? (
            <text
              key={point.period}
              x={x(i)}
              y={VIEW_H - 10}
              className="chart-tick"
              textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"}
            >
              {point.period.slice(0, 4)}
            </text>
          ) : null,
        )}
      </svg>
      <figcaption className="chart-caption">
        Data centres recorded in OpenStreetMap at the end of each month. The hatched
        stretch is before <strong>{RELIABLE_FROM}</strong>, when{" "}
        <code>telecom=data_center</code> was not yet in common use — the near-zero
        readings there describe the tag, not the country. This is a count of what has
        been mapped, and OpenStreetMap carries no construction dates.
      </figcaption>
    </figure>
  );
}
