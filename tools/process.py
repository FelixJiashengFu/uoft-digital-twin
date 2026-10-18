"""Turn raw Overpass JSON (data/osm/*.json) into the compact dataset the viewer embeds.

Usage: python3 -I tools/process.py data/osm data/campus.json

Coordinates are projected to a local tangent plane centred on the study area
(x = metres east, y = metres north) and stored as integer decimetres.
"""
import json
import math
import re
import sys
from collections import defaultdict

SRC, OUT = sys.argv[1], sys.argv[2]

S, W, N, E = 43.6545, -79.4060, 43.6715, -79.3855
LAT0, LON0 = (S + N) / 2, (W + E) / 2
PHI = math.radians(LAT0)
M_LAT = 111132.954 - 559.822 * math.cos(2 * PHI) + 1.175 * math.cos(4 * PHI)
M_LON = 111412.84 * math.cos(PHI) - 93.5 * math.cos(3 * PHI)


def proj(p):
    return ((p['lon'] - LON0) * M_LON, (p['lat'] - LAT0) * M_LAT)


XMIN, YMIN = proj({'lat': S, 'lon': W})
XMAX, YMAX = proj({'lat': N, 'lon': E})


def load(name):
    with open(f'{SRC}/{name}.json', encoding='utf-8') as f:
        return json.load(f)['elements']


# ---------------------------------------------------------------- geometry

def close(a, b):
    return abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6


def signed_area(r):
    s = 0.0
    for i in range(len(r) - 1):
        s += r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1]
    return s / 2


def centroid(r):
    a = signed_area(r)
    if abs(a) < 1e-9:
        xs = [p[0] for p in r]
        ys = [p[1] for p in r]
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    cx = cy = 0.0
    for i in range(len(r) - 1):
        f = r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1]
        cx += (r[i][0] + r[i + 1][0]) * f
        cy += (r[i][1] + r[i + 1][1]) * f
    return (cx / (6 * a), cy / (6 * a))


def inside(pt, r):
    x, y = pt
    c = False
    for i in range(len(r) - 1):
        x1, y1 = r[i]
        x2, y2 = r[i + 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def dp(points, tol):
    """Douglas-Peucker on an open polyline."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]
        bx, by = points[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1e-9
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            d = abs(dy * points[i][0] - dx * points[i][1] + bx * ay - by * ax) / L
            if d > best:
                best, bi = d, i
        if best > tol:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(points, keep) if k]


def simplify_ring(r, tol):
    if len(r) <= 5:
        return r
    s = dp(r, tol)
    return s if len(s) >= 4 else r


def assemble(ways):
    pool = [w[:] for w in ways if len(w) >= 2]
    rings = []
    while pool:
        cur = pool.pop(0)
        while not close(cur[0], cur[-1]):
            hit = False
            for i, w in enumerate(pool):
                if close(w[0], cur[-1]):
                    cur = cur + w[1:]
                elif close(w[-1], cur[-1]):
                    cur = cur + w[::-1][1:]
                elif close(w[-1], cur[0]):
                    cur = w[:-1] + cur
                elif close(w[0], cur[0]):
                    cur = w[::-1][:-1] + cur
                else:
                    continue
                pool.pop(i)
                hit = True
                break
            if not hit:
                break
        if close(cur[0], cur[-1]) and len(cur) >= 4:
            rings.append(cur)
    return rings


def polygons_of(e):
    """Return [(outer, [holes])] in projected metres for a way or multipolygon relation."""
    if e['type'] == 'way':
        g = [proj(p) for p in e.get('geometry', []) if p]
        if len(g) >= 4 and close(g[0], g[-1]):
            return [(g, [])]
        return []
    outers, inners = [], []
    for m in e.get('members', []):
        if m.get('type') != 'way' or not m.get('geometry'):
            continue
        g = [proj(p) for p in m['geometry'] if p]
        (inners if m.get('role') == 'inner' else outers).append(g)
    outs = assemble(outers)
    ins = assemble(inners)
    res = [(o, []) for o in outs]
    for h in ins:
        for o, hs in res:
            if inside(h[0], o):
                hs.append(h)
                break
    return res


def clip_ring(ring, xmin, ymin, xmax, ymax):
    """Sutherland-Hodgman against an axis-aligned rectangle; returns closed ring or []."""
    pts = ring[:-1]
    for edge in range(4):
        if not pts:
            return []
        out = []

        def ins(p):
            return (p[0] >= xmin, p[1] >= ymin, p[0] <= xmax, p[1] <= ymax)[edge]

        def cut(p, q):
            if edge in (0, 2):
                xv = xmin if edge == 0 else xmax
                t = (xv - p[0]) / (q[0] - p[0])
                return (xv, p[1] + t * (q[1] - p[1]))
            yv = ymin if edge == 1 else ymax
            t = (yv - p[1]) / (q[1] - p[1])
            return (p[0] + t * (q[0] - p[0]), yv)

        for i in range(len(pts)):
            cur, prev = pts[i], pts[i - 1]
            if ins(cur):
                if not ins(prev):
                    out.append(cut(prev, cur))
                out.append(cur)
            elif ins(prev):
                out.append(cut(prev, cur))
        pts = out
    if len(pts) < 3:
        return []
    return pts + [pts[0]]


def clip_line(line, xmin, ymin, xmax, ymax):
    """Split a polyline into the pieces inside the rectangle (Liang-Barsky per segment)."""
    pieces, cur = [], []
    for i in range(len(line) - 1):
        (x0, y0), (x1, y1) = line[i], line[i + 1]
        dx, dy = x1 - x0, y1 - y0
        t0, t1 = 0.0, 1.0
        ok = True
        for p, q in ((-dx, x0 - xmin), (dx, xmax - x0), (-dy, y0 - ymin), (dy, ymax - y0)):
            if p == 0:
                if q < 0:
                    ok = False
                    break
            else:
                t = q / p
                if p < 0:
                    t0 = max(t0, t)
                else:
                    t1 = min(t1, t)
        if not ok or t0 > t1:
            if len(cur) >= 2:
                pieces.append(cur)
            cur = []
            continue
        a = (x0 + t0 * dx, y0 + t0 * dy)
        b = (x0 + t1 * dx, y0 + t1 * dy)
        if not cur:
            cur = [a]
        elif not close(cur[-1], a):
            if len(cur) >= 2:
                pieces.append(cur)
            cur = [a]
        cur.append(b)
        if t1 < 1.0:
            pieces.append(cur)
            cur = []
    if len(cur) >= 2:
        pieces.append(cur)
    return pieces


def enc(points):
    """Flatten to integer decimetres."""
    out = []
    for x, y in points:
        out += [round(x * 10), round(y * 10)]
    return out


def enc_ring(r):
    return enc(r[:-1])  # drop closing vertex


def obb(r):
    pts = r[:-1]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    best = None
    # try each edge direction; minimum-area rectangle is aligned with one of them
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        ang = math.atan2(y2 - y1, x2 - x1)
        c, s = math.cos(ang), math.sin(ang)
        us = [(p[0] - cx) * c + (p[1] - cy) * s for p in pts]
        vs = [-(p[0] - cx) * s + (p[1] - cy) * c for p in pts]
        area = (max(us) - min(us)) * (max(vs) - min(vs))
        if best is None or area < best[0]:
            best = (area, ang, min(us), max(us), min(vs), max(vs))
    _, ang, u0, u1, v0, v1 = best
    c, s = math.cos(ang), math.sin(ang)
    um, vm = (u0 + u1) / 2, (v0 + v1) / 2
    ox, oy = cx + um * c - vm * s, cy + um * s + vm * c
    hl, hw = (u1 - u0) / 2, (v1 - v0) / 2
    if hw > hl:  # keep the ridge along the long side
        ang += math.pi / 2
        hl, hw = hw, hl
    return ox, oy, ang, hl, hw


# ---------------------------------------------------------------- tags

def num(v):
    if v is None:
        return None
    v = str(v).strip().lower().replace(',', '.')
    m = re.match(r'^(-?\d+(?:\.\d+)?)\s*(m|ft|\')?', v)
    if not m:
        return None
    x = float(m.group(1))
    if m.group(2) in ('ft', "'"):
        x *= 0.3048
    return x


NAMED_COLOURS = {
    'red': '#9a4b3d', 'beige': '#d6c6a6', 'grey': '#9c9c98', 'gray': '#9c9c98', 'white': '#e8e6e0',
    'lightgrey': '#c8c8c4', 'lightgray': '#c8c8c4', 'brown': '#7a5a44', 'black': '#3a3a3a',
    'orange': '#c37a40', 'olive': '#7a7a4a', 'buff': '#d9c08c', 'yellow': '#d6bf62', 'teal': '#3f7878',
    'green': '#517a4c', 'dark grey': '#58585a', 'darkgrey': '#58585a', 'turquoise': '#4c9e9e',
    'brown gray': '#7d7068', 'silver': '#c0c0c0', 'tan': '#d2b48c', 'cream': '#e8dcc0',
}


def colour(v):
    if not v:
        return None
    v = v.split(',')[0].split(';')[0].strip().lower()
    if re.match(r'^#[0-9a-f]{6}$', v):
        return v
    if re.match(r'^#[0-9a-f]{3}$', v):
        return '#' + ''.join(ch * 2 for ch in v[1:])
    return NAMED_COLOURS.get(v)


def h32(s):
    h = 2166136261
    for ch in str(s):
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


HOUSE = {'house', 'semidetached_house', 'detached', 'terrace'}
SMALL = {'garage', 'garages', 'shed', 'roof', 'kiosk', 'carport', 'hut'}

ROOF_CODE = {'flat': 0, 'skillion': 0, 'gabled': 1, 'round': 1, 'hipped': 2, 'half-hipped': 2,
             'mansard': 2, 'pyramidal': 3, 'dome': 4}

CAMPUS_OPS = re.compile(r'university of toronto|trinity college|victoria university|st\.? michael', re.I)

RES_NAMES = {
    'whitney hall', 'wetmore hall', 'burwash hall', 'annesley hall', 'margaret addison hall', 'elmsley hall',
    'sorbara hall student residence', 'wilson hall', 'morrison hall', 'chestnut residence', 'graduate house',
    'loretto college', "st. hilda's college", 'oak house', 'founders house', 'sir daniel wilson residence',
    'charles street student family housing', 'new residence (new college)', 'woodsworth college residence',
    'innis residence', 'campusone', 'shatz hall student residence', 'north building', 'rowell jackman hall',
}
SERVICE_KEYS = ['simcoe hall', 'hart house', 'koffler', 'student', 'union', 'faculty club', 'enrolment',
                'admin', 'alumni', 'communications house', 'convocation', 'graduate studies', 'utsu',
                'early learning', 'exams', 'continuing studies']
INFRA_KEYS = ['steam plant', 'chiller', 'caretaking', 'substation', 'loading dock', 'parkade', 'parking']
LIB_KEYS = ['library', 'gerstein']
ATH_KEYS = ['athletic', 'varsity', 'goldring centre', 'sport']


def campus_category(name, btype):
    n = (name or '').lower()
    if any(k in n for k in INFRA_KEYS) or btype in SMALL:
        return 'infra'
    if n == 'goldring centre' or any(k in n for k in ATH_KEYS if k != 'goldring centre'):
        if 'student' not in n:
            return 'athletics'
    if any(k in n for k in LIB_KEYS):
        return 'library'
    if n in RES_NAMES or 'residence' in n or btype in ('dormitory', 'residential', 'apartments') or btype in HOUSE:
        return 'residence'
    if any(k in n for k in SERVICE_KEYS):
        return 'services'
    if 'college' in n:
        return 'college'
    return 'academic'


def context_category(name, btype, tags):
    n = (name or '').lower()
    if btype in ('church', 'chapel', 'cathedral', 'synagogue', 'mosque', 'temple') or 'church' in n or tags.get('amenity') == 'place_of_worship':
        return 'x_religious'
    if btype == 'hospital' or 'hospital' in n or tags.get('amenity') in ('hospital', 'clinic'):
        return 'x_health'
    if 'museum' in n or tags.get('tourism') in ('museum', 'gallery') or btype in ('public', 'government', 'civic') or 'library' in n:
        return 'x_civic'
    if btype in HOUSE or btype in ('apartments', 'residential', 'dormitory', 'hotel', 'hostel'):
        return 'x_residential'
    if btype in ('retail', 'commercial', 'office', 'industrial', 'warehouse'):
        return 'x_commercial'
    return 'x_other'


# ---------------------------------------------------------------- campus boundary

campus_polys = []
campus_outline = []
KEEP_CAMPUS = {18447148, 20224402, 60304653, 61759776, 1502657605, 1502658805, 1502659706, 1504220927,
               1504222043, 1504222290, 1504225085, 1504227411, 1504227412, 1504227413, 1540356416}
for e in load('campus'):
    if e['id'] not in KEEP_CAMPUS:
        continue
    for outer, holes in polygons_of(e):
        campus_polys.append((outer, [min(p[0] for p in outer), min(p[1] for p in outer),
                                     max(p[0] for p in outer), max(p[1] for p in outer)]))
        if e['id'] == 18447148:
            for piece in clip_line(outer, XMIN, YMIN, XMAX, YMAX):
                campus_outline.append(enc(dp(piece, 0.6)))


def in_campus(pt):
    for ring, bb in campus_polys:
        if bb[0] <= pt[0] <= bb[2] and bb[1] <= pt[1] <= bb[3] and inside(pt, ring):
            return True
    return False


# ---------------------------------------------------------------- buildings

palette = []
pal_idx = {}


def pal(c):
    if c not in pal_idx:
        pal_idx[c] = len(palette)
        palette.append(c)
    return pal_idx[c]


BRICK = ['#9b5b47', '#a8735a', '#8c6a55', '#b38b6d', '#7f5646', '#c2a183', '#98705c']
STONE = ['#b9a588', '#a88f72', '#c4b69c', '#9e7e66', '#b3a999', '#8d8073', '#c9bda6']
GLASS = ['#8e9aa6', '#a9b3bc', '#7f8c99', '#b9bfc4', '#97a3ad']
CONCRETE = ['#bdb8b0', '#a9a49c', '#c9c4ba', '#9d9890', '#b4afa6']

raw = []  # one record per polygon
for e in load('buildings'):
    t = e.get('tags', {})
    is_part = 'building:part' in t and 'building' not in t
    if not is_part and 'building' not in t:
        continue
    if t.get('building') in ('no',) or t.get('building:part') in ('no',):
        continue
    for outer, holes in polygons_of(e):
        if signed_area(outer) < 0:
            outer = outer[::-1]
        outer = simplify_ring(outer, 0.2)
        holes = [simplify_ring(h if signed_area(h) < 0 else h[::-1], 0.2) for h in holes]
        area = abs(signed_area(outer)) - sum(abs(signed_area(h)) for h in holes)
        if area < 4:
            continue
        c = centroid(outer)
        if not (XMIN <= c[0] <= XMAX and YMIN <= c[1] <= YMAX):
            continue
        raw.append({'e': e, 't': t, 'part': is_part, 'outer': outer, 'holes': holes, 'area': area, 'c': c,
                    'bb': [min(p[0] for p in outer), min(p[1] for p in outer),
                           max(p[0] for p in outer), max(p[1] for p in outer)]})

outlines = [r for r in raw if not r['part']]
parts = [r for r in raw if r['part']]

# grid index for outlines
CELL = 50.0
grid = defaultdict(list)
for i, r in enumerate(outlines):
    bb = r['bb']
    for gx in range(int(bb[0] // CELL), int(bb[2] // CELL) + 1):
        for gy in range(int(bb[1] // CELL), int(bb[3] // CELL) + 1):
            grid[(gx, gy)].append(i)

part_area = defaultdict(float)
for p in parts:
    pt = p['c']
    if not inside(pt, p['outer']):
        pt = p['outer'][0]
        pt = ((pt[0] + p['c'][0]) / 2, (pt[1] + p['c'][1]) / 2)
    best = None
    for i in grid.get((int(pt[0] // CELL), int(pt[1] // CELL)), []):
        o = outlines[i]
        if inside(pt, o['outer']) and (best is None or o['area'] < outlines[best]['area']):
            best = i
    p['parent'] = best
    if best is not None:
        part_area[best] += p['area']

# ---------------------------------------------------------------- meta per outline (and orphan parts)

meta = []


def make_meta(r, campus):
    t = r['t']
    name = t.get('name') or t.get('name:en') or ''
    btype = t.get('building') or t.get('building:part') or 'yes'
    m = {'id': ('w' if r['e']['type'] == 'way' else 'r') + str(r['e']['id'])}
    if name:
        m['n'] = name
    zh = t.get('name:zh-Hans') or t.get('name:zh')
    if zh:
        m['z'] = zh
    addr = ' '.join(x for x in (t.get('addr:housenumber'), t.get('addr:street')) if x)
    if addr:
        m['a'] = addr
    m['b'] = btype
    lv = num(t.get('building:levels'))
    if lv:
        m['l'] = int(round(lv))
    for k, kk in (('start_date', 'y'), ('operator', 'op'), ('wikipedia', 'w'), ('building:material', 'mat'),
                  ('website', 'web')):
        if t.get(k):
            m[kk] = t[k]
    m['cp'] = 1 if campus else 0
    m['c'] = campus_category(name, btype) if campus else context_category(name, btype, t)
    m['ar'] = round(r['area'])
    return m


NOT_CAMPUS_TYPES = {'apartments', 'retail', 'office', 'hotel', 'church', 'commercial', 'hospital'}
GREEK = re.compile(r'\b(alpha|beta|gamma|delta|epsilon|zeta|theta|kappa|lambda|sigma|phi|psi|chi|omega|upsilon)\b', re.I)


def is_campus(t, c):
    by_op = bool(CAMPUS_OPS.search(t.get('operator', '')))
    if by_op:
        return True
    if not in_campus(c):
        return False
    # private and civic buildings that sit inside the campus polygon
    name = t.get('name', '')
    if (t.get('building') in NOT_CAMPUS_TYPES or t.get('amenity') in ('hospital', 'place_of_worship')
            or GREEK.search(name) or 'museum' in name.lower() or name in ('Campus Coop', 'Coach House Books')):
        return False
    return True


for i, o in enumerate(outlines):
    campus = is_campus(o['t'], o['c'])
    o['mi'] = len(meta)
    meta.append(make_meta(o, campus))

for p in parts:
    if p['parent'] is not None:
        p['mi'] = outlines[p['parent']]['mi']
    else:
        campus = is_campus(p['t'], p['c'])
        p['mi'] = len(meta)
        meta.append(make_meta(p, campus))

# ---------------------------------------------------------------- heights, roofs, colours

def level_h(btype):
    return 3.0 if btype in HOUSE or btype in ('apartments', 'residential', 'dormitory') else 3.6


def default_h(btype, campus):
    if btype in HOUSE:
        return 9.0
    if btype in SMALL:
        return 3.0
    if btype in ('university', 'school') or campus:
        return 14.0
    if btype == 'apartments':
        return 18.0
    if btype in ('church', 'hospital'):
        return 18.0
    if btype == 'retail':
        return 6.0
    return 8.0


geo = []
for r in outlines + parts:
    t = r['t']
    m = meta[r['mi']]
    btype = t.get('building') or t.get('building:part') or 'yes'
    h = num(t.get('height'))
    lv = num(t.get('building:levels'))
    rl = num(t.get('roof:levels'))
    rh = num(t.get('roof:height'))
    mh = num(t.get('min_height'))
    if mh is None:
        ml = num(t.get('building:min_level'))
        mh = ml * level_h(btype) if ml is not None else 0.0
    shape = t.get('roof:shape')
    if shape is None and btype in HOUSE and not r['part']:
        shape = 'gabled'
    code = ROOF_CODE.get(shape, 0)
    ox, oy, ang, hl, hw = obb(r['outer'])
    if code and rh is None:
        if rl:
            rh = rl * 2.8
        elif code == 4:
            rh = min(hw, 12.0)
        elif code == 3:
            rh = min(hw * 0.8, 6.0)
        else:
            rh = min(hw * 0.7, 4.5)
    if not code:
        rh = 0.0
    if h is None:
        if lv:
            h = lv * level_h(btype) + (rh or 0) + mh
        else:
            h = default_h(btype, m['cp']) + mh + (rh or 0) * 0.5
    rh = min(rh or 0.0, max(h - mh - 1.0, 0.0))
    wall = h - rh
    if wall <= mh + 0.3:
        wall = mh + 0.3
        h = max(h, wall + rh)

    # realistic colours
    seed = h32(m['id'])
    c = colour(t.get('building:colour'))
    if not c:
        if m['cp']:
            c = STONE[seed % len(STONE)]
        elif btype in HOUSE or (btype in ('residential', 'apartments') and h < 14):
            c = BRICK[seed % len(BRICK)]
        elif h >= 40:
            c = GLASS[seed % len(GLASS)]
        else:
            c = CONCRETE[seed % len(CONCRETE)]
    rc = colour(t.get('roof:colour'))
    if not rc:
        rc = '#55524f' if code in (1, 2, 3) else ('#7c9a8c' if code == 4 else None)

    g = {
        'o': enc_ring(r['outer']),
        'z': [round(mh * 10), round(wall * 10), round(h * 10)],
        'm': r['mi'],
        'w': pal(c),
    }
    if r['holes']:
        g['h'] = [enc_ring(x) for x in r['holes']]
    if rc:
        g['r'] = pal(rc)
    if code:
        g['s'] = code
        g['bx'] = [round(ox * 10), round(oy * 10), round(ang * 1000), round(hl * 10), round(hw * 10)]
    if r['part']:
        g['p'] = 1
    geo.append(g)
    r['g'] = g

# drop outlines that are fully represented by parts, but keep them for picking
for i, o in enumerate(outlines):
    if part_area.get(i, 0) >= 0.5 * o['area']:
        o['g']['x'] = 1  # skip when rendering

# fill heights into meta (max over its pieces)
for g in geo:
    m = meta[g['m']]
    m['h'] = max(m.get('h', 0), g['z'][2] / 10)

# ---------------------------------------------------------------- landscape

land = load('landscape')
areas = defaultdict(list)
roads = defaultdict(list)
labels = []
subway = []
stations = []

WIDTH_CLASS = {
    'primary': 'major', 'primary_link': 'major', 'secondary': 'major', 'secondary_link': 'major', 'trunk': 'major',
    'tertiary': 'minor', 'tertiary_link': 'minor', 'residential': 'minor', 'unclassified': 'minor',
    'living_street': 'minor', 'service': 'service', 'pedestrian': 'path', 'footway': 'path', 'path': 'path',
    'cycleway': 'path', 'steps': 'path', 'construction': 'service',
}
AREA_KIND = {
    'grass': 'grass', 'village_green': 'grass', 'recreation_ground': 'grass', 'park': 'park', 'garden': 'garden',
    'dog_park': 'park', 'pitch': 'pitch', 'stadium': 'pitch', 'track': 'track', 'sports_centre': 'pitch',
    'wood': 'wood', 'scrub': 'wood', 'water': 'water', 'parking': 'parking',
}

label_cands = []
for e in land:
    t = e.get('tags', {})
    if e['type'] == 'node':
        if t.get('railway') == 'station' or t.get('station') == 'subway':
            x, y = proj(e)
            if XMIN <= x <= XMAX and YMIN <= y <= YMAX:
                stations.append([t.get('name', '').replace(' station', ''), round(x * 10), round(y * 10)])
        continue
    hw = t.get('highway')
    kind = AREA_KIND.get(t.get('leisure')) or AREA_KIND.get(t.get('landuse')) or AREA_KIND.get(t.get('natural')) \
        or ('parking' if t.get('amenity') == 'parking' else None)
    if hw and t.get('area') == 'yes' and hw in ('pedestrian', 'footway'):
        kind = 'plaza'
    if kind:
        if t.get('parking') in ('underground', 'multi-storey'):
            continue
        for outer, holes in polygons_of(e):
            o = clip_ring(outer, XMIN, YMIN, XMAX, YMAX)
            if not o:
                continue
            o = simplify_ring(o, 0.4)
            hs = [enc_ring(simplify_ring(h, 0.4)) for h in holes if all(XMIN <= p[0] <= XMAX and YMIN <= p[1] <= YMAX for p in h)]
            areas[kind].append([enc_ring(o)] + hs)
        continue
    if t.get('railway') == 'subway':
        name = t.get('name', '')
        line = 1 if name.startswith('Line 1') else 2 if name.startswith('Line 2') else 0
        if not line:
            continue
        g = [proj(p) for p in e.get('geometry', [])]
        for piece in clip_line(g, XMIN, YMIN, XMAX, YMAX):
            subway.append([line] + enc(dp(piece, 1.0)))
        continue
    if hw in WIDTH_CLASS:
        if t.get('tunnel') in ('yes', 'building_passage') and hw not in ('footway', 'path'):
            continue
        if t.get('indoor') == 'yes' or (num(t.get('layer')) or 0) < 0:
            continue
        cls = WIDTH_CLASS[hw]
        g = [proj(p) for p in e.get('geometry', [])]
        for piece in clip_line(g, XMIN, YMIN, XMAX, YMAX):
            piece = dp(piece, 0.4)
            roads[cls].append(enc(piece))
            name = t.get('name')
            if name and cls in ('major', 'minor'):
                L = sum(math.hypot(piece[i + 1][0] - piece[i][0], piece[i + 1][1] - piece[i][1]) for i in range(len(piece) - 1))
                if L > 80:
                    # label at the midpoint of the longest segment
                    best = max(range(len(piece) - 1), key=lambda i: math.hypot(piece[i + 1][0] - piece[i][0], piece[i + 1][1] - piece[i][1]))
                    (x0, y0), (x1, y1) = piece[best], piece[best + 1]
                    if math.hypot(x1 - x0, y1 - y0) > 40:
                        label_cands.append((L, name, (x0 + x1) / 2, (y0 + y1) / 2, math.atan2(y1 - y0, x1 - x0), cls))

label_cands.sort(key=lambda c: -c[0])
for L, name, x, y, a, cls in label_cands:
    if any(l[0] == name and math.hypot(l[1] / 10 - x, l[2] / 10 - y) < 420 for l in labels):
        continue
    if a > math.pi / 2:
        a -= math.pi
    if a < -math.pi / 2:
        a += math.pi
    labels.append([name, round(x * 10), round(y * 10), round(a * 1000), 1 if cls == 'major' else 0])

trees = []
for e in load('trees'):
    x, y = proj(e)
    if XMIN <= x <= XMAX and YMIN <= y <= YMAX:
        hgt = num(e.get('tags', {}).get('height'))
        trees += [round(x * 10), round(y * 10), round((hgt or 0) * 10)]

out = {
    'origin': [LAT0, LON0],
    'scale': [M_LAT, M_LON],
    'bounds': [round(XMIN * 10), round(YMIN * 10), round(XMAX * 10), round(YMAX * 10)],
    'palette': palette,
    'meta': meta,
    'geo': geo,
    'areas': areas,
    'roads': roads,
    'labels': labels,
    'subway': subway,
    'stations': stations,
    'trees': trees,
    'campusOutline': campus_outline,
    'osmBase': None,
}
with open(f'{SRC}/buildings.json', encoding='utf-8') as f:
    out['osmBase'] = json.load(f).get('osm3s', {}).get('timestamp_osm_base')

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

cats = defaultdict(int)
for m in meta:
    cats[m['c']] += 1
print('polygons', len(geo), 'meta', len(meta), 'campus', sum(m['cp'] for m in meta))
print('skipped outlines', sum(1 for g in geo if g.get('x')), 'parts', len(parts),
      'orphan parts', sum(1 for p in parts if p['parent'] is None))
print('categories', dict(cats))
print('areas', {k: len(v) for k, v in areas.items()}, 'roads', {k: len(v) for k, v in roads.items()})
print('labels', len(labels), 'subway', len(subway), 'stations', stations, 'trees', len(trees) // 3)
print('palette', len(palette))
