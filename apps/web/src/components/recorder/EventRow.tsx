/**
 * One line of the event-marker channel: what appeared, what came off the map.
 *
 * Extracted from the front page so the wording can be held by a test. A
 * deletion in OpenStreetMap means an element stopped matching the data-centre
 * filter. It does not mean a building came down, and this project does not get
 * to imply that it does — the same invariant the changes page guards, now
 * repeated on the front page and therefore owed the same guard.
 *
 * The glyph carries the direction as shape, deflecting up for an arrival and
 * down for a removal, so a reader who cannot separate the two inks still reads
 * the two events correctly.
 */
export interface ChangeRow {
  id: string;
  date: string;
  kind: string;
  name: string | null;
  county_name?: string | null;
}

export function EventRow({ change }: { change: ChangeRow }) {
  const appeared = change.kind === "creation";

  return (
    <li className="pp-event">
      <span className="pp-event-date">{change.date}</span>
      <svg
        className={`pp-event-mark ${appeared ? "pp-event-up" : "pp-event-down"}`}
        width="14"
        height="12"
        viewBox="0 0 14 12"
        aria-hidden="true"
      >
        <path
          d={
            appeared
              ? "M0 10 L5 10 L7 2 L9 10 L14 10"
              : "M0 2 L5 2 L7 10 L9 2 L14 2"
          }
        />
      </svg>
      <span className="pp-event-what">
        {change.name || <em>unnamed</em>}
        {change.county_name ? <span> · {change.county_name}</span> : null}
        <span> · {appeared ? "appeared" : "removed from OSM"}</span>
      </span>
    </li>
  );
}
