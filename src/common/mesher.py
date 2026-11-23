"""2D eksenel simetrik hibrit mesh: yapısal sınır tabakası (Python) + dış bölge üçgenleri (Gmsh).

Alan (y >= 0, eksen y = 0):
        farfield (y = H)
   +--------------------------------------------------+
   |                                                  |
 inlet          ___________________________          outlet
   |      ____/  burun (L)   gövde (2,0 m) |  iz      |
   +-----*-----------------------------------+--------+
    axis  uç(0,0)      wall_rocket         taban   axis

1) Duvar zinciri (uç yayı/meplat yüzü + burun eğrisi + gövde + taban) boyut kurallarına göre düğümlenir.
2) Her duvar düğümünden dış normal yönünde geometrik büyüyen katmanlar (ilk yükseklik h1, kalınlık t).
   - Küçük kırıklar (< fan eşiği): açıortay normali. Dışbükey köşeler: tek düğümden fan.
   - Uç ve taban-eksen düğümlerinin normali tam eksen yönünde -> BL kolonu eksen üzerinde.
3) BL üst kenarı sabit sınır olarak Gmsh'a verilir; dış bölge Frontal-Delaunay üçgenlerle örülür.
4) Birleştirilen mesh Fluent ASCII .msh olarak yazılır (common/fluent_msh.py).

Sınır isimleri sabit sözleşmedir: inlet, outlet, farfield, wall_rocket, axis; hücre bölgesi: fluid.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

import gmsh
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import brentq

from .config import CONFIG_DIR
from .fluent_msh import make_face_zones, write_fluent_msh
from .geometry import NoseGeometry

log = logging.getLogger(__name__)

BOUNDARY_NAMES = ("inlet", "outlet", "farfield", "wall_rocket", "axis")
BC_TYPES = {
    "inlet": "pressure-far-field",
    "outlet": "pressure-far-field",
    "farfield": "pressure-far-field",
    "wall_rocket": "wall",
    "axis": "axis",
}


def load_mesh_settings() -> dict:
    return json.loads((CONFIG_DIR / "mesh_settings.json").read_text(encoding="utf-8"))


# =========================================================================== duvar segmentleri

class Segment:
    """Duvar zincirinin bir parçası. s ∈ [0, length] yay uzunluğu parametresi."""

    length: float
    sizes: tuple[float, float, float]   # (başlangıç, bitiş, en büyük) teğetsel hücre boyu

    def point(self, s: np.ndarray) -> np.ndarray: ...
    def normal(self, s: np.ndarray) -> np.ndarray: ...


class ArcSeg(Segment):
    def __init__(self, center: tuple[float, float], r: float, th0: float, th1: float, sizes):
        self.c = np.asarray(center, float)
        self.r, self.th0, self.th1 = r, th0, th1
        self.length = r * abs(th0 - th1)
        self.sizes = sizes

    def _th(self, s):
        return self.th0 + (self.th1 - self.th0) * np.asarray(s, float) / self.length

    def point(self, s):
        th = self._th(s)
        return self.c + self.r * np.column_stack([np.cos(th), np.sin(th)])

    def normal(self, s):
        th = self._th(s)
        return np.column_stack([np.cos(th), np.sin(th)])   # dışbükey yay: radyal dış normal


class LineSeg(Segment):
    def __init__(self, p0, p1, sizes):
        self.p0, self.p1 = np.asarray(p0, float), np.asarray(p1, float)
        d = self.p1 - self.p0
        self.length = float(np.hypot(*d))
        self.t = d / self.length
        self.n = np.array([-self.t[1], self.t[0]])
        self.sizes = sizes

    def point(self, s):
        return self.p0 + np.outer(np.asarray(s, float), self.t)

    def normal(self, s):
        return np.tile(self.n, (len(np.atleast_1d(s)), 1))


class CurveSeg(Segment):
    """Yoğun profil noktalarından yay-uzunluğu parametreli kübik spline."""

    def __init__(self, pts: np.ndarray, sizes, force_start_normal=None):
        d = np.hypot(*np.diff(pts, axis=0).T)
        keep = np.concatenate([[True], d > 1e-13])
        pts = pts[keep]
        s = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))])
        self.length = float(s[-1])
        self.sx = CubicSpline(s, pts[:, 0])
        self.sy = CubicSpline(s, pts[:, 1])
        self.p_start, self.p_end = pts[0], pts[-1]
        self.sizes = sizes
        self.force_start_normal = force_start_normal

    def point(self, s):
        s = np.clip(np.asarray(s, float), 0, self.length)
        p = np.column_stack([self.sx(s), self.sy(s)])
        p[s <= 0] = self.p_start            # uç noktalar birebir korunur
        p[s >= self.length] = self.p_end
        return p

    def normal(self, s):
        s = np.clip(np.asarray(s, float), 0, self.length)
        tx, ty = self.sx(s, 1), self.sy(s, 1)
        n = np.column_stack([-ty, tx])
        n /= np.linalg.norm(n, axis=1)[:, None]
        if self.force_start_normal is not None:
            n[s <= 0] = self.force_start_normal
        return n


def distribute(length: float, a: float, b: float, m: float, slope: float) -> np.ndarray:
    """Teğetsel düğüm konumları: h(s) = min(m, a + slope·s, b + slope·(length − s))."""
    a, b = min(a, m), min(b, m)
    s = np.linspace(0.0, length, 20001)
    h = np.minimum(m, np.minimum(a + slope * s, b + slope * (length - s)))
    inv = 1.0 / h
    I = np.concatenate([[0.0], np.cumsum(0.5 * (inv[1:] + inv[:-1]) * np.diff(s))])
    n = max(1, int(round(I[-1])))
    return np.interp(np.linspace(0, I[-1], n + 1), I, s)


def build_wall_segments(geo: NoseGeometry, body_length: float, s: dict) -> list[Segment]:
    sz = s["sizes"]
    L, R = geo.L, geo.R
    Lb = L + body_length
    segs: list[Segment] = []

    if geo.arc is not None:
        a = geo.arc
        i_t = geo.n_arc_pts - 1
        xt, yt = float(geo.x[i_t]), float(geo.y[i_t])
        th_t = math.atan2(yt, xt - a.rn)       # kaydırılmış koordinatlarda merkez (rn, 0)
        segs.append(ArcSeg((a.rn, 0.0), a.rn, math.pi, th_t, (sz["tip_arc"],) * 3))
        i0 = i_t
        force = None
    elif geo.tip.kind == "flat":
        # Meplat: köşedeki fanın üst kenar aralığı (~t·15°) ile uyumlu olması için tip_arc değil tip_region
        segs.append(LineSeg((0.0, 0.0), (0.0, float(geo.y[1])), (sz["tip_region"],) * 3))
        i0 = 1
        force = None
    else:
        i0 = 0
        force = np.array([-1.0, 0.0])           # küt uç: normal tam eksen yönünde

    pts = np.column_stack([geo.x[i0:], geo.y[i0:]])
    breaks = [0] + [k - i0 for k in geo.kink_idx if 0 < k - i0 < len(pts) - 1] + [len(pts) - 1]
    for j in range(len(breaks) - 1):
        if j > 0:
            start = sz["nose_wall"]
        elif geo.tip.kind == "flat":
            start = sz["tip_region"]
        else:
            start = sz["tip_arc"]
        segs.append(CurveSeg(pts[breaks[j]:breaks[j + 1] + 1],
                             (start, sz["nose_wall"], sz["nose_wall"]),
                             force_start_normal=force if j == 0 else None))

    x_mid = L + s["body_split"]
    segs.append(LineSeg((L, R), (x_mid, R), (sz["nose_wall"], sz["body_wall"], sz["body_wall"])))
    segs.append(LineSeg((x_mid, R), (Lb, R), (sz["body_wall"], sz["base_corner"], sz["body_wall"])))
    segs.append(LineSeg((Lb, R), (Lb, 0.0), (sz["base_corner"], sz["base_wall"], sz["base_wall"])))
    return segs


# =========================================================================== sınır tabakası

def bl_heights(h1: float, ratio0: float, t: float) -> tuple[np.ndarray, float]:
    n = math.ceil(math.log(1 + t * (ratio0 - 1) / h1) / math.log(ratio0))
    r = brentq(lambda r: h1 * (r**n - 1) / (r - 1) - t, 1.0001, 3.0)
    return np.concatenate([[0.0], np.cumsum(h1 * r ** np.arange(n))]), r


@dataclass
class BLMesh:
    xy: np.ndarray
    cells: list[np.ndarray]
    wall_nodes: set[int]
    top_chain: list[int]          # BL üst kenarı (uç-eksen -> taban-eksen)
    n_layers: int
    ratio: float
    n_wall_nodes: int
    n_fans: int
    info: dict = field(default_factory=dict)


def _angle(u, v) -> float:
    """u'dan v'ye işaretli açı (CCW pozitif)."""
    return math.atan2(u[0] * v[1] - u[1] * v[0], u[0] * v[0] + u[1] * v[1])


def build_bl(segs: list[Segment], s: dict) -> BLMesh:
    bl = s["boundary_layer"]
    heights, ratio = bl_heights(bl["first_height"], bl["growth_ratio"], bl["thickness"])
    nL = len(heights) - 1
    fan_thr = math.radians(s["fan"]["threshold_deg"])
    fan_max = math.radians(s["fan"]["max_sector_deg"])
    slope = s["tangential_growth"] - 1.0

    # (duvar noktası, [normal(ler)]) listesi
    stations: list[tuple[np.ndarray, list[np.ndarray]]] = []
    n_fans = 0
    for i, seg in enumerate(segs):
        a, b, m = seg.sizes
        sv = distribute(seg.length, a, b, m, slope)
        P, N = seg.point(sv), seg.normal(sv)
        if i == 0:
            stations.append((P[0], [N[0]]))
        else:
            # Birleşim: önceki segmentin son normali ile bu segmentin ilk normali
            p_prev, n_prev = stations[-1][0], stations[-1][1][-1]
            n_next = N[0]
            phi = _angle(n_prev, n_next)
            if abs(phi) < fan_thr:
                nb = n_prev + n_next
                stations[-1] = (p_prev, [nb / np.linalg.norm(nb)])
            else:
                if phi > 0:
                    raise ValueError(f"İçbükey köşe ({math.degrees(phi):.1f}°) — BL fanı uygulanamaz")
                k = max(1, math.ceil(abs(phi) / fan_max))
                th0 = math.atan2(n_prev[1], n_prev[0])
                rays = [np.array([math.cos(th0 + phi * j / k), math.sin(th0 + phi * j / k)]) for j in range(k + 1)]
                stations[-1] = (p_prev, rays)
                n_fans += 1
        for j in range(1, len(sv)):
            stations.append((P[j], [N[j]]))

    xy: list[np.ndarray] = []
    columns: list[list[int]] = []
    wall_nodes: set[int] = set()
    for p, rays in stations:
        w = len(xy)
        xy.append(p)
        wall_nodes.add(w)
        for n in rays:
            col = [w]
            for h in heights[1:]:
                col.append(len(xy))
                xy.append(p + h * n)
            columns.append(col)
    xy = np.array(xy)

    # Uç ve taban-eksen kolonlarını tam eksene sabitle (yuvarlama hatası)
    for col in (columns[0], columns[-1]):
        xy[col, 1] = 0.0

    cells: list[np.ndarray] = []
    for c0, c1 in zip(columns[:-1], columns[1:]):
        k0 = 0
        if c0[0] == c1[0]:                       # fan: ilk katman üçgen
            cells.append(np.array([c0[0], c1[1], c0[1]]))
            k0 = 1
        for k in range(k0, nL):
            cells.append(np.array([c0[k], c1[k], c1[k + 1], c0[k + 1]]))

    top = [col[-1] for col in columns]
    return BLMesh(xy, cells, wall_nodes, top, nL, ratio, len(stations), n_fans)


# =========================================================================== dış bölge (Gmsh)

def mesh_outer(blm: BLMesh, geo: NoseGeometry, Lb: float, s: dict, verbose=False):
    dom, sz, box = s["domain"], s["sizes"], s["refinement_boxes"]
    Xu, H, Xd = dom["upstream_factor"] * Lb, dom["radial_factor"] * Lb, dom["downstream_factor"] * Lb
    top_xy = blm.xy[blm.top_chain]
    spacing = np.hypot(*np.diff(top_xy, axis=0).T)
    lc_pt = np.concatenate([[spacing[0]], 0.5 * (spacing[1:] + spacing[:-1]), [spacing[-1]]])

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 1 if verbose else 0)
        gmsh.model.add("outer")
        g = gmsh.model.geo
        ptags = [g.addPoint(float(x), float(y), 0.0, float(h)) for (x, y), h in zip(top_xy, lc_pt)]
        top_lines = [g.addLine(a, b) for a, b in zip(ptags[:-1], ptags[1:])]
        far = sz["far"]
        p_in0 = g.addPoint(-Xu, 0, 0, far)
        p_in1 = g.addPoint(-Xu, H, 0, far)
        p_o1 = g.addPoint(Lb + Xd, H, 0, far)
        p_o0 = g.addPoint(Lb + Xd, 0, 0, far)
        c_ax1 = g.addLine(p_in0, ptags[0])
        c_ax2 = g.addLine(ptags[-1], p_o0)
        c_out = g.addLine(p_o0, p_o1)
        c_far = g.addLine(p_o1, p_in1)
        c_in = g.addLine(p_in1, p_in0)
        loop = g.addCurveLoop([c_ax1] + top_lines + [c_ax2, c_out, c_far, c_in])
        surf = g.addPlaneSurface([loop])
        for c in top_lines:
            g.mesh.setTransfiniteCurve(c, 2)
        g.synchronize()

        f = gmsh.model.mesh.field
        fields = []

        def thresh(ids, dim, smin, dmin, smax, dmax, sampling=200):
            d = f.add("Distance")
            f.setNumbers(d, "CurvesList" if dim == 1 else "PointsList", ids)
            if dim == 1:
                f.setNumber(d, "Sampling", sampling)
            t = f.add("Threshold")
            f.setNumber(t, "InField", d)
            for k, v in (("SizeMin", smin), ("SizeMax", smax), ("DistMin", dmin), ("DistMax", dmax)):
                f.setNumber(t, k, v)
            f.setNumber(t, "StopAtDistMax", 1)
            fields.append(t)

        thresh([ptags[0]], 0, sz["tip_region"], 0.006, sz["near_box"], 0.05)
        thresh(top_lines, 1, sz["body_wall"], 0.0, far, 2.5, sampling=4)
        for (x0, x1, y1, size) in (
            (-box["near_nose_up"], geo.L, box["near_nose_radial"], sz["near_box"]),
            (Lb, Lb + box["wake_length"], box["wake_radial"], sz["wake_box"]),
        ):
            b = f.add("Box")
            for k, v in (("VIn", size), ("VOut", far), ("XMin", x0), ("XMax", x1),
                         ("YMin", 0.0), ("YMax", y1), ("Thickness", 0.5 * y1)):
                f.setNumber(b, k, v)
            fields.append(b)
        fmin = f.add("Min")
        f.setNumbers(fmin, "FieldsList", fields)
        f.setAsBackgroundMesh(fmin)

        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 1)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 1)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.Algorithm", 6)
        gmsh.option.setNumber("Mesh.Smoothing", 5)
        gmsh.model.mesh.generate(2)

        ntags, coords, _ = gmsh.model.mesh.getNodes()
        oxy = coords.reshape(-1, 3)[:, :2]
        tag2local = {int(t): i for i, t in enumerate(ntags)}
        # BL üst düğümleri ile eşleme
        shared = {}
        for k, pt in enumerate(ptags):
            nt, _, _ = gmsh.model.mesh.getNodes(0, pt)
            shared[tag2local[int(nt[0])]] = blm.top_chain[k]
        _, enodes = gmsh.model.mesh.getElementsByType(2)
        tris = np.array([tag2local[int(t)] for t in enodes]).reshape(-1, 3)
        return oxy, tris, shared, (Xu, H, Lb + Xd)
    finally:
        gmsh.finalize()


# =========================================================================== kalite

def _quality_block(P: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """P: (n, k, 2) aynı tipteki hücreler -> alan, equiangle skewness, kenar oranı."""
    k = P.shape[1]
    nxt, prv = np.roll(P, -1, axis=1), np.roll(P, 1, axis=1)
    area = 0.5 * np.sum(P[..., 0] * nxt[..., 1] - P[..., 1] * nxt[..., 0], axis=1)
    u, v = prv - P, nxt - P
    cosv = np.sum(u * v, axis=2) / (np.linalg.norm(u, axis=2) * np.linalg.norm(v, axis=2))
    ang = np.degrees(np.arccos(np.clip(cosv, -1.0, 1.0)))
    ideal = 60.0 if k == 3 else 90.0
    skew = np.maximum((ang.max(axis=1) - ideal) / (180 - ideal), (ideal - ang.min(axis=1)) / ideal)
    e = np.linalg.norm(nxt - P, axis=2)
    return area, skew, e.max(axis=1) / e.min(axis=1)


def cell_quality(xy: np.ndarray, cells: list[np.ndarray]) -> dict:
    n = len(cells)
    areas, skews, ars = np.empty(n), np.empty(n), np.empty(n)
    for k in (3, 4):
        idx = np.array([i for i, c in enumerate(cells) if len(c) == k], dtype=np.int64)
        if len(idx):
            P = xy[np.array([cells[i] for i in idx])]
            areas[idx], skews[idx], ars[idx] = _quality_block(P)
    return {
        "n_negative_area": int((areas <= 0).sum()),
        "max_skewness": float(skews.max()),
        "p99_skewness": float(np.percentile(skews, 99)),
        "n_skew_gt_0p9": int((skews > 0.9).sum()),
        "max_aspect_ratio": float(ars.max()),
        "_skews": skews,
    }


# =========================================================================== ana fonksiyon

@dataclass
class MeshResult:
    geom_id: str
    path: Path | None
    n_nodes: int
    n_cells: int
    n_quads: int
    n_tris: int
    n_layers: int
    bl_ratio: float
    n_wall_nodes: int
    max_skewness: float
    p99_skewness: float
    n_negative_area: int
    max_aspect_ratio: float
    ok: bool
    message: str = ""


def build_mesh(geo: NoseGeometry, body_length: float, out_path: Path | None,
               settings: dict | None = None, preview_png: Path | None = None,
               verbose: bool = False) -> MeshResult:
    s = settings or load_mesh_settings()
    Lb = geo.L + body_length

    segs = build_wall_segments(geo, body_length, s)
    blm = build_bl(segs, s)
    oxy, otris, shared, (Xu, H, Xo) = mesh_outer(blm, geo, Lb, s, verbose)

    # Birleştirme: dış düğümlerden paylaşılanları BL düğümlerine eşle
    n_bl = len(blm.xy)
    remap = np.empty(len(oxy), dtype=np.int64)
    new_xy = []
    for i in range(len(oxy)):
        if i in shared:
            remap[i] = shared[i]
        else:
            remap[i] = n_bl + len(new_xy)
            new_xy.append(oxy[i])
    xy = np.vstack([blm.xy, np.array(new_xy)]) if new_xy else blm.xy
    cells = list(blm.cells) + [remap[t] for t in otris]

    # Tüm hücreleri CCW yap
    for i, c in enumerate(cells):
        p = xy[c]
        a = np.dot(p[:, 0], np.roll(p[:, 1], -1)) - np.dot(p[:, 1], np.roll(p[:, 0], -1))
        if a < 0:
            cells[i] = c[::-1].copy()

    q = cell_quality(xy, cells)
    tol = 1e-9
    wall = blm.wall_nodes

    def classify(a: int, b: int):
        if a in wall and b in wall:
            return "wall_rocket"
        (xa, ya), (xb, yb) = xy[a], xy[b]
        if abs(ya) < tol and abs(yb) < tol:
            return "axis"
        if abs(xa + Xu) < tol and abs(xb + Xu) < tol:
            return "inlet"
        if abs(xa - Xo) < tol and abs(xb - Xo) < tol:
            return "outlet"
        if abs(ya - H) < tol and abs(yb - H) < tol:
            return "farfield"
        return None

    interior, boundary = make_face_zones(cells, xy, classify)
    missing = [b for b in BOUNDARY_NAMES if b not in boundary]

    thr = s["quality"]
    problems = []
    if q["n_negative_area"]:
        problems.append(f"{q['n_negative_area']} ters/sıfır alanlı hücre")
    if q["max_skewness"] > thr["max_skewness"]:
        problems.append(f"max çarpıklık {q['max_skewness']:.3f} > {thr['max_skewness']}")
    if missing:
        problems.append(f"eksik sınır bölgeleri: {missing}")
    ok = not problems

    if preview_png is not None:
        _preview(xy, cells, q["_skews"], geo, Lb, preview_png)

    path = None
    if ok and out_path is not None:
        write_fluent_msh(out_path, xy, cells, interior, boundary, BC_TYPES,
                         comment=f"RocketCFD {geo.geom_id} L={geo.L} R={geo.R}")
        path = out_path

    n_tri = sum(1 for c in cells if len(c) == 3)
    return MeshResult(geo.geom_id, path, len(xy), len(cells), len(cells) - n_tri, n_tri,
                      blm.n_layers, blm.ratio, blm.n_wall_nodes, q["max_skewness"], q["p99_skewness"],
                      q["n_negative_area"], q["max_aspect_ratio"], ok, "; ".join(problems))


def _preview(xy, cells, skews, geo: NoseGeometry, Lb: float, png: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection

    polys = [xy[c] for c in cells]
    bx = np.array([[p[:, 0].min(), p[:, 0].max(), p[:, 1].min(), p[:, 1].max()] for p in polys])
    views = [
        ("Genel", (-0.3, Lb + 1.2), (0, 0.6)),
        ("Uç (6 mm)", (-0.004, 0.008), (0, 0.006)),
        ("Uç yakın", (-0.0003, 0.0015), (0, 0.0012)),
        ("Omuz", (geo.L - 0.015, geo.L + 0.015), (geo.R - 0.004, geo.R + 0.008)),
        ("Taban köşesi", (Lb - 0.008, Lb + 0.012), (geo.R - 0.008, geo.R + 0.008)),
        ("Taban-eksen", (Lb - 0.004, Lb + 0.012), (0, 0.008)),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    for ax, (title, xl, yl) in zip(axes.flat, views):
        sel = np.where((bx[:, 1] >= xl[0]) & (bx[:, 0] <= xl[1]) & (bx[:, 3] >= yl[0]) & (bx[:, 2] <= yl[1]))[0]
        pc = PolyCollection([polys[i] for i in sel], array=skews[sel], cmap="RdYlGn_r",
                            edgecolors="k", linewidths=0.2, clim=(0, 1))
        ax.add_collection(pc)
        ax.set_xlim(*xl); ax.set_ylim(*yl); ax.set_aspect("equal"); ax.set_title(title)
    fig.colorbar(pc, ax=axes, shrink=0.6, label="Equiangle skewness")
    fig.suptitle(f"{geo.geom_id} — {len(cells)} hücre")
    png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(png, dpi=110)
    plt.close(fig)
