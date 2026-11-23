"""Ortam doğrulaması: Python paketleri + PyFluent ile headless Fluent 2ddp başlatma/kapatma testi.

Kullanım:  .venv\\Scripts\\python.exe src\\tools\\check_env.py [--no-fluent]
Her makinede (İstanbul / Ankara) kurulumdan sonra bir kez çalıştırılır.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # src/

from common.config import LOG_DIR, load_machine_config  # noqa: E402
from common.fluent_session import _fluent_pids, fluent_solver  # noqa: E402

REQUIRED = ("numpy", "scipy", "pandas", "matplotlib", "gmsh", "psutil", "ansys.fluent.core")


def check_packages() -> bool:
    ok = True
    for mod in REQUIRED:
        try:
            m = __import__(mod, fromlist=["__version__"])
            print(f"  [OK]   {mod:<20} {getattr(m, '__version__', '?')}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [HATA] {mod:<20} {exc}")
            ok = False
    return ok


def check_fluent(cfg: dict) -> bool:
    fluent_exe = Path(cfg["fluent_exe"])
    if not fluent_exe.exists():
        print(f"  [HATA] fluent.exe bulunamadı: {fluent_exe}")
        return False
    print(f"  fluent.exe: {fluent_exe}")

    before = _fluent_pids()
    t0 = time.time()
    with fluent_solver(cfg, cwd=LOG_DIR / "check_env", processor_count=2) as solver:
        print(f"  [OK]   Fluent başlatıldı ({time.time() - t0:.1f} s)")
        print(f"         Sürüm: {solver.get_fluent_version()}")
        solver.tui.report.system.proc_stats()
        print("  [OK]   TUI komutu çalıştı")
    leftover = _fluent_pids() - before
    if leftover:
        print(f"  [HATA] Kapanmayan Fluent süreçleri: {sorted(leftover)}")
        return False
    print(f"  [OK]   Oturum temiz kapatıldı, artık süreç yok (toplam {time.time() - t0:.1f} s)")
    return True


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("ansys").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fluent", action="store_true", help="Fluent başlatma testini atla")
    args = ap.parse_args()

    cfg = load_machine_config()
    print(f"Makine: {cfg.get('machine_name')}  |  Python: {sys.version.split()[0]}")
    print("Paketler:")
    ok = check_packages()
    if ok and not args.no_fluent:
        print("Fluent testi:")
        ok = check_fluent(cfg)
    print("SONUÇ:", "BAŞARILI" if ok else "BAŞARISIZ")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
