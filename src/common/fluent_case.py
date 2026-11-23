"""Fluent vaka kurulumu ve izlenen çözüm denemesi (tek hız noktası).

Kullanım sırası (bir mesh oturumu içinde):
    setup_physics(solver, msh, geo_meta, phys, workdir)     # bir kez — FİZİK KİLİDİ
    set_freestream(solver, fs, geo_meta, phys)              # her hız noktasında (BC + Reference Values)
    res = run_attempt(solver, prof, workdir, fresh_init=...) # izlenen çözüm

Başarısızlık sınıfları: diverged | oscillating | stalled | crash | timeout ; başarı: done | done_flagged
"""
from __future__ import annotations

import csv
import json
import logging
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from .atmosphere import Freestream

log = logging.getLogger(__name__)

PF = "farfield", "inlet", "outlet"        # pressure-far-field bölgeleri


# =========================================================================== kurulum (fizik kilidi)

def setup_physics(solver, msh: Path, geo_meta: dict, phys: dict, workdir: Path) -> None:
    st = solver.settings
    st.file.read_case(file_name=str(Path(msh).resolve()))
    g = st.setup.general
    g.solver.type = "density-based-implicit"      # varsayılan; profil isterse apply_numerics değiştirir
    g.solver.two_dim_space = phys["two_dim_space"]
    g.operating_conditions.operating_pressure = phys["operating_pressure"]

    st.setup.models.energy.enabled = phys["energy"]
    v = st.setup.models.viscous
    v.model = phys["viscous_model"]
    v.k_omega_model = phys["k_omega_model"]

    air = st.setup.materials.fluid["air"]
    a = phys["air"]
    air.density.option = a["density"]
    air.viscosity.option = a["viscosity"]
    air.specific_heat.option = "constant"
    air.specific_heat.value = a["cp"]
    air.thermal_conductivity.option = "constant"
    air.thermal_conductivity.value = a["thermal_conductivity"]

    rd = st.solution.report_definitions.drag
    if "cd" not in rd.get_object_names():
        rd.create(name="cd")
    rd["cd"].zones = [phys["drag_zone"]]
    rd["cd"].force_vector = phys["drag_direction"]

    # Fluent'in residual tabanlı otomatik durdurması kapalı — yakınsamaya biz karar veririz
    eqs = st.solution.monitor.residual.equations
    for eq in eqs():
        eqs[eq].check_convergence = False
    st.solution.monitor.residual.options.n_save = 100000


def set_report_file(solver, out_path: Path) -> None:
    rf = solver.settings.solution.monitor.report_files
    if "cd-file" not in rf.get_object_names():
        rf.create(name="cd-file")
    rf["cd-file"].report_defs = ["cd"]
    rf["cd-file"].file_name = str(out_path)
    rf["cd-file"].frequency = 1


def set_freestream(solver, fs: Freestream, geo_meta: dict, phys: dict) -> None:
    st = solver.settings
    ti = phys["freestream_turbulence"]
    for z in PF:
        ff = st.setup.boundary_conditions.pressure_far_field[z]
        ff.gauge_pressure.value = fs.p           # operating pressure = 0 -> gauge = mutlak statik
        ff.m.value = fs.mach
        ff.t.value = fs.T
        ff.flow_direction = [1.0, 0.0]
        ff.turbulent_specification = "Intensity and Viscosity Ratio"
        ff.turbulent_intensity = ti["intensity"]
        # v241: k-ω'da etkin olan anahtar 'turbulent_viscosity_ratio_real' ('turbulent_viscosity_ratio' pasif)
        tvr = ff.turbulent_viscosity_ratio_real
        if "value" in (getattr(tvr, "child_names", None) or []):
            tvr.value = ti["viscosity_ratio"]
        else:
            ff.turbulent_viscosity_ratio_real = ti["viscosity_ratio"]

    R = geo_meta["R"]
    ref = st.setup.reference_values
    ref.area = math.pi * R * R
    ref.length = geo_meta["L"] + geo_meta["body_length"]
    ref.density = fs.rho
    ref.velocity = fs.velocity
    ref.temperature = fs.T
    ref.pressure = fs.p
    ref.viscosity = fs.mu


def read_reference_values(solver) -> dict:
    return dict(solver.settings.setup.reference_values())


# =========================================================================== sayısal ayarlar

def apply_numerics(solver, prof: dict, second_order: bool) -> None:
    st = solver.settings
    if st.setup.general.solver.type() != prof["solver_type"]:
        st.setup.general.solver.type = prof["solver_type"]
    m = st.solution.methods
    m.gradient_scheme = prof["gradient"]
    order = "second-order-upwind" if second_order else "first-order-upwind"
    if prof["solver_type"].startswith("density"):
        try:
            m.flux_type.dbns_cases.flux_type = prof["flux_type"]
        except Exception as exc:  # noqa: BLE001
            log.warning("flux_type ayarlanamadı (%s): %s", prof["flux_type"], exc)
        ds = m.discretization_scheme
        for k in ds():
            ds[k] = order
    else:
        m.p_v_coupling.flow_scheme = "Coupled"
        ds = m.discretization_scheme
        for k in ds():
            ds[k] = order if k != "pressure" else ("second-order" if second_order else "standard")


def set_courant(solver, prof: dict, it: int) -> float:
    r = prof["courant_ramp_iters"]
    c0, c1 = prof["courant_start"], prof["courant_end"]
    c = c1 if r <= 0 or it >= r else c0 * (c1 / c0) ** (it / r)     # geometrik rampa
    st = solver.settings.solution.controls
    if prof["solver_type"].startswith("density"):
        st.courant_number = float(c)
    else:
        st.p_v_controls.flow_courant_number = float(c)
    return c


def initialize(solver, method: str, last_good: Path | None = None) -> None:
    init = solver.settings.solution.initialization
    if method == "last_good" and last_good and last_good.exists():
        solver.settings.file.read_data(file_name=str(last_good))
        return
    if method == "previous":
        return                                 # warm-start: mevcut alan korunur
    init.initialization_type = "hybrid"
    init.hybrid_initialize()
    if method == "fmg":
        solver.tui.solve.initialize.fmg_initialize("yes")


# =========================================================================== izleme

def read_out_file(path: Path) -> tuple[np.ndarray, np.ndarray]:
    its, vals = [], []
    if not path.exists():
        return np.array(its), np.array(vals)
    for line in path.read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) >= 2:
            try:
                its.append(int(float(parts[0])))
                vals.append(float(parts[1]))
            except ValueError:
                continue
    return np.array(its), np.array(vals)


def read_residuals(solver) -> dict[str, np.ndarray]:
    try:
        data = solver.monitors.get_monitor_set_data(monitor_set_name="residual")
        _, series = data
        return {k: np.asarray(v, float) for k, v in series.items()}
    except Exception as exc:  # noqa: BLE001
        log.debug("residual okunamadı: %s", exc)
        return {}


def window_stats(cd: np.ndarray, w: int) -> dict:
    seg = cd[-w:]
    mean = float(np.mean(seg))
    std = float(np.std(seg))
    half = len(seg) // 2
    drift = abs(float(np.mean(seg[half:]) - np.mean(seg[:half])))
    amp = float(seg.max() - seg.min()) / 2
    den = abs(mean) if mean else 1.0
    return {"mean": mean, "rel_std": std / den, "rel_drift": drift / den, "rel_amp": amp / den}


@dataclass
class AttemptResult:
    outcome: str
    cd: float | None
    iterations: int
    elapsed_s: float
    cd_rel_std: float | None = None
    cd_rel_drift: float | None = None
    cd_rel_amp: float | None = None
    residual_drop_orders: dict = field(default_factory=dict)
    message: str = ""
    last_good: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def run_attempt(solver, prof: dict, workdir: Path, fresh_init: bool = True,
                init_method: str | None = None) -> AttemptResult:
    """Profilde tanımlı izlenen çözüm. workdir: cd.out, history.csv, last_good.dat.h5, result.json."""
    workdir.mkdir(parents=True, exist_ok=True)
    out = workdir / "cd.out"
    out.unlink(missing_ok=True)
    set_report_file(solver, out)
    last_good = workdir / "last_good.dat.h5"
    t0 = time.time()

    method = init_method or (prof["init_method"] if fresh_init else "previous")
    apply_numerics(solver, prof, second_order=prof["first_order_iters"] <= 0)
    initialize(solver, method, last_good)

    it = 0
    switched = prof["first_order_iters"] <= 0
    switch_it = 0 if switched else None
    res0: dict[str, float] = {}
    hist_rows = []
    outcome, msg = None, ""

    while it < prof["max_iters"]:
        if time.time() - t0 > prof["timeout_s"]:
            outcome, msg = "timeout", f"{prof['timeout_s']} s aşıldı"
            break
        if not switched and it >= prof["first_order_iters"]:
            apply_numerics(solver, prof, second_order=True)
            switched, switch_it = True, it
            log.info("  it=%d: ikinci dereceye geçildi", it)
        c = set_courant(solver, prof, it)
        n = min(prof["check_interval"], prof["max_iters"] - it)
        try:
            solver.settings.solution.run_calculation.iterate(iter_count=n)
        except Exception as exc:  # noqa: BLE001
            txt = str(exc)
            outcome = "diverged" if any(s in txt.lower() for s in ("diverg", "floating point", "nan")) else "crash"
            msg = txt[:400]
            break

        its, cd = read_out_file(out)
        done_it = int(its[-1]) if len(its) else it
        if done_it < it + n:   # Fluent iterasyonu erken kesti (ör. divergence detected)
            outcome, msg = "diverged", f"Fluent iterasyonu {done_it}'te kesti (beklenen {it + n})"
            it = done_it
            break
        it = done_it
        if len(cd) == 0 or not np.all(np.isfinite(cd[-n:])):
            outcome, msg = "diverged", "Cd NaN/Inf"
            break

        resid = read_residuals(solver)
        last = {k: float(v[-1]) for k, v in resid.items() if len(v)}
        for k, v in last.items():
            if k not in res0 and v > 0:
                res0[k] = v
        growth = {k: math.log10(last[k] / res0[k]) for k in last if k in res0 and last[k] > 0}
        hist_rows.append({"iter": it, "courant": c, "cd": float(cd[-1]),
                          **{f"res_{k}": v for k, v in last.items()}})
        if growth and max(growth.values()) > prof["div_residual_growth_orders"]:
            outcome, msg = "diverged", f"residual {max(growth, key=growth.get)} {max(growth.values()):.1f} mertebe arttı"
            break

        if it % prof["checkpoint_interval"] < n:
            try:
                solver.settings.file.write_data(file_name=str(last_good))
            except Exception as exc:  # noqa: BLE001
                log.warning("checkpoint yazılamadı: %s", exc)

        # Yakınsama: ikinci derecede en az conv_window iterasyon ve min_iters
        w = prof["conv_window"]
        if switched and it - switch_it >= w and it >= prof["min_iters"]:
            ws = window_stats(cd, w)
            if ws["rel_std"] < prof["conv_cd_rel_std"] and ws["rel_drift"] < prof["conv_cd_rel_drift"]:
                outcome = "done"
                break

    _write_history(workdir / "history.csv", hist_rows)
    its, cd = read_out_file(out)
    ws = window_stats(cd, min(prof["conv_window"], len(cd))) if len(cd) >= 20 else None
    if outcome is None:   # max_iters doldu
        if ws and switched and ws["rel_amp"] < prof["osc_accept_rel_amp"] and ws["rel_drift"] < prof["osc_accept_rel_amp"] / 2:
            outcome, msg = "done_flagged", f"pencere kriteri sağlanmadı; salınım ±{ws['rel_amp']:.2%} kabul sınırında"
        elif ws and ws["rel_drift"] >= ws["rel_amp"] / 2:
            outcome, msg = "stalled", "max_iters doldu; Cd sürükleniyor"
        else:
            outcome, msg = "oscillating", f"max_iters doldu; salınım ±{(ws or {}).get('rel_amp', float('nan')):.2%}"

    ok = outcome in ("done", "done_flagged")
    if ok and not switched:
        outcome, ok, msg = "stalled", False, "ikinci dereceye geçilmeden bitti (geçerlilik kuralı)"
    resid_drop = {}
    resid = read_residuals(solver)
    for k, v in resid.items():
        if len(v) and v[0] > 0 and v[-1] > 0:
            resid_drop[k] = round(math.log10(v[0] / v[-1]), 2)

    res = AttemptResult(
        outcome=outcome, cd=ws["mean"] if (ok and ws) else None, iterations=int(it),
        elapsed_s=round(time.time() - t0, 1),
        cd_rel_std=ws["rel_std"] if ws else None, cd_rel_drift=ws["rel_drift"] if ws else None,
        cd_rel_amp=ws["rel_amp"] if ws else None, residual_drop_orders=resid_drop, message=msg,
        last_good=str(last_good) if last_good.exists() else None,
    )
    (workdir / "result.json").write_text(json.dumps(res.as_dict(), indent=2), encoding="utf-8")
    return res


def _write_history(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    keys = sorted({k for r in rows for k in r}, key=lambda k: (k != "iter", k != "courant", k != "cd", k))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
