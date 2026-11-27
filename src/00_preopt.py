"""Ön optimizasyon: serbest parametreli profiller (02/08 rn, 03 L1/R1, 04 Rt, 19 a) için aday taraması.

Akış:
  1) --plan    aday listesini ve koşu sayısını yazdırır (Fluent yok)
  2) --build   aday geometrileri + mesh'leri üretir (meshes/preopt/), docs/preopt/candidates.json yazar,
               koşuları 'preopt' kampanyasına kaydeder (temsili hızlar)
  3) çözüm     src/03_orchestrator.py --mode batch --campaign preopt   (Ankara veya kullanıcı onayıyla İstanbul)
  3b) --stage2 <spec.json>   ikinci aşama (ince tarama) adayları: kimlik P02_L200_s01, aynı 'preopt' kampanyası,
               meshes/preopt/; candidates.json'a EKLENİR (1. aşama korunur). Üretim makinesinde --register-stage2 ile kayıt.
               spec: {"note": "...", "items": [{"pid": "02", "L": 0.2, "free": [{"rn_over_R": 0.4}, ...]}]}
               --select 1. ve 2. aşama adaylarını birlikte değerlendirir.
  4) --select  her (profil, L) için K_kayıp'ı en düşük adayı seçer, config/nose_params.json 'selected' alanına yazar,
               docs/preopt_report.md üretir. Ardından: src/01_mesh_gen.py --geom <20 geometri> ile ana mesh'ler yenilenir.

Aday kimliği: P03_L300_c04. Amaç fonksiyonu ana çalışmayla aynıdır: K_kayıp = ∫Cd(t)dt; Cd(v) temsili hızlar arasında PCHIP.
"""
from __future__ import annotations

import argparse
import itertools
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import db  # noqa: E402
from common.atmosphere import freestream  # noqa: E402
from common.config import CONFIG_DIR, DOCS_DIR, MESH_DIR, load_nose_params, load_velocities  # noqa: E402
from common.geometry import build_geometry, load_profile_defs  # noqa: E402
from common.metrics import k_loss  # noqa: E402
from common.solver_profile import load_physics, regime_for  # noqa: E402

log = logging.getLogger("preopt")
CAMPAIGN = "preopt"
PRE_DIR = DOCS_DIR / "preopt"
CANDIDATES_JSON = PRE_DIR / "candidates.json"

# Temsili hızlar: ses altı düşük / ses altı yüksek / transonik / süpersonik
PREOPT_VELS = [5, 10, 15, 19]

GRID = {
    "02": {"rn_over_R": [0.05, 0.10, 0.20, 0.30]},
    "08": {"rn_over_R": [0.05, 0.10, 0.20, 0.30]},
    "03": {"L1_over_L": [0.3, 0.5, 0.7], "R1_over_R": [0.6, 0.75, 0.85]},
    "04": {"Rt_over_R": [0.05, 0.10, 0.20, 0.30]},
    "19": {"a_over_L": [0.05, 0.25, 1.0]},
}


def candidates(npar: dict) -> list[dict]:
    R = npar["fixed"]["R"]
    out = []
    for L in npar["fixed"]["L_values"]:
        for pid, grid in GRID.items():
            keys = list(grid)
            k = 0
            for combo in itertools.product(*(grid[x] for x in keys)):
                fp = dict(zip(keys, combo))
                if pid == "03":   # dışbükeylik: ilk koni ikinciden dik
                    L1, R1 = fp["L1_over_L"] * L, fp["R1_over_R"] * R
                    if not R1 / L1 > (R - R1) / (L - L1):
                        continue
                k += 1
                out.append({"cand_id": f"P{pid}_L{round(L * 1000):03d}_c{k:02d}", "pid": pid, "L": L, "free": fp})
    return out


def _free_abs(c: dict, R: float) -> dict:
    f = dict(c["free"])
    if "rn_over_R" in f:
        f["rn"] = f.pop("rn_over_R") * R
    return f


def cmd_plan(npar: dict) -> list[dict]:
    cs = candidates(npar)
    by = {}
    for c in cs:
        by.setdefault((c["pid"], c["L"]), 0)
        by[(c["pid"], c["L"])] += 1
    print(f"Aday geometri: {len(cs)}   temsili hızlar: {PREOPT_VELS}   koşu: {len(cs) * len(PREOPT_VELS)}")
    for (pid, L), n in sorted(by.items()):
        print(f"  P{pid} L={L * 1000:.0f} mm: {n} aday")
    return cs


def cmd_build(npar: dict) -> None:
    from common.mesher import build_mesh
    cs = candidates(npar)
    R, rn_mesh = npar["fixed"]["R"], npar["mesh_tip_blunting"]["rn_mesh"]
    defs = load_profile_defs()
    out_dir = MESH_DIR / CAMPAIGN
    out_dir.mkdir(parents=True, exist_ok=True)
    ok_ids = []
    for i, c in enumerate(cs, 1):
        path = out_dir / f"{c['cand_id']}.msh.gz"
        if path.exists():
            ok_ids.append(c["cand_id"])
            continue
        try:
            geo = build_geometry(defs[c["pid"]], c["L"], R, _free_abs(c, R), rn_mesh)
            if not geo.checks["ok"]:
                raise ValueError(f"geometri doğrulaması: {geo.checks}")
            geo_id = geo.geom_id
            geo.id_override = c["cand_id"]
            res = build_mesh(geo, npar["fixed"]["body_length"], path)
            c["mesh"] = {"ok": res.ok, "cells": res.n_cells, "max_skew": round(res.max_skewness, 3), "msg": res.message}
            log.info("[%d/%d] %s (%s) %s hücre=%d", i, len(cs), c["cand_id"], geo_id, "OK" if res.ok else res.message, res.n_cells)
            if res.ok:
                ok_ids.append(c["cand_id"])
        except Exception as exc:  # noqa: BLE001
            log.error("[%d/%d] %s HATA: %s", i, len(cs), c["cand_id"], exc)
            c["mesh"] = {"ok": False, "msg": str(exc)}
    PRE_DIR.mkdir(parents=True, exist_ok=True)
    if CANDIDATES_JSON.exists():   # 2. aşama adaylarını koru (--build yeniden çalıştırılırsa kaybolmasın)
        new_ids = {c["cand_id"] for c in cs}
        cs += [c for c in json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))["candidates"] if c["cand_id"] not in new_ids]
    CANDIDATES_JSON.write_text(json.dumps({"vels": PREOPT_VELS, "candidates": cs}, indent=2), encoding="utf-8")
    _register(ok_ids)


def _register(ok_ids: list[str]) -> None:
    phys = load_physics()
    pts = []
    for p in load_velocities():
        if p["index"] in PREOPT_VELS:
            m = freestream(p["velocity_ms"], p["altitude_m"], phys).mach
            pts.append({**p, "mach": m, "regime": regime_for(m)})
    with db.connect() as con:
        n = db.ensure_runs(con, CAMPAIGN, ok_ids, pts, mesh_version="preopt")
        db.event(con, "INFO", "queue", f"{n} ön optimizasyon koşusu kuyruğa eklendi")
    print(f"{len(ok_ids)} aday mesh hazır; {n} koşu 'preopt' kampanyasına eklendi.")


def _feasible(pid: str, L: float, R: float, fp: dict) -> bool:
    if pid == "03":
        L1, R1 = fp["L1_over_L"] * L, fp["R1_over_R"] * R
        return 0 < L1 < L and 0 < R1 < R and R1 / L1 > (R - R1) / (L - L1)
    for k in ("rn_over_R", "Rt_over_R"):
        if k in fp:
            return 0 < fp[k] < 1
    if "a_over_L" in fp:
        return fp["a_over_L"] > 0
    return True


def cmd_stage2(npar: dict, spec_path: Path) -> list[str]:
    """2. aşama adayları: geometri + mesh (Python kalite kapısı) + candidates.json. Fluent kontrolü ve kayıt ayrı adımlar."""
    from common.mesher import build_mesh
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    R, rn_mesh = npar["fixed"]["R"], npar["mesh_tip_blunting"]["rn_mesh"]
    defs = load_profile_defs()
    meta = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
    existing = {c["cand_id"]: c for c in meta["candidates"]}
    out_dir = MESH_DIR / CAMPAIGN
    ok_ids, new = [], []
    for it in spec["items"]:
        pid, L = it["pid"], float(it["L"])
        base = f"P{pid}_L{round(L * 1000):03d}"
        k = sum(1 for cid in existing if cid.startswith(base + "_s"))
        for fp in it["free"]:
            if set(fp) != set(GRID[pid]):
                raise SystemExit(f"{base}: serbest parametre adları {sorted(GRID[pid])} olmalı, verilen {sorted(fp)}")
            if not _feasible(pid, L, R, fp):
                print(f"  {base} {fp}: kısıtı sağlamıyor, atlandı")
                continue
            if any(c["pid"] == pid and abs(c["L"] - L) < 1e-9 and c["free"] == fp for c in existing.values()):
                print(f"  {base} {fp}: zaten aday, atlandı")
                continue
            k += 1
            c = {"cand_id": f"{base}_s{k:02d}", "pid": pid, "L": L, "free": fp, "stage": 2}
            path = out_dir / f"{c['cand_id']}.msh.gz"
            try:
                geo = build_geometry(defs[pid], L, R, _free_abs(c, R), rn_mesh)
                if not geo.checks["ok"]:
                    raise ValueError(f"geometri doğrulaması: {geo.checks}")
                geo.id_override = c["cand_id"]
                res = build_mesh(geo, npar["fixed"]["body_length"], path)
                c["mesh"] = {"ok": res.ok, "cells": res.n_cells, "max_skew": round(res.max_skewness, 3), "msg": res.message}
                print(f"  {c['cand_id']} {fp}: {'OK' if res.ok else res.message} hücre={res.n_cells}", flush=True)
                if res.ok:
                    ok_ids.append(c["cand_id"])
            except Exception as exc:  # noqa: BLE001
                c["mesh"] = {"ok": False, "msg": str(exc)}
                print(f"  {c['cand_id']} {fp}: HATA {exc}")
            existing[c["cand_id"]] = c
            new.append(c)
    meta["candidates"] = list(existing.values())
    CANDIDATES_JSON.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"2. aşama: {len(new)} yeni aday, {len(ok_ids)} mesh OK. Sonraki: check_mesh_fluent.py (her aday) -> commit/push -> "
          f"üretim makinesinde --register-stage2")
    return ok_ids


def cmd_select(npar: dict, allow_partial: bool) -> None:
    import pandas as pd
    meta = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
    cs = {c["cand_id"]: c for c in meta["candidates"]}
    with db.connect() as con:
        df = pd.read_sql_query("SELECT geom_id, vel_idx, velocity_ms, status, cd FROM runs WHERE campaign=?",
                               con, params=(CAMPAIGN,))
    rows = []
    for cid, g in df.groupby("geom_id"):
        okd = g[g.status.isin(["done", "done_flagged"])]
        complete = len(okd) == len(meta["vels"])
        if not complete and not allow_partial:
            continue
        if len(okd) < 2:
            continue
        k = k_loss(dict(zip(okd.velocity_ms, okd.cd)))
        c = cs[cid]
        rows.append({"cand_id": cid, "pid": c["pid"], "L": c["L"], **c["free"], "complete": complete,
                     **{f"cd_v{int(v):02d}": cd for v, cd in zip(okd.vel_idx, okd.cd)}, **k})
    if not rows:
        raise SystemExit("Seçim için yeterli sonuç yok.")
    res = pd.DataFrame(rows).sort_values(["pid", "L", "K_kayip"])
    p = CONFIG_DIR / "nose_params.json"
    npar = json.loads(p.read_text(encoding="utf-8"))
    lines = ["# Ön Optimizasyon Raporu", "",
             f"Temsili hızlar: {meta['vels']}. Amaç: K_kayıp = ∫Cd(t)dt (PCHIP, uçuş profili). Her (profil, L) için en düşük K seçildi.", ""]
    for (pid, L), g in res.groupby(["pid", "L"]):
        best = g.iloc[0]
        key = f"L{round(L * 1000):03d}"
        sel = {k: float(best[k]) for k in GRID[pid]}
        npar["free_params"][pid]["selected"][key] = sel
        lines += [f"## P{pid} — L = {L * 1000:.0f} mm", "", f"Seçilen: `{best['cand_id']}` {sel}  K = {best['K_kayip']:.5f}", "",
                  g[["cand_id"] + list(GRID[pid]) + [c for c in g.columns if c.startswith("cd_v")] + ["K_kayip", "complete"]]
                  .to_markdown(index=False, floatfmt=".5f"), ""]
    npar["free_params"]["status"] = "selected" if res["complete"].all() else "selected_partial"
    p.write_text(json.dumps(npar, indent=2, ensure_ascii=False), encoding="utf-8")
    res.to_csv(PRE_DIR / "preopt_results.csv", index=False)
    (DOCS_DIR / "preopt_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Seçim yazıldı: {p}  rapor: {DOCS_DIR / 'preopt_report.md'}")
    print("Sonraki adım: ana mesh'leri yenileyin -> src/01_mesh_gen.py --geom " +
          " ".join(sorted({f'P{r.pid}_L{round(r.L * 1000):03d}' for r in res.itertuples()})))


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true")
    g.add_argument("--build", action="store_true")
    g.add_argument("--select", action="store_true")
    g.add_argument("--stage2", metavar="SPEC_JSON", help="2. aşama adaylarını üret (mesh + candidates.json)")
    g.add_argument("--register-stage2", action="store_true",
                   help="2. aşama adaylarını (mesh'leri Git'ten gelmiş) DB'ye kaydet — üretim makinesinde")
    ap.add_argument("--allow-partial", action="store_true", help="--select: eksik hızlı adayları da değerlendir")
    args = ap.parse_args()
    npar = load_nose_params()
    if args.plan:
        cmd_plan(npar)
    elif args.build:
        cmd_build(npar)
    elif args.stage2:
        cmd_stage2(npar, Path(args.stage2))
    elif args.register_stage2:
        meta = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
        _register([c["cand_id"] for c in meta["candidates"]
                   if c.get("stage") == 2 and (MESH_DIR / CAMPAIGN / f"{c['cand_id']}.msh.gz").exists()])
    else:
        cmd_select(npar, args.allow_partial)
    return 0


if __name__ == "__main__":
    sys.exit(main())
