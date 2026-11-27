"""Duvar y⁺ kontrolü: kaydedilmiş akış alanlarından (data/fields/<geom>/vNN.dat.h5) wall_rocket üzerinde y⁺ istatistiği.

y⁺ en büyük hızda (v20, M 1,26) en yüksektir; k-ω SST duvar fonksiyonsuz (low-Re) çözüm için hedef y⁺ ≲ 1 (en fazla ~5).
Her geometri AYRI Fluent oturumunda okunur (tek oturumda ikinci case okuması güvenilir değil — check_mesh_fluent dersi).

Kullanım:
  .venv\\Scripts\\python.exe src\\tools\\yplus_check.py --fields data\\ankara_20261127\\fields [--vel 20] [--geoms P01_L200 ...]
Çıktı: docs/mesh/yplus.csv (geom, vel, alan-ağırlıklı ort., max, burun/gövde ayrımı yok)
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # src/

from common.atmosphere import freestream  # noqa: E402
from common.config import DOCS_DIR, LOG_DIR, MESH_DIR, load_machine_config, load_velocities  # noqa: E402
from common.fluent_case import set_freestream, setup_physics  # noqa: E402
from common.fluent_session import fluent_solver  # noqa: E402
from common.solver_profile import load_physics  # noqa: E402

_spec = importlib.util.spec_from_file_location("orch", Path(__file__).resolve().parents[1] / "03_orchestrator.py")
_orch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_orch)
geo_meta = _orch.geo_meta

NUM = r"([0-9.]+(?:e[+-]?\d+)?)"


def yplus_one(gid: str, dat: Path, vel: int, phys: dict, work: Path) -> dict:
    v = next(p for p in load_velocities() if p["index"] == vel)
    fs = freestream(v["velocity_ms"], v["altitude_m"], phys)
    meta = geo_meta(gid)
    trn = work / f"{gid}_v{vel:02d}.trn"
    trn.unlink(missing_ok=True)
    with fluent_solver(load_machine_config(), cwd=work, processor_count=2) as s:
        setup_physics(s, MESH_DIR / f"{gid}.msh.gz", meta, phys, work)
        set_freestream(s, fs, meta, phys)
        s.settings.file.read_data(file_name=str(dat.resolve()))
        s.tui.file.start_transcript(str(trn))
        for kind in ("area-weighted-avg", "facet-max", "facet-min"):
            s.tui.report.surface_integrals.__getattribute__(kind.replace("-", "_"))("wall_rocket", "()", "y-plus", "no")
        s.tui.file.stop_transcript()
    text = trn.read_text(encoding="utf-8", errors="replace")
    vals = re.findall(r"(?mi)^\s*wall_rocket\s+" + NUM, text)
    out = {"geom_id": gid, "vel_idx": vel, "mach": round(fs.mach, 3)}
    for k, x in zip(("yplus_avg", "yplus_max", "yplus_min"), vals[:3]):
        out[k] = float(x)
    out["parsed"] = len(vals) >= 3
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--fields", required=True)
    ap.add_argument("--vel", type=int, default=20)
    ap.add_argument("--geoms", nargs="*")
    a = ap.parse_args()
    root = Path(a.fields)
    geoms = a.geoms or sorted(d.name for d in root.iterdir() if re.fullmatch(r"P\d\d_L\d{3}", d.name)
                              and (d / f"v{a.vel:02d}.dat.h5").exists())
    phys = load_physics()
    work = LOG_DIR / "yplus"
    work.mkdir(parents=True, exist_ok=True)
    out = DOCS_DIR / "mesh" / "yplus.csv"
    rows = []
    for i, gid in enumerate(geoms, 1):
        try:
            r = yplus_one(gid, root / gid / f"v{a.vel:02d}.dat.h5", a.vel, phys, work)
        except Exception as exc:  # noqa: BLE001
            r = {"geom_id": gid, "vel_idx": a.vel, "parsed": False, "error": str(exc)[:200]}
        rows.append(r)
        print(f"[{i}/{len(geoms)}] {r}", flush=True)
        keys = sorted({k for x in rows for k in x}, key=lambda k: ["geom_id", "vel_idx", "mach", "yplus_avg", "yplus_max",
                                                                     "yplus_min", "parsed", "error"].index(k))
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
