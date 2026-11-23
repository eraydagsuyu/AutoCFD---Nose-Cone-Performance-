"""PyFluent oturumunu güvenli biçimde başlatma ve kapatma.

Ansys 2024 R1 (v241) yalnızca ansys-fluent-core <= 0.37.x ile desteklenir.
PyFluent'in session.exit() çağrısı bazen fluent.exe + cx2410.exe süreçlerini açık bırakır;
toplu koşuda bu bellek sızıntısına dönüşür. Bu yüzden:
  1) Başlatmadan önce mevcut Fluent süreçlerinin PID'leri kaydedilir.
  2) Kapatırken önce zaman aşımlı düzgün exit denenir.
  3) Ardından başlatmadan sonra doğmuş ve hâlâ yaşayan Fluent süreçleri ağaçlarıyla sonlandırılır.
"""
from __future__ import annotations

import contextlib
import logging
import re
import time
from pathlib import Path
from typing import Iterator

import psutil

log = logging.getLogger(__name__)

FLUENT_PROC_RE = re.compile(r"^(fluent|cx\d+|fl\d+|fl_mpi\d+|fluent_cortex)\.exe$", re.IGNORECASE)


def _fluent_pids() -> set[int]:
    pids = set()
    for p in psutil.process_iter(["pid", "name"]):
        name = p.info.get("name") or ""
        if FLUENT_PROC_RE.match(name):
            pids.add(p.info["pid"])
    return pids


def _kill_tree(pid: int) -> None:
    # Süreç bu sırada kendiliğinden kapanmış olabilir (yarış durumu) — sessizce geç.
    try:
        parent = psutil.Process(pid)
        procs = parent.children(recursive=True) + [parent]
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return
    for p in procs:
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            p.kill()
    psutil.wait_procs(procs, timeout=15)


def cleanup_new_fluent_processes(baseline: set[int], grace_s: float = 15.0) -> int:
    """baseline'da olmayan (yani bizim başlattığımız) Fluent süreçlerinin kendiliğinden kapanmasını
    grace_s saniye bekler; hâlâ yaşayanları ağaçlarıyla sonlandırır."""
    deadline = time.monotonic() + grace_s
    leftovers = _fluent_pids() - baseline
    while leftovers and time.monotonic() < deadline:
        time.sleep(1.0)
        leftovers = _fluent_pids() - baseline
    for pid in sorted(leftovers):
        log.warning("Kapanmayan Fluent süreci sonlandırılıyor: PID %s", pid)
        _kill_tree(pid)
    return len(leftovers)


@contextlib.contextmanager
def fluent_solver(machine_cfg: dict, cwd: Path, processor_count: int | None = None,
                  start_timeout: int = 300, exit_timeout: int = 30) -> Iterator[object]:
    """Headless 2ddp Fluent çözücü oturumu (context manager).

    Kullanım:
        with fluent_solver(cfg, cwd=LOG_DIR) as solver:
            solver.settings...
    """
    import ansys.fluent.core as pyfluent

    cwd.mkdir(parents=True, exist_ok=True)
    baseline = _fluent_pids()
    session = None
    try:
        session = pyfluent.launch_fluent(
            fluent_path=machine_cfg["fluent_exe"],
            dimension=2,
            precision="double",
            processor_count=processor_count or int(machine_cfg["fluent_cores"]),
            ui_mode="no_gui",
            mode="solver",
            cwd=str(cwd),
            start_timeout=start_timeout,
        )
        yield session
    finally:
        if session is not None:
            try:
                # timeout_force=False: PyFluent'in cleanup .bat araması v241'de başarısız oluyor;
                # zorla kapatmayı cleanup_new_fluent_processes() kendisi yapar.
                session.exit(timeout=exit_timeout, timeout_force=False, wait=False)
            except Exception as exc:  # noqa: BLE001
                log.warning("session.exit() hata verdi: %s", exc)
        n = cleanup_new_fluent_processes(baseline)
        if n:
            log.info("%d artık Fluent süreci temizlendi", n)
