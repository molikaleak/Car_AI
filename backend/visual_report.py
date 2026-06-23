"""
visual_report.py
~~~~~~~~~~~~~~~~
Generates high-aesthetic visual report cards as PNG images using Pillow.
Each report displays three metric panels (IN, OUT, Occupancy) with a
dark-themed dashboard style.
"""

import os
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from src import timezone_helper


# ---------------------------------------------------------------------------
# Font search paths ordered by platform preference
# ---------------------------------------------------------------------------
_FONT_SEARCH_PATHS: List[str] = [
    # macOS
    "/System/Library/Fonts/Supplemental/Helvetica.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    # Windows
    "C:\\Windows\\Fonts\\arial.ttf",
]


def _find_system_font() -> Optional[str]:
    """Return the first available system font path, or ``None`` if none exist."""
    for path in _FONT_SEARCH_PATHS:
        if os.path.exists(path):
            return path
    return None


def _load_fonts(font_path: Optional[str]) -> dict:
    """Load a family of sized fonts from *font_path*.

    Falls back to the Pillow default bitmap font when the TrueType file
    cannot be loaded.

    Returns:
        A dict keyed by role name (``title``, ``subtitle``, ``value``,
        ``label``, ``footer``) mapped to ``ImageFont`` instances.
    """
    sizes = {
        "title": 24,
        "subtitle": 14,
        "value": 48,
        "label": 11,
        "footer": 11,
    }

    if font_path is not None:
        try:
            return {role: ImageFont.truetype(font_path, size) for role, size in sizes.items()}
        except Exception:
            pass  # fall through to default

    default = ImageFont.load_default()
    return {role: default for role in sizes}


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    fill: Tuple[int, ...],
    center_x: float,
    y: float,
    fallback_x: float,
) -> None:
    """Draw *text* horizontally centred around *center_x* at vertical position *y*.

    Uses ``draw.textlength`` when available for precise measurement.  If
    measurement fails for any reason the text is placed at *fallback_x*.
    """
    try:
        if hasattr(draw, "textlength"):
            tw = draw.textlength(text, font=font)
        else:
            tw = len(text) * 10  # rough per-character estimate
        tx = center_x - tw / 2
        draw.text((tx, y), text, font=font, fill=fill)
    except Exception:
        draw.text((fallback_x, y), text, font=font, fill=fill)


def generate_visual_report_card(
    title: str,
    count_in: int,
    count_out: int,
    output_path: str = "report.png",
) -> str:
    """Generate a dark-themed dashboard report card and save it as a PNG.

    The image contains three metric panels:

    * **Vehicles Entered (IN)** – cyan accent
    * **Vehicles Exited (OUT)** – orange accent
    * **Current Occupancy** – purple accent

    Args:
        title: A descriptive title shown in the header subtitle line.
        count_in: Total number of vehicles that entered.
        count_out: Total number of vehicles that exited.
        output_path: Filesystem path where the PNG will be saved.

    Returns:
        The *output_path* string after the image has been written.
    """
    # ------------------------------------------------------------------
    # Canvas setup
    # ------------------------------------------------------------------
    width, height = 800, 450
    bg_color = (11, 13, 25)  # deep obsidian navy
    img = Image.new("RGB", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # ------------------------------------------------------------------
    # Fonts
    # ------------------------------------------------------------------
    font_path = _find_system_font()
    fonts = _load_fonts(font_path)

    # ------------------------------------------------------------------
    # Border outline
    # ------------------------------------------------------------------
    draw.rectangle([10, 10, width - 10, height - 10], outline=(255, 255, 255, 10), width=1)

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    now = timezone_helper.get_local_now()
    draw.text((40, 30), "GATEWAY INTELLIGENCE CAPTURE", font=fonts["title"], fill=(255, 255, 255))
    draw.text(
        (40, 65),
        f"{title.upper()} - {now.strftime('%B %d, %Y')}",
        font=fonts["subtitle"],
        fill=(148, 163, 184),
    )

    # Separator line
    draw.line([40, 95, width - 40, 95], fill=(255, 255, 255, 20), width=1)

    # ------------------------------------------------------------------
    # Metric panels
    # ------------------------------------------------------------------
    inside_count = max(0, count_in - count_out)

    panels = [
        {
            "rect": [40, 130, 260, 320],
            "border": (0, 240, 255),
            "label": "VEHICLES ENTERED (IN)",
            "val": str(count_in),
            "val_color": (0, 240, 255),
        },
        {
            "rect": [290, 130, 510, 320],
            "border": (255, 170, 0),
            "label": "VEHICLES EXITED (OUT)",
            "val": str(count_out),
            "val_color": (255, 170, 0),
        },
        {
            "rect": [540, 130, 760, 320],
            "border": (189, 52, 254),
            "label": "CURRENT OCCUPANCY",
            "val": str(inside_count),
            "val_color": (189, 52, 254),
        },
    ]

    for panel in panels:
        rx1, ry1, rx2, ry2 = panel["rect"]
        pw = rx2 - rx1
        panel_center_x = rx1 + pw / 2

        # Panel border (rounded when Pillow supports it)
        try:
            draw.rounded_rectangle(panel["rect"], radius=12, outline=panel["border"], width=2)
        except AttributeError:
            draw.rectangle(panel["rect"], outline=panel["border"], width=2)

        # Centred value
        _draw_centered_text(
            draw,
            text=panel["val"],
            font=fonts["value"],
            fill=panel["val_color"],
            center_x=panel_center_x,
            y=ry1 + 50,
            fallback_x=rx1 + 75,
        )

        # Centred label
        _draw_centered_text(
            draw,
            text=panel["label"],
            font=fonts["label"],
            fill=(148, 163, 184),
            center_x=panel_center_x,
            y=ry1 + 130,
            fallback_x=rx1 + 25,
        )

    # ------------------------------------------------------------------
    # Footer
    # ------------------------------------------------------------------
    footer_text = (
        f"ChomRok Bot • Visual Gateway Analytics • "
        f"Generated at {timezone_helper.get_local_now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    draw.text((40, 395), footer_text, font=fonts["footer"], fill=(71, 85, 105))

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    img.save(output_path)
    print(f"🎨 Generated visual report card: {output_path}")
    return output_path


if __name__ == "__main__":
    generate_visual_report_card("Test Report", 24, 15, "test_report.png")
