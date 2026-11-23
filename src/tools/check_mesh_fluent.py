"""Bir veya daha çok .msh dosyasını headless Fluent'te okuyup mesh/check + mesh/quality çalıştırır.
Tüm dosyalar tek Fluent oturumunda sırayla kontrol edilir.

Kullanım:
  .venv\\Scripts\\python.exe src\\tools\\check_mesh_fluent.py meshes\\P16_L300.msh [diğer.msh ...]
  .venv\\Scripts\\python.exe src\\tools\\check_mesh_fluent.py --all
Çıktı: logs\\mesh_check\\<id>.trn + docs\\mesh\\fluent_mesh_check.csv
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # src/

from common.config import CONFIG_DIR, DOCS_DIR, LOG_DIR, MESH_DIR, load_machine_config  # noqa: E402
from common.fluent_session import fluent_solver  # noqa: E402

EXPECTED_ZONES = {"fluid", "interior-fluid", "wall_rocket", "axis", "farfield", "inlet", "outlet"}


def parse_transcript(text: str) -> dict:
    out = {"min_orthogonal_quality": None, "max_aspect_ratio": None, "min_2d_volume": None}
    m = re.search(r"Minimum Orthogonal Quality\s*=\s*([0-9.eE+-]+)", text)
    if m:
        out["min_orthogonal_quality"] = float(m.group(1))
    m = re.search(r"Maximum Aspect Ratio\s*=\s*([0-9.eE+-]+)", text)
    if m:
        out["max_aspect_ratio"] = float(m.group(1))
    m = re.search(r"minimum 2d volume \(m3\):\s*([0-9.eE+-]+)", text)
    if m:
        out["min_2d_volume"] = float(m.group(1))
    out["non_positive_volume"] = "non-positive volume" in text
    out["left_handed_faces"] = "left-handed faces" in text
    zones = set(re.findall(r"(?m)^\s*\d+\s+(\S+)\s+(?:wall|axis|pressure-far-field|interior|fluid)\s", text))
    out["zones_ok"] = EXPECTED_ZONES.issubset(zones)
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dir", default=None, help="--all için klasör (varsayılan meshes/; ör. meshes/preopt)")
    ap.add_argument("--report", default="fluent_mesh_check.csv")
    args = ap.parse_args()
    src_dir = Path(args.dir) if args.dir else MESH_DIR
    files = sorted(src_dir.glob("P*_L*.msh.gz")) if args.all else [Path(f) for f in args.files]
    if not files:
        ap.error("Kontrol edilecek dosya yok")

    thr = json.loads((CONFIG_DIR / "mesh_settings.json").read_text(encoding="utf-8"))["quality"]["fluent_min_orthogonal_quality"]
    work = LOG_DIR / "mesh_check"
    work.mkdir(parents=True, exist_ok=True)
    rows = []
    with fluent_solver(load_machine_config(), cwd=work, processor_count=2) as solver:
        solver.tui.define.models.axisymmetric("yes")
        for i, msh in enumerate(files, 1):
            gid = msh.name.split(".")[0]
            trn = work / f"{gid}.trn"
            trn.unlink(missing_ok=True)
            solver.tui.file.start_transcript(str(trn))
            solver.tui.file.read_case(str(msh.resolve()))
            solver.tui.mesh.check()
            solver.tui.mesh.quality()
            solver.tui.define.boundary_conditions.list_zones()
            solver.tui.file.stop_transcript()
            r = parse_transcript(trn.read_text(encoding="utf-8", errors="replace"))
            oq = r["min_orthogonal_quality"]
            r["ok"] = (oq is not None and oq >= thr and not r["non_positive_volume"]
                       and not r["left_handed_faces"] and r["zones_ok"])
            r["geom_id"] = gid
            rows.append(r)
            print(f"[{i}/{len(files)}] {gid}: minOQ={oq}  {'OK' if r['ok'] else 'HATA'}", flush=True)

    df = pd.DataFrame(rows)
    out = DOCS_DIR / "mesh" / args.report
    if out.exists():
        old = pd.read_csv(out)
        df = pd.concat([old[~old["geom_id"].isin(df["geom_id"])], df]).sort_values("geom_id")
    df.to_csv(out, index=False)
    bad = df[~df["ok"].astype(bool)]
    print(f"Toplam {len(df)}  |  hatalı {len(bad)}  |  min OQ = {df['min_orthogonal_quality'].min()}")
    if len(bad):
        print(bad[["geom_id", "min_orthogonal_quality", "non_positive_volume", "left_handed_faces", "zones_ok"]].to_string(index=False))
    return 0 if bad.empty else 1


if __name__ == "__main__":
    sys.exit(main())
