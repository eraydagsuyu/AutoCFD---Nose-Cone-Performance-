"""Tek koşu: 1 mesh × 1 hız noktası, izlenen çözüm.

Kullanım:
  .venv\\Scripts\\python.exe src\\02_fluent_solver.py --geom P16_L300 --vel 5 [--set courant_end=5 --set max_iters=3000]

--vel: Vt_graph.txt'deki hız noktası indeksi (1..20).
Çıktılar: logs\\runs\\<geom>_v<NN>\\<YYYYmmdd-HHMMSS>\\ {meta.json, cd.out, history.csv, result.json, fluent.trn}
Orkestratör aynı modülü (run_single) çağırır; bu betik tekli test ve denetçi incelemesi içindir.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.atmosphere import freestream  # noqa: E402
from common.config import LOG_DIR, MESH_DIR, load_machine_config, load_nose_params, load_velocities  # noqa: E402
from common.fluent_case import read_reference_values, run_attempt, set_freestream, setup_physics  # noqa: E402
from common.fluent_session import fluent_solver  # noqa: E402
from common.solver_profile import load_physics, profile_hash, resolve_profile  # noqa: E402

log = logging.getLogger("solver")


def geo_meta(gid: str) -> dict:
    npar = load_nose_params()
    L = int(gid.split("_L")[1]) / 1000.0
    return {"geom_id": gid, "R": npar["fixed"]["R"], "L": L, "body_length": npar["fixed"]["body_length"]}


def parse_sets(items: list[str]) -> dict:
    out = {}
    for s in items or []:
        k, _, v = s.partition("=")
        out[k.strip()] = v.strip()
    return out


def run_single(gid: str, vel_idx: int, overrides: dict, cores: int | None = None) -> dict:
    cfg = load_machine_config()
    phys = load_physics()
    pt = next(p for p in load_velocities() if p["index"] == vel_idx)
    fs = freestream(pt["velocity_ms"], pt["altitude_m"], phys)
    prof, regime = resolve_profile(fs.mach, overrides)
    meta = geo_meta(gid)
    msh = MESH_DIR / f"{gid}.msh.gz"
    workdir = LOG_DIR / "runs" / f"{gid}_v{vel_idx:02d}" / time.strftime("%Y%m%d-%H%M%S")
    workdir.mkdir(parents=True, exist_ok=True)

    log.info("%s v%02d: V=%.1f m/s M=%.3f h=%.0f m  rejim=%s  profil=%s",
             gid, vel_idx, fs.velocity, fs.mach, fs.altitude, regime, profile_hash(prof))
    with fluent_solver(cfg, cwd=workdir, processor_count=cores) as solver:
        solver.tui.file.start_transcript(str(workdir / "fluent.trn"))
        setup_physics(solver, msh, meta, phys, workdir)
        set_freestream(solver, fs, meta, phys)
        ref = read_reference_values(solver)
        (workdir / "meta.json").write_text(json.dumps({
            "geom_id": gid, "vel_idx": vel_idx, "freestream": fs.as_dict(), "profile": prof,
            "profile_hash": profile_hash(prof), "overrides": overrides, "reference_values": ref,
            "mesh": str(msh), "machine": cfg.get("machine_name"),
        }, indent=2, default=str), encoding="utf-8")
        res = run_attempt(solver, prof, workdir, fresh_init=True)
        solver.tui.file.stop_transcript()
    log.info("%s v%02d: %s  Cd=%s  it=%d  %.0fs  %s", gid, vel_idx, res.outcome,
             f"{res.cd:.5f}" if res.cd is not None else "-", res.iterations, res.elapsed_s, res.message)
    return {"workdir": str(workdir), **res.as_dict()}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--geom", required=True)
    ap.add_argument("--vel", type=int, required=True, help="Hız noktası indeksi 1..20")
    ap.add_argument("--set", action="append", default=[], help="Sayısal override: anahtar=değer")
    ap.add_argument("--cores", type=int, default=None)
    args = ap.parse_args()
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(LOG_DIR / "solver.log", encoding="utf-8"),
                                  logging.StreamHandler(sys.stdout)])
    logging.getLogger("ansys").setLevel(logging.WARNING)
    out = run_single(args.geom.upper(), args.vel, parse_sets(args.set), args.cores)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out["outcome"] in ("done", "done_flagged") else 1


if __name__ == "__main__":
    sys.exit(main())
