/**
 * The colours the maps are painted in.
 *
 * MapLibre paint expressions take resolved colour values, not `var()`
 * references, and a custom property holding `light-dark()` does not resolve
 * through `getComputedStyle` — so the map palette cannot read the stylesheet at
 * runtime and has to be declared here.
 *
 * That duplication is exactly what went wrong once already. The three map
 * components each carried their own copy of the old ivory palette as literals;
 * when the site moved onto chart paper the stylesheet changed and the copies did
 * not, so every dot kept its amber, every halo kept painting the old page colour
 * `#faf8f3` as a near-white ring on a green-grey ground, and the choropleth kept
 * a ramp mixed for a page that no longer existed.
 *
 * So there is one copy, here, and `mapPalette.test.ts` reads `globals.css` and
 * fails if any value below stops matching the token it mirrors. A duplication
 * that cannot silently drift is a different thing from one that can.
 */

export type Theme = "light" | "dark";
export type ThemePair = Record<Theme, string>;

/** --page. The halo around every mark, so a dot reads as sitting on the paper. */
export const MAP_PAPER: ThemePair = { light: "#dde3d6", dark: "#1a1815" };

/**
 * The pens, assigned as they are everywhere else on the site and never cycled.
 *
 * The facility takes pen 1 because the count is pen 1 wherever it appears — a
 * reader who learns the ink on the front page keeps it here. It used to be
 * `--caution` amber, which on this ground read as a fourth hue that graded
 * nothing.
 */
export const MAP_FACILITY: ThemePair = { light: "#b03a26", dark: "#de5c39" };
export const MAP_SUBSTATION: ThemePair = { light: "#4a4ebf", dark: "#7c7ddd" };
export const MAP_PLANT: ThemePair = { light: "#0f7a55", dark: "#2fa277" };

/** --unmeasured-edge. A site not placed on the scale is not a weak step of it. */
export const MAP_UNPLACED: ThemePair = { light: "#727663", dark: "#6d715f" };

/**
 * Nine stages along one hue, spanning the same range as `--seq-1`…`--seq-7`.
 *
 * One hue rather than nine, because stage is an ordered progression: a
 * categorical set would say stage 3 and stage 4 are different kinds of thing
 * rather than adjacent points on one scale. Dark runs the same steps reversed,
 * so "further along" always resolves to the higher-contrast end against
 * whichever ground is behind it.
 */
export const STAGE_RAMP: Record<Theme, string[]> = {
  //     0          1          2          3          4          5          6          7          8
  light: [
    "#c5c8ea",
    "#abaee0",
    "#9195d6",
    "#767ccc",
    "#5c63c3",
    "#444bb7",
    "#3a419d",
    "#303683",
    "#272b68",
  ],
  dark: [
    "#272b68",
    "#303683",
    "#3a419d",
    "#444bb7",
    "#5c63c3",
    "#767ccc",
    "#9195d6",
    "#abaee0",
    "#c5c8ea",
  ],
};

/**
 * The basemap is CARTO's raster positron: near-white in light, near-black in
 * dark. Dropped straight onto chart paper it read as a hole punched in the page
 * — the one surface on the site still wearing the palette everything else left.
 *
 * Tinting the tiles toward the paper was the first attempt and it produced grey
 * land inside a sage page: a desaturated photograph rather than something
 * printed. So the tiles are made translucent instead and the paper is put behind
 * them, which is the truthful version of the same idea — the map is printed on
 * the sheet, and the sheet shows through. Saturation is taken all the way out
 * because the basemap is context and the three pens are the subject; a coloured
 * underlay argues with them for no gain.
 *
 * Done with MapLibre's own raster paint properties rather than a CSS filter,
 * because a filter composites the whole canvas including the marks drawn on top.
 */
export const BASEMAP_PAINT: Record<Theme, Record<string, number>> = {
  light: {
    "raster-saturation": -1,
    "raster-contrast": -0.3,
    "raster-brightness-min": 0.1,
    "raster-brightness-max": 0.95,
    "raster-opacity": 0.42,
  },
  dark: {
    "raster-saturation": -1,
    "raster-contrast": -0.2,
    "raster-brightness-min": 0.08,
    "raster-brightness-max": 0.7,
    "raster-opacity": 0.5,
  },
};

/** The MapLibre `match` expression, so the legend and the polygons cannot drift. */
export function stageColourExpression(theme: Theme): unknown[] {
  return [
    "match",
    ["get", "stage"],
    ...STAGE_RAMP[theme].flatMap((colour, stage) => [stage, colour]),
    MAP_UNPLACED[theme],
  ];
}
