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
        "page": "#faf8f3",
        "surface-1": "#fefdfa",
        "surface-2": "#f4f1e8",
        "ink-1": "#17150f",
        "ink-2": "#514c40",
        "ink-muted": "#6d6759",
        "accent": "#2f5fd0",
        "accent-solid": "#2a4fae",
        "link": "#2a4fae",
        "brand": "#a6610a",
        "good": "#3d7a33",
        "critical": "#b8422f",
        "caution": "#8a5a09",
        "unmeasured": "#e8e3d7",
        "unmeasured-edge": "#9e9277",
        "assert-edge-predicted": "#7c8fd7",
        "assert-edge-inferred": "#5d76cd",
        "assert-edge-calculated": "#3f5cc4",
        "assert-edge-extracted": "#334da7",
        "assert-edge-reported": "#2a3f89",
        "warn-bg": "#fdf6e6",
        "seq-2": "#b4c2f2",
        "seq-3": "#8ba0e8",
        "seq-4": "#5f7ddc",
        "seq-5": "#3f5cc4",
        "seq-6": "#2c419b",
    },
    "dark": {
        "page": "#131210",
        "surface-1": "#1d1b17",
        "surface-2": "#24211c",
        "ink-1": "#faf7f0",
        "ink-2": "#c9c1b0",
        "ink-muted": "#948b78",
        "accent": "#7d97ee",
        "accent-solid": "#33468f",
        "link": "#93a9f2",
        "brand": "#f0a63c",
        "good": "#68a458",
        "critical": "#dc7259",
        "caution": "#e0913f",
        "unmeasured": "#2b2823",
        "unmeasured-edge": "#6d6659",
        "assert-edge-predicted": "#4460c5",
        "assert-edge-inferred": "#6179ce",
        "assert-edge-calculated": "#8093d8",
        "assert-edge-extracted": "#9aa9e0",
        "assert-edge-reported": "#b4c0e8",
        "warn-bg": "#2c2517",
        "seq-2": "#2c419b",
        "seq-3": "#3f5cc4",
        "seq-4": "#5f7ddc",
        "seq-5": "#8ba0e8",
        "seq-6": "#b4c2f2",
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
