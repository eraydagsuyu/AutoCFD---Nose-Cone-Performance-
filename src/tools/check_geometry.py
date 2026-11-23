"""80 geometrinin (20 profil × 4 L) üretimi, doğrulaması ve grafikleri.

Çıktılar:
  docs/geometry/geometry_check.csv        — her geometri için kontrol tablosu
  docs/geometry/profiles_L{LLL}.png       — 20 profilin karşılaştırması (her L için)
  docs/geometry/tips_L{LLL}.png           — uç bölgesi yakın görünüm (yuvarlatma kontrolü)

Kullanım:  .venv\\Scripts\\python.exe src\\tools\\check_geometry.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # src/

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from common.config import DOCS_DIR, load_nose_params  # noqa: E402
from common.geometry import build_all  # noqa: E402

OUT = DOCS_DIR / "geometry"


def expected_kind(pid: str, mtb: dict) -> str:
    exp = mtb["expected_classification"]
    if pid in exp["sharp_apex"]:
        return "sharp"
    if pid in exp["zero_tip_curvature_radius"]:
        return "zero_radius"
    if pid in exp["flat_face"]:
        return "flat"
    return "blunt"   # 02, 08, 09, 13, 19


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    npar = load_nose_params()
    mtb = npar["mesh_tip_blunting"]
    geos = build_all(npar)

    rows = []
    for g in geos:
        c = g.checks
        exp = expected_kind(g.pid, mtb)
        rows.append({
            "geom_id": g.geom_id,
            "name": g.name,
            "tip_kind": g.tip.kind,
            "expected": exp,
            "kind_match": g.tip.kind == exp,
            "exponent_p": round(g.tip.exponent, 3),
            "tip_Rc_mm": round(g.tip.radius * 1000, 3) if g.tip.radius == g.tip.radius else None,
            "blunted_1mm": g.arc is not None,
            "L_sharp_mm": round(g.L_sharp * 1000, 4),
            "length_err_um": round(c["length_err_m"] * 1e6, 4),
            "shoulder_err_um": round(c["shoulder_err_m"] * 1e6, 4),
            "y_max_mm": round(c["y_max_m"] * 1000, 3),
            "exceeds_R": c["exceeds_R"],
            "arc_tan_err_deg": round(c.get("arc_tangency_err_deg", 0.0), 5),
            "ok": c["ok"],
        })
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "geometry_check.csv", index=False, encoding="utf-8")

    # Grafikler
    cmap = plt.get_cmap("tab20")
    for L in npar["fixed"]["L_values"]:
        sub = [g for g in geos if abs(g.L - L) < 1e-12]
        tag = f"L{round(L * 1000):03d}"

        fig, ax = plt.subplots(figsize=(13, 6.5))
        for i, g in enumerate(sub):
            ax.plot(g.x * 1000, g.y * 1000, color=cmap(i), lw=1.2, label=f"{g.pid} {g.name}")
        ax.axhline(g.R * 1000, color="k", ls="--", lw=0.8)
        ax.set_xlabel("x [mm]"); ax.set_ylabel("y [mm]")
        ax.set_title(f"Burun konisi profilleri — L = {L * 1000:.0f} mm, R = {g.R * 1000:.0f} mm")
        ax.set_aspect("equal"); ax.grid(alpha=0.3)
        ax.legend(fontsize=7, ncol=2, loc="lower right")
        fig.tight_layout(); fig.savefig(OUT / f"profiles_{tag}.png", dpi=130); plt.close(fig)

        fig, axes = plt.subplots(4, 5, figsize=(16, 12))
        for ax, g in zip(axes.flat, sub):
            m = g.x < 0.006
            ax.plot(g.x[m] * 1000, g.y[m] * 1000, "b-", lw=1.2)
            if g.arc is not None:
                ax.plot(g.x[:g.n_arc_pts] * 1000, g.y[:g.n_arc_pts] * 1000, "r-", lw=2.2, label="1 mm yay")
            ax.set_xlim(-0.2, 6); ax.set_ylim(0, 6); ax.set_aspect("equal"); ax.grid(alpha=0.3)
            ax.set_title(f"{g.pid} [{g.tip.kind}]", fontsize=9)
        fig.suptitle(f"Uç bölgesi (ilk 6 mm) — {tag}  (kırmızı: 1 mm mesh yuvarlatması)")
        fig.tight_layout(); fig.savefig(OUT / f"tips_{tag}.png", dpi=110); plt.close(fig)

    pd.set_option("display.width", 220); pd.set_option("display.max_rows", 100)
    cols = ["geom_id", "tip_kind", "kind_match", "exponent_p", "tip_Rc_mm", "blunted_1mm",
            "L_sharp_mm", "length_err_um", "y_max_mm", "exceeds_R", "arc_tan_err_deg", "ok"]
    print(df[cols].to_string(index=False))
    print()
    print(f"Toplam: {len(df)}  |  ok: {df.ok.sum()}  |  sınıf uyuşmazlığı: {(~df.kind_match).sum()}  "
          f"|  R'yi aşan: {df.exceeds_R.sum()}")
    return 0 if df.ok.all() else 1


if __name__ == "__main__":
    sys.exit(main())
