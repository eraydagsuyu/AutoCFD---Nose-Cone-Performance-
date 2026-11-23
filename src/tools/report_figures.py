"""Raporlar için veri ve şekil üretimi (docs/report_assets/).

- accel_convergence.png : v17 warm-start, sayısal ayar karşılaştırması (CFL 5 / 20 / CASM / enhanced-CASM 20, 50)
- cd_mach_P16_L300.png   : doğrulama koşularının Cd(M) değerleri
- cfd_vs_semiempirical.png : ses altı CFD vs Barrowman/OpenRocket yarı-ampirik tahmin
- facts.json             : raporlarda kullanılan ölçülmüş sayılar
"""
from __future__ import annotations

import glob
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from common import db  # noqa: E402
from common.atmosphere import freestream  # noqa: E402
from common.config import DOCS_DIR, LOG_DIR, load_nose_params, load_velocities  # noqa: E402
from common.fluent_case import read_out_file  # noqa: E402
from common.geometry import build_geometry, free_params_for, load_profile_defs  # noqa: E402
from common.solver_profile import load_physics  # noqa: E402

OUT = DOCS_DIR / "report_assets"
plt.rcParams.update({"font.family": "Arial", "font.size": 10})


def nose_wetted_area(gid: str) -> tuple[float, float]:
    npar = load_nose_params()
    pid, L = gid[1:3], int(gid.split("_L")[1]) / 1000
    g = build_geometry(load_profile_defs()[pid], L, npar["fixed"]["R"], free_params_for(pid, L, npar),
                       npar["mesh_tip_blunting"]["rn_mesh"])
    ds = np.hypot(np.diff(g.x), np.diff(g.y))
    ym = 0.5 * (g.y[1:] + g.y[:-1])
    return float(np.sum(2 * math.pi * ym * ds)), g.R


def barrowman(gid: str, fs, body_len: float) -> dict:
    """Barrowman / OpenRocket yarı-ampirik: türbülanslı düz levha sürtünmesi (Schlichting) + taban sürüklemesi."""
    S_nose, R = nose_wetted_area(gid)
    L = int(gid.split("_L")[1]) / 1000
    S_wet = S_nose + 2 * math.pi * R * body_len
    A = math.pi * R * R
    Re = fs.re_per_m * (L + body_len)
    cf = 0.455 / math.log10(Re) ** 2.58
    cd_f = cf * S_wet / A
    M = fs.mach
    cd_b = 0.12 + 0.13 * M * M if M < 1 else 0.25 / M
    return {"Re_L": Re, "cf": cf, "S_wet": S_wet, "cd_friction": cd_f, "cd_base": cd_b, "cd_total": cd_f + cd_b}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    facts: dict = {}
    phys = load_physics()
    P = {p["index"]: p for p in load_velocities()}

    # 1) Hızlandırma karşılaştırması
    ref_dir = sorted(glob.glob(str(LOG_DIR / "runs" / "P16_L300_v17" / "2026*")))
    curves = {}
    for d in ref_dir:
        _, cd = read_out_file(Path(d) / "cd.out")
        if len(cd) > 3000:
            curves["CFL 5 (referans, 4451 it)"] = cd
    for name, label in (("cfl20", "CFL 20"), ("casm_cfl5", "CASM + CFL 5"),
                        ("ecasm_cfl20", "enhanced-CASM + CFL 20"), ("ecasm_cfl50", "enhanced-CASM + CFL 50 (seçilen)")):
        _, cd = read_out_file(LOG_DIR / "accel" / name / "cd.out")
        if len(cd):
            curves[label] = cd
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    for lab, cd in curves.items():
        ax.plot(np.arange(1, len(cd) + 1), cd, lw=1.6 if "seçilen" in lab else 1.0, label=lab)
    ax.axhline(0.4913, color="k", ls="--", lw=0.8, label="nihai Cd = 0,4913")
    ax.set_xlim(0, 4500); ax.set_ylim(0.3, 0.52)
    ax.set_xlabel("İterasyon (warm-start, v16 alanından)"); ax.set_ylabel("Cd")
    ax.set_title("P16_L300, v17 (M = 1,062): sayısal ayarların yakınsama hızına etkisi")
    ax.grid(alpha=0.3); ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout(); fig.savefig(OUT / "accel_convergence.png", dpi=170); plt.close(fig)

    # 2) Doğrulama koşuları (DB) + tekli testler
    with db.connect() as con:
        runs = pd.read_sql_query("SELECT vel_idx, mach, status, cd FROM runs WHERE campaign='main' AND geom_id='P16_L300' "
                                 "AND status IN ('done','done_flagged') ORDER BY vel_idx", con)
        atts = pd.read_sql_query("SELECT r.vel_idx, a.attempt_no, a.outcome, a.init_method, a.iterations, a.elapsed_s, a.cd "
                                 "FROM attempts a JOIN runs r ON a.run_id=r.run_id WHERE r.geom_id='P16_L300' "
                                 "ORDER BY r.vel_idx, a.attempt_id", con)
    facts["validation_runs"] = runs.to_dict("records")
    facts["validation_attempts"] = atts.to_dict("records")
    extra = {17: 0.4913, 19: 0.4734, 20: 0.4616}       # accel/accel2 ölçümleri (aynı fizik, yeni ayar)
    fig, ax = plt.subplots(figsize=(8, 4.3))
    ax.plot(runs.mach, runs.cd, "o-", color="C0", label="Orkestratör koşuları (DB)")
    ems = [freestream(P[v]["velocity_ms"], P[v]["altitude_m"], phys).mach for v in extra]
    ax.plot(ems, list(extra.values()), "s", color="C3", label="Hızlandırma deneyleri (v17, v19, v20)")
    for _, r in runs.iterrows():
        if r.status == "done_flagged":
            ax.annotate("flag", (r.mach, r.cd), textcoords="offset points", xytext=(4, 4), fontsize=7)
    ax.set_xlabel("Mach"); ax.set_ylabel("Cd (A_ref = πR²)"); ax.grid(alpha=0.3); ax.legend(fontsize=8)
    ax.set_title("P16_L300 (Von Kármán, L = 300 mm) — doğrulama noktaları")
    fig.tight_layout(); fig.savefig(OUT / "cd_mach_P16_L300.png", dpi=170); plt.close(fig)

    # 3) CFD vs yarı-ampirik (ses altı)
    body = load_nose_params()["fixed"]["body_length"]
    rows = []
    for _, r in runs.iterrows():
        v = int(r.vel_idx)
        fs = freestream(P[v]["velocity_ms"], P[v]["altitude_m"], phys)
        if fs.mach >= 0.7:
            continue
        b = barrowman("P16_L300", fs, body)
        rows.append({"vel_idx": v, "mach": fs.mach, "Re_L": b["Re_L"], "cd_cfd": r.cd, "cd_friction_be": b["cd_friction"],
                     "cd_base_be": b["cd_base"], "cd_semi": b["cd_total"], "diff_pct": 100 * (r.cd - b["cd_total"]) / b["cd_total"]})
    cmp = pd.DataFrame(rows)
    facts["semiempirical"] = cmp.to_dict("records")
    fig, ax = plt.subplots(figsize=(8, 4.3))
    x = np.arange(len(cmp))
    ax.bar(x - 0.2, cmp.cd_cfd, 0.4, label="CFD (Fluent, k-ω SST)")
    ax.bar(x + 0.2, cmp.cd_friction_be, 0.4, label="Yarı-ampirik: sürtünme", color="C2")
    ax.bar(x + 0.2, cmp.cd_base_be, 0.4, bottom=cmp.cd_friction_be, label="Yarı-ampirik: taban", color="C1")
    for i, d in enumerate(cmp.diff_pct):
        ax.text(i, max(cmp.cd_cfd.iloc[i], cmp.cd_semi.iloc[i]) + 0.008, f"{d:+.1f}%", ha="center", fontsize=8)
    ax.set_xticks(x, [f"v{int(v):02d}\nM {m:.2f}" for v, m in zip(cmp.vel_idx, cmp.mach)])
    ax.set_ylabel("Cd"); ax.set_ylim(0, 0.52); ax.grid(alpha=0.3, axis="y"); ax.legend(fontsize=8, loc="upper right")
    ax.set_title("Ses altı: CFD ile Barrowman/OpenRocket yarı-ampirik tahmini")
    fig.tight_layout(); fig.savefig(OUT / "cfd_vs_semiempirical.png", dpi=170); plt.close(fig)

    # 4) Mesh istatistikleri
    mr = pd.read_csv(DOCS_DIR / "mesh" / "mesh_report.csv")
    fc = pd.read_csv(DOCS_DIR / "mesh" / "fluent_mesh_check.csv")
    facts["mesh"] = {"n": int(len(mr)), "cells_min": int(mr.n_cells.min()), "cells_max": int(mr.n_cells.max()),
                     "skew_max": float(mr.max_skewness.max()), "oq_min": float(fc.min_orthogonal_quality.min()),
                     "oq_median": float(fc.min_orthogonal_quality.median()), "n_layers": int(mr.n_layers.iloc[0]),
                     "bl_ratio": float(mr.bl_ratio.iloc[0])}
    pre = DOCS_DIR / "mesh" / "fluent_mesh_check_preopt.csv"
    if pre.exists():
        p = pd.read_csv(pre)
        facts["mesh_preopt"] = {"n": int(len(p)), "ok": int(p.ok.sum()), "oq_min": float(p.min_orthogonal_quality.min())}
    (OUT / "facts.json").write_text(json.dumps(facts, indent=2, default=float, ensure_ascii=False), encoding="utf-8")
    print(cmp.round(4).to_string(index=False))
    print(json.dumps(facts["mesh"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
