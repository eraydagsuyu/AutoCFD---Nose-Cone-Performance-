"""GCI raporu (Celik vd. 2008, J. Fluids Eng. 130(7)): 'gci' kampanyasının Cd'lerinden ağ yakınsama mertebesi,
Richardson ekstrapolasyonu ve ince/orta ağ için GCI.

r_21, r_32 hücre sayılarından: r = (N_ince / N_kaba)^(1/2) (2D). p sabit-noktalı iterasyonla (r_21 ≠ r_32 için q terimi).
Salınımlı yakınsama (ε32/ε21 < 0) veya p ≤ 0 ise GCI hesaplanmaz, durum yazılır.

Kullanım: .venv\\Scripts\\python.exe src\\tools\\gci_report.py [--db data\\results.db]
Çıktı: docs/gci/gci_results.csv + docs/gci/gci_report.md
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # src/

from common.config import DATA_DIR, DOCS_DIR  # noqa: E402


def order_p(e21: float, e32: float, r21: float, r32: float) -> float:
    s = math.copysign(1.0, e32 / e21)
    p = abs(math.log(abs(e32 / e21))) / math.log(r21)
    for _ in range(100):
        q = math.log((r21 ** p - s) / (r32 ** p - s))
        p_new = abs(math.log(abs(e32 / e21)) + q) / math.log(r21)
        if abs(p_new - p) < 1e-10:
            break
        p = p_new
    return p


def gci(f1: float, f2: float, f3: float, r21: float, r32: float) -> dict:
    e21, e32 = f2 - f1, f3 - f2
    out = {"e21_rel": abs(e21 / f1), "e32_rel": abs(e32 / f2)}
    if e21 == 0 or e32 == 0:
        return {**out, "status": "değişim yok"}
    if e32 / e21 < 0:
        return {**out, "status": "salınımlı yakınsama", "gci_fine_band": 1.25 * max(abs(e21), abs(e32)) / abs(f1)}
    p = order_p(e21, e32, r21, r32)
    if p <= 0:
        return {**out, "status": "ıraksama", "p": p}
    f_ext = (r21 ** p * f1 - f2) / (r21 ** p - 1)
    return {**out, "status": "monoton", "p": p, "f_ext": f_ext, "e_ext_rel": abs((f_ext - f1) / f_ext),
            "gci_fine": 1.25 * abs(e21 / f1) / (r21 ** p - 1), "gci_medium": 1.25 * abs(e32 / f2) / (r32 ** p - 1)}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DATA_DIR / "results.db"))
    a = ap.parse_args()
    con = sqlite3.connect(a.db)
    df = pd.read_sql_query("SELECT geom_id, vel_idx, mach, regime, status, cd FROM runs WHERE campaign='gci'", con)
    meshes = pd.read_csv(DOCS_DIR / "gci" / "gci_meshes.csv").set_index("geom_id")
    df["base"], df["level"] = df.geom_id.str[:-3], df.geom_id.str[-1].astype(int)
    rows = []
    for (base, v), g in df.groupby(["base", "vel_idx"]):
        g = g.set_index("level")
        okd = g[g.status.isin(["done", "done_flagged"])]
        row = {"geom": base, "vel_idx": v, "mach": round(float(g.mach.iloc[0]), 3), "regime": g.regime.iloc[0],
               **{f"cd_g{l}": (okd.cd.get(l) if l in okd.index else None) for l in (1, 2, 3)},
               "flagged": ",".join(f"g{l}" for l in okd.index if okd.loc[l, "status"] == "done_flagged")}
        if len(okd) == 3:
            n = {l: meshes.loc[f"{base}_g{l}", "n_cells"] for l in (1, 2, 3)}
            r21, r32 = (n[1] / n[2]) ** 0.5, (n[2] / n[3]) ** 0.5
            row.update({"r21": r21, "r32": r32, **gci(okd.cd[1], okd.cd[2], okd.cd[3], r21, r32)})
        else:
            row["status"] = f"eksik ({len(okd)}/3)"
        rows.append(row)
    res = pd.DataFrame(rows).sort_values(["geom", "vel_idx"])
    out = DOCS_DIR / "gci"
    out.mkdir(parents=True, exist_ok=True)
    res.to_csv(out / "gci_results.csv", index=False)
    show = res.copy()
    for c in ("e21_rel", "e32_rel", "e_ext_rel", "gci_fine", "gci_medium", "gci_fine_band"):
        if c in show:
            show[c] = show[c].map(lambda x: f"{x * 100:.2f}%" if pd.notna(x) else "")
    cols = [c for c in ("geom", "vel_idx", "mach", "cd_g1", "cd_g2", "cd_g3", "status", "p", "f_ext", "gci_fine", "gci_medium",
                        "gci_fine_band", "flagged") if c in show]
    md = ["# GCI (ağ bağımsızlığı) raporu", "",
          "Yöntem: Celik vd. (2008). g1 ince, g2 orta (= ana analiz mesh'i), g3 kaba; r ≈ 1,5. "
          "`gci_medium` ana analizin ağ belirsizliğidir.", "",
          show[cols].to_markdown(index=False, floatfmt=".5f")]
    (out / "gci_report.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
