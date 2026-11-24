"""Sonuç günlüğü: her koşu kesinleştiğinde data/results_log.csv dosyasına bir satır ekler.

SQLite (data/results.db) asıl kayıttır; bu CSV, insan tarafından okunabilir, yalnızca-ekleme
yedeğidir. Her satır yazıldıktan sonra flush + fsync yapılır: elektrik/internet kesintisinde
o ana kadar biten koşuların Cd'leri dosyada kalır. Birden çok işçi aynı dosyaya yazabildiği
için ekleme, ayrı bir kilit dosyası üzerinden (msvcrt / fcntl) seri hâle getirilir.

Ayraç: virgül, ondalık: nokta (Excel'de "Veri > Metinden" ile açın).
"""
from __future__ import annotations

import csv
import io
import os
import time
from pathlib import Path

from .config import DATA_DIR

RESULTS_CSV = DATA_DIR / "results_log.csv"

FIELDS = [
    "timestamp", "machine", "campaign", "worker", "geom_id", "vel_idx", "velocity_ms", "mach", "altitude_m",
    "regime", "status", "cd", "attempt_no", "iterations", "elapsed_s", "init_method",
    "cd_rel_std", "cd_rel_amp", "message",
]


class _FileLock:
    """Süreçler arası basit kilit (Windows: msvcrt, diğer: fcntl)."""

    def __init__(self, path: Path, timeout_s: float = 30.0):
        self.path, self.timeout_s, self.fh = path, timeout_s, None

    def __enter__(self):
        self.fh = open(self.path, "a+b")
        deadline = time.monotonic() + self.timeout_s
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    self.fh.seek(0)
                    msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.05)

    def __exit__(self, *exc):
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        finally:
            self.fh.close()


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.6g}"
    return v


def append_result(row: dict, path: Path = RESULTS_CSV) -> None:
    """Bir sonuç satırını kilitli, fsync'li olarak ekler. Hata fırlatmaz (yedek kayıt koşuyu durdurmamalı)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS, extrasaction="ignore", lineterminator="\n")
    w.writerow({k: _fmt(row.get(k)) for k in FIELDS})
    line = buf.getvalue()
    with _FileLock(path.with_suffix(".lock")):
        new = not path.exists() or path.stat().st_size == 0
        with open(path, "a", encoding="utf-8", newline="") as fh:
            if new:
                fh.write(",".join(FIELDS) + "\n")
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
