"use client";

/**
 * The multi-channel recorder sheet.
 *
 * Three channels share one strip of paper and therefore one time base. That
 * sharing is the point rather than a saving: a multi-channel chart is read by
 * laying a straightedge across every channel at once, so the crosshair here
 * spans all of them and the margin readout is slaved to it. Two charts side by
 * side cannot be read that way, and a chart with two y-axes — the usual answer
 * to "plot these together" — invites the reader to compare two scales that were
 * chosen independently, which is how a mapping count ends up looking like it
 * causes a national electricity total.
 *
 * The channels deliberately do not cover the same span, and the blank paper
 * that leaves is load-bearing:
 *
 *   - The count and the monthly change start in 2015-07, where the first
 *     recorded edit is, and stop at 2026-06, where the history window closes.
 *   - The electricity channel starts in 2014 and runs to 2030, because that is
 *     what LBNL publishes.
 *
 * So each channel has paper where it has no data, and on this instrument that
 * is not a zero, it is an absence — which is the one thing this project asks
 * every one of its surfaces to get right.
 */

import { useCallback, useMemo, useRef, useState } from "react";

import {
  EPOCH_YEAR,
  bandPath,
  formatPeriod,
  linePath,
  monthIndex,
  niceTicks,
  periodFromIndex,
  scaleLinear,
  stepPath,
} from "@/lib/recorder";

export interface ChannelPoint {
  t: number;
  v: number;
}

export interface ScenarioBand {
  t: number;
  lo: number;
  hi: number;
}

export interface Channel {
  id: string;
  /** Printed at the head of the channel, the way a recorder labels its pens. */
  name: string;
  unit: string;
  pen: 1 | 2 | 3;
  claim: "reported" | "observed" | "inferred" | "predicted";
  /** Plot height in viewBox units. Channels are not all worth the same paper. */
  height: number;
  max: number;
  /**
   * `step` for a running total that changes on discrete months, `spike` for a
   * per-month deflection off a zero rule, `spot` for readings published only in
   * particular years, where the pen lifts in between rather than interpolating.
   */
  render: "step" | "spike" | "spot";
  points: ChannelPoint[];
  band?: ScenarioBand[];
  projection?: ChannelPoint[];
  /** Shown in the readout when the cursor sits where this channel has no data. */
  absentLabel: string;
}

interface Props {
  channels: Channel[];
  /** Everything before this reads too low, because the tag was not yet in use. */
  deadBandUntil: string;
  /** Where the paper the count is drawn on runs out. */
  lastAdvance: string;
  fromPeriod: string;
  toPeriod: string;
  /**
   * Where the readout rests when nothing is hovered.
   *
   * It used to rest at the right-hand end of the paper, which is 2030 — a month
   * where two of the three channels have no reading at all, so the panel's
   * resting state was three lines of "no paper". Correct, and a terrible first
   * impression of an instrument. It rests at the last month that was actually
   * recorded instead.
   */
  restAt: string;
  children: React.ReactNode;
}

const VIEW_W = 1000;
const PAD_L = 46;
const PAD_R = 16;
const PAD_T = 22;
const AXIS_H = 26;
const GUTTER = 32;

export function RecorderChart({
  channels,
  deadBandUntil,
  lastAdvance,
  fromPeriod,
  toPeriod,
  restAt,
  children,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [cursor, setCursor] = useState<number | null>(null);

  const t0 = monthIndex(fromPeriod);
  const t1 = monthIndex(toPeriod);

  const layout = useMemo(() => {
    let y = PAD_T;
    const lanes = channels.map((channel) => {
      const top = y;
      y += channel.height + GUTTER;
      return { channel, top, bottom: top + channel.height };
    });
    return { lanes, height: y - GUTTER + AXIS_H };
  }, [channels]);

  const x = useMemo(
    () => scaleLinear([t0, t1], [PAD_L, VIEW_W - PAD_R]),
    [t0, t1],
  );

  const deadBandEnd = x(monthIndex(deadBandUntil));
  const advanceX = x(monthIndex(lastAdvance));

  // Year rules run the full height of the sheet rather than per channel: one
  // sheet of paper has one set of divisions, and that is what lets the eye carry
  // a moment in time from the top channel to the bottom one.
  const years = useMemo(() => {
    const out: number[] = [];
    for (
      let year = EPOCH_YEAR;
      year <= EPOCH_YEAR + Math.floor(t1 / 12);
      year += 1
    ) {
      out.push(year);
    }
    return out;
  }, [t1]);

  const handlePointer = useCallback(
    (event: React.PointerEvent<SVGSVGElement>) => {
      const svg = svgRef.current;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const ratio = (event.clientX - rect.left) / rect.width;
      const px = ratio * VIEW_W;
      const t = t0 + ((px - PAD_L) / (VIEW_W - PAD_R - PAD_L)) * (t1 - t0);
      setCursor(Math.max(t0, Math.min(t1, Math.round(t))));
    },
    [t0, t1],
  );

  const handleKey = useCallback(
    (event: React.KeyboardEvent<SVGSVGElement>) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      const step = event.shiftKey ? 12 : 1;
      setCursor((prev) => {
        const base = prev ?? t1;
        const next = event.key === "ArrowLeft" ? base - step : base + step;
        return Math.max(t0, Math.min(t1, next));
      });
    },
    [t0, t1],
  );

  return (
    <div className="pp-sheet">
      <div className="pp-margin">
        {children}
        <Readout
          channels={channels}
          cursor={cursor}
          fallback={monthIndex(restAt)}
        />
      </div>

      <div className="pp-plot">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${VIEW_W} ${layout.height}`}
          className="pp-chart"
          tabIndex={0}
          role="img"
          aria-label={`Three channels on one time base from ${formatPeriod(fromPeriod)} to ${formatPeriod(toPeriod)}. ${channels
            .map((c) => `${c.name}, ${c.unit}, ${c.claim}`)
            .join(
              ". ",
            )}. Use the left and right arrow keys to move the cursor.`}
          onPointerMove={handlePointer}
          onPointerLeave={() => setCursor(null)}
          onKeyDown={handleKey}
          onFocus={() => setCursor((prev) => prev ?? monthIndex(restAt))}
          onBlur={() => setCursor(null)}
        >
          <defs>
            <pattern
              id="pp-deadband"
              width="7"
              height="7"
              patternUnits="userSpaceOnUse"
              patternTransform="rotate(45)"
            >
              <line x1="0" y1="0" x2="0" y2="7" className="pp-hatch-line" />
            </pattern>
          </defs>

          {/* Year divisions, full height. */}
          {years.map((year) => {
            const px = x((year - EPOCH_YEAR) * 12);
            if (px < PAD_L - 1 || px > VIEW_W - PAD_R + 1) return null;
            return (
              <line
                key={year}
                x1={px}
                x2={px}
                y1={PAD_T}
                y2={layout.height - AXIS_H}
                className="pp-grid-major"
              />
            );
          })}

          {/* The stretch where the instrument was not yet trustworthy. It covers
              every channel because the reason — a tag still being adopted —
              affects everything drawn from that tag. */}
          {deadBandEnd > PAD_L && (
            <>
              <rect
                x={PAD_L}
                y={PAD_T}
                width={deadBandEnd - PAD_L}
                height={layout.height - AXIS_H - PAD_T}
                fill="url(#pp-deadband)"
              />
              <line
                x1={deadBandEnd}
                x2={deadBandEnd}
                y1={PAD_T}
                y2={layout.height - AXIS_H}
                className="pp-deadband-edge"
              />
              <text x={PAD_L + 5} y={PAD_T + 16} className="pp-deadband-label">
                <tspan x={PAD_L + 5}>undercounted</tspan>
                <tspan x={PAD_L + 5} dy="10.5">
                  tag in adoption
                </tspan>
              </text>
            </>
          )}

          {layout.lanes.map(({ channel, top, bottom }) => (
            <Lane
              key={channel.id}
              channel={channel}
              top={top}
              bottom={bottom}
              x={x}
            />
          ))}

          {/* Where the count's paper runs out. Everything to the right of this
              on channels 1 and 2 is blank because nothing was recorded there,
              not because nothing happened there. */}
          {advanceX < VIEW_W - PAD_R && (
            <>
              <line
                x1={advanceX}
                x2={advanceX}
                y1={PAD_T}
                y2={layout.height - AXIS_H}
                className="pp-deadband-edge"
              />
              <text
                x={advanceX + 5}
                y={PAD_T + 16}
                className="pp-deadband-label"
              >
                <tspan x={advanceX + 5}>chart ends</tspan>
                <tspan x={advanceX + 5} dy="10.5">
                  no paper past here
                </tspan>
              </text>
            </>
          )}

          {/* Time axis, printed once at the foot for the whole sheet. */}
          {years
            .filter((year) => year % 2 === 0)
            .map((year) => {
              const px = x((year - EPOCH_YEAR) * 12);
              if (px < PAD_L - 1 || px > VIEW_W - PAD_R + 1) return null;
              return (
                <text
                  key={year}
                  x={px}
                  y={layout.height - AXIS_H + 15}
                  className="pp-tick"
                  textAnchor="middle"
                >
                  {year}
                </text>
              );
            })}

          {cursor !== null && (
            <g>
              <line
                x1={x(cursor)}
                x2={x(cursor)}
                y1={PAD_T}
                y2={layout.height - AXIS_H}
                className="pp-crosshair"
              />
              {layout.lanes.map(({ channel, top, bottom }) => {
                const value = valueAt(channel, cursor);
                if (value === null) return null;
                const y = scaleLinear([0, channel.max], [bottom, top]);
                return (
                  <circle
                    key={channel.id}
                    cx={x(cursor)}
                    cy={y(value.v)}
                    r={3.4}
                    className={`pp-crosshair-dot pp-fill-${channel.pen}`}
                  />
                );
              })}
            </g>
          )}
        </svg>
      </div>
    </div>
  );
}

/** One channel: its ruling, its scale, its trace. */
function Lane({
  channel,
  top,
  bottom,
  x,
}: {
  channel: Channel;
  top: number;
  bottom: number;
  x: (v: number) => number;
}) {
  const y = scaleLinear([0, channel.max], [bottom, top]);
  const ticks = niceTicks(0, channel.max, 3).filter((t) => t <= channel.max);

  return (
    <g>
      {ticks.map((tick) => (
        <g key={tick}>
          <line
            x1={PAD_L}
            x2={VIEW_W - PAD_R}
            y1={y(tick)}
            y2={y(tick)}
            className="pp-grid-minor"
          />
          <text
            x={PAD_L - 6}
            y={y(tick) + 3.2}
            className="pp-tick"
            textAnchor="end"
          >
            {tick >= 10000
              ? `${Math.round(tick / 1000)}k`
              : tick.toLocaleString("en-US")}
          </text>
        </g>
      ))}

      <line
        x1={PAD_L}
        x2={VIEW_W - PAD_R}
        y1={bottom}
        y2={bottom}
        className="pp-zero"
      />

      <text x={PAD_L + 4} y={top - 8} className="pp-channel-name">
        {channel.name} · {channel.unit}
      </text>

      {/* The scenario range is drawn as a band, not as three lines: LBNL
          publishes it as a range and a reader should meet it as one. */}
      {channel.band && channel.band.length > 1 && (
        <path
          d={bandPath(
            channel.band,
            (d) => x(d.t),
            (d) => y(d.hi),
            (d) => y(d.lo),
          )}
          className="pp-band"
        />
      )}

      {channel.render === "step" && (
        <path
          d={stepPath(
            channel.points,
            (d) => x(d.t),
            (d) => y(d.v),
          )}
          className={`pp-trace pp-trace-${channel.pen}`}
        />
      )}

      {channel.render === "spike" &&
        // A month with no net change is the zero rule, which is already drawn.
        channel.points
          .filter((point) => point.v !== 0)
          .map((point) => (
            <line
              key={point.t}
              x1={x(point.t)}
              x2={x(point.t)}
              y1={bottom}
              y2={y(point.v)}
              className={`pp-trace pp-trace-${channel.pen}`}
            />
          ))}

      {channel.render === "spot" && (
        <>
          {/* Dotted, because the pen genuinely lifts between published years.
              A solid line here would draw values for years LBNL never
              published, in the same ink as the ones it did. */}
          <path
            d={linePath(
              channel.points,
              (d) => x(d.t),
              (d) => y(d.v),
            )}
            className={`pp-trace pp-trace-${channel.pen} pp-trace-projected`}
          />
          {channel.points.map((point) => (
            <rect
              key={point.t}
              x={x(point.t) - 2.6}
              y={y(point.v) - 2.6}
              width={5.2}
              height={5.2}
              className={`pp-fill-${channel.pen}`}
            />
          ))}
        </>
      )}

      {channel.projection && channel.projection.length > 1 && (
        <path
          d={linePath(
            channel.projection,
            (d) => x(d.t),
            (d) => y(d.v),
          )}
          className={`pp-trace pp-trace-${channel.pen} pp-trace-projected`}
        />
      )}
    </g>
  );
}

/**
 * The value a channel shows at a given month.
 *
 * Returns null where the channel has no reading, and the caller renders that as
 * absent rather than as zero. A `spot` channel only answers for the months it
 * actually published, so dragging the cursor across 2019 on the electricity
 * channel says "not published", which is true — LBNL did not publish 2019.
 */
function valueAt(
  channel: Channel,
  t: number,
): { v: number; exact: boolean } | null {
  if (channel.points.length === 0) return null;
  if (channel.render === "spot") {
    const hit = channel.points.find((p) => Math.abs(p.t - t) <= 6);
    return hit ? { v: hit.v, exact: true } : null;
  }
  if (t < channel.points[0].t) return null;
  const last = channel.points[channel.points.length - 1];
  if (t > last.t) return null;
  let found = channel.points[0];
  for (const point of channel.points) {
    if (point.t <= t) found = point;
    else break;
  }
  return { v: found.v, exact: found.t === t };
}

function Readout({
  channels,
  cursor,
  fallback,
}: {
  channels: Channel[];
  cursor: number | null;
  fallback: number;
}) {
  const t = cursor ?? fallback;
  return (
    <div className="pp-readout">
      <span className="pp-label">Readout</span>
      <span className="pp-readout-when">
        {formatPeriod(periodFromIndex(t))}
      </span>
      <div className="pp-readout-rows">
        {channels.map((channel) => {
          const value = valueAt(channel, t);
          return (
            <div className="pp-readout-row" key={channel.id}>
              <i
                className={`pp-fill-${channel.pen}`}
                style={{ background: `var(--pen-${channel.pen})` }}
              />
              <span>{channel.name}</span>
              <b>
                {value
                  ? `${value.v.toLocaleString("en-US")} ${channel.unit}`
                  : channel.absentLabel}
              </b>
            </div>
          );
        })}
      </div>
      <p className="pp-readout-hint">
        {cursor === null
          ? "Move across the chart, or focus it and use ← →"
          : "Shift + ← → moves a year"}
      </p>
    </div>
  );
}
