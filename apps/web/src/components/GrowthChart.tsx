/**
 * Cumulative sites tracked, over time.
 *
 * Drawn as inline SVG rather than with a charting library: the published site
 * makes a point of shipping no third-party requests, and a step area is a
 * polyline, not a reason to take a dependency.
 *
 * Deliberately *not* stage-banded. The endpoint returns a per-stage breakdown
 * and it is currently identical across every stage, because each site in the
 * corpus has exactly one recorded transition — straight to its final stage.
 * Drawing eight bands would produce eight identical curves and imply a
 * progression the records do not contain. When sites start accumulating
 * transitions, banding this becomes worth doing.
 */
import type { StageGrowthPoint } from "@/lib/types";
import { ScrollArea } from "@/components/ScrollArea";

const VIEW_W = 720;
const VIEW_H = 200;
const PAD_L = 34;
const PAD_B = 26;
const PAD_T = 10;
const PAD_R = 8;

export function GrowthChart({ points }: { points: StageGrowthPoint[] }) {
  if (points.length === 0) {
    return <p className="muted small">No stage transitions recorded yet.</p>;
  }

  const max = Math.max(...points.map((p) => p.sites_tracked), 1);
  const plotW = VIEW_W - PAD_L - PAD_R;
  const plotH = VIEW_H - PAD_T - PAD_B;

  const x = (i: number) =>
    PAD_L +
    (points.length === 1 ? plotW / 2 : (i / (points.length - 1)) * plotW);
  const y = (v: number) => PAD_T + plotH - (v / max) * plotH;

  // Stepped, because the series is a cumulative count that changes on discrete
  // months. Interpolating between them would draw sites appearing on dates no
  // record supports.
  const steps: string[] = [];
  points.forEach((point, i) => {
    const px = x(i);
    const py = y(point.sites_tracked);
    if (i === 0) {
      steps.push(`M ${px} ${py}`);
    } else {
      steps.push(`L ${px} ${y(points[i - 1].sites_tracked)}`, `L ${px} ${py}`);
    }
  });
  const line = steps.join(" ");
  const area = `${line} L ${x(points.length - 1)} ${y(0)} L ${x(0)} ${y(0)} Z`;

  const ticks = [0, Math.round(max / 2), max].filter(
    (v, i, a) => a.indexOf(v) === i,
  );

  // Enough labels to orient without crowding the axis.
  const labelEvery = Math.max(1, Math.ceil(points.length / 6));

  return (
    <figure className="chart">
      <ScrollArea
        className="chart-scroll"
        label="Cumulative sites tracked, scrollable chart"
      >
        <svg
          viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
          className="chart-svg"
          role="img"
          aria-label={`Cumulative sites tracked, rising from ${points[0].sites_tracked} in ${points[0].month} to ${points[points.length - 1].sites_tracked} in ${points[points.length - 1].month}`}
        >
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={PAD_L}
                x2={VIEW_W - PAD_R}
                y1={y(tick)}
                y2={y(tick)}
                className="chart-grid"
              />
              <text
                x={PAD_L - 7}
                y={y(tick) + 3.5}
                className="chart-tick"
                textAnchor="end"
              >
                {tick}
              </text>
            </g>
          ))}

          <path d={area} className="chart-area" />
          <path d={line} className="chart-line" />

          {points.map((point, i) =>
            i % labelEvery === 0 || i === points.length - 1 ? (
              <text
                key={point.month}
                x={x(i)}
                y={VIEW_H - 8}
                className="chart-tick"
                textAnchor={
                  i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"
                }
              >
                {point.month}
              </text>
            ) : null,
          )}
        </svg>
      </ScrollArea>
      <figcaption className="chart-caption">
        Sites carrying at least one recorded stage transition, cumulative. Dated
        by the evidence each transition rests on, not by when Helios ingested
        it.
      </figcaption>
    </figure>
  );
}
