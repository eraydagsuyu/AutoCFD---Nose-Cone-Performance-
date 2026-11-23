"""Burun konisi profil geometrisi.

Akış:
  1) inputs/nose_cones/NN_*.txt içindeki MATLAB denklemi NumPy ifadesine çevrilir (kısıtlı isim alanı).
  2) Türetilen parametreler (rho, th, xtc/x0c, xto/x0o) "keskin" uzunluk L' ile hesaplanır.
  3) Uç tipi sayısal olarak sınıflandırılır (yerel üs y ~ c·x^p):
       p ≈ 1           -> sivri tepe (sharp)            -> 1 mm mesh radyusu
       0.5 < p < 1     -> sıfır eğrilik yarıçaplı uç     -> 1 mm mesh radyusu
       p ≈ 0.5         -> küt uç, Rc = c²/2              -> Rc < rn_mesh ise 1 mm radyus
       y(0) > 0        -> düz meplat yüzeyi               -> radyus yok
  4) Gerekirse profile teğet, merkezi eksende olan rn_mesh yarıçaplı yay eklenir.
  5) Toplam burun uzunluğu tam L olacak şekilde L' iteratif ayarlanır (L' − x_tip(L') = L).

Koordinatlar: uç x = 0, omuz x = L, eksen y = 0. Birimler: metre.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

from .config import NOSE_DIR, load_nose_params

# --------------------------------------------------------------------------- denklem çevirisi

_SAFE_FUNCS = {
    "sqrt": None,  # aşağıda _safe_sqrt ile doldurulur
    "max": np.maximum,
    "min": np.minimum,
    "cos": np.cos,
    "sin": np.sin,
    "tan": np.tan,
    "acos": np.arccos,
    "asin": np.arcsin,
    "atan": np.arctan,
    "exp": np.exp,
    "log": np.log,
    "abs": np.abs,
    "pi": math.pi,
}


def _safe_sqrt(v):
    """Yuvarlama kaynaklı çok küçük negatifleri 0'a çeker; gerçek negatifler NaN üretir (doğrulamada yakalanır)."""
    v = np.asarray(v, dtype=float)
    v = np.where((v < 0) & (v > -1e-14), 0.0, v)
    with np.errstate(invalid="ignore"):
        return np.sqrt(v)


_SAFE_FUNCS["sqrt"] = _safe_sqrt


def matlab_to_numpy(expr: str) -> str:
    expr = expr.strip().rstrip(";")
    if expr.startswith("y ="):
        expr = expr[3:].strip()
    expr = expr.replace(".*", "*").replace("./", "/").replace(".^", "**").replace("^", "**")
    if re.search(r"[;\[\]{}@'\"]|__|import|lambda", expr):
        raise ValueError(f"Denklemde izin verilmeyen ifade: {expr!r}")
    return expr


@dataclass
class ProfileDef:
    pid: str
    name: str
    file: str
    expr: str
    code: object
    params: list[str]


def load_profile_defs(nose_dir: Path = NOSE_DIR) -> dict[str, ProfileDef]:
    defs = {}
    for path in sorted(nose_dir.glob("[0-9][0-9]_*.txt")):
        meta, eq = {}, None
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#") and ":" in line:
                k, v = line[1:].split(":", 1)
                meta[k.strip()] = v.strip()
            elif line.strip().startswith("y ="):
                eq = line.strip()
        expr = matlab_to_numpy(eq)
        pid = meta["id"]
        defs[pid] = ProfileDef(
            pid=pid, name=meta["name"], file=path.name, expr=expr,
            code=compile(expr, path.name, "eval"),
            params=[p.strip() for p in meta.get("params", "").split(",") if p.strip()],
        )
    if len(defs) != 20:
        raise ValueError(f"20 profil bekleniyordu, {len(defs)} bulundu ({nose_dir})")
    return defs


# --------------------------------------------------------------------------- türetilen parametreler

def derived_params(pid: str, R: float, Ls: float, free: dict) -> dict:
    """Keskin uzunluk Ls (= L') için denklemin ihtiyaç duyduğu tüm parametreler."""
    p = {"R": R, "L": Ls}
    rho = (R**2 + Ls**2) / (2 * R)
    p["rho"] = rho
    if pid == "02":
        rn = free["rn"]
        xt = Ls**2 / R * math.sqrt(rn**2 / (R**2 + Ls**2))
        yt = xt * R / Ls
        x0 = xt + math.sqrt(rn**2 - yt**2)
        p.update(rn=rn, xtc=xt, x0c=x0, _x_tip=x0 - rn)
    elif pid == "08":
        rn = free["rn"]
        x0 = Ls - math.sqrt((rho - rn) ** 2 - (rho - R) ** 2)
        yt = rn * (rho - R) / (rho - rn)
        xt = x0 - math.sqrt(rn**2 - yt**2)
        p.update(rn=rn, xto=xt, x0o=x0, _x_tip=x0 - rn)
    elif pid == "03":
        p.update(L1=free["L1_over_L"] * Ls, R1=free["R1_over_R"] * R)
    elif pid == "04":
        p.update(Rt=free["Rt_over_R"] * R)
    elif pid == "19":
        p.update(a=free["a_over_L"] * Ls)
    return p


def make_func(pdef: ProfileDef, params: dict):
    ns = dict(_SAFE_FUNCS)
    ns.update({k: v for k, v in params.items() if not k.startswith("_")})
    Ls = params["L"]

    def f(x):
        x = np.asarray(x, dtype=float)
        local = dict(ns)
        local["x"] = x
        local["th"] = np.arccos(np.clip(1.0 - 2.0 * x / Ls, -1.0, 1.0))
        y = eval(pdef.code, {"__builtins__": {}}, local)  # noqa: S307 — kısıtlı isim alanı
        return np.broadcast_to(np.asarray(y, dtype=float), x.shape).copy()

    return f


# --------------------------------------------------------------------------- uç sınıflandırma

@dataclass
class TipInfo:
    kind: str            # sharp | zero_radius | blunt | flat
    exponent: float      # yerel üs p (y ~ c x^p)
    radius: float        # uç eğrilik yarıçapı (blunt için), diğerlerinde 0 veya nan
    needs_blunting: bool


def classify_tip(f, x_tip: float, Ls: float, rn_mesh: float) -> TipInfo:
    y0 = float(f(np.array([x_tip]))[0])
    # Eşik fiziksel: en küçük gerçek meplat 2,45 mm; küresel körleştirmenin başlangıcındaki yuvarlama
    # kalıntısı (~1e-10 m) meplat sanılmamalı (P08_L200_c04 hatası).
    if y0 > 1e-5 * Ls:
        return TipInfo("flat", 0.0, math.nan, False)
    d1, d2 = 1e-8 * Ls, 1e-6 * Ls
    y1, y2 = f(np.array([x_tip + d1, x_tip + d2]))
    p = math.log(y2 / y1) / math.log(d2 / d1)
    if p > 0.97:
        return TipInfo("sharp", p, 0.0, True)
    if abs(p - 0.5) < 0.03:
        c = y2 / math.sqrt(d2)
        Rc = c**2 / 2.0
        return TipInfo("blunt", p, Rc, Rc < rn_mesh)
    return TipInfo("zero_radius", p, 0.0, True)


# --------------------------------------------------------------------------- uç yuvarlatma

@dataclass
class BluntArc:
    xc: float   # merkez (keskin koordinatlarda)
    rn: float
    xt: float   # teğet noktası x
    yt: float


def _deriv(f, x, h):
    return float((f(np.array([x + h]))[0] - f(np.array([x - h]))[0]) / (2 * h))


def fit_blunting_arc(f, Ls: float, rn: float) -> BluntArc:
    """Merkezi eksende, profile teğet rn yarıçaplı çember: f(x)·sqrt(1+f'(x)²) = rn."""

    def g(x):
        y = float(f(np.array([x]))[0])
        return y * math.sqrt(1.0 + _deriv(f, x, 1e-5 * x) ** 2) - rn

    lo, hi = 1e-7 * Ls, 1e-4 * Ls
    while g(hi) < 0:
        hi *= 2
        if hi > 0.5 * Ls:
            raise RuntimeError("Uç yuvarlatma için teğet nokta bulunamadı")
    xt = brentq(g, lo, hi, xtol=1e-14, rtol=1e-12)
    yt = float(f(np.array([xt]))[0])
    fp = _deriv(f, xt, 1e-5 * xt)
    xc = xt + yt * fp
    return BluntArc(xc=xc, rn=rn, xt=xt, yt=yt)


# --------------------------------------------------------------------------- tam geometri

@dataclass
class NoseGeometry:
    pid: str
    name: str
    L: float
    R: float
    L_sharp: float
    params: dict
    tip: TipInfo
    arc: BluntArc | None
    x: np.ndarray          # uç x=0 ... omuz x=L
    y: np.ndarray
    n_arc_pts: int         # x/y dizisinin başındaki yay noktası sayısı (0 = yay yok)
    kink_idx: list[int] = field(default_factory=list)   # eğim süreksizliği olan nokta indeksleri (ör. 03'te L1)
    checks: dict = field(default_factory=dict)
    id_override: str | None = None      # ön optimizasyon adayları için (ör. P03_L300_c04)

    @property
    def geom_id(self) -> str:
        return self.id_override or f"P{self.pid}_L{round(self.L * 1000):03d}"


def _cluster(a: float, b: float, n: int) -> np.ndarray:
    s = np.linspace(0.0, 1.0, n)
    return a + (b - a) * (1.0 - np.cos(0.5 * math.pi * s))   # a yakınında sık


def build_geometry(pdef: ProfileDef, L: float, R: float, free: dict, rn_mesh: float,
                   n_curve: int = 400, n_arc: int = 40) -> NoseGeometry:
    Ls = L
    for _ in range(30):
        params = derived_params(pdef.pid, R, Ls, free)
        f = make_func(pdef, params)
        x_tip = params.get("_x_tip", 0.0)
        tip = classify_tip(f, x_tip, Ls, rn_mesh)
        arc = fit_blunting_arc(f, Ls, rn_mesh) if tip.needs_blunting else None
        x_start = (arc.xc - arc.rn) if arc else x_tip
        new_Ls = L + x_start
        if abs(new_Ls - Ls) < 1e-10:   # 0,1 nm
            break
        Ls = new_Ls
    else:
        raise RuntimeError(f"{pdef.pid}: L' iterasyonu yakınsamadı")

    kinks_sharp = [params["L1"]] if pdef.pid == "03" else []

    def with_kinks(xa: np.ndarray) -> np.ndarray:
        """Kırık noktalarını örnek dizisine tam olarak ekler (spline'ın köşeyi yuvarlamaması için)."""
        for k in kinks_sharp:
            if xa[0] < k < xa[-1]:
                xa = np.unique(np.append(xa, k))
        return xa

    xs, ys = [], []
    if arc:
        th_t = math.atan2(arc.yt, arc.xt - arc.xc)          # teğet noktasının açısı
        ang = np.linspace(math.pi, th_t, n_arc)
        xs.append(arc.xc + arc.rn * np.cos(ang))
        ys.append(arc.rn * np.sin(ang))
        xc_ = with_kinks(_cluster(arc.xt, Ls, n_curve)[1:])
        xs.append(xc_)
        ys.append(f(xc_))
        n_arc_pts = n_arc
    elif tip.kind == "flat":
        xc_ = with_kinks(_cluster(x_tip, Ls, n_curve))
        xs.append(np.array([x_tip]))
        ys.append(np.array([0.0]))
        xs.append(xc_)
        ys.append(f(xc_))
        n_arc_pts = 0
    else:
        xc_ = with_kinks(_cluster(x_tip, Ls, n_curve))
        yv = f(xc_)
        yv[0] = 0.0
        xs.append(xc_)
        ys.append(yv)
        n_arc_pts = 0

    x = np.concatenate(xs) - x_start
    y = np.concatenate(ys)
    kink_idx = [int(np.argmin(np.abs(x - (k - x_start)))) for k in kinks_sharp]
    geo = NoseGeometry(pdef.pid, pdef.name, L, R, Ls, params, tip, arc, x, y, n_arc_pts, kink_idx)
    geo.checks = validate(geo, f)
    return geo


def validate(geo: NoseGeometry, f) -> dict:
    x, y, L, R = geo.x, geo.y, geo.L, geo.R
    c = {
        "finite": bool(np.all(np.isfinite(y))),
        "nonneg": bool(np.all(y >= -1e-12)),
        "length_err_m": float(abs(x[-1] - L)),
        "tip_at_zero": bool(abs(x[0]) < 1e-12),
        "shoulder_err_m": float(abs(y[-1] - R)),
        "y_max_m": float(np.nanmax(y)),
        "exceeds_R": bool(np.nanmax(y) > R * (1 + 1e-9)),
        "x_monotonic": bool(np.all(np.diff(x) >= -1e-15)),
    }
    if geo.arc:
        a = geo.arc
        fp = _deriv(f, a.xt, 1e-5 * a.xt)
        arc_slope = -(a.xt - a.xc) / a.yt
        c["arc_tangency_err_deg"] = float(abs(math.degrees(math.atan(fp) - math.atan(arc_slope))))
    c["ok"] = (c["finite"] and c["nonneg"] and c["length_err_m"] < 1e-9 and c["tip_at_zero"]
               and c["shoulder_err_m"] < 1e-6 and c["x_monotonic"]
               and c.get("arc_tangency_err_deg", 0.0) < 0.05)
    return c


# --------------------------------------------------------------------------- toplu üretim

def free_params_for(pid: str, L: float, nose_params: dict) -> dict:
    """Seçilmiş (preopt) değer varsa onu, yoksa geçici (provisional) değeri döndürür."""
    fp = nose_params["free_params"].get(pid)
    if not fp:
        return {}
    sel = fp.get("selected", {}).get(f"L{round(L * 1000):03d}")
    if sel:
        out = dict(sel)
    else:
        out = dict(fp["provisional"])
    if "rn_over_R" in out:
        out["rn"] = out.pop("rn_over_R") * nose_params["fixed"]["R"]
    return out


def build_all(nose_params: dict | None = None) -> list[NoseGeometry]:
    nose_params = nose_params or load_nose_params()
    R = nose_params["fixed"]["R"]
    rn_mesh = nose_params["mesh_tip_blunting"]["rn_mesh"]
    defs = load_profile_defs()
    out = []
    for L in nose_params["fixed"]["L_values"]:
        for pid, pdef in defs.items():
            out.append(build_geometry(pdef, L, R, free_params_for(pid, L, nose_params), rn_mesh))
    return out
