"""Ankara ilerleme ekranı: tamamlanma yüzdesi, işçiler, son sonuçlar, tahmini bitiş.

Salt okunur (veritabanına yazmaz). scripts\\progress_monitor.ps1 bunu her 5 dakikada bir çağırır.
  .venv\\Scripts\\python.exe src\\tools\\progress.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "results.db"
TARGETS = {"preopt": 368, "main": 1600}          # 92 aday × 4 hız; 80 geometri × 20 hız
LABELS = {"preopt": "Ön optimizasyon", "main": "Ana analiz"}
FINAL = ("done", "done_flagged", "skipped", "mesh_error")


def bar(frac: float, width: int = 40) -> str:
    n = int(round(max(0.0, min(1.0, frac)) * width))
    return "█" * n + "░" * (width - n)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    now = datetime.now()
    print(f"  RocketCFD — Analiz İlerlemesi            {now:%d.%m.%Y %H:%M}   (her 5 dk yenilenir)")
    print("  " + "─" * 72)
    if not DB.exists():
        print("  Veritabanı henüz yok (data/results.db). Analiz başlamamış olabilir.")
        return 0
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=30)
    con.row_factory = sqlite3.Row

    tot_done = tot_target = 0
    for c, target in TARGETS.items():
        cnt = {r["status"]: r["n"] for r in con.execute(
            "SELECT status, COUNT(*) n FROM runs WHERE campaign=? GROUP BY status", (c,))}
        fin = sum(cnt.get(s, 0) for s in FINAL)
        tot_done += fin
        tot_target += target
        extra = []
        if cnt.get("running"):
            extra.append(f"çözülüyor {cnt['running']}")
        if cnt.get("needs_review"):
            extra.append(f"inceleme bekliyor {cnt['needs_review']}")
        if cnt.get("done_flagged"):
            extra.append(f"işaretli {cnt['done_flagged']}")
        print(f"  {LABELS[c]:<16} {bar(fin / target, 30)} %{100 * fin / target:5.1f}  ({fin}/{target})"
              + (f"  [{', '.join(extra)}]" if extra else ""))
    print()
    frac = tot_done / tot_target
    print(f"  GENEL            {bar(frac, 30)} %{100 * frac:5.1f}  ({tot_done}/{tot_target} koşu)")

    # Hız: son 6 saatte kesinleşen koşular -> tahmini bitiş
    since = (now - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
    first = con.execute("SELECT MIN(updated_at) t FROM runs WHERE status IN ('done','done_flagged')").fetchone()["t"]
    recent = con.execute("SELECT COUNT(*) n FROM runs WHERE status IN ('done','done_flagged') AND updated_at>=?",
                         (since,)).fetchone()["n"]
    if first and recent:
        hours = min(6.0, (now - datetime.strptime(first, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600)
        rate = recent / max(hours, 0.25)
        left = tot_target - tot_done
        eta = now + timedelta(hours=left / rate)
        print(f"  Hız: ~{rate:.1f} koşu/saat   Kalan: {left} koşu   Tahmini bitiş: {eta:%d.%m.%Y %H:%M} "
              f"(~{left / rate / 24:.1f} gün)")
    print()

    print("  İşçiler:")
    any_w = False
    for row in con.execute("SELECT value FROM control WHERE key LIKE 'heartbeat%' ORDER BY key"):
        h = json.loads(row["value"])
        age = (time.time() - time.mktime(time.strptime(h["ts"], "%Y-%m-%d %H:%M:%S"))) / 60
        state = "çalışıyor" if age < 15 else "!! YANIT YOK (15 dk+) !!"
        print(f"    {h.get('worker', '?'):<10} {state:<24} {age:4.0f} dk önce  {h.get('current', '')}")
        any_w = True
    if not any_w:
        print("    (henüz kalp atışı yok)")
    print()

    print("  Son tamamlanan koşular:")
    for r in con.execute("SELECT campaign, geom_id, vel_idx, mach, status, cd, updated_at FROM runs "
                         "WHERE status IN ('done','done_flagged') ORDER BY updated_at DESC LIMIT 6"):
        print(f"    {r['updated_at'][5:16]}  {r['campaign']:<6} {r['geom_id']} v{r['vel_idx']:02d}  "
              f"M={r['mach']:.3f}  Cd={r['cd']:.4f}  {'(işaretli)' if r['status'] == 'done_flagged' else ''}")
    print("  " + "─" * 72)
    print("  Bu pencereyi kapatmak analizleri DURDURMAZ. Fluent/python süreçlerini kapatmayın.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
