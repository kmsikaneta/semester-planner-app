"""The weather world: every busyness level is a kind of weather.

open = Clear, calm = Fair, steady = Overcast, busy = Rain, peak = Storm.

Two places use this in v1:
- Icons next to busyness labels everywhere (a second signal besides color).
- The sky at the top of Today's brief. Until the Higgsfield art is in
  assets/skies/<name>.png, a flat code-drawn version of the same rolling-hills
  scene stands in, using the same palettes as HIGGSFIELD_PROMPTS.md.

Weather carries no blame: a storm isn't your fault, you just prepare for it.
"""

from __future__ import annotations

import base64
from pathlib import Path

SKY_DIR = Path(__file__).parent / "assets" / "skies"

WEATHER = {
    "open": {"name": "Clear", "file": "clear", "line": "Clear skies. Nothing due."},
    "calm": {"name": "Fair", "file": "fair", "line": "Fair weather. A light day."},
    "steady": {"name": "Overcast", "file": "overcast", "line": "Overcast. A normal, steady day."},
    "busy": {"name": "Rain", "file": "rain", "line": "Rain. A full day, so start early."},
    "peak": {"name": "Storm", "file": "storm", "line": "Storm. One of your heaviest days."},
}

# Palettes from the approved Higgsfield prompts (HIGGSFIELD_PROMPTS.md).
SKY_PALETTES = {
    "open": {"sky": ["#DCEFF5", "#EAF5EE", "#FFF4DA"], "sun": "#F6C85F",
             "hills": ["#CFE8C6", "#A6D8AE", "#79BF8E"], "clouds": [], "dark": False},
    "calm": {"sky": ["#FFE6BE", "#FDDBA9", "#FFF6E8"], "sun": "#F4B25C",
             "hills": ["#D5E6AE", "#A8D49B", "#74B482"], "clouds": ["#FFF6E8"], "dark": False},
    "steady": {"sky": ["#E9E2D0", "#F3EBD6", "#F8F3E6"], "sun": None,
               "hills": ["#E2D59F", "#CDBB76", "#AE9A55"], "clouds": ["#DED3B8", "#F8F3E6"], "dark": False},
    "busy": {"sky": ["#B7AFC4", "#CFC6D6", "#E8B98A"], "sun": None,
             "hills": ["#7FA58A", "#5E8A6E", "#456B55"], "clouds": ["#8F8AA3", "#6F6A86"], "dark": False},
    "peak": {"sky": ["#2E2A4A", "#3D3560", "#5A4A78"], "sun": None,
             "hills": ["#2F4A44", "#23382F", "#1A2A24"], "clouds": ["#5A4A78", "#7A6A96"], "dark": True},
}


def name(level: str) -> str:
    return WEATHER.get(level, WEATHER["open"])["name"]


# ---------- Icons (drawn in code, 24x24, inherit text color) ----------
_CLOUD = "M7.5 18.5h9.25a3.75 3.75 0 0 0 .4-7.48 5.25 5.25 0 0 0-10.1 1.3A3.1 3.1 0 0 0 7.5 18.5z"
_CLOUD_HIGH = "M7.5 14.5h9.25a3.75 3.75 0 0 0 .4-7.48 5.25 5.25 0 0 0-10.1 1.3A3.1 3.1 0 0 0 7.5 14.5z"
_RAYS = "".join(
    f'<line x1="{12 + 7 * dx:.1f}" y1="{12 + 7 * dy:.1f}" x2="{12 + 9.3 * dx:.1f}" y2="{12 + 9.3 * dy:.1f}"/>'
    for dx, dy in [(1, 0), (0.707, 0.707), (0, 1), (-0.707, 0.707), (-1, 0), (-0.707, -0.707), (0, -1), (0.707, -0.707)]
)

_ICON_BODY = {
    "open": f'<circle cx="12" cy="12" r="4.2"/>{_RAYS}',
    "calm": (
        '<circle cx="8.5" cy="8.5" r="3"/>'
        '<line x1="8.5" y1="2.6" x2="8.5" y2="3.8"/><line x1="2.6" y1="8.5" x2="3.8" y2="8.5"/>'
        '<line x1="4.3" y1="4.3" x2="5.2" y2="5.2"/><line x1="12.7" y1="4.3" x2="11.8" y2="5.2"/>'
        f'<path d="{_CLOUD}" fill="var(--surface, #fff)"/>'
    ),
    "steady": f'<path d="{_CLOUD}"/>',
    "busy": (
        f'<path d="{_CLOUD_HIGH}"/>'
        '<line x1="9" y1="17" x2="8" y2="20"/><line x1="12.5" y1="17" x2="11.5" y2="20"/><line x1="16" y1="17" x2="15" y2="20"/>'
    ),
    "peak": (
        f'<path d="{_CLOUD_HIGH}"/>'
        '<path d="M12.6 14.2 10.4 18h2.6l-1.4 3.6" stroke-width="1.9"/>'
    ),
}


def icon(level: str, size: int = 18, color: str = "currentColor") -> str:
    body = _ICON_BODY.get(level, _ICON_BODY["open"])
    return (
        f'<svg class="wx-icon" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" '
        f'aria-label="{name(level)}" role="img">{body}</svg>'
    )


# ---------- The sky (brief header) ----------
def _sky_image_uri(level: str) -> str | None:
    path = SKY_DIR / f"{WEATHER[level]['file']}.png"
    if not path.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def _cloud(cx: float, cy: float, s: float, fill: str, opacity: float = 1.0) -> str:
    return (
        f'<g fill="{fill}" opacity="{opacity}">'
        f'<ellipse cx="{cx}" cy="{cy}" rx="{70 * s}" ry="{22 * s}"/>'
        f'<circle cx="{cx - 28 * s}" cy="{cy - 10 * s}" r="{24 * s}"/>'
        f'<circle cx="{cx + 12 * s}" cy="{cy - 20 * s}" r="{32 * s}"/>'
        f'<circle cx="{cx + 44 * s}" cy="{cy - 6 * s}" r="{20 * s}"/></g>'
    )


def sky_svg(level: str) -> str:
    """A flat, code-drawn rolling-hills sky: the stand-in until the real art lands."""
    p = SKY_PALETTES.get(level, SKY_PALETTES["open"])
    s0, s1, s2 = p["sky"]
    h1, h2, h3 = p["hills"]
    parts = [
        '<svg class="sky-art" viewBox="0 0 1200 300" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">',
        f'<defs><linearGradient id="sky-{level}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{s0}"/><stop offset="0.55" stop-color="{s1}"/><stop offset="1" stop-color="{s2}"/>'
        f'</linearGradient></defs>',
        f'<rect width="1200" height="300" fill="url(#sky-{level})"/>',
    ]
    if level == "peak":
        parts.append('<rect y="196" width="1200" height="10" fill="#E06049" opacity="0.75"/>')
    if p["sun"]:
        r = 58 if level == "calm" else 40
        cy = 170 if level == "calm" else 96
        parts.append(f'<circle cx="930" cy="{cy}" r="{r * 1.9}" fill="{p["sun"]}" opacity="0.18"/>')
        parts.append(f'<circle cx="930" cy="{cy}" r="{r}" fill="{p["sun"]}"/>')
    clouds = p["clouds"]
    if level == "calm":
        parts += [_cloud(300, 90, 0.7, clouds[0], 0.95), _cloud(640, 60, 0.5, clouds[0], 0.9)]
    elif level == "steady":
        parts += [_cloud(180, 80, 1.3, clouds[0]), _cloud(520, 60, 1.6, clouds[1]), _cloud(880, 90, 1.4, clouds[0]),
                  _cloud(1120, 60, 1.2, clouds[1])]
    elif level in ("busy", "peak"):
        parts += [_cloud(160, 70, 1.6, clouds[1]), _cloud(470, 50, 1.9, clouds[0]), _cloud(820, 70, 1.7, clouds[1]),
                  _cloud(1100, 50, 1.6, clouds[0])]
        streak = "#ECE8F2" if level == "busy" else "#9C90B8"
        parts.append(f'<g stroke="{streak}" stroke-width="2" stroke-linecap="round" opacity="0.6">')
        for i in range(26):
            x = 40 + i * 46
            y = 120 + (i * 37) % 60
            parts.append(f'<line x1="{x}" y1="{y}" x2="{x - 10}" y2="{y + 26}"/>')
        parts.append("</g>")
    if level == "peak":
        parts.append('<path d="M330 92 298 150h26l-18 52 52-70h-28l22-40z" fill="#FFD27A"/>')
    # The same landscape in every sky: three hills, a path, a few trees.
    parts += [
        f'<path d="M0 205 C 200 168, 380 198, 560 184 S 900 158, 1200 192 L1200 300 L0 300Z" fill="{h1}"/>',
        f'<path d="M0 238 C 180 204, 420 236, 640 220 S 980 198, 1200 228 L1200 300 L0 300Z" fill="{h2}"/>',
        f'<path d="M0 272 C 260 244, 520 270, 760 256 S 1060 246, 1200 262 L1200 300 L0 300Z" fill="{h3}"/>',
        f'<path d="M520 300 C 560 280, 610 270, 660 262 S 720 252, 760 248" stroke="{s2}" stroke-width="7" fill="none" opacity="0.55" stroke-linecap="round"/>',
    ]
    for tx, ty, tr in [(214, 208, 11), (236, 212, 8), (1010, 214, 12), (1034, 219, 8)]:
        parts.append(f'<circle cx="{tx}" cy="{ty}" r="{tr}" fill="{h3}"/>')
    parts.append("</svg>")
    return "".join(parts)


def sky(level: str) -> str:
    """The brief's sky: the real Higgsfield art if it's in the repo, else the code-drawn stand-in."""
    uri = _sky_image_uri(level)
    if uri:
        return f'<img class="sky-art" src="{uri}" alt="{name(level)} sky"/>'
    return sky_svg(level)


def is_dark(level: str) -> bool:
    return SKY_PALETTES.get(level, SKY_PALETTES["open"])["dark"]
