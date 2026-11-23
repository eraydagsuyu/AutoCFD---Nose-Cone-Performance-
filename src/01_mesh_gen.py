"""Burun konisi geometrilerinden Fluent .msh üretimi.

Kullanım:
  .venv\\Scripts\\python.exe src\\01_mesh_gen.py --geom P16_L300 [--preview]
  .venv\\Scripts\\python.exe src\\01_mesh_gen.py --all [--preview] [--skip-existing]

Çıktılar:
  meshes\\<geom_id>.msh.gz          Fluent ASCII mesh, gzip (kalite kapısını geçenler; Git'te tutulur)
  docs\\mesh\\preview_<id>.png       (--preview) yakın görünüm + çarpıklık renkleri
  docs\\mesh\\mesh_report.csv        her koşuda güncellenen özet tablo
  logs\\mesh_gen.log
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.config import DOCS_DIR, LOG_DIR, MESH_DIR, load_nose_params  # noqa: E402
from common.geometry import build_geometry, free_params_for, load_profile_defs  # noqa: E402
from common.mesher import build_mesh  # noqa: E402

log = logging.getLogger("mesh_gen")
REPORT = DOCS_DIR / "mesh" / "mesh_report.csv"


def all_geom_ids(npar: dict) -> list[str]:
    ids = []
    for L in npar["fixed"]["L_values"]:
        for pid in sorted(load_profile_defs()):
            ids.append(f"P{pid}_L{round(L * 1000):03d}")
    return ids


def parse_geom_id(gid: str) -> tuple[str, float]:
    p, l = gid.upper().split("_")
    return p[1:], int(l[1:]) / 1000.0


def mesh_one(gid: str, npar: dict, defs: dict, preview: bool) -> dict:
    pid, L = parse_geom_id(gid)
    R = npar["fixed"]["R"]
    geo = build_geometry(defs[pid], L, R, free_params_for(pid, L, npar),
                         npar["mesh_tip_blunting"]["rn_mesh"])
    if not geo.checks["ok"]:
        raise ValueError(f"Geometri doğrulaması başarısız: {geo.checks}")
    t0 = time.time()
    res = build_mesh(geo, npar["fixed"]["body_length"], MESH_DIR / f"{gid}.msh.gz",
                     preview_png=(DOCS_DIR / "mesh" / f"preview_{gid}.png") if preview else None)
    row = asdict(res)
    row["path"] = str(res.path) if res.path else ""
    row["tip_kind"] = geo.tip.kind
    row["blunted_1mm"] = geo.arc is not None
    row["elapsed_s"] = round(time.time() - t0, 1)
    return row


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--geom", nargs="+", help="Geometri ID(leri), ör. P16_L300")
    g.add_argument("--all", action="store_true", help="80 geometrinin tümü")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--skip-existing", action="store_true")
    args = ap.parse_args()

    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(LOG_DIR / "mesh_gen.log", encoding="utf-8"),
                                  logging.StreamHandler(sys.stdout)])
    npar = load_nose_params()
    defs = load_profile_defs()
    ids = all_geom_ids(npar) if args.all else [x.upper() for x in args.geom]

    old = pd.read_csv(REPORT) if REPORT.exists() else pd.DataFrame()
    rows = []
    for i, gid in enumerate(ids, 1):
        if args.skip_existing and (MESH_DIR / f"{gid}.msh.gz").exists():
            log.info("[%d/%d] %s atlandı (mevcut)", i, len(ids), gid)
            continue
        try:
            row = mesh_one(gid, npar, defs, args.preview)
            lvl = logging.INFO if row["ok"] else logging.ERROR
            log.log(lvl, "[%d/%d] %s  hücre=%d  maxSkew=%.3f  %.1fs  %s", i, len(ids), gid,
                    row["n_cells"], row["max_skewness"], row["elapsed_s"],
                    "OK" if row["ok"] else "mesh_error: " + row["message"])
        except Exception as exc:  # noqa: BLE001 — tek geometri hatası tüm koşuyu durdurmaz
            log.exception("[%d/%d] %s HATA: %s", i, len(ids), gid, exc)
            row = {"geom_id": gid, "ok": False, "message": f"{type(exc).__name__}: {exc}"}
        rows.append(row)

    new = pd.DataFrame(rows)
    if not old.empty and not new.empty:
        old = old[~old["geom_id"].isin(new["geom_id"])]
    rep = pd.concat([old, new], ignore_index=True).sort_values("geom_id")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    rep.to_csv(REPORT, index=False)
    n_bad = int((~new["ok"].astype(bool)).sum()) if not new.empty else 0
    log.info("Bitti: %d mesh, %d hatalı. Rapor: %s", len(new), n_bad, REPORT)
    return 0 if n_bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
