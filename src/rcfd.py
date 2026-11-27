"""rcfd — RocketCFD denetçi CLI (Ankara'daki Claude Code ve insan operatör için).

Okuma:
  rcfd status                      ilerleme, durum dağılımı, kalp atışı, tahmini kalan süre
  rcfd failures                    needs_review koşuları (son sonuç + mesaj)
  rcfd inspect <run>               deneme geçmişi + Cd/residual grafiği (logs/inspect/<run>.png)
  rcfd events [--tail N] [--level WARNING]
  rcfd profile <run>               bu koşu için birleşik profil (rejim + override)
  rcfd export                      sonuç tabloları -> docs/results/

Müdahale (her biri --reason zorunlu; decided_by = agent | human):
  rcfd retry <run> [--set k=v ...] [--init previous|last_good|neighbor|hybrid|fmg] --reason "..."
  rcfd requeue --status needs_review [--regime transonic] [--geom P04_L400] [--set k=v] --reason "..."
  rcfd skip <run> --reason "..."
  rcfd priority <geom> <n>
  rcfd pause | resume | stop       (stop = TÜM işçiler mevcut koşu bitince çıkar; bayrak `resume`'a kadar kalır)

<run>: run_id veya GEOM:VEL (ör. P16_L300:17). Kullanım: .venv\\Scripts\\python.exe src\\rcfd.py <komut> ...
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import db  # noqa: E402
from common.config import DOCS_DIR, LOG_DIR  # noqa: E402
from common.solver_profile import ALLOWED_OVERRIDES, OverrideError, resolve_profile, validate_overrides  # noqa: E402

INIT_CHOICES = ("previous", "last_good", "neighbor", "hybrid", "fmg")


def _who(args) -> str:
    return "human" if getattr(args, "human", False) else "agent"


def _parse_sets(items) -> dict:
    out = {}
    for s in items or []:
        k, sep, v = s.partition("=")
        if not sep:
            raise SystemExit(f"--set biçimi anahtar=değer olmalı: {s!r}")
        out[k.strip()] = v.strip()
    return out


def _run_or_die(con, ref: str, campaign: str):
    r = db.find_run(con, ref, campaign)
    if r is None:
        raise SystemExit(f"Koşu bulunamadı: {ref} (campaign={campaign})")
    return r


# --------------------------------------------------------------------------- okuma

def cmd_status(con, args) -> None:
    c = args.campaign
    rows = con.execute("SELECT status, COUNT(*) n FROM runs WHERE campaign=? GROUP BY status", (c,)).fetchall()
    total = sum(r["n"] for r in rows)
    counts = {r["status"]: r["n"] for r in rows}
    done = counts.get("done", 0) + counts.get("done_flagged", 0)
    print(f"Kampanya: {c}   toplam {total}   tamamlanan {done} (%{100 * done / max(total, 1):.1f})")
    for s in ("done", "done_flagged", "running", "pending", "retry_pending", "needs_review", "skipped", "mesh_error"):
        if counts.get(s):
            print(f"  {s:<14} {counts[s]:5d}")
    print("Rejime göre (tamamlanan / toplam, ort. koşu süresi):")
    for r in con.execute(
            "SELECT r.regime, COUNT(*) n, SUM(r.status IN ('done','done_flagged')) d, "
            "(SELECT AVG(a.elapsed_s) FROM attempts a JOIN runs r2 ON a.run_id=r2.run_id "
            " WHERE r2.regime=r.regime AND r2.campaign=? AND a.outcome IN ('done','done_flagged')) t "
            "FROM runs r WHERE r.campaign=? GROUP BY r.regime", (c, c)).fetchall():
        t = f"{r['t'] / 60:.1f} dk" if r["t"] else "-"
        print(f"  {str(r['regime']):<11} {r['d'] or 0:4d}/{r['n']:<4d}  {t}")
    # tahmini kalan süre: rejim ort. süresi × kalan koşu
    eta = 0.0
    for r in con.execute(
            "SELECT regime, SUM(status IN ('pending','retry_pending','running')) k FROM runs WHERE campaign=? GROUP BY regime",
            (c,)).fetchall():
        t = con.execute("SELECT AVG(a.elapsed_s) t FROM attempts a JOIN runs r ON a.run_id=r.run_id "
                        "WHERE r.regime=? AND a.outcome IN ('done','done_flagged')", (r["regime"],)).fetchone()["t"]
        if t and r["k"]:
            eta += t * r["k"]
    if eta:
        print(f"Tahmini kalan süre (sıralı, ek deneme hariç): {eta / 3600:.1f} saat")
    for row in con.execute("SELECT key, value FROM control WHERE key LIKE 'heartbeat%' ORDER BY key").fetchall():
        h = json.loads(row["value"])
        age = time.time() - time.mktime(time.strptime(h["ts"], "%Y-%m-%d %H:%M:%S"))
        flag = "" if age < 900 else "   <-- UYARI: 15 dk'dan eski, işçi çalışıyor mu?"
        print(f"İşçi {h.get('worker', '?'):<6} {h['ts']} ({age / 60:.0f} dk önce) pid={h['pid']} "
              f"{h.get('cores', '?')} çekirdek: {h['current']}{flag}")
    for cl in con.execute("SELECT * FROM claims WHERE campaign=?", (c,)).fetchall():
        print(f"  sahiplenilmiş: {cl['geom_id']} <- {cl['worker']} (PID {cl['pid']}, {cl['ts']})")
    for k in ("pause", "stop_after_current"):
        if db.get_control(con, k) == "1":
            print(f"Kontrol: {k} AKTİF")


def cmd_failures(con, args) -> None:
    rows = con.execute(
        "SELECT r.run_id, r.geom_id, r.vel_idx, r.mach, r.regime, r.n_attempts, a.outcome, a.message, a.decided_by "
        "FROM runs r LEFT JOIN attempts a ON a.attempt_id = (SELECT MAX(attempt_id) FROM attempts WHERE run_id=r.run_id) "
        "WHERE r.campaign=? AND r.status='needs_review' ORDER BY r.geom_id, r.vel_idx", (args.campaign,)).fetchall()
    if not rows:
        print("needs_review koşu yok.")
        return
    for r in rows:
        print(f"[{r['run_id']}] {r['geom_id']}:{r['vel_idx']:<2d} M={r['mach']:.3f} {r['regime']:<10} "
              f"deneme={r['n_attempts']} son={r['outcome']} ({r['decided_by']}): {(r['message'] or '')[:150]}")


def cmd_inspect(con, args) -> None:
    run = _run_or_die(con, args.run, args.campaign)
    print(f"[{run['run_id']}] {run['geom_id']}:{run['vel_idx']}  M={run['mach']}  {run['regime']}  "
          f"durum={run['status']}  Cd={run['cd']}  flagged={run['cd_flagged']}")
    if run["next_overrides"] or run["next_init"]:
        print(f"  sıradaki deneme: init={run['next_init']} override={run['next_overrides']} "
              f"({run['next_decided_by']}: {run['next_reason']})")
    atts = con.execute("SELECT * FROM attempts WHERE run_id=? ORDER BY attempt_no", (run["run_id"],)).fetchall()
    for a in atts:
        cd = f"{a['cd']:.5f}" if a["cd"] is not None else "-"
        print(f"  #{a['attempt_no']} {a['outcome']:<12} Cd={cd} it={a['iterations']} {a['elapsed_s'] or 0:.0f}s "
              f"init={a['init_method']} by={a['decided_by']} override={a['overrides_json']}")
        if a["message"]:
            print(f"      mesaj: {a['message'][:300]}")
        if a["reason"]:
            print(f"      gerekçe: {a['reason']}")
    if not atts:
        return
    wd = Path(atts[-1]["workdir"])
    hist = wd / "history.csv"
    print(f"  son deneme klasörü: {wd}")
    if hist.exists():
        import pandas as pd
        h = pd.read_csv(hist)
        print(h.tail(8).to_string(index=False))
        _plot(h, wd, run, atts)


def _plot(h, wd: Path, run, atts) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from common.fluent_case import read_out_file
    its, cd = read_out_file(wd / "cd.out")
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 8), sharex=False)
    if len(cd):
        a1.plot(range(1, len(cd) + 1), cd, lw=0.8)
        tail = cd[-min(len(cd), 1000):]
        lo, hi = tail.min(), tail.max()
        pad = max((hi - lo) * 2, abs(tail.mean()) * 0.01)
        a1.set_ylim(lo - pad, hi + pad)
    a1.set_ylabel("Cd"); a1.set_xlabel("deneme içi iterasyon"); a1.grid(alpha=0.3)
    a1.set_title(f"{run['geom_id']}:{run['vel_idx']}  M={run['mach']:.3f}  son deneme: {atts[-1]['outcome']}")
    for col in [c for c in h.columns if c.startswith("res_")]:
        a2.semilogy(h["iter"], h[col], label=col[4:])
    a2b = a2.twinx()
    a2b.plot(h["iter"], h["courant"], "k--", lw=0.8)
    a2b.set_ylabel("Courant")
    a2.set_xlabel("iterasyon"); a2.set_ylabel("residual"); a2.legend(fontsize=7); a2.grid(alpha=0.3)
    out = LOG_DIR / "inspect" / f"{run['geom_id']}_v{run['vel_idx']:02d}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(out, dpi=100); plt.close(fig)
    print(f"  grafik: {out}")


def cmd_events(con, args) -> None:
    q = "SELECT * FROM events"
    a = []
    if args.level:
        levels = {"INFO": ("INFO", "WARNING", "ERROR"), "WARNING": ("WARNING", "ERROR"), "ERROR": ("ERROR",)}[args.level]
        q += f" WHERE level IN ({','.join('?' * len(levels))})"
        a += list(levels)
    q += " ORDER BY event_id DESC LIMIT ?"
    a.append(args.tail)
    for e in reversed(con.execute(q, a).fetchall()):
        print(f"{e['ts']} {e['level']:<7} {e['kind']:<15} {e['geom_id'] or '':<9} run={e['run_id'] or '-'}  {e['message']}")


def cmd_profile(con, args) -> None:
    run = _run_or_die(con, args.run, args.campaign)
    ov = json.loads(run["next_overrides"] or "{}")
    prof, regime = resolve_profile(run["mach"], ov)
    print(json.dumps(prof, indent=2, ensure_ascii=False))
    print("İzinli override anahtarları:", ", ".join(sorted(ALLOWED_OVERRIDES)))


def cmd_export(con, args) -> None:
    import pandas as pd
    df = pd.read_sql_query("SELECT * FROM runs WHERE campaign=?", con, params=(args.campaign,))
    out = DOCS_DIR / "results"
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / f"runs_{args.campaign}.csv", index=False)
    piv = df[df.status.isin(["done", "done_flagged"])].pivot(index="geom_id", columns="vel_idx", values="cd")
    piv.to_csv(out / f"cd_matrix_{args.campaign}.csv")
    print(f"Yazıldı: {out}  ({len(df)} koşu, {piv.notna().sum().sum()} Cd)")


# --------------------------------------------------------------------------- müdahale

def _schedule(con, run, overrides: dict, init: str | None, who: str, reason: str) -> None:
    # budget_base: deneme bütçesi ve otomatik basamaklar bu müdahaleden itibaren yeniden sayılır
    con.execute("UPDATE runs SET status='retry_pending', next_overrides=?, next_init=?, next_decided_by=?, "
                "next_reason=?, budget_base=n_attempts, updated_at=? WHERE run_id=?",
                (json.dumps(overrides), init, who, reason, db.now(), run["run_id"]))
    db.event(con, "INFO", f"{who}_retry", f"init={init} override={overrides} gerekçe: {reason}",
             run["run_id"], run["geom_id"])


def cmd_retry(con, args) -> None:
    run = _run_or_die(con, args.run, args.campaign)
    if run["status"] in ("done", "done_flagged") and not args.force:
        raise SystemExit("Koşu zaten tamamlanmış. Yeniden çözmek için --force (sonuç üzerine yazılır).")
    if run["status"] == "running":
        raise SystemExit("Koşu şu an çalışıyor; bitmesini bekleyin.")
    try:
        ov = validate_overrides(_parse_sets(args.set))
        resolve_profile(run["mach"], ov)
    except OverrideError as exc:
        raise SystemExit(f"REDDEDİLDİ (fizik kilidi / izin listesi): {exc}")
    _schedule(con, run, ov, args.init, _who(args), args.reason)
    print(f"[{run['run_id']}] {run['geom_id']}:{run['vel_idx']} yeniden kuyrukta: init={args.init} override={ov}")


def cmd_requeue(con, args) -> None:
    q = "SELECT * FROM runs WHERE campaign=? AND status=?"
    a = [args.campaign, args.status]
    if args.regime:
        q += " AND regime=?"
        a.append(args.regime)
    if args.geom:
        q += " AND geom_id=?"
        a.append(args.geom.upper())
    rows = con.execute(q, a).fetchall()
    try:
        ov = validate_overrides(_parse_sets(args.set))
    except OverrideError as exc:
        raise SystemExit(f"REDDEDİLDİ: {exc}")
    if args.status in ("done", "done_flagged") and not args.force:
        raise SystemExit("Tamamlanmış koşuları yeniden kuyruğa almak için --force gerekli.")
    con.execute("BEGIN")
    for r in rows:
        _schedule(con, r, ov, args.init, _who(args), args.reason)
    con.execute("COMMIT")
    print(f"{len(rows)} koşu yeniden kuyruğa alındı.")


def cmd_skip(con, args) -> None:
    run = _run_or_die(con, args.run, args.campaign)
    con.execute("UPDATE runs SET status='skipped', updated_at=? WHERE run_id=?", (db.now(), run["run_id"]))
    db.event(con, "WARNING", f"{_who(args)}_skip", f"gerekçe: {args.reason}", run["run_id"], run["geom_id"])
    print(f"[{run['run_id']}] atlandı.")


def cmd_priority(con, args) -> None:
    n = con.execute("UPDATE runs SET priority=? WHERE campaign=? AND geom_id=?",
                    (args.n, args.campaign, args.geom.upper())).rowcount
    print(f"{n} koşunun önceliği {args.n} yapıldı.")


def cmd_control(con, args) -> None:
    if args.cmd == "pause":
        db.set_control(con, "pause", "1")
    elif args.cmd == "resume":
        db.set_control(con, "pause", None)
        db.set_control(con, "stop_after_current", None)
    elif args.cmd == "stop":
        db.set_control(con, "stop_after_current", "1")
    db.event(con, "INFO", f"control_{args.cmd}", f"{_who(args)} tarafından")
    print(f"{args.cmd}: tamam (koşular arasında uygulanır).")
    if args.cmd == "stop":
        print("Tüm işçiler mevcut koşularını bitirince çıkar. Yeniden başlatmadan önce `rcfd resume` gerekir.")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(prog="rcfd", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--campaign", default="main")
    ap.add_argument("--human", action="store_true", help="müdahaleyi insan olarak kaydet (varsayılan: agent)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("status")
    sp.add_parser("failures")
    p = sp.add_parser("inspect"); p.add_argument("run")
    p = sp.add_parser("events"); p.add_argument("--tail", type=int, default=30); p.add_argument("--level", choices=("INFO", "WARNING", "ERROR"))
    p = sp.add_parser("profile"); p.add_argument("run")
    sp.add_parser("export")
    p = sp.add_parser("retry"); p.add_argument("run"); p.add_argument("--set", action="append")
    p.add_argument("--init", choices=INIT_CHOICES); p.add_argument("--reason", required=True); p.add_argument("--force", action="store_true")
    p = sp.add_parser("requeue"); p.add_argument("--status", default="needs_review"); p.add_argument("--regime")
    p.add_argument("--geom"); p.add_argument("--set", action="append"); p.add_argument("--init", choices=INIT_CHOICES)
    p.add_argument("--reason", required=True); p.add_argument("--force", action="store_true")
    p = sp.add_parser("skip"); p.add_argument("run"); p.add_argument("--reason", required=True)
    p = sp.add_parser("priority"); p.add_argument("geom"); p.add_argument("n", type=int)
    for c in ("pause", "resume", "stop"):
        sp.add_parser(c)
    args = ap.parse_args()
    handlers = {"status": cmd_status, "failures": cmd_failures, "inspect": cmd_inspect, "events": cmd_events,
                "profile": cmd_profile, "export": cmd_export, "retry": cmd_retry, "requeue": cmd_requeue,
                "skip": cmd_skip, "priority": cmd_priority, "pause": cmd_control, "resume": cmd_control,
                "stop": cmd_control}
    with db.connect() as con:
        handlers[args.cmd](con, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
