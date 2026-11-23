"""Orkestratör: SQLite kuyruğu, mesh başına tek Fluent oturumu, warm-start, otomatik kurtarma.

Kullanım:
  # İstanbul (geliştirme) — yalnızca tek koşu:
  .venv\\Scripts\\python.exe src\\03_orchestrator.py --mode single --geom P16_L300 --vel 5
  # Ankara (üretim) — machine_config.json: "allow_batch": true
  .venv\\Scripts\\python.exe src\\03_orchestrator.py --mode batch [--campaign main] [--geoms P01_L200 ...] [--vels 1 2 3]

Denetçi müdahalesi src/rcfd.py ile yapılır (retry / skip / pause / resume / stop).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sys
import time
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import db  # noqa: E402
from common.atmosphere import freestream  # noqa: E402
from common.config import CONFIG_DIR, DATA_DIR, LOG_DIR, MESH_DIR, load_machine_config, load_nose_params, load_velocities  # noqa: E402
from common.fluent_case import run_attempt, set_freestream, setup_physics  # noqa: E402
from common.fluent_session import fluent_solver  # noqa: E402
from common.solver_profile import (OverrideError, load_physics, profile_hash, regime_for,  # noqa: E402
                                   resolve_profile, validate_overrides)

log = logging.getLogger("orchestrator")
FIELDS_DIR = DATA_DIR / "fields"
MAX_LAUNCH_FAILS = 3
MAX_ATTEMPTS = 8
MAX_SESSION_RESTARTS = 3


class SessionBroken(RuntimeError):
    """Fluent oturumu kullanılamaz durumda — yeniden açılmalı."""


# =========================================================================== yardımcılar

def velocity_points(phys: dict) -> list[dict]:
    pts = []
    for p in load_velocities():
        fs = freestream(p["velocity_ms"], p["altitude_m"], phys)
        pts.append({**p, "mach": round(fs.mach, 5), "regime": regime_for(fs.mach)})
    return pts


def main_geoms(final_only: bool = True) -> list[str]:
    """Ana kampanya geometrileri. final_only: serbest parametreli profiller (02/03/04/08/19) yalnızca ön optimizasyonla
    o L için 'selected' değeri yazıldıysa dahil edilir — geçici (provisional) parametreli mesh'ler çözülmez."""
    npar = load_nose_params()
    from common.geometry import load_profile_defs
    free = npar["free_params"]
    out = []
    for L in npar["fixed"]["L_values"]:
        key = f"L{round(L * 1000):03d}"
        for pid in sorted(load_profile_defs()):
            if final_only and pid in free and isinstance(free[pid], dict) and key not in free[pid].get("selected", {}):
                continue
            out.append(f"P{pid}_{key}")
    return out


def geo_meta(gid: str) -> dict:
    """gid: P16_L300 (ana) veya P03_L300_c04 (ön optimizasyon adayı)."""
    npar = load_nose_params()
    m = re.match(r"^P(\d{2})_L(\d{3})(?:_c\d+)?$", gid)
    if not m:
        raise ValueError(f"Geçersiz geometri kimliği: {gid}")
    return {"geom_id": gid, "R": npar["fixed"]["R"], "L": int(m.group(2)) / 1000.0,
            "body_length": npar["fixed"]["body_length"]}


def mesh_path(campaign: str, gid: str) -> Path:
    return (MESH_DIR / f"{gid}.msh.gz") if campaign == "main" else (MESH_DIR / campaign / f"{gid}.msh.gz")


def load_policy() -> dict:
    return json.loads((CONFIG_DIR / "recovery_policy.json").read_text(encoding="utf-8"))


def next_step_overrides(step: dict, prof: dict, current: dict) -> dict:
    """Politika basamağını son denemenin çözülmüş profiline uygular -> yeni override sözlüğü."""
    out = dict(current)
    for k, f in step.get("scale", {}).items():
        v = prof[k] * f
        out[k] = int(round(v)) if isinstance(prof[k], int) else v
    out.update(step.get("set", {}))
    return validate_overrides(out)


def pid_alive(pid: int | None) -> bool:
    try:
        return bool(pid) and psutil.pid_exists(pid) and "python" in psutil.Process(pid).name().lower()
    except psutil.Error:
        return False


def lock_path(worker: str) -> Path:
    return DATA_DIR / f"orchestrator_{worker}.lock"


def acquire_lock(worker: str) -> None:
    lp = lock_path(worker)
    lp.parent.mkdir(parents=True, exist_ok=True)
    if lp.exists():
        try:
            pid = int(lp.read_text().strip())
            if pid_alive(pid):
                raise SystemExit(f"'{worker}' işçisi zaten çalışıyor (PID {pid}). Kilit: {lp}")
        except ValueError:
            pass
    lp.write_text(str(os.getpid()))


def release_lock(worker: str) -> None:
    lp = lock_path(worker)
    try:
        if lp.exists() and lp.read_text().strip() == str(os.getpid()):
            lp.unlink()
    except OSError:
        pass


# =========================================================================== orkestratör

class Orchestrator:
    def __init__(self, campaign: str, mode: str, geoms: list[str] | None, vels: list[int] | None,
                 cores: int | None, idle_hours: float, worker: str = "w1"):
        self.campaign, self.mode, self.worker = campaign, mode, worker
        self.geoms_filter = [g.upper() for g in geoms] if geoms else None
        self.vels_filter = vels
        self.cfg = load_machine_config()
        self.cores = cores or int(self.cfg["fluent_cores"])
        self.phys = load_physics()
        self.policy = load_policy()
        self.idle_hours = idle_hours
        self.machine = self.cfg.get("machine_name", "?")
        self.session_vel: float | None = None

    # ------------------------------------------------------------------ kuyruk
    def _filter_sql(self) -> tuple[str, list]:
        sql, args = " AND campaign=?", [self.campaign]
        if self.geoms_filter:
            sql += f" AND geom_id IN ({','.join('?' * len(self.geoms_filter))})"
            args += self.geoms_filter
        if self.vels_filter:
            sql += f" AND vel_idx IN ({','.join('?' * len(self.vels_filter))})"
            args += list(self.vels_filter)
        return sql, args

    def _drop_dead_claims(self, con) -> None:
        for c in con.execute("SELECT campaign, geom_id, worker, pid FROM claims").fetchall():
            if not pid_alive(c["pid"]):
                con.execute("DELETE FROM claims WHERE campaign=? AND geom_id=?", (c["campaign"], c["geom_id"]))
                db.event(con, "WARNING", "claim_dropped", f"Ölü işçi {c['worker']} (PID {c['pid']}) sahiplenmesi düşürüldü",
                         geom_id=c["geom_id"])

    def claim_geom(self, con) -> str | None:
        """Çözülecek bir geometriyi atomik olarak sahiplenir (çoklu işçi güvenli)."""
        f, a = self._filter_sql()
        con.execute("BEGIN IMMEDIATE")
        try:
            self._drop_dead_claims(con)
            r = con.execute(f"SELECT geom_id FROM runs WHERE status IN ('pending','retry_pending'){f} "
                            f"AND geom_id NOT IN (SELECT geom_id FROM claims WHERE campaign=?) "
                            f"GROUP BY geom_id ORDER BY MAX(priority) DESC, geom_id LIMIT 1",
                            a + [self.campaign]).fetchone()
            if r:
                con.execute("INSERT INTO claims (campaign, geom_id, worker, pid, ts) VALUES (?,?,?,?,?)",
                            (self.campaign, r["geom_id"], self.worker, os.getpid(), db.now()))
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        return r["geom_id"] if r else None

    def release_claim(self, gid: str) -> None:
        with db.connect() as con:
            con.execute("DELETE FROM claims WHERE campaign=? AND geom_id=? AND pid=?", (self.campaign, gid, os.getpid()))

    def next_run(self, con, gid: str):
        f, a = self._filter_sql()
        return con.execute(f"SELECT * FROM runs WHERE geom_id=? AND status IN ('pending','retry_pending'){f} "
                           f"ORDER BY vel_idx LIMIT 1", [gid] + a).fetchone()

    def recover_stale(self, con) -> None:
        """Yaşayan bir işçinin sahiplenmediği 'running' koşular yarım kalmıştır -> yeniden kuyruğa."""
        self._drop_dead_claims(con)
        stale = con.execute("SELECT run_id, geom_id FROM runs WHERE status='running' AND campaign=? "
                            "AND geom_id NOT IN (SELECT geom_id FROM claims WHERE campaign=?)",
                            (self.campaign, self.campaign)).fetchall()
        for r in stale:
            con.execute("UPDATE runs SET status='retry_pending', next_init='neighbor', next_decided_by='auto', "
                        "next_reason='orkestratör yeniden başlatıldı (yarım kalan koşu)', updated_at=? WHERE run_id=?",
                        (db.now(), r["run_id"]))
            db.event(con, "WARNING", "stale_run", "Yarım kalan koşu yeniden kuyruğa alındı", r["run_id"], r["geom_id"])

    def heartbeat(self, con, what: str) -> None:
        db.set_control(con, f"heartbeat:{self.worker}", json.dumps({
            "ts": db.now(), "pid": os.getpid(), "machine": self.machine, "worker": self.worker,
            "cores": self.cores, "current": what}))

    # ------------------------------------------------------------------ kontrol
    def check_control(self, con) -> str:
        if db.get_control(con, "stop_after_current") == "1":
            return "stop"
        if db.get_control(con, "pause") == "1":
            return "pause"
        return "run"

    # ------------------------------------------------------------------ ana döngü
    def run(self) -> int:
        acquire_lock(self.worker)
        launch_fails = 0
        try:
            with db.connect() as con:
                if self.campaign == "main":   # diğer kampanyaların koşularını kendi betikleri kaydeder (ör. 00_preopt.py)
                    pts = velocity_points(self.phys)
                    if self.vels_filter:
                        pts = [p for p in pts if p["index"] in self.vels_filter]
                    added = db.ensure_runs(con, self.campaign, self.geoms_filter or main_geoms(), pts)
                    if added:
                        db.event(con, "INFO", "queue", f"{added} koşu kuyruğa eklendi ({self.campaign})")
                self.recover_stale(con)
                db.event(con, "INFO", "start", f"Orkestratör başladı: worker={self.worker} mode={self.mode} "
                                               f"campaign={self.campaign} cores={self.cores} machine={self.machine} pid={os.getpid()}")
            idle_since = None
            while True:
                with db.connect() as con:
                    ctl = self.check_control(con)
                    if ctl == "stop":
                        db.set_control(con, "stop_after_current", None)
                        db.event(con, "INFO", "stop", "stop_after_current isteğiyle durduruldu")
                        return 0
                    if ctl == "pause":
                        self.heartbeat(con, "paused")
                        time.sleep(30)
                        continue
                    gid = self.claim_geom(con)
                    if gid is None:
                        left = con.execute("SELECT COUNT(*) n FROM runs WHERE status='needs_review' AND campaign=?",
                                           (self.campaign,)).fetchone()["n"]
                        others = con.execute("SELECT COUNT(*) n FROM claims WHERE campaign=? AND pid<>?",
                                             (self.campaign, os.getpid())).fetchone()["n"]
                        if self.mode != "single" and others:
                            self.heartbeat(con, f"bekliyor (diğer işçiler {others} geometride çalışıyor)")
                            time.sleep(60)
                            continue
                        if self.mode == "single" or left == 0:
                            db.event(con, "INFO", "complete", f"Kuyruk boş. needs_review: {left}")
                            return 0
                        if idle_since is None:
                            idle_since = time.time()
                            db.event(con, "WARNING", "idle", f"Çözülebilir koşu kalmadı; {left} koşu denetçi incelemesi bekliyor")
                        if time.time() - idle_since > self.idle_hours * 3600:
                            db.event(con, "WARNING", "idle_exit", "Bekleme süresi doldu, çıkılıyor")
                            return 0
                        self.heartbeat(con, f"idle (needs_review={left})")
                        time.sleep(60)
                        continue
                    idle_since = None
                try:
                    status = self.process_geom(gid)
                finally:
                    self.release_claim(gid)
                if status == "launch_failed":
                    launch_fails += 1
                    if launch_fails >= MAX_LAUNCH_FAILS:
                        with db.connect() as con:
                            db.event(con, "ERROR", "worker_exit",
                                     f"{self.worker}: Fluent art arda {launch_fails} kez açılamadı (lisans/kurulum?); işçi çıkıyor")
                        return 3
                    time.sleep(60)
                else:
                    launch_fails = 0
        finally:
            release_lock(self.worker)

    # ------------------------------------------------------------------ geometri (oturum)
    def process_geom(self, gid: str) -> str:
        """Dönüş: 'ok' | 'launch_failed' (Fluent hiç açılamadı — koşular cezalandırılmaz)."""
        msh = mesh_path(self.campaign, gid)
        if not msh.exists():
            with db.connect() as con:
                f, a = self._filter_sql()
                con.execute(f"UPDATE runs SET status='mesh_error', updated_at=? WHERE geom_id=? "
                            f"AND status IN ('pending','retry_pending'){f}", [db.now(), gid] + a)
                db.event(con, "ERROR", "mesh_error", f"Mesh dosyası yok: {msh}", geom_id=gid)
            return "ok"
        meta = geo_meta(gid)
        restarts = 0
        opened_once = False
        while restarts <= MAX_SESSION_RESTARTS:
            sess_dir = LOG_DIR / "sessions" / f"{gid}_{time.strftime('%Y%m%d-%H%M%S')}"
            sess_dir.mkdir(parents=True, exist_ok=True)
            try:
                with fluent_solver(self.cfg, cwd=sess_dir, processor_count=self.cores) as solver:
                    opened_once = True
                    solver.tui.file.start_transcript(str(sess_dir / "fluent.trn"))
                    setup_physics(solver, msh, meta, self.phys, sess_dir)
                    with db.connect() as con:
                        db.event(con, "INFO", "session_open", f"Fluent oturumu açıldı ({self.cores} çekirdek)", geom_id=gid)
                    prev_ok = False
                    self.session_vel = None
                    while True:
                        with db.connect() as con:
                            if self.check_control(con) != "run":
                                return "ok"
                            self.heartbeat(con, f"{gid} oturumu açık")
                            run = self.next_run(con, gid)
                        if run is None:
                            return "ok"
                        prev_ok = self.execute_run(solver, dict(run), meta, prev_ok)
                        if self.mode == "single":
                            with db.connect() as con:
                                r = con.execute("SELECT status FROM runs WHERE run_id=?", (run["run_id"],)).fetchone()
                            if r["status"] not in db.RUNNABLE:
                                return "ok"
            except SessionBroken as exc:
                restarts += 1
                with db.connect() as con:
                    db.event(con, "ERROR", "session_restart", f"Fluent oturumu yeniden açılıyor ({restarts}/{MAX_SESSION_RESTARTS}): {exc}",
                             geom_id=gid)
            except Exception as exc:  # noqa: BLE001 — kurulum/oturum hatası
                log.exception("%s oturum hatası", gid)
                with db.connect() as con:
                    db.event(con, "ERROR", "session_error", f"{type(exc).__name__}: {str(exc)[:300]}", geom_id=gid)
                if not opened_once:          # Fluent hiç açılamadı: lisans/kurulum sorunu — koşulara dokunma
                    return "launch_failed"
                restarts += 1
        with db.connect() as con:
            f, a = self._filter_sql()
            con.execute(f"UPDATE runs SET status='needs_review', updated_at=? WHERE geom_id=? "
                        f"AND status IN ('pending','retry_pending','running'){f}", [db.now(), gid] + a)
            db.event(con, "ERROR", "geom_abandoned", "Oturum tekrar tekrar çöktü; geometri denetçiye bırakıldı", geom_id=gid)
        return "ok"

    # ------------------------------------------------------------------ tek koşu + kurtarma
    def _fields_dir(self, gid: str) -> Path:
        return FIELDS_DIR / (gid if self.campaign == "main" else f"{self.campaign}/{gid}")

    def _auto_warm_ok(self, gid: str, prev_ok: bool, v_new: float, max_ratio: float) -> tuple[bool, str]:
        """Otomatik warm-start yalnızca kaynak alanın hızı yeterince yakınsa: max(v/v0, v0/v) ≤ max_ratio."""
        if prev_ok and self.session_vel:
            v0 = self.session_vel
        else:
            meta = self._fields_dir(gid) / "latest.json"
            if not meta.exists():
                return False, "kaynak alan yok"
            idx = json.loads(meta.read_text(encoding="utf-8"))["vel_idx"]
            v0 = {p["index"]: p["velocity_ms"] for p in load_velocities()}[idx]
        ratio = max(v_new / v0, v0 / v_new)
        return ratio <= max_ratio, f"hız oranı {ratio:.2f} (sınır {max_ratio})"

    def _init_for(self, run: dict, gid: str, prev_ok: bool, last_workdir: Path | None,
                  v_new: float | None = None, max_ratio: float | None = None) -> tuple[str, Path | None]:
        if not run.get("next_init") and v_new and max_ratio:
            ok, why = self._auto_warm_ok(gid, prev_ok, v_new, max_ratio)
            if not ok:
                log.info("  warm-start yerine soğuk başlatma: %s", why)
                return "hybrid", None
        want = run.get("next_init") or ("previous" if prev_ok else "neighbor")
        latest = self._fields_dir(gid) / "latest.dat.h5"
        if want == "previous":
            return ("previous", None) if (prev_ok or run.get("next_init") == "previous") else self._init_for(
                {**run, "next_init": "neighbor"}, gid, False, last_workdir)
        if want == "last_good":
            lg = (last_workdir / "last_good.dat.h5") if last_workdir else None
            if lg and lg.exists():
                return "file", lg
            want = "neighbor"
        if want == "neighbor":
            return ("file", latest) if latest.exists() else ("hybrid", None)
        return want, None   # hybrid | fmg

    def execute_run(self, solver, run: dict, meta: dict, prev_ok: bool) -> bool:
        """Koşuyu kurtarma basamaklarıyla çözer. Dönüş: oturumdaki alan yakınsamış mı (sonraki hız için)."""
        gid, rid = run["geom_id"], run["run_id"]
        pts = {p["index"]: p for p in load_velocities()}
        p = pts[run["vel_idx"]]
        fs = freestream(p["velocity_ms"], p["altitude_m"], self.phys)
        last_workdir = None
        with db.connect() as con:
            last = con.execute("SELECT workdir FROM attempts WHERE run_id=? ORDER BY attempt_no DESC LIMIT 1", (rid,)).fetchone()
            if last and last["workdir"]:
                last_workdir = Path(last["workdir"])

        while True:
            with db.connect() as con:
                run = dict(con.execute("SELECT * FROM runs WHERE run_id=?", (rid,)).fetchone())
                if run["n_attempts"] - (run["budget_base"] or 0) >= MAX_ATTEMPTS:
                    con.execute("UPDATE runs SET status='needs_review', updated_at=? WHERE run_id=?", (db.now(), rid))
                    db.event(con, "WARNING", "needs_review", f"Deneme sınırı ({MAX_ATTEMPTS}) doldu", rid, gid)
                    return False
            try:
                overrides = validate_overrides(json.loads(run["next_overrides"] or "{}"))
            except OverrideError as exc:
                with db.connect() as con:
                    con.execute("UPDATE runs SET status='needs_review', updated_at=? WHERE run_id=?", (db.now(), rid))
                    db.event(con, "ERROR", "bad_override", str(exc), rid, gid)
                return False
            prof, regime = resolve_profile(fs.mach, overrides)
            init_method, init_file = self._init_for(run, gid, prev_ok, last_workdir,
                                                    fs.velocity, prof["warm_max_velocity_ratio"])
            attempt_no = run["n_attempts"] + 1
            workdir = LOG_DIR / "runs" / f"{gid}_v{run['vel_idx']:02d}" / f"a{attempt_no}_{time.strftime('%Y%m%d-%H%M%S')}"
            decided_by = run["next_decided_by"] or "auto"
            reason = run["next_reason"] or ("ilk deneme" if attempt_no == 1 else "")
            started = db.now()
            with db.connect() as con:
                con.execute("UPDATE runs SET status='running', n_attempts=?, regime=?, mach=?, updated_at=? WHERE run_id=?",
                            (attempt_no, regime, fs.mach, started, rid))
                self.heartbeat(con, f"{gid} v{run['vel_idx']:02d} deneme {attempt_no} ({init_method})")
            log.info("%s v%02d deneme %d: M=%.3f %s init=%s override=%s", gid, run["vel_idx"], attempt_no,
                     fs.mach, regime, init_method, overrides or "-")
            try:
                set_freestream(solver, fs, meta, self.phys)
                res = run_attempt(solver, prof, workdir, fresh_init=init_method in ("hybrid", "fmg"),
                                  init_method=init_method, init_file=init_file)
                outcome, broken = res.outcome, False
            except Exception as exc:  # noqa: BLE001 — Fluent/gRPC çökmesi
                log.exception("%s v%02d: oturum hatası", gid, run["vel_idx"])
                from common.fluent_case import AttemptResult
                res = AttemptResult(outcome="crash", cd=None, iterations=0, elapsed_s=0.0,
                                    message=f"{type(exc).__name__}: {str(exc)[:300]}")
                outcome, broken = "crash", True

            ok = outcome in db.FINAL_OK
            with db.connect() as con:
                con.execute(
                    "INSERT INTO attempts (run_id, attempt_no, started_at, ended_at, profile_hash, profile_json, overrides_json, "
                    "init_method, outcome, cd, iterations, elapsed_s, cd_rel_std, cd_rel_drift, cd_rel_amp, message, workdir, "
                    "decided_by, reason, machine) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (rid, attempt_no, started, db.now(), profile_hash(prof), json.dumps(prof), json.dumps(overrides),
                     init_method if init_file is None else f"{init_method}:{init_file.name}", outcome, res.cd,
                     res.iterations, res.elapsed_s, res.cd_rel_std, res.cd_rel_drift, res.cd_rel_amp, res.message,
                     str(workdir), decided_by, reason, self.machine))
                if ok:
                    con.execute("UPDATE runs SET status=?, cd=?, cd_flagged=?, next_overrides=NULL, next_init=NULL, "
                                "next_decided_by=NULL, next_reason=NULL, updated_at=? WHERE run_id=?",
                                (outcome, res.cd, int(outcome == "done_flagged"), db.now(), rid))
                    db.event(con, "INFO", outcome, f"Cd={res.cd:.5f} it={res.iterations} {res.elapsed_s:.0f}s "
                                                   f"{res.message}".strip(), rid, gid)
            if ok:
                self._save_fields(solver, gid, run["vel_idx"], workdir)
                self.session_vel = fs.velocity
                return True

            # ---- başarısız: politika basamağı
            ladder = self.policy.get(outcome, [])
            with db.connect() as con:
                # Basamak indeksi: son denetçi/insan müdahalesinden (budget_base) sonraki aynı sınıftaki başarısızlıklar.
                # Denetçi denemesi başarısız olursa otomatik basamaklar onun override'larını taban alarak devam eder.
                base = run["budget_base"] or 0
                k = con.execute("SELECT COUNT(*) n FROM attempts WHERE run_id=? AND outcome=? AND attempt_no>?",
                                (rid, outcome, base)).fetchone()["n"] - 1
                if k >= len(ladder):
                    con.execute("UPDATE runs SET status='needs_review', updated_at=? WHERE run_id=?", (db.now(), rid))
                    db.event(con, "WARNING", "needs_review", f"{outcome}: {res.message} — otomatik basamaklar bitti", rid, gid)
                    if broken:
                        raise SessionBroken(res.message)
                    return False
                step = ladder[k]
                try:
                    new_ov = next_step_overrides(step, prof, overrides)
                except OverrideError as exc:
                    con.execute("UPDATE runs SET status='needs_review', updated_at=? WHERE run_id=?", (db.now(), rid))
                    db.event(con, "ERROR", "bad_policy", f"Politika basamağı geçersiz: {exc}", rid, gid)
                    return False
                con.execute("UPDATE runs SET status='retry_pending', next_overrides=?, next_init=?, next_decided_by='auto', "
                            "next_reason=?, updated_at=? WHERE run_id=?",
                            (json.dumps(new_ov), step["init"], f"politika {outcome}[{k}]", db.now(), rid))
                db.event(con, "WARNING", "retry", f"{outcome} ({res.message}) -> basamak {k + 1}/{len(ladder)}: "
                                                  f"init={step['init']} override={new_ov}", rid, gid)
            last_workdir = workdir
            prev_ok = False
            if broken or step.get("restart_session"):
                raise SessionBroken(res.message or outcome)

    def _save_fields(self, solver, gid: str, vel_idx: int, workdir: Path) -> None:
        d = FIELDS_DIR / (gid if self.campaign == "main" else f"{self.campaign}/{gid}")
        d.mkdir(parents=True, exist_ok=True)
        latest = d / "latest.dat.h5"
        try:
            solver.settings.file.write_data(file_name=str(latest.resolve()))
            (d / "latest.json").write_text(json.dumps({"vel_idx": vel_idx, "ts": db.now()}), encoding="utf-8")
            vmin, vmax = 1, len(load_velocities())
            if self.campaign == "main" and vel_idx in (vmin, vmax):
                shutil.copy2(latest, d / f"v{vel_idx:02d}.dat.h5")    # görsel doğrulama için saklanır
        except Exception as exc:  # noqa: BLE001
            log.warning("%s alan dosyası yazılamadı: %s", gid, exc)
        lg = workdir / "last_good.dat.h5"
        lg.unlink(missing_ok=True)     # başarılı koşunun checkpoint'i gereksiz (disk)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("single", "batch"), required=True)
    ap.add_argument("--campaign", default="main")
    ap.add_argument("--geom", help="single mod: geometri")
    ap.add_argument("--vel", type=int, help="single mod: hız indeksi")
    ap.add_argument("--geoms", nargs="*", help="batch: geometri filtresi")
    ap.add_argument("--vels", nargs="*", type=int, help="batch: hız filtresi")
    ap.add_argument("--cores", type=int)
    ap.add_argument("--worker", default="w1", help="işçi adı (çoklu işçi: w1, w2, ...)")
    ap.add_argument("--idle-hours", type=float, default=12.0,
                    help="batch: kuyruk boşalıp yalnızca needs_review kalınca denetçiyi bekleme süresi")
    args = ap.parse_args()

    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(LOG_DIR / "orchestrator.log", encoding="utf-8"),
                                  logging.StreamHandler(sys.stdout)])
    logging.getLogger("ansys").setLevel(logging.WARNING)

    cfg = load_machine_config()
    if args.mode == "batch" and not cfg.get("allow_batch", False):
        log.error("Bu makinede batch kapalı (machine_config.json: allow_batch=false). İstanbul'da yalnızca --mode single.")
        return 2
    if args.mode == "single":
        if not (args.geom and args.vel):
            ap.error("single mod için --geom ve --vel gerekli")
        geoms, vels = [args.geom], [args.vel]
    else:
        geoms, vels = args.geoms, args.vels
    worker = "single" if args.mode == "single" else args.worker
    orch = Orchestrator(args.campaign, args.mode, geoms, vels, args.cores, args.idle_hours, worker)
    return orch.run()


if __name__ == "__main__":
    sys.exit(main())
