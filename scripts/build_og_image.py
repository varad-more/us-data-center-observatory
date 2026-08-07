"""Draw the social-preview card that link unfurls use.

Run by hand -- `python3 scripts/build_og_image.py` -- and commit the PNG it
writes to `apps/web/public/og.png`. It is deliberately not wired into the build
or into CI: nothing on the card is derived from observatory data, so there is no
rebuild-and-diff gate that could go stale, and a share card does not need to be
regenerated on every push that changes a county count.

The card is the instrument with no reading on it. That is the point rather than
a shortcut: on this site a flat trace and blank paper mean different things, so
a decorative squiggle across a share card would be a reading nobody measured,
published to the one surface that travels without its axis labels. What the card
carries is the paper, its ruling, the tractor-feed edges, and the three pen inks
in their fixed order -- everything that identifies the instrument, and no claim.

Run it on the project virtualenv -- `.venv/bin/python scripts/build_og_image.py`
-- not on the system interpreter, which on macOS is still 3.9. Pillow is already
there, pulled in by pdfplumber under the `documents` extra; it is left as that
transitive rather than declared, because one hand-run tool that writes a file
already in the repository is not worth a direct dependency.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "apps" / "web" / "public" / "og.png"

# 1200x630 is the size every unfurler resamples from, and the 1.91:1 that X
# crops `summary_large_image` to without cutting anything off.
W, H = 1200, 630

# --------------------------------------------------------------- the palette --
# Light-mode values from apps/web/src/app/globals.css. A share card cannot ask
# the reader which theme they are in, and paper is the side this instrument is
# drawn on, so the light values are the ones that travel.
PAPER = (221, 227, 214)  # --page
PLATE = (212, 219, 203)  # --surface-1, the margin gutters
INK = (35, 36, 32)  # --ink-1
INK_2 = (78, 79, 69)  # --ink-2
INK_MUTED = (86, 88, 80)  # --ink-muted
RULE = (180, 98, 60)  # the rust the paper is pre-printed in
PENS = ((176, 58, 38), (74, 78, 191), (15, 122, 85))  # --pen-1, --pen-2, --pen-3

# Fixed order, never cycled: this is the same assignment the front page's margin
# plate makes, and the card is a legend for it.
CHANNELS = (
    ("FACILITIES ON THE MAP", "running total"),
    ("ADDED THAT MONTH", "net of removals"),
    ("US ELECTRICITY, TWh", "reported, then predicted"),
)

GUTTER = 46  # tractor-feed margin down both edges
PITCH = 21  # minor rule spacing; every fifth rule is drawn major
PAD = 92  # left margin of the type, measured from the sheet edge

# Archivo and Azeret Mono ship here as variable woff2, which Pillow cannot read,
# so the card is set in the nearest thing the host already has: a grotesque for
# the plates and a typewriter face for the readings. Both lists fall through to
# the DejaVu paths a Linux box would have, so this is runnable off a Mac.
SANS = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
NARROW = (
    "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
)
MONO = (
    "/System/Library/Fonts/Supplemental/Courier New Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
)


def font(candidates: tuple[str, ...], size: int) -> ImageFont.FreeTypeFont:
    """Return the first candidate face that exists on this host."""
    for path in candidates:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise SystemExit(f"none of these fonts are installed: {', '.join(candidates)}")


def over(colour: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
    """Composite `colour` onto the paper at `alpha`, since PNG output is opaque."""
    return tuple(  # type: ignore[return-value]
        round(c * alpha + p * (1 - alpha)) for c, p in zip(colour, PAPER, strict=True)
    )


def tracked(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    face: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    spacing: float,
) -> None:
    """Draw `text` letter-spaced. Pillow has no tracking, and plate caps need it."""
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=face, fill=fill)
        x += draw.textlength(char, font=face) + spacing


def main() -> None:
    """Draw the card and write it to `OUT`."""
    card = Image.new("RGB", (W, H), PAPER)
    draw = ImageDraw.Draw(card)

    minor, major = over(RULE, 0.075), over(RULE, 0.19)

    # The ruling runs edge to edge under everything else, as pre-printed paper
    # does -- the plates are laid on top of it, they do not interrupt it.
    for i in range(1, H // PITCH + 1):
        draw.line([(0, i * PITCH), (W, i * PITCH)], fill=major if i % 5 == 0 else minor)
    for i in range(1, W // PITCH + 1):
        draw.line([(i * PITCH, 0), (i * PITCH, H)], fill=major if i % 5 == 0 else minor)

    # Tractor-feed edges. The gutters are unruled: on real chart paper the
    # sprocket margin is the part the pens never reach.
    for x0 in (0, W - GUTTER):
        draw.rectangle([x0, 0, x0 + GUTTER, H], fill=PLATE)
    for edge in (GUTTER, W - GUTTER):
        draw.line([(edge, 0), (edge, H)], fill=major)
    hole = 7
    for y in range(PITCH * 2, H, PITCH * 3):
        for cx in (GUTTER // 2, W - GUTTER // 2):
            draw.ellipse([cx - hole, y - hole, cx + hole, y + hole], fill=PAPER, outline=major)

    # Header plate: solid ink with the paper knocked out of it, the one inversion
    # the site allows itself.
    plate_h = 54
    draw.rectangle([GUTTER, 0, W - GUTTER, plate_h], fill=INK)
    tracked(draw, (PAD, 18), "HELIOS", font(NARROW, 23), PAPER, 4.2)
    tracked(
        draw,
        (PAD + 116, 19),
        "US AI INFRASTRUCTURE OBSERVATORY",
        font(NARROW, 21),
        (168, 172, 158),
        3.4,
    )

    # The title. Two lines because one would have to be set small enough to lose
    # in a timeline, and the break falls where the sentence already breaks.
    title = font(SANS, 72)
    draw.text((PAD, 132), "US data centres:", font=title, fill=INK)
    draw.text((PAD, 216), "where they are,", font=title, fill=INK)
    draw.text((PAD, 300), "what they draw.", font=title, fill=INK)

    draw.line([(PAD, 412), (W - PAD, 412)], fill=INK_MUTED)

    # The pen legend, in the fixed order the front page assigns.
    label, meta = font(NARROW, 22), font(MONO, 18)
    for i, ((name, note), pen) in enumerate(zip(CHANNELS, PENS, strict=True)):
        y = 442 + i * 40
        draw.rectangle([PAD, y + 7, PAD + 30, y + 12], fill=pen)
        tracked(draw, (PAD + 48, y), name, label, INK, 2.0)
        draw.text((PAD + 372, y + 2), note, font=meta, fill=INK_MUTED)

    # Bottom right: what the reader is being asked to trust, and where it lives.
    right = font(MONO, 19)
    for i, line in enumerate(("Counted from public records.", "OpenStreetMap + LBNL + FERC")):
        text = line
        width = draw.textlength(text, font=right)
        draw.text((W - PAD - width, 452 + i * 28), text, font=right, fill=INK_2)

    card.save(OUT, optimize=True)
    print(f"wrote {OUT.relative_to(Path.cwd())} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
