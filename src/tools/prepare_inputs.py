"""Ham girdileri (inputs/raw) proje formatına dönüştürür.

- Vt_graph.txt   -> config/velocities.json, config/flight_profile.csv
- Nosecone_eq.txt -> inputs/nose_cones/NN_<isim>.txt (20 dosya)

Tek seferlik / tekrarlanabilir: aynı girdiyle her zaman aynı çıktıyı üretir.
Kullanım:  python src/tools/prepare_inputs.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "inputs" / "raw"
CONFIG = ROOT / "config"
NOSE_DIR = ROOT / "inputs" / "nose_cones"

KNOWN_FUNCS = {"sqrt", "max", "min", "cos", "sin", "tan", "acos", "asin", "atan", "pi", "exp", "log", "abs"}

TR_MAP = str.maketrans({
    "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "İ": "i", "ö": "o", "Ö": "o",
    "ş": "s", "Ş": "s", "ü": "u", "Ü": "u", "á": "a", "ρ": "rho",
})


def tr_float(s: str) -> float:
    return float(s.strip().replace(",", "."))


def slugify(name: str) -> str:
    s = name.translate(TR_MAP).lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def prepare_velocities() -> list[dict]:
    rows = []
    for line in (RAW / "Vt_graph.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"Beklenmeyen satır formatı: {line!r}")
        idx, v, mach, t, alt = parts
        rows.append({
            "index": int(idx),
            "velocity_ms": tr_float(v),
            "mach": tr_float(mach),
            "time_s": tr_float(t),
            "altitude_m": tr_float(alt),
        })
    rows.sort(key=lambda r: r["velocity_ms"])
    if len(rows) != 20:
        raise ValueError(f"20 hız noktası bekleniyordu, {len(rows)} bulundu")

    (CONFIG / "velocities.json").write_text(
        json.dumps({
            "source": "inputs/raw/Vt_graph.txt",
            "note": "Artan hız sırası (warm-start için). Basınç/sıcaklık ISA'dan altitude_m ile hesaplanır.",
            "points": rows,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    with open(CONFIG / "flight_profile.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "velocity_ms", "mach", "altitude_m"])
        for r in sorted(rows, key=lambda r: r["time_s"]):
            w.writerow([r["time_s"], r["velocity_ms"], r["mach"], r["altitude_m"]])
    return rows


def prepare_nose_cones() -> list[dict]:
    NOSE_DIR.mkdir(parents=True, exist_ok=True)
    pat = re.compile(r"^(\d{2})\s+(.+?)\s*==>>\s*(.+?);?\s*$")
    cones = []
    for line in (RAW / "Nosecone_eq.txt").read_text(encoding="utf-8").splitlines():
        m = pat.match(line.strip())
        if not m:
            continue
        nid, name, eq = m.group(1), m.group(2).strip(), m.group(3).strip().rstrip(";")
        if not eq.startswith("y ="):
            raise ValueError(f"{nid}: denklem 'y =' ile başlamıyor: {eq!r}")
        rhs = eq[len("y ="):].strip()
        idents = set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", rhs))
        params = sorted(idents - KNOWN_FUNCS - {"x"})
        # Parantez içi ayırt edici bilgi (K, n, C, ince/şişkin) korunur; "ρ=..." gibi notlar atılır
        slug = slugify(re.sub(r"[,]?\s*ρ\s*=.*?(?=\))", "", name))
        fname = f"{nid}_{slug}.txt"
        (NOSE_DIR / fname).write_text(
            f"# id: {nid}\n"
            f"# name: {name}\n"
            f"# params: {', '.join(params)}\n"
            f"# syntax: MATLAB (x: eksenel koordinat [m], uç x=0; y: yarıçap [m])\n"
            f"y = {rhs};\n",
            encoding="utf-8",
        )
        cones.append({"id": nid, "name": name, "file": fname, "params": params})
    if len(cones) != 20:
        raise ValueError(f"20 profil bekleniyordu, {len(cones)} bulundu")
    return cones


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    CONFIG.mkdir(parents=True, exist_ok=True)
    vel = prepare_velocities()
    cones = prepare_nose_cones()
    print(f"Hız noktası: {len(vel)}  ({vel[0]['velocity_ms']}–{vel[-1]['velocity_ms']} m/s)")
    for c in cones:
        print(f"  {c['file']:<45} params: {', '.join(c['params'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
