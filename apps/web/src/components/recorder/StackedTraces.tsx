/**
 * The helicorder wall: one thin trace per region, stacked, at one shared gain.
 *
 * A seismic network draws every station at the same gain so that a large event
 * at one station is visibly larger than a quiet day at another. Normalising
 * each trace to its own maximum would make every county look equally busy,
 * which is the single most misleading thing this particular picture could do:
 * the finding here is precisely that one county's curve dwarfs the rest, and a
 * per-row scale would erase exactly that.
 *
 * So every trace below is drawn against the same ceiling, and the ceiling is
 * printed in the margin.
 */
import Link from "next/link";

import { monthIndex, scaleLinear, stepPath } from "@/lib/recorder";

export interface TraceRow {
  id: string;
  name: string;
  state: string;
  href: string;
  value: string;
  points: { period: string; count: number }[];
}

const TRACE_W = 420;
const TRACE_H = 38;

/** The stepped trace closed back down to the baseline, so it can be filled. */
function areaPath(
  points: { period: string; count: number }[],
  x: (t: number) => number,
  y: (v: number) => number,
): string {
  if (points.length === 0) return "";
  const line = stepPath(
    points,
    (d) => x(monthIndex(d.period)),
    (d) => y(d.count),
  );
  const first = x(monthIndex(points[0].period));
  const last = x(monthIndex(points[points.length - 1].period));
  return `${line} L ${last} ${TRACE_H} L ${first} ${TRACE_H} Z`;
}

export function StackedTraces({
  rows,
  max,
  fromPeriod,
  toPeriod,
}: {
  rows: TraceRow[];
  max: number;
  fromPeriod: string;
  toPeriod: string;
}) {
  const x = scaleLinear(
    [monthIndex(fromPeriod), monthIndex(toPeriod)],
    [0, TRACE_W],
  );
  const y = scaleLinear([0, max], [TRACE_H - 1, 1]);

  const firstYear = Number(fromPeriod.slice(0, 4));
  const lastYear = Number(toPeriod.slice(0, 4));
  const axisYears: number[] = [];
  for (let year = firstYear + 1; year <= lastYear; year += 2)
    axisYears.push(year);

  return (
    <div className="pp-stack">
      {rows.map((row) => (
        <div className="pp-stack-row" key={row.id}>
          <div className="pp-stack-name">
            <Link href={row.href}>{row.name}</Link> <span>{row.state}</span>
          </div>
          <svg
            className="pp-stack-trace"
            viewBox={`0 0 ${TRACE_W} ${TRACE_H}`}
            preserveAspectRatio="none"
            role="img"
            aria-label={`${row.name}, ${row.state}: ${row.value}, drawn at the same scale as every other row.`}
          >
            <line
              x1={0}
              x2={TRACE_W}
              y1={TRACE_H - 1}
              y2={TRACE_H - 1}
              className="pp-grid-minor"
            />
            {/* Filled to the baseline as well as stroked. At one shared gain a
                county with 33 facilities draws four pixels above the zero rule,
                so as a hairline eleven of these twelve rows are flat lines at
                slightly different heights and the comparison the shared gain
                exists to make does not land. Mass reads where position cannot. */}
            <path d={areaPath(row.points, x, y)} className="pp-stack-fill" />
            <path
              d={stepPath(
                row.points,
                (d) => x(monthIndex(d.period)),
                (d) => y(d.count),
              )}
              className="pp-trace pp-trace-1"
            />
          </svg>
          <div className="pp-stack-value pp-num">{row.value}</div>
        </div>
      ))}

      {/* One axis for the whole wall. Every row shares this time base, so
          printing it twelve times would be twelve chances for them to disagree.
          Laid out in HTML rather than SVG: the traces are drawn with
          preserveAspectRatio="none" so they fill the row, and any text inside
          that viewBox would be stretched by the same factor. */}
      <div className="pp-stack-row pp-stack-axis">
        <span />
        <span className="pp-stack-axis-track">
          {axisYears.map((year) => (
            <span
              key={year}
              className="pp-stack-axis-year"
              style={{
                left: `${(x(monthIndex(`${year}-01`)) / TRACE_W) * 100}%`,
              }}
            >
              {year}
            </span>
          ))}
        </span>
        <span />
      </div>
    </div>
  );
}
