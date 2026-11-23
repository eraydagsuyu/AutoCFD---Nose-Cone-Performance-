"""Son işleme: Cd(v) -> Cd(t), K_kayıp = ∫Cd(t)dt, sıralama ve grafikler.

Kullanım:
  .venv\\Scripts\\python.exe src\\04_postprocess.py [--allow-partial] [--min-points 15]

Çıktılar (docs/results/):
  ranking.csv / ranking.md    geometri sıralaması (K_kayıp küçükten büyüğe), yardımcı ∫v²·Cd dt
  cd_v_L<LLL>.png             her L için 20 profilin Cd(v) eğrileri
  cd_t_top.png                en iyi 8 geometrinin Cd(t) eğrileri
  cd_matrix.csv               geometri × hız Cd matrisi
--allow-partial: eksik hız noktası olan geometriler de (en az --min-points noktayla) değerlendirilir ve işaretlenir.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from common import db  # noqa: E402
from common.config import DOCS_DIR, load_velocities  # noqa: E402
from common.geometry import load_profile_defs  # noqa: E402
from common.metrics import cd_of_t, flight_profile, k_loss  # noqa: E402

OUT = DOCS_DIR / "results"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", default="main")
    ap.add_argument("--allow-partial", action="store_true")
    ap.add_argument("--min-points", type=int, default=15)
    args = ap.parse_args()

    with db.connect() as con:
        df = pd.read_sql_query("SELECT geom_id, vel_idx, velocity_ms, mach, status, cd, cd_flagged FROM runs WHERE campaign=?",
                               con, params=(args.campaign,))
    ok = df[df.status.isin(["done", "done_flagged"])]
    if ok.empty:
        raise SystemExit("Tamamlanmış koşu yok.")
    n_vel = len(load_velocities())
    names = {pid: d.name for pid, d in load_profile_defs().items()}
    fp = flight_profile()

    rows = []
    for gid, g in ok.groupby("geom_id"):
        complete = len(g) == n_vel
        if not complete and not (args.allow_partial and len(g) >= args.min_points):
            continue
        k = k_loss(dict(zip(g.velocity_ms, g.cd)), fp)
        pid = gid[1:3]
        rows.append({"geom_id": gid, "profil": f"{pid} {names.get(pid, '')}", "L_mm": int(gid.split("_L")[1]),
                     "n_points": len(g), "complete": complete, "n_flagged": int(g.cd_flagged.sum()),
                     "K_kayip": k["K_kayip"], "K_v2": k["K_v2"]})
    if not rows:
        raise SystemExit("Değerlendirilecek geometri yok (eksik noktalar için --allow-partial).")
    rank = pd.DataFrame(rows).sort_values("K_kayip").reset_index(drop=True)
    rank.index += 1
    OUT.mkdir(parents=True, exist_ok=True)
    rank.to_csv(OUT / "ranking.csv", index_label="sira")
    (OUT / "ranking.md").write_text("# Burun Konisi Sıralaması (K_kayıp küçükten büyüğe)\n\n" +
                                    rank.to_markdown(floatfmt=".5f") + "\n", encoding="utf-8")
    ok.pivot(index="geom_id", columns="vel_idx", values="cd").to_csv(OUT / "cd_matrix.csv")

    # Cd(v) — her L için
    for L, gL in ok.assign(L=ok.geom_id.str.slice(5, 8)).groupby("L"):
        fig, ax = plt.subplots(figsize=(11, 6.5))
        cmap = plt.get_cmap("tab20")
        for i, (gid, g) in enumerate(gL.groupby("geom_id")):
            g = g.sort_values("mach")
            ax.plot(g.mach, g.cd, "o-", ms=3, lw=1, color=cmap(i % 20), label=f"{gid[:3]} {names.get(gid[1:3], '')}")
        ax.set_xlabel("Mach"); ax.set_ylabel("Cd (A_ref = πR²)"); ax.grid(alpha=0.3)
        ax.set_title(f"Cd(Mach) — L = {int(L)} mm")
        ax.legend(fontsize=7, ncol=2)
        fig.tight_layout(); fig.savefig(OUT / f"cd_v_L{L}.png", dpi=120); plt.close(fig)

    # Cd(t) — en iyi 8
    fig, ax = plt.subplots(figsize=(11, 6))
    for gid in rank.geom_id.head(8):
        g = ok[ok.geom_id == gid]
        d = cd_of_t(dict(zip(g.velocity_ms, g.cd)), fp)
        ax.plot(d.time_s, d.cd, lw=1.3, label=f"{gid}  K={rank.set_index('geom_id').loc[gid, 'K_kayip']:.4f}")
    ax.set_xlabel("t [s]"); ax.set_ylabel("Cd(t)"); ax.grid(alpha=0.3); ax.legend(fontsize=8)
    ax.set_title("En düşük K_kayıp — Cd(t)")
    fig.tight_layout(); fig.savefig(OUT / "cd_t_top.png", dpi=120); plt.close(fig)

    print(rank.head(15).to_string())
    best = rank.iloc[0]
    print(f"\nEn iyi: {best.geom_id} ({best.profil}, L={best.L_mm} mm)  K_kayıp={best.K_kayip:.5f}"
          f"{'' if best.complete else '  [EKSİK NOKTA]'}")
    print(f"Çıktılar: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
