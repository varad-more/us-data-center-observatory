import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RegionPicker } from "./RegionPicker";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("next/link", () => ({
  default: ({
    href,
    children,
  }: {
    href: string;
    children: React.ReactNode;
  }) => <a href={href}>{children}</a>,
}));

const REGIONS = {
  items: [
    {
      region_id: "county:51107",
      kind: "county",
      name: "Loudoun County",
      state: "VA",
    },
    {
      region_id: "county:41051",
      kind: "county",
      name: "Washington County",
      state: "OR",
    },
    {
      region_id: "county:49053",
      kind: "county",
      name: "Washington County",
      state: "UT",
    },
    { region_id: "state:VA", kind: "state", name: "Virginia", state: "VA" },
  ],
};

function mockFetch(payload: unknown, ok = true) {
  return vi.fn().mockResolvedValue({
    ok,
    status: ok ? 200 : 503,
    json: async () => payload,
  });
}

beforeEach(() => {
  push.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RegionPicker", () => {
  it("names where the reader already is before the list arrives", () => {
    // A never-settling fetch, so the component stays in its pre-load state.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
    render(
      <RegionPicker
        currentId="county:51107"
        currentLabel="Loudoun County, VA"
      />,
    );

    const select = screen.getByLabelText(/change region/i) as HTMLSelectElement;
    expect(select).toBeDisabled();
    // Not an empty control and not a spinner: the one option is the answer to
    // "where am I", which is useful even while the picker is not yet usable.
    expect(select.value).toBe("county:51107");
    expect(screen.getByRole("option")).toHaveTextContent("Loudoun County, VA");
  });

  it("fetches the published list and keeps same-named counties apart", async () => {
    vi.stubGlobal("fetch", mockFetch(REGIONS));
    render(
      <RegionPicker
        currentId="county:51107"
        currentLabel="Loudoun County, VA"
      />,
    );

    await waitFor(() =>
      expect(screen.getByLabelText(/change region/i)).toBeEnabled(),
    );

    // Two counties share a name; without the state they would be indistinguishable
    // in a list of hundreds.
    expect(
      screen.getByRole("option", { name: "Washington County, OR" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: "Washington County, UT" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: /United States/ }),
    ).toBeInTheDocument();
  });

  it("navigates by slug, not by the colon-form id", async () => {
    vi.stubGlobal("fetch", mockFetch(REGIONS));
    render(
      <RegionPicker
        currentId="county:51107"
        currentLabel="Loudoun County, VA"
      />,
    );
    await waitFor(() =>
      expect(screen.getByLabelText(/change region/i)).toBeEnabled(),
    );

    fireEvent.change(screen.getByLabelText(/change region/i), {
      target: { value: "county:41051" },
    });

    // The route is `/regions/county-41051`; pushing the raw id would 404.
    expect(push).toHaveBeenCalledWith("/regions/county-41051");
  });

  it("falls back to the index when the list cannot be loaded", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(
      <RegionPicker
        currentId="county:51107"
        currentLabel="Loudoun County, VA"
      />,
    );

    // A failed shortcut must not strand the reader: every region is still
    // reachable from the index.
    const link = await screen.findByRole("link", {
      name: /browse all regions/i,
    });
    expect(link).toHaveAttribute("href", "/regions");
    expect(screen.queryByLabelText(/change region/i)).toBeNull();
  });

  it("requests the published data path", async () => {
    const fetchMock = mockFetch(REGIONS);
    vi.stubGlobal("fetch", fetchMock);
    render(<RegionPicker currentId="state:VA" currentLabel="Virginia" />);

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0][0])).toMatch(
      /\/data\/regions\.json$/,
    );
  });
});
