"""Çözücü profili: base + rejim + koşuya özel override birleşimi ve fizik kilidi.

Override yalnızca ALLOWED_OVERRIDES anahtarlarında yapılabilir. Fizik ayarları config/physics.json'dadır
ve hiçbir yoldan override edilemez (80 geometrinin Cd'leri karşılaştırılabilir kalmalı).
"""
from __future__ import annotations

import hashlib
import json

from .config import CONFIG_DIR

PROFILE_DIR = CONFIG_DIR / "solver_profiles"
REGIMES = ("subsonic", "transonic", "supersonic")

# Sayısal izin listesi: anahtar -> (tip, alt sınır, üst sınır | izinli değerler)
ALLOWED_OVERRIDES: dict[str, tuple] = {
    "solver_type": (str, ("density-based-implicit", "pressure-based")),
    "flux_type": (str, ("Roe-FDS", "AUSM")),
    "init_method": (str, ("hybrid", "fmg", "previous", "last_good")),
    "first_order_iters": (int, 0, 5000),
    "courant_start": (float, 0.05, 50.0),
    "courant_end": (float, 0.05, 200.0),
    "courant_ramp_iters": (int, 0, 10000),
    "min_iters": (int, 100, 50000),
    "max_iters": (int, 200, 50000),
    "check_interval": (int, 10, 500),
    "checkpoint_interval": (int, 50, 5000),
    "conv_window": (int, 50, 5000),
    "conv_cd_rel_std": (float, 1e-6, 1e-2),
    "conv_cd_rel_drift": (float, 1e-6, 1e-2),
    "osc_accept_rel_amp": (float, 1e-4, 0.02),
    "div_residual_growth_orders": (float, 1.0, 6.0),
    "stall_check_iters": (int, 200, 20000),
    "timeout_s": (int, 300, 86400),
}


class OverrideError(ValueError):
    pass


def _read(name: str) -> dict:
    return json.loads((PROFILE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def load_physics() -> dict:
    return json.loads((CONFIG_DIR / "physics.json").read_text(encoding="utf-8"))


def regime_for(mach: float) -> str:
    for r in REGIMES:
        p = _read(r)
        if p["mach_min"] <= mach < p["mach_max"]:
            return r
    raise ValueError(f"Mach {mach} için rejim profili yok")


def validate_overrides(overrides: dict) -> dict:
    out = {}
    for k, v in (overrides or {}).items():
        if k not in ALLOWED_OVERRIDES:
            raise OverrideError(f"'{k}' override edilemez (fizik kilidi veya bilinmeyen anahtar). "
                                f"İzinli: {sorted(ALLOWED_OVERRIDES)}")
        spec = ALLOWED_OVERRIDES[k]
        typ = spec[0]
        try:
            v = typ(v)
        except (TypeError, ValueError) as exc:
            raise OverrideError(f"'{k}' için geçersiz tip: {v!r}") from exc
        if typ is str:
            if v not in spec[1]:
                raise OverrideError(f"'{k}' = {v!r} izinli değil: {spec[1]}")
        elif not (spec[1] <= v <= spec[2]):
            raise OverrideError(f"'{k}' = {v} aralık dışı [{spec[1]}, {spec[2]}]")
        out[k] = v
    return out


def resolve_profile(mach: float, overrides: dict | None = None) -> tuple[dict, str]:
    """(birleşik profil, regime). Profilde 'note', 'mach_min', 'mach_max' meta anahtarları atılır."""
    regime = regime_for(mach)
    prof = {k: v for k, v in _read("base").items() if k != "note"}
    prof.update({k: v for k, v in _read(regime).items() if k not in ("note", "mach_min", "mach_max")})
    prof.update(validate_overrides(overrides or {}))
    prof["regime"] = regime
    if prof["min_iters"] > prof["max_iters"]:
        raise OverrideError("min_iters > max_iters")
    return prof, regime


def profile_hash(prof: dict) -> str:
    return hashlib.sha1(json.dumps(prof, sort_keys=True).encode()).hexdigest()[:10]
