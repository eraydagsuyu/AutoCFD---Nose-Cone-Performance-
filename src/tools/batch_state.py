"""resume_batch.ps1 için durum özeti (salt okunur). Çıktı tek satır: <preopt_bitmemiş> <main_bitmemiş> <seçim_yapıldı 0|1>

bitmemiş = pending / retry_pending / running / needs_review; seçim_yapıldı = serbest parametreli her profilde 4 L için 'selected' var.
"""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNFINISHED = ("pending", "retry_pending", "running", "needs_review")


def left(con, campaign: str) -> int:
    q = f"SELECT COUNT(*) FROM runs WHERE campaign=? AND status IN ({','.join('?' * len(UNFINISHED))})"
    return con.execute(q, (campaign, *UNFINISHED)).fetchone()[0]


def main() -> None:
    db = ROOT / "data" / "results.db"
    if db.exists():
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
        p, m = left(con, "preopt"), left(con, "main")
    else:
        p = m = 0
    free = json.loads((ROOT / "config" / "nose_params.json").read_text(encoding="utf-8"))["free_params"]
    sel = int(all(len(v.get("selected", {})) >= 4 for v in free.values() if isinstance(v, dict)))
    print(p, m, sel)


if __name__ == "__main__":
    main()
