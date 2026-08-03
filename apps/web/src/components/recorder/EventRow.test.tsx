import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EventRow } from "./EventRow";

/**
 * A deletion in OpenStreetMap is an element that stopped matching the
 * data-centre filter. It is not a building coming down, and shortening
 * "removed from OSM" to "closed" would turn a fact about the map into a claim
 * about the world. The changes page already holds this line; the front page
 * repeats the wording, so it is owed the same test.
 */
const base = {
  id: "way/1",
  date: "2026-06-19",
  name: "Example DC",
  county_name: "Loudoun County, VA",
};

describe("EventRow", () => {
  it("words a disappearance as a removal from the map", () => {
    render(<EventRow change={{ ...base, kind: "deletion" }} />);

    expect(screen.getByText(/removed from OSM/)).toBeInTheDocument();
    expect(screen.queryByText(/\bclosed\b/i)).toBeNull();
    expect(screen.queryByText(/\bdemolished\b/i)).toBeNull();
  });

  it("words an arrival as an appearance on the map, not a completion", () => {
    render(<EventRow change={{ ...base, kind: "creation" }} />);

    expect(screen.getByText(/appeared/)).toBeInTheDocument();
    expect(screen.queryByText(/\bbuilt\b/i)).toBeNull();
    expect(screen.queryByText(/\bopened\b/i)).toBeNull();
  });

  it("separates the two directions by shape, not by colour alone", () => {
    const { container: up } = render(
      <EventRow change={{ ...base, kind: "creation" }} />,
    );
    const { container: down } = render(
      <EventRow change={{ ...base, kind: "deletion" }} />,
    );

    const upPath = up.querySelector(".pp-event-mark path")?.getAttribute("d");
    const downPath = down
      .querySelector(".pp-event-mark path")
      ?.getAttribute("d");
    expect(upPath).toBeTruthy();
    expect(upPath).not.toBe(downPath);
  });

  it("says a facility is unnamed rather than leaving the row blank", () => {
    render(<EventRow change={{ ...base, name: null, kind: "creation" }} />);
    expect(screen.getByText("unnamed")).toBeInTheDocument();
  });
});
