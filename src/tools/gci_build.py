"""Mesh bağımsızlığı (GCI) çalışması: 3 geometri × 3 ağ seviyesi -> 'gci' kampanyası (kullanıcı onaylı, 2026-11-27).

Seviyeler (r = 1,5): g1 ince (boyut × 1/r), g2 orta (= ana analizin ayarları), g3 kaba (boyut × r).
Ölçeklenen: tüm `sizes`, BL ilk yüksekliği, BL büyüme oranı (gr**f), teğetsel büyüme eğimi, fan sektörü. Domain, BL kalınlığı,
geometri ve fizik DEĞİŞMEZ. Ana analizin mesh'lerine dokunulmaz (çıktı meshes/gci/).

Kullanım:
  .venv\\Scripts\\python.exe src\\tools\\gci_build.py --build      # 9 mesh (meshes/gci/<geom>_g<n>.msh.gz) + docs/gci/gci_meshes.csv
  .venv\\Scripts\\python.exe src\\tools\\gci_build.py --register   # 36 koşuyu 'gci' kampanyasına kaydeder (Ankara DB'sinde)
Çözüm:  scripts\\start_batch.ps1 -Campaign gci -Workers 1
Rapor:  src\\tools\\gci_report.py
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # src/

from common import db  # noqa: E402
from common.atmosphere import freestream  # noqa: E402
from common.config import DOCS_DIR, MESH_DIR, load_nose_params, load_velocities  # noqa: E402
from common.geometry import build_geometry, free_params_for, load_profile_defs  # noqa: E402
from common.mesher import build_mesh, load_mesh_settings  # noqa: E402
from common.solver_profile import load_physics, regime_for  # noqa: E402

CAMPAIGN = "gci"
GEOMS = ["P01_L300", "P16_L300", "P04_L300"]       # konik (sivri), Haack (yumuşak), meplatlı (küt köşe)
RATIO = 1.5
LEVELS = {1: 1.0 / RATIO, 2: 1.0, 3: RATIO}       # boyut çarpanı f
VELS = [5, 10, 15, 19]                            # ön optimizasyonla aynı temsili hızlar
OUT_DIR = MESH_DIR / CAMPAIGN


def scaled_settings(f: float) -> dict:
    s = copy.deepcopy(load_mesh_settings())
    for k in s["sizes"]:
        s["sizes"][k] *= f
    bl = s["boundary_layer"]
    bl["first_height"] *= f
    bl["growth_ratio"] = bl["growth_ratio"] ** f
    s["tangential_growth"] = 1.0 + (s["tangential_growth"] - 1.0) * f
    s["fan"]["max_sector_deg"] *= f
    return s


def cmd_build() -> None:
    npar, defs = load_nose_params(), load_profile_defs()
    R = npar["fixed"]["R"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for gid in GEOMS:
        pid, L = gid[1:3], int(gid[-3:]) / 1000.0
        free = free_params_for(pid, L, npar)
        for lvl, f in LEVELS.items():
            geo = build_geometry(defs[pid], L, R, free, npar["mesh_tip_blunting"]["rn_mesh"])
            if not geo.checks["ok"]:
                raise SystemExit(f"{gid}: geometri doğrulaması başarısız {geo.checks}")
            out = OUT_DIR / f"{gid}_g{lvl}.msh.gz"
            res = build_mesh(geo, npar["fixed"]["body_length"], out, settings=scaled_settings(f))
            rows.append({"geom_id": f"{gid}_g{lvl}", "base": gid, "level": lvl, "size_factor": round(f, 4), "free": json.dumps(free),
                         "ok": res.ok, "n_cells": res.n_cells, "max_skewness": round(res.max_skewness, 3), "message": res.message})
            print(f"{gid}_g{lvl}: f={f:.3f} hücre={res.n_cells} maxSkew={res.max_skewness:.3f} {'OK' if res.ok else res.message}",
                  flush=True)
    (DOCS_DIR / "gci").mkdir(parents=True, exist_ok=True)
    with open(DOCS_DIR / "gci" / "gci_meshes.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    bad = [r for r in rows if not r["ok"]]
    print(f"{len(rows) - len(bad)}/{len(rows)} mesh OK. Sonraki: src\\tools\\check_mesh_fluent.py --all --dir meshes\\gci "
          f"--report fluent_mesh_check_gci.csv")
    if bad:
        raise SystemExit(1)


def cmd_register() -> None:
    ids = [f"{g}_g{l}" for g in GEOMS for l in LEVELS]
    missing = [i for i in ids if not (OUT_DIR / f"{i}.msh.gz").exists()]
    if missing:
        raise SystemExit(f"Mesh yok: {missing}")
    phys = load_physics()
    pts = []
    for p in load_velocities():
        if p["index"] in VELS:
            m = freestream(p["velocity_ms"], p["altitude_m"], phys).mach
            pts.append({**p, "mach": m, "regime": regime_for(m)})
    with db.connect() as con:
        n = db.ensure_runs(con, CAMPAIGN, ids, pts, mesh_version="gci")
        db.event(con, "INFO", "queue", f"{n} GCI koşusu kuyruğa eklendi")
    print(f"{n} koşu '{CAMPAIGN}' kampanyasına eklendi ({len(ids)} mesh × {len(pts)} hız).")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--build", action="store_true")
    g.add_argument("--register", action="store_true")
    a = ap.parse_args()
    cmd_build() if a.build else cmd_register()
    return 0


if __name__ == "__main__":
    sys.exit(main())
