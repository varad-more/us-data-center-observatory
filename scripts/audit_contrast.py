"""WCAG contrast audit for the Helios token system.

Checks every foreground/background pair the interface actually produces, in both
themes, against the floor that pair owes: 4.5:1 where the value is read as text,
3:1 where it is read only as a mark (a border, a swatch, a map polygon).
"""


def srgb_to_linear(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * srgb_to_linear(r) + 0.7152 * srgb_to_linear(g) + 0.0722 * srgb_to_linear(b)


def ratio(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    lo, hi = min(a, b), max(a, b)
    return (hi + 0.05) / (lo + 0.05)


def mix(fg: str, bg: str, pct: float) -> str:
    """Approximates CSS color-mix(in srgb, fg pct%, bg) for audit purposes."""
    f, b = fg.lstrip("#"), bg.lstrip("#")
    out = []
    for i in (0, 2, 4):
        fv, bv = int(f[i : i + 2], 16), int(b[i : i + 2], 16)
        out.append(round(fv * pct + bv * (1 - pct)))
    return "#" + "".join(f"{v:02x}" for v in out)


THEMES = {
    "light": {
        "page": "#dde3d6",
        "surface-1": "#d4dbcb",
        "surface-2": "#cbd3c1",
        "ink-1": "#232420",
        "ink-2": "#4e4f45",
        "ink-muted": "#565850",
        "accent": "#4a4ebf",
        "accent-solid": "#39399e",
        "link": "#232420",
        "brand": "#232420",
        "good": "#0f7a55",
        "critical": "#b03a26",
        "caution": "#8a5a09",
        "unmeasured": "#c8cfbe",
        "unmeasured-edge": "#727663",
        "assert-edge-predicted": "#676ec7",
        "assert-edge-inferred": "#4e55bd",
        "assert-edge-calculated": "#3d44a4",
        "assert-edge-extracted": "#313684",
        "assert-edge-reported": "#252a65",
        "warn-bg": "#d8d9c0",
        "seq-2": "#a5aecd",
        "seq-3": "#8189bd",
        "seq-4": "#6167b2",
        "seq-5": "#4a4ebf",
        "seq-6": "#383a95",
        "pp-paper": "#dde3d6",
        "pp-paper-plate": "#d4dbcb",
        "pp-paper-deep": "#cbd3c1",
        "pp-ink": "#232420",
        "pp-ink-2": "#4e4f45",
        "pp-ink-muted": "#565850",
        "axis": "#8e9686",
        "pen-1": "#b03a26",
        "pen-2": "#4a4ebf",
        "pen-3": "#0f7a55",
    },
    "dark": {
        "page": "#1a1815",
        "surface-1": "#211e1a",
        "surface-2": "#262320",
        "ink-1": "#ede7d9",
        "ink-2": "#b5ae9e",
        "ink-muted": "#948e80",
        "accent": "#7c7ddd",
        "accent-solid": "#3b3d92",
        "link": "#ede7d9",
        "brand": "#ede7d9",
        "good": "#2fa277",
        "critical": "#de5c39",
        "caution": "#d69340",
        "unmeasured": "#2b2823",
        "unmeasured-edge": "#6d715f",
        "assert-edge-predicted": "#5d63c3",
        "assert-edge-inferred": "#777ccd",
        "assert-edge-calculated": "#8f94d6",
        "assert-edge-extracted": "#a6a9de",
        "assert-edge-reported": "#bdbfe6",
        "warn-bg": "#2a2619",
        "seq-2": "#2d3470",
        "seq-3": "#3c439c",
        "seq-4": "#5a5fc0",
        "seq-5": "#8189bd",
        "seq-6": "#a5aecd",
        "pp-paper": "#1a1815",
        "pp-paper-plate": "#211e1a",
        "pp-paper-deep": "#262320",
        "pp-ink": "#ede7d9",
        "pp-ink-2": "#b5ae9e",
        "pp-ink-muted": "#948e80",
        "axis": "#514c44",
        "pen-1": "#de5c39",
        "pen-2": "#7c7ddd",
        "pen-3": "#2fa277",
    },
}

# (label, fg token, bg token, floor, kind)
TEXT, MARK = 4.5, 3.0

CHECKS = [
    ("body ink on page", "ink-1", "page", TEXT),
    ("secondary ink on page", "ink-2", "page", TEXT),
    ("muted ink on page", "ink-muted", "page", TEXT),
    ("muted ink on panel", "ink-muted", "surface-1", TEXT),
    ("muted ink on raised", "ink-muted", "surface-2", TEXT),
    ("secondary ink on panel", "ink-2", "surface-1", TEXT),
    ("link on page", "link", "page", TEXT),
    ("link on panel", "link", "surface-1", TEXT),
    ("wordmark on page", "brand", "page", TEXT),
    ("body ink on unmeasured fill", "ink-1", "unmeasured", TEXT),
    ("secondary ink on unmeasured fill", "ink-2", "unmeasured", TEXT),
    ("body ink on warn fill", "ink-1", "warn-bg", TEXT),
    # The recorder world on the front page. Its ground is a different material
    # from the rest of the site, so none of the pairs above cover it.
    ("recorder ink on paper", "pp-ink", "pp-paper", TEXT),
    ("recorder secondary on paper", "pp-ink-2", "pp-paper", TEXT),
    ("recorder muted on paper", "pp-ink-muted", "pp-paper", TEXT),
    ("recorder muted on plate", "pp-ink-muted", "pp-paper-plate", TEXT),
    ("recorder muted on readout", "pp-ink-muted", "pp-paper-deep", TEXT),
    ("recorder secondary on readout", "pp-ink-2", "pp-paper-deep", TEXT),
    # The header rail, which is a plate: bank labels, resting links, and the
    # hovered link, whose ground deepens under the cursor.
    ("rail ink on plate", "pp-ink", "pp-paper-plate", TEXT),
    ("rail link on plate", "pp-ink-2", "pp-paper-plate", TEXT),
]

MARK_CHECKS = [
    ("accent mark on page", "accent", "page", MARK),
    ("good mark on page", "good", "page", MARK),
    ("critical mark on page", "critical", "page", MARK),
    ("caution mark on page", "caution", "page", MARK),
    ("unmeasured edge on panel", "unmeasured-edge", "surface-1", MARK),
    ("badge edge: predicted", "assert-edge-predicted", "surface-1", MARK),
    ("badge edge: inferred", "assert-edge-inferred", "surface-1", MARK),
    ("badge edge: calculated", "assert-edge-calculated", "surface-1", MARK),
    ("badge edge: extracted", "assert-edge-extracted", "surface-1", MARK),
    ("badge edge: reported", "assert-edge-reported", "surface-1", MARK),
    # Every pen against every ground it is actually drawn on: the ruled plot,
    # the margin plate and the readout panel.
    ("pen 1 on paper", "pen-1", "pp-paper", MARK),
    ("pen 2 on paper", "pen-2", "pp-paper", MARK),
    ("pen 3 on paper", "pen-3", "pp-paper", MARK),
    ("pen 1 on readout", "pen-1", "pp-paper-deep", MARK),
    ("pen 2 on readout", "pen-2", "pp-paper-deep", MARK),
    ("pen 3 on readout", "pen-3", "pp-paper-deep", MARK),
    ("pen 2 bar on plate", "pen-2", "pp-paper-plate", MARK),
    # The rail's current-page rule. It is the only thing distinguishing the page
    # you are on from the twelve you are not, so it has to clear the mark floor
    # against the plate it is inked on.
    ("pen 1 current rule on plate", "pen-1", "pp-paper-plate", MARK),
    # The keyboard focus ring, against every ground it can be drawn over. SC
    # 1.4.11 and 2.4.13 put it on the mark floor, and it was below it in dark:
    # the ring used --accent-solid, which is defined as a fill to put white text
    # on, and as a ring on a near-black page it measured 1.98:1.
    ("focus ring on page", "accent", "page", MARK),
    ("focus ring on panel", "accent", "surface-1", MARK),
    ("focus ring on raised panel", "accent", "surface-2", MARK),
    ("focus ring on paper", "pen-2", "pp-paper", MARK),
    ("focus ring on plate", "pen-2", "pp-paper-plate", MARK),
]

# Badge labels take --ink-1 over a tinted fill; these are the real rendered pairs.
BADGE_FILLS = [
    ("reported", "seq-6", 0.26),
    ("extracted", "seq-5", 0.20),
    ("calculated", "seq-4", 0.16),
    ("inferred", "seq-3", 0.14),
    ("predicted", "seq-2", 0.12),
]

failures = []

for theme, t in THEMES.items():
    print(f"\n{'=' * 62}\n  {theme.upper()}\n{'=' * 62}")

    print("\n  text (owes 4.5:1)")
    for label, fg, bg, floor in CHECKS:
        r = ratio(t[fg], t[bg])
        ok = r >= floor
        if not ok:
            failures.append((theme, label, r, floor))
        print(f"    {'ok ' if ok else 'FAIL'}  {r:5.2f}  {label}")

    print("\n  marks (owes 3:1)")
    for label, fg, bg, floor in MARK_CHECKS:
        r = ratio(t[fg], t[bg])
        ok = r >= floor
        if not ok:
            failures.append((theme, label, r, floor))
        print(f"    {'ok ' if ok else 'FAIL'}  {r:5.2f}  {label}")

    print("\n  badge label on its own fill (owes 4.5:1)")
    for name, seq, pct in BADGE_FILLS:
        fill = mix(t[seq], t["surface-1"], pct)
        r = ratio(t["ink-1"], fill)
        ok = r >= TEXT
        if not ok:
            failures.append((theme, f"badge {name}", r, TEXT))
        print(f"    {'ok ' if ok else 'FAIL'}  {r:5.2f}  badge {name} (fill {fill})")

    r = ratio(t["ink-2"], t["unmeasured"])
    ok = r >= TEXT
    if not ok:
        failures.append((theme, "badge unknown", r, TEXT))
    print(f"    {'ok ' if ok else 'FAIL'}  {r:5.2f}  badge unknown")

    print("\n  filled control (owes 4.5:1)")
    r = ratio("#ffffff", t["accent-solid"])
    ok = r >= TEXT
    if not ok:
        failures.append((theme, "on-accent on accent-solid", r, TEXT))
    print(f"    {'ok ' if ok else 'FAIL'}  {r:5.2f}  white on --accent-solid")

print(f"\n{'=' * 62}")
if failures:
    print(f"  {len(failures)} FAILURES")
    for theme, label, r, floor in failures:
        print(f"    {theme:5}  {label:38} {r:5.2f} < {floor}")
    raise SystemExit(1)
print("  all pairs clear their floor")
