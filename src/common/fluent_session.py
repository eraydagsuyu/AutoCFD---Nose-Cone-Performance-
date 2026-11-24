"""PyFluent oturumunu güvenli biçimde başlatma ve kapatma.

Ansys 2024 R1 (v241) yalnızca ansys-fluent-core <= 0.37.x ile desteklenir.
PyFluent'in session.exit() çağrısı bazen fluent.exe + cx2410.exe süreçlerini açık bırakır;
toplu koşuda bu bellek sızıntısına dönüşür. Bu yüzden:
  1) Başlatmadan önce mevcut Fluent süreçlerinin PID'leri kaydedilir.
  2) Kapatırken önce zaman aşımlı düzgün exit denenir.
  3) Ardından BU oturumun süreçlerinden hâlâ yaşayanlar ağaçlarıyla sonlandırılır.

Çoklu işçi (2026-11-25): başlatmalar data/fluent_launch.lock ile sıraya sokulur; kilit tutulurken doğan Fluent
süreçleri bu oturumun "kendi" süreçleridir. Temizlik yalnızca bunlara uygulanır — eskiden "başlatmadan sonra doğan
her Fluent süreci" öldürülüyordu ve bu, aynı anda çalışan diğer işçinin Fluent'ini de öldürürdü.
İsteğe bağlı `cpu_list`: kendi fl_mpi süreçleri bu mantıksal çekirdeklere sabitlenir (Ankara hibrit 4P+4E işlemcisinde
sabitlemesiz 2 eşzamanlı oturum 1,43 s/it; P'ye ve E'ye sabitlenince 0,30 ve 0,43 s/it — ölçüldü).
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


def _alive(pids: set[int]) -> set[int]:
    out = set()
    for pid in pids:
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            p = psutil.Process(pid)
            if p.is_running() and p.status() != psutil.STATUS_ZOMBIE and FLUENT_PROC_RE.match(p.name() or ""):
                out.add(pid)
    return out


def cleanup_own_fluent_processes(own: set[int], grace_s: float = 15.0) -> int:
    """Bu oturumun süreçlerinin (own) kendiliğinden kapanmasını grace_s saniye bekler; yaşayanları ağaçlarıyla
    sonlandırır. Başka işçilerin Fluent süreçlerine dokunmaz."""
    deadline = time.monotonic() + grace_s
    leftovers = _alive(own)
    while leftovers and time.monotonic() < deadline:
        time.sleep(1.0)
        leftovers = _alive(own)
    for pid in sorted(leftovers):
        log.warning("Kapanmayan Fluent süreci sonlandırılıyor: PID %s", pid)
        _kill_tree(pid)
    return len(leftovers)


def _pin(own: set[int], cpu_list: list[int], expect_mpi: int, wait_s: float = 60.0) -> None:
    """Kendi fl_mpi süreçlerini cpu_list'e sabitler (beklenen sayıda fl_mpi görünene kadar en çok wait_s bekler)."""
    deadline = time.monotonic() + wait_s
    while True:
        mpi = [pid for pid in _alive(own) if psutil.Process(pid).name().lower().startswith("fl_mpi")]
        if len(mpi) >= expect_mpi or time.monotonic() > deadline:
            break
        time.sleep(1.0)
    n = 0
    for pid in mpi:
        with contextlib.suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            psutil.Process(pid).cpu_affinity(cpu_list)
            n += 1
    log.info("CPU sabitleme: %d/%d fl_mpi süreci -> çekirdekler %s", n, expect_mpi, cpu_list)


@contextlib.contextmanager
def fluent_solver(machine_cfg: dict, cwd: Path, processor_count: int | None = None,
                  start_timeout: int = 300, exit_timeout: int = 30,
                  cpu_list: list[int] | None = None) -> Iterator[object]:
    """Headless 2ddp Fluent çözücü oturumu (context manager).

    Kullanım:
        with fluent_solver(cfg, cwd=LOG_DIR) as solver:
            solver.settings...
    """
    import ansys.fluent.core as pyfluent

    from .config import DATA_DIR
    from .results_log import _FileLock

    cwd.mkdir(parents=True, exist_ok=True)
    nproc = processor_count or int(machine_cfg["fluent_cores"])
    session = None
    own: set[int] = set()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        # Başlatma kilidi: kilit tutulurken doğan Fluent süreçleri yalnızca bu oturuma aittir.
        with _FileLock(DATA_DIR / "fluent_launch.lock", timeout_s=start_timeout + 600):
            baseline = _fluent_pids()
            try:
                session = pyfluent.launch_fluent(
                    fluent_path=machine_cfg["fluent_exe"],
                    dimension=2,
                    precision="double",
                    processor_count=nproc,
                    ui_mode="no_gui",
                    mode="solver",
                    cwd=str(cwd),
                    start_timeout=start_timeout,
                )
                if cpu_list:
                    own = _fluent_pids() - baseline
                    _pin(own, cpu_list, expect_mpi=nproc)
            finally:
                own = _fluent_pids() - baseline
        yield session
    finally:
        if session is not None:
            try:
                # timeout_force=False: PyFluent'in cleanup .bat araması v241'de başarısız oluyor;
                # zorla kapatmayı cleanup_own_fluent_processes() kendisi yapar.
                session.exit(timeout=exit_timeout, timeout_force=False, wait=False)
            except Exception as exc:  # noqa: BLE001
                log.warning("session.exit() hata verdi: %s", exc)
        n = cleanup_own_fluent_processes(own)
        if n:
            log.info("%d artık Fluent süreci temizlendi", n)
