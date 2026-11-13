"""Generate branding/mark.svg and branding/logo.svg (the PNG masters are rendered by render.js).

The football is a real truncated icosahedron (12 black pentagons, 20 white
hexagons) projected orthographically, so it reads as a classic match ball at
every size. Run: python3 branding/build_svg.py && node branding/render.js
"""
import itertools
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
PHI = (1 + 5 ** 0.5) / 2


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    length = math.sqrt(_dot(a, a))
    return tuple(x / length for x in a)


def truncated_icosahedron():
    """Return (pentagons, hexagons) as lists of 3D vertex loops on the unit sphere."""
    ico = []
    for s1, s2 in itertools.product((1, -1), repeat=2):
        ico += [(0, s1, s2 * PHI), (s1, s2 * PHI, 0), (s2 * PHI, 0, s1)]
    edges = [(i, j) for i, j in itertools.combinations(range(12), 2)
             if abs(math.dist(ico[i], ico[j]) - 2) < 1e-9]
    point = {}
    for i, j in edges:
        point[(i, j)] = tuple(a + (b - a) / 3 for a, b in zip(ico[i], ico[j]))
        point[(j, i)] = tuple(a + (b - a) / 3 for a, b in zip(ico[j], ico[i]))
    neighbours = {i: [j for a, b in edges for i2, j in ((a, b), (b, a)) if i2 == i] for i in range(12)}
    faces = [f for f in itertools.combinations(range(12), 3)
             if all(b in neighbours[a] for a, b in itertools.combinations(f, 2))]

    def ordered(points, centre):
        n = _norm(centre)
        ref = _norm(_sub(points[0], centre))
        side = _cross(n, ref)
        return sorted(points, key=lambda p: math.atan2(_dot(_sub(p, centre), side), _dot(_sub(p, centre), ref)))

    pentagons = [ordered([point[(i, j)] for j in neighbours[i]], ico[i]) for i in range(12)]
    hexagons = []
    for a, b, c in faces:
        pts = [point[(a, b)], point[(b, a)], point[(b, c)], point[(c, b)], point[(c, a)], point[(a, c)]]
        centre = tuple(sum(v) / 3 for v in zip(ico[a], ico[b], ico[c]))
        hexagons.append(ordered(pts, centre))
    scale = max(math.sqrt(_dot(p, p)) for loop in pentagons for p in loop)
    unit = lambda loop: [tuple(x / scale for x in p) for p in loop]
    return [unit(l) for l in pentagons], [unit(l) for l in hexagons]


def _rotation(v):
    """Rotate so vector v points at the viewer (+z), then tilt a little for life."""
    v = _norm(v)
    axis = _cross(v, (0, 0, 1))
    s, c = math.sqrt(_dot(axis, axis)), v[2]
    if s < 1e-12:
        base = lambda p: p
    else:
        k = tuple(x / s for x in axis)
        def base(p):
            kp = _cross(k, p)
            kd = _dot(k, p)
            return tuple(p[i] * c + kp[i] * s + k[i] * kd * (1 - c) for i in range(3))
    tilt_x, tilt_z = math.radians(-16), math.radians(12)

    def rotate(p):
        x, y, z = base(p)
        y, z = y * math.cos(tilt_x) - z * math.sin(tilt_x), y * math.sin(tilt_x) + z * math.cos(tilt_x)
        x, y = x * math.cos(tilt_z) - y * math.sin(tilt_z), x * math.sin(tilt_z) + y * math.cos(tilt_z)
        return x, y, z
    return rotate


def football(cx, cy, r, ns="b"):
    pentagons, hexagons = truncated_icosahedron()
    front = tuple(sum(c) / 5 for c in zip(*pentagons[0]))
    rotate = _rotation(front)

    def path(loop):
        pts = [rotate(p) for p in loop]
        if sum(p[2] for p in pts) / len(pts) <= 0.05:
            return None
        return "M" + "L".join("%.2f %.2f" % (cx + p[0] * r, cy - p[1] * r) for p in pts) + "Z"

    black = "".join(p for p in map(path, pentagons) if p)
    white = "".join(p for p in map(path, hexagons) if p)
    return f'''  <defs>
    <radialGradient id="{ns}-shade" cx="0.34" cy="0.3" r="0.78">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0"/>
      <stop offset="0.62" stop-color="#7a93ab" stop-opacity="0.05"/>
      <stop offset="1" stop-color="#0b2238" stop-opacity="0.32"/>
    </radialGradient>
    <clipPath id="{ns}-clip"><circle cx="{cx}" cy="{cy}" r="{r}"/></clipPath>
  </defs>
  <circle cx="{cx}" cy="{cy}" r="{r + 3.2:.1f}" fill="#081224"/>
  <g clip-path="url(#{ns}-clip)">
    <circle cx="{cx}" cy="{cy}" r="{r}" fill="#ffffff"/>
    <path d="{white}" fill="#ffffff" stroke="#14283c" stroke-width="{r * 0.055:.2f}" stroke-linejoin="round"/>
    <path d="{black}" fill="#0b1726" stroke="#0b1726" stroke-width="{r * 0.055:.2f}" stroke-linejoin="round"/>
    <circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#{ns}-shade)"/>
    <ellipse cx="{cx - r * 0.38:.2f}" cy="{cy - r * 0.42:.2f}" rx="{r * 0.2:.2f}" ry="{r * 0.12:.2f}" fill="#ffffff" fill-opacity="0.55" transform="rotate(-35 {cx - r * 0.38:.2f} {cy - r * 0.42:.2f})"/>
  </g>
  <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#081224" stroke-width="{r * 0.07:.2f}"/>
'''


def mark_body(ns="sli"):
    return f'''  <defs>
    <linearGradient id="{ns}-bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#14456a"/>
      <stop offset="1" stop-color="#081224"/>
    </linearGradient>
    <linearGradient id="{ns}-live" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#05c6cc"/>
      <stop offset="1" stop-color="#a2ef59"/>
    </linearGradient>
  </defs>
  <rect x="4" y="4" width="120" height="120" rx="28" fill="url(#{ns}-bg)"/>
  <rect x="4.75" y="4.75" width="118.5" height="118.5" rx="27.25" fill="none" stroke="#3fb8ba" stroke-opacity=".35" stroke-width="1.5"/>
  <rect x="14" y="22" width="80" height="58" rx="11" fill="#0b2238" stroke="#eaf6ff" stroke-width="5"/>
  <path d="M54 80v10M40 92h28" stroke="#eaf6ff" stroke-width="5" stroke-linecap="round"/>
  <rect x="24" y="33" width="40" height="9" rx="4.5" fill="url(#{ns}-live)"/>
  <rect x="24" y="48" width="50" height="7" rx="3.5" fill="#5d86a8"/>
  <rect x="24" y="61" width="30" height="7" rx="3.5" fill="#5d86a8"/>
  <circle cx="78" cy="37.5" r="5" fill="#a2ef59"/>
  <path d="M85.5 31.5a8 8 0 0 1 0 12M90.5 27a14.5 14.5 0 0 1 0 21" fill="none" stroke="#a2ef59" stroke-width="3.5" stroke-linecap="round"/>
{football(91, 89, 27, ns + "-ball")}'''


def build():
    mark = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128">
  <title>SportsLiveInfo</title>
{mark_body()}</svg>
'''
    logo = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 250 100" width="250" height="100">
  <title>SportsLiveInfo</title>
  <defs>
    <linearGradient id="logo-badge" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0f3352"/><stop offset="1" stop-color="#081224"/></linearGradient>
    <linearGradient id="logo-word" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#05c6cc"/><stop offset="1" stop-color="#a2ef59"/></linearGradient>
  </defs>
  <rect x="1" y="1" width="248" height="98" rx="20" fill="url(#logo-badge)" stroke="#3fb8ba" stroke-opacity=".45" stroke-width="1.5"/>
  <svg x="12" y="14" width="72" height="72" viewBox="0 0 128 128">
{mark_body("logo-mark")}  </svg>
  <text x="94" y="50" font-family="Inter, 'DejaVu Sans', sans-serif" font-size="25" font-weight="800" letter-spacing="-0.6" fill="#ffffff">SportsLive</text>
  <text x="94" y="74" font-family="Inter, 'DejaVu Sans', sans-serif" font-size="19" font-weight="800" letter-spacing="-0.3" fill="url(#logo-word)">Info</text>
  <text x="141" y="73" font-family="Inter, 'DejaVu Sans', sans-serif" font-size="9.5" font-weight="600" letter-spacing="1.4" fill="#9fc3dc">TV GUIDE · LIVE</text>
</svg>
'''
    (HERE / "mark.svg").write_text(mark)
    (HERE / "logo.svg").write_text(logo)


if __name__ == "__main__":
    build()
