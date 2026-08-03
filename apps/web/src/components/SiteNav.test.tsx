import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NAV_GROUPS, SiteNav, normalisePath } from "./SiteNav";

/**
 * The rail is the only thing on every page of the site, and its two claims are
 * both the kind that fail silently. "You are here" was styled for and never
 * emitted, so the rule sat unmatched in the stylesheet while thirteen links
 * looked identical on all fifteen routes; and the group names, which are the
 * whole reason the links are grouped, lived only in an `aria-label` and so were
 * invisible to everyone reading the screen.
 */
let pathname = "/";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));
vi.mock("next/link", () => ({
  default: ({ children, href, ...rest }: React.ComponentProps<"a">) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock("./ThemeToggle", () => ({
  ThemeToggle: () => <button type="button">Dark</button>,
}));

function renderAt(path: string) {
  pathname = path;
  return render(<SiteNav />);
}

describe("SiteNav", () => {
  it("marks the page the reader is on, and marks only that one", () => {
    renderAt("/growth/");

    const current = screen
      .getAllByRole("link")
      .filter((a) => a.getAttribute("aria-current") === "page");
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveTextContent("Growth");
  });

  it("resolves the exported trailing slash against the written href", () => {
    // The site exports with trailingSlash: true. Comparing "/growth/" to
    // "/growth" raw is what left the current-page rule unmatched on every route.
    expect(normalisePath("/growth/")).toBe(normalisePath("/growth"));
    expect(normalisePath("/")).toBe("/");
    expect(normalisePath("")).toBe("/");
  });

  it("does not mark the overview as current from inside another section", () => {
    // "/" is a prefix of every path on the site. Treated as one, the home link
    // would be highlighted on all fifteen routes, which is the same as marking
    // none of them.
    renderAt("/regions/county-51107/");

    const overview = screen.getByRole("link", { name: "Overview" });
    expect(overview).not.toHaveAttribute("aria-current");
    expect(overview).not.toHaveAttribute("data-section");
  });

  it("shows the section a detail page belongs to, without claiming it is the page", () => {
    renderAt("/regions/county-51107/");

    const regions = screen.getByRole("link", { name: "Regions" });
    expect(regions).toHaveAttribute("data-section", "true");
    expect(regions).not.toHaveAttribute("aria-current");
    expect(
      screen
        .getAllByRole("link")
        .filter((a) => a.getAttribute("aria-current") === "page"),
    ).toHaveLength(0);
  });

  it("prints every group name rather than hiding it in an aria-label", () => {
    renderAt("/");

    for (const group of NAV_GROUPS) {
      expect(screen.getByText(group.label)).toBeInTheDocument();
    }
  });

  it("keeps each group's links inside their own labelled list", () => {
    renderAt("/");

    const arizona = screen.getByRole("list", { name: "Arizona study" });
    expect(
      within(arizona).getByRole("link", { name: "Parcel map" }),
    ).toBeInTheDocument();
    expect(within(arizona).queryByRole("link", { name: "Growth" })).toBeNull();
  });

  it("gives the collapsed menu button the state a screen reader reads", () => {
    renderAt("/");

    const button = screen.getByRole("button", { name: "Menu" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute(
      "aria-controls",
      screen.getByRole("navigation", { name: "Primary" }).id,
    );
  });
});
