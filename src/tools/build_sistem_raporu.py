"""Sistem detaylı raporu PDF'i -> docs/pdf/Sistem_Raporu.pdf"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pdf_style import H1, H2, P, PageBreak, Spacer, box, build, bullets, code, image, numbered, table  # noqa: E402

from common.atmosphere import freestream  # noqa: E402
from common.config import DOCS_DIR, load_velocities  # noqa: E402
from common.solver_profile import load_physics, regime_for  # noqa: E402

A = DOCS_DIR / "report_assets"


def f2(x, n=4):
    return f"{x:.{n}f}".replace(".", ",")


def story() -> list:
    facts = json.loads((A / "facts.json").read_text(encoding="utf-8"))
    m = facts["mesh"]
    s = []
    s += [P("Sistem Detaylı Raporu", "title"),
          P("Model Roket Burun Konisi — Parametrik 2D Eksenel Simetrik CFD Otomasyonu<br/>"
            "Durum tarihi: 24.11.2026 &nbsp;•&nbsp; Ansys Fluent 2024 R1 &nbsp;•&nbsp; Depo: eraydagsuyu/AutoCFD---Nose-Cone-Performance-",
            "subtitle")]
    s += [box("Proje; 20 burun konisi profili × 4 burun uzunluğu = <b>80 geometrinin</b>, uçuş profilinden alınan "
              "<b>20 hız noktasında</b> (M 0,062–1,256) eksenel simetrik RANS analizini (<b>1.600 koşu</b>) otomatikleştirir. "
              "Her geometri için Cd(v) → Cd(t) dönüştürülür ve <b>K<sub>kayıp</sub> = ∫Cd(t)dt</b> en düşük olan burun seçilir. "
              "Geometri (80/80), mesh (80/80 + 92 aday) ve çözücü/orkestratör katmanları <b>tamamlanmış ve doğrulanmıştır</b>. "
              "Sayısal hızlandırma çalışmasıyla tahmini toplam süre <b>~15 günden ~3 güne</b> indirilmiştir. Üretim koşusu "
              "24.11.2026 akşamı Ankara'da başlayacaktır.", "info", "Yönetici özeti")]
    s += [table([
        ["Gösterge", "Değer"],
        ["Geometri / mesh", "80 geometri, 80 mesh (92–129 bin hücre), Fluent kontrolü 80/80; ön optimizasyon için 92 aday mesh"],
        ["Analiz matrisi", "80 × 20 = 1.600 ana koşu + 92 × 4 = 368 ön optimizasyon koşusu"],
        ["Koşu süresi (İstanbul, 10 çekirdek)", "ses altı ~3 dk, transonik soğuk 6,4 dk, süpersonik warm 4,4 dk"],
        ["Hızlandırma", "enhanced-CASM + CFL 50: transonik yakınsama ~4000 → ~500 iterasyon (8×)"],
        ["Paralellik", "8 çekirdek → 2 işçi × 4 çekirdek (ölçülen ölçeklenme zayıf: 5 çek. 215 s, 10 çek. 191 s)"],
        ["Toplam süre tahmini", "≈ 145 işçi-saati → 2 işçiyle ≈ 72 saat (≈ 3 gün)"],
        ["Doğrulama", "Ses altında CFD, Barrowman/OpenRocket yarı-ampirik tahminin %3,6–6,8 altında (tutarlı)"],
    ], widths=[1.3, 3.4])]
    s.append(PageBreak())

    # 1
    s += [H1("1. Amaç, kapsam ve bağlam")]
    s += [P("Çalışmanın amacı, bir model roketin uçuşu boyunca maruz kaldığı toplam aerodinamik kaybı en aza indiren burun "
            "konisini nesnel bir ölçütle seçmektir. Her burun konisinin arkasında 2,0 m'lik silindirik gövde bulunur. "
            "Kapsam ve mimari, proje başlangıcındaki <i>Model Roket Burun Konisi Parametrik CFD Otomasyon Mimarisi</i> "
            "belgesine dayanır; uygulama sırasında ölçüm ve testlerle gerekçelendirilen sapmalar Bölüm 13'te listelenmiştir.")]
    s += [H2("1.1 İki makineli iş akışı")]
    s += [table([
        ["Konum", "Rol", "Kural"],
        ["İstanbul (geliştirme)", "Kod, geometri, mesh, tekli doğrulama koşuları; Claude Code ile geliştirme", "Yalnızca --mode single (1 mesh × 1 hız); batch başlatılmaz"],
        ["GitHub", "Kod, ayarlar, 80 + 92 mesh (.msh.gz), raporlar", "machine_config.json, data/, logs/ Git dışında"],
        ["Ankara (üretim)", "Toplu koşu (2 işçi), denetçi Claude Code, SSH ile uzaktan yönetim", "allow_batch = true; Tailscale + OpenSSH"],
    ], widths=[1, 2.2, 2.2])]
    s += [H2("1.2 Amaç fonksiyonu")]
    s += [P("Her geometri için 20 hız noktasındaki Cd değerleri Cd(v) eğrisini oluşturur. Uçuş profili v(t) üzerinde "
            "PCHIP interpolasyonuyla Cd(t) elde edilir ve trapez kuralıyla <b>K<sub>kayıp</sub> = ∫ Cd(t) dt</b> "
            "(t = 0,12 → 3,80 s) hesaplanır. Yardımcı gösterge olarak dinamik basınç ağırlıklı ∫v²·Cd dt de raporlanır. "
            "Cd referans alanı tüm geometrilerde aynıdır (A = πR²), bu yüzden karşılaştırma adildir.")]

    # 2
    s += [H1("2. Sabit parametreler ve kullanıcı kararları")]
    s += [table([
        ["Parametre / karar", "Değer", "Kaynak"],
        ["Gövde ve burun dış yarıçapı R", "49 mm (değiştirilemez)", "Kullanıcı"],
        ["Burun uzunluğu L", "200, 300, 400, 500 mm; toplam uzunluk tam L", "Kullanıcı"],
        ["Gövde uzunluğu", "2,0 m düz silindir, küt taban", "Mimari belge"],
        ["Mesh uç radyusu", "1 mm, yalnızca singularity oluşturan profillere", "Kullanıcı"],
        ["Profil 07", "Şişkin sekant ogive (ρ = 0,75ρ<sub>t</sub>) R'yi ~1 mm aştığı için ρ = 1,25ρ<sub>t</sub> orta sekant ogive", "Kullanıcı"],
        ["Serbest parametreler", "02/08 rn, 03 L1/R1, 04 Rt, 19 a → ön optimizasyonla belirlenir", "Kullanıcı"],
        ["Yazılım", "Ansys 2024 R1 (v241), PyFluent 0.37.2, Python 3.11, Gmsh 4.15.2", "Kullanıcı + uyumluluk testi"],
        ["Ankara makinesi", "8 çekirdek (arkadaş beyanı; kurulumda doğrulanacak)", "Kullanıcı"],
        ["Denetçi yetkisi", "Sayısal override ve profil commit'i serbest; fizik/mesh/domain için kullanıcı onayı", "Kullanıcı"],
        ["Mesh'ler Git'te", "Ankara'da yeniden üretim süresi harcanmasın", "Kullanıcı"],
    ], widths=[1.4, 2.6, 0.9])]
    s += [H2("2.1 Uçuş profili ve hız noktaları (ISA)")]
    phys = load_physics()
    rows = [["#", "V [m/s]", "Mach", "t [s]", "h [m]", "T [K]", "p [Pa]", "Re/m", "Rejim"]]
    for p in load_velocities():
        f = freestream(p["velocity_ms"], p["altitude_m"], phys)
        rows.append([str(p["index"]), f"{f.velocity:.1f}", f"{f.mach:.3f}", f"{p['time_s']:.2f}", f"{f.altitude:.0f}",
                     f"{f.T:.1f}", f"{f.p:.0f}", f"{f.re_per_m:.2e}", regime_for(f.mach)])
    s += [table(rows, widths=[0.35, 0.7, 0.6, 0.55, 0.6, 0.6, 0.75, 0.8, 0.85], font_size=7.6)]
    s += [P("ISA ile hesaplanan Mach, girdi dosyasındaki değerlerle |ΔM| < 0,0007 uyuşur. Rejim dağılımı: 11 ses altı, "
            "7 transonik, 2 süpersonik.", "small")]

    # 3
    s += [H1("3. Geometri")]
    s += [P("20 profilin denklemi MATLAB sözdiziminden NumPy'a, yalnızca izin verilen fonksiyonları içeren kısıtlı bir isim "
            "alanında çevrilir. Türetilen büyüklükler (tanjant ogive yarıçapı ρ, Haack açısı θ, 02/08 küresel körleştirme "
            "teğet noktaları) analitik olarak hesaplanır. Uç tipi, uçtaki yerel üs (y ~ c·x<super>p</super>) ile sayısal "
            "olarak sınıflandırılır.")]
    s += [table([
        ["Uç sınıfı", "Ölçüt", "Profiller", "İşlem"],
        ["Sivri tepe", "p ≈ 1 (sonlu eğim)", "01, 03, 05, 06, 07, 10, 11, 12", "1 mm teğet yay"],
        ["Sıfır eğrilik yarıçapı", "0,5 < p < 1", "14, 15, 16, 17, 18, 20", "1 mm teğet yay"],
        ["Küt (sonlu R<sub>c</sub>)", "p ≈ 0,5; R<sub>c</sub> = c²/2", "09, 13, 19 (a'ya bağlı), 02, 08", "R<sub>c</sub> < 1 mm ise yay (19 @ L500)"],
        ["Düz meplat", "y(0) > 0", "04", "Yay yok"],
    ], widths=[1, 1.1, 1.7, 1.2])]
    s += [P("Yuvarlatma ucu kısalttığından, keskin profil uzunluğu L' iteratif olarak (L' − x<sub>uç</sub>(L') = L) "
            "ayarlanır; böylece toplam burun uzunluğu tam L kalır. Sonuç: <b>80/80 geometri geçerli</b>, uç sınıflandırması "
            "beklenenle birebir, uzunluk hatası < 0,001 µm, R'yi aşan geometri yok.")]
    s += image(DOCS_DIR / "geometry" / "profiles_L300.png", 0.98, "Şekil 1 — 20 profil, L = 300 mm (R = 49 mm)")
    s += image(DOCS_DIR / "geometry" / "tips_L500.png", 0.82, "Şekil 2 — Uç bölgesi (ilk 6 mm), L = 500 mm; kırmızı: 1 mm mesh yuvarlatması")

    # 4
    s += [H1("4. Mesh")]
    s += [H2("4.1 Neden hibrit yapı?")]
    s += bullets([
        "<b>Gmsh BoundaryLayer alanı terk edildi:</b> duvarın eksenle buluştuğu taban noktasında 160 mm'lik yassı, bozuk fan "
        "üretti (minSJ ≈ 0,001). Bu, 80 geometride tekrarlanacak sistematik bir hataydı.",
        "<b>Mimari belgedeki \"Fluent MSH2 okur\" bilgisi yanlış:</b> MSH2 Gmsh'ın formatıdır. Mesh, Fluent'in kendi ASCII "
        "<i>.msh</i> formatında yazılır (bölge adları ve BC tipleri dosyaya gömülü) ve gzip ile sıkıştırılır (6,9 → 2,2 MB).",
        "<b>Sınır tabakası Python'da yapısal örülür:</b> duvar düğümlerinden dış normal boyunca geometrik katmanlar; küçük "
        "kırıklarda açıortay normali, dışbükey köşelerde (taban köşesi, meplat köşesi) fan; uç ve taban-eksen kolonları eksen "
        "üzerinde. Dış bölge Gmsh Frontal-Delaunay üçgenlerle örülür.",
    ])
    s += [H2("4.2 Parametreler")]
    s += [table([
        ["Büyüklük", "Değer", "Gerekçe"],
        ["İlk hücre yüksekliği", "1 µm", "y⁺ ≈ 1 @ 418 m/s (u<sub>τ</sub> ≈ 15 m/s, c<sub>f</sub> ≈ 0,0026)"],
        ["Katman / oran / kalınlık", f"{m['n_layers']} / {f2(m['bl_ratio'], 3)} / 4 mm", "SST duvar fonksiyonsuz (low-Re) çözüm"],
        ["Teğetsel boyut", "uç yayı 50 µm, burun 1 mm, gövde 3 mm, taban köşesi 0,5 mm", "Büyüme oranı 1,1"],
        ["Domain", "önde 2·L<sub>b</sub>, radyal 2·L<sub>b</sub>, arkada 5·L<sub>b</sub> (L<sub>b</sub> = L + 2 m)", "Far-field yansımasını sınırlama"],
        ["Sıklaştırma kutuları", "burun önü 4 mm, iz bölgesi 1 m × 0,12 m, 5 mm", "Şok ve taban izi"],
        ["Hücre sayısı", f"{m['cells_min']:,} – {m['cells_max']:,}".replace(",", "."), "L ile artar"],
        ["Kalite (Python)", f"max equiangle skewness {f2(m['skew_max'], 2)} (fan ilk katmanı)", "Eşik 0,90"],
        ["Kalite (Fluent)", f"min orthogonal quality {f2(m['oq_min'], 3)} (80/80 geçti)", "Eşik 0,05; mesh/check temiz"],
    ], widths=[1.2, 2, 2])]
    s += image(A / "mesh_preview_P16_L300.png", 1.0, "Şekil 3 — P16_L300 mesh: uç, omuz, taban köşesi (fan) ve taban-eksen birleşimi; renk = skewness")
    s += [H2("4.3 Kritik teknik notlar")]
    s += bullets([
        "Gmsh <i>Threshold</i> alanlarında <b>StopAtDistMax = 1</b> zorunlu; aksi hâlde SizeMax tüm alana uygulanır "
        "(ilk denemede mesh milyarlarca hücreye gidip takıldı).",
        "Fluent 2D yüz yönü: n0 → n1 yönünde c0 <b>solda</b>. Ters yazıldığında Fluent tüm hücreleri negatif hacimli raporladı.",
        "Meplat (04) köşesinde duvar boyutu 0,3 mm olmalı; 50 µm'de BL üst kenarında aralık sıçradı ve OQ 0,047'ye düştü (düzeltildi → 0,23).",
    ])

    # 5
    s += [H1("5. Fizik modeli (fizik kilidi)")]
    s += [P("Aşağıdaki ayarlar <i>config/physics.json</i> dosyasındadır ve hiçbir koşu için override edilemez; böylece 80 "
            "geometrinin sonuçları birbiriyle karşılaştırılabilir kalır.")]
    s += [table([
        ["Bileşen", "Ayar"],
        ["Uzay", "2D eksenel simetrik, roket ekseni y = 0 (axis)"],
        ["Akışkan", "Hava, ideal gaz, Sutherland viskozitesi (μ<sub>0</sub> = 1,716·10⁻⁵, T<sub>0</sub> = 273,11 K, S = 110,56 K), c<sub>p</sub> = 1006,43"],
        ["Enerji / türbülans", "Enerji denklemi açık; k-ω SST (tam türbülanslı)"],
        ["Dış sınırlar", "inlet / outlet / farfield: pressure-far-field (Mach, statik p, T); TI = %0,1, μ<sub>t</sub>/μ = 10"],
        ["Atmosfer", "ISA troposfer: T = 288,15 − 0,0065·h; p = 101325·(T/288,15)<super>5,25588</super>; operating pressure = 0"],
        ["Reference Values", "Her hızda güncellenir: A = πR² = 0,007543 m², ρ, V, T, p, μ; uzunluk = L + 2 m"],
        ["Kuvvet", "Drag, wall_rocket (burun + gövde + taban), yön (1, 0); Fluent eksenel simetride tam 2π gövdeyi raporlar"],
    ], widths=[1, 3.6])]

    # 6
    s += [H1("6. Çözücü ve sayısal optimizasyon çalışmaları")]
    s += [H2("6.1 Çözücü ve izleme")]
    s += bullets([
        "Density-based implicit, Roe-FDS, least-squares gradyan; birinci dereceden başlayıp ikinci dereceye geçiş; geometrik CFL rampası.",
        "Fluent'in residual tabanlı durdurması kapalı; her 50 iterasyonda Cd (.out) ve residual okunur, karar Python'da verilir.",
        "<b>Yakınsama:</b> (a) sıkı pencere: ikinci derecede son 300 iterasyonda Cd bağıl std < 2·10⁻⁴ ve kayma < 5·10⁻⁴ → <i>done</i>; "
        "(b) ortalama yakınsaması: art arda iki 500'lük pencerenin ortalama farkı < %0,1 ve salınım < %1 → <i>done_flagged</i> (1000 iterasyon ortalaması).",
        "<b>Iraksama (mutlak ölçüt):</b> NaN/Inf, residual > 10, |Cd| > 50 veya Fluent'in iterasyonu kesmesi.",
        "<b>Geçerlilik kuralı:</b> kabul edilen her Cd ikinci derece ayrıklaştırma ile elde edilmiş olmalıdır.",
        "Her 500 iterasyonda <i>last_good</i> checkpoint; başarılı koşuda silinir (disk).",
    ])
    s += [H2("6.2 Hızlandırma deneyi (ölçülmüş)")]
    s += [P("Başlangıç profiliyle (CFL 5) soğuk transonik koşu 27 dk sürdü ve 8000 iterasyon sınırına dayandı. Önce warm-start "
            "ölçüldü (v16 alanından v17: 12,8 dk, 4451 iterasyon), ardından aynı başlangıç dosyasıyla dört sayısal ayar karşılaştırıldı:")]
    s += [table([
        ["Ayar (v17, M = 1,062, warm-start)", "500 it", "1000 it", "1500 it", "Nihai değere ulaşma"],
        ["CFL 5 (referans)", "0,419", "0,447", "0,469", "~4000 it"],
        ["CFL 20", "0,473", "0,490", "0,493", "~1000 it"],
        ["CASM + CFL 5", "0,447", "0,479", "0,491", "~1500 it"],
        ["enhanced-CASM + CFL 20", "0,487", "0,491", "0,492", "~750 it"],
        ["<b>enhanced-CASM + CFL 50 (seçilen)</b>", "<b>0,492</b>", "<b>0,492</b>", "<b>0,491</b>", "<b>~500 it (8×)</b>"],
    ], widths=[2.1, 0.6, 0.6, 0.6, 1.2])]
    s += image(A / "accel_convergence.png", 0.98, "Şekil 4 — Sayısal ayarların yakınsama hızına etkisi (referans nihai Cd = 0,4913)")
    s += [P("Doğrulama: v05 soğuk 900 it / 3,3 dk (Cd 0,3633; CFL 5 ile 0,3638, fark %0,14), v19 ve v20 süpersonik warm 1401 it / "
            "4,4 dk, ıraksama yok. Karar: tüm rejimlerde enhanced-CASM + CFL 50; ıraksarsa kurtarma basamakları CFL'yi yarıya indirir.")]
    s += [H2("6.3 Warm-start ve hız oranı kuralı")]
    s += [P("Bir geometrinin hızları artan sırada aynı Fluent oturumunda çözülür; her hız bir öncekinin yakınsamış alanından "
            "başlar. Ancak düşük hızlarda adımlar göreli olarak büyüktür (v1 → v2 hız ×2). Bu geçişte warm-start; CASM açık veya "
            "kapalı, CFL 1,5 ile 50 arasındaki <b>tüm ayarlarda ıraksadı</b>. Soğuk başlatma ise sorunsuzdu. Bu yüzden kaynak alanın "
            "hızına oran > 1,3 ise otomatik soğuk başlatma yapılır (pratikte v2–v4 soğuk, v5 ve sonrası warm). Kural sonrasında "
            "v3, v5, v6 kurtarma gerektirmeden tek denemede çözüldü.")]
    s += [H2("6.4 Rejim profilleri (config/solver_profiles)")]
    s += [table([
        ["Anahtar", "base / ses altı", "transonik", "süpersonik"],
        ["Mach aralığı", "0 – 0,7", "0,7 – 1,15", "≥ 1,15"],
        ["CASM / CFL (son)", "enhanced / 50", "enhanced / 50", "enhanced / 50"],
        ["Soğuk: 1. derece it / CFL başlangıç / rampa", "300 / 1 / 400", "500 / 0,5 / 800", "400 / 0,5 / 600"],
        ["Warm: 1. derece / CFL başlangıç / rampa / min it", "0 / 1 / 500 / 600", "aynı", "aynı"],
        ["min / max iterasyon (soğuk)", "800 / 3000", "1500 / 4000", "1200 / 4000"],
        ["warm_max_velocity_ratio", "1,3", "1,3", "1,3"],
    ], widths=[2.2, 1.1, 1.1, 1.1])]

    # 7
    s += [H1("7. Denetimli çözüm mimarisi")]
    s += [P("<b>İlke:</b> toplu koşu denetçi olmadan uçtan uca çalışır. Rutin kurtarmayı Python yapar; Ankara'daki Claude Code "
            "(denetçi) yalnızca otomatik basamakların çözemediği koşulara müdahale eder ve bunu <b>kod değil veri</b> değiştirerek "
            "yapar. Her müdahale gerekçesiyle veritabanına kaydedilir.")]
    s += [table([
        ["Katman", "Dosya", "Görev"],
        ["Çözücü", "common/fluent_case.py, 02_fluent_solver.py", "Tek deneme: kurulum, BC + Reference Values, izleme, sınıflandırma, checkpoint"],
        ["Orkestratör", "03_orchestrator.py", "SQLite kuyruğu, geometri sahiplenme, warm-start zinciri, kurtarma basamakları, kontrol tablosu"],
        ["Denetçi aracı", "rcfd.py", "status, failures, inspect, events, profile, export / retry, requeue, skip, priority, pause, resume, stop"],
        ["Kurallar", "CLAUDE.md, docs/runbook_supervisor.md", "Yetki sınırları, teşhis tablosu, kullanıcıya bildirim durumları"],
        ["Fluent oturumu", "common/fluent_session.py", "Güvenli başlatma/kapatma; v241'de açık kalan fluent.exe + cx2410.exe süreçlerini temizler"],
    ], widths=[0.9, 1.6, 2.6])]
    s += [H2("7.1 Durum makinesi ve kurtarma")]
    s += [P("<font name='Consolas'>pending → running → done | done_flagged | retry_pending → running … → needs_review | skipped | mesh_error</font>")]
    s += [table([
        ["Başarısızlık", "Otomatik basamaklar (config/recovery_policy.json)"],
        ["diverged", "1) last_good, CFL ×0,5  2) neighbor, CFL ×0,5, uzun rampa  3) hybrid soğuk, CFL ×0,4, 800 it 1. derece  4) FMG + AUSM"],
        ["stalled", "1) mevcut alandan devam (max it ×0,6)  2) devam, CFL ×0,5"],
        ["oscillating", "1) devam, CFL ×0,5  2) devam, pencere ×1,5"],
        ["timeout", "1) devam, süre ×1,5"],
        ["crash", "1) Fluent oturumunu yeniden aç + neighbor  2) yeniden aç + hybrid"],
    ], widths=[0.9, 4])]
    s += bullets([
        "Basamaklar bitince koşu <i>needs_review</i> olur ve kuyruk diğer koşularla devam eder.",
        "Denetçi denemesi başarısız olursa otomatik basamaklar onun ayarlarını taban alarak sürer (deneme bütçesi müdahaleden itibaren sayılır).",
        "<b>Fizik kilidi:</b> override yalnızca izin listesindeki sayısal anahtarlarda ve sınırlar içinde mümkündür; "
        "türbülans modeli, gaz modeli, BC tipi, mesh ve Reference Values reddedilir (test edildi).",
        "Kurtarma zinciri gerçek bir ıraksamayla uçtan uca doğrulandı (v2: diverged → last_good → neighbor → hybrid → stalled → devam → done_flagged).",
    ])
    s += [H2("7.2 Çoklu işçi, SSH dayanıklılığı, veri")]
    s += bullets([
        "İşçiler geometriyi atomik olarak sahiplenir (<i>claims</i> tablosu, BEGIN IMMEDIATE). Ölü işçinin sahiplenmesi düşer, "
        "yarım koşusu otomatik yeniden kuyruğa alınır (test edildi). Fluent hiç açılamazsa (lisans) koşular cezalandırılmaz; işçi çıkar.",
        "<i>start_batch.ps1</i> işçileri WMI (Win32_Process.Create) ile başlatır: Windows OpenSSH, oturumdan başlatılan süreçleri "
        "Job Object ile birlikte sonlandırabildiği için Start-Process kullanılmaz.",
        "SQLite (WAL) tabloları: runs, attempts (profil hash, override, başlatma yöntemi, sonuç, kim karar verdi, gerekçe), "
        "events (+ logs/events.jsonl), control (pause / stop / kalp atışı), claims.",
        "Her geometrinin en son yakınsamış alanı <i>data/fields/&lt;geom&gt;/latest.dat.h5</i>; v01 ve v20 alanları görsel doğrulama için saklanır.",
    ])

    # 8
    s += [H1("8. Çekirdek ölçeklenmesi ve süre hesapları")]
    s += [P("Aynı koşu (P16_L300, v1, soğuk, 1000 iterasyon) farklı çekirdek sayısıyla ölçüldü: <b>5 çekirdek 215 s</b>, "
            "<b>10 çekirdek 191 s</b>. Çekirdeği iki katına çıkarmak yalnızca %11 hız kazandırıyor (paralel verim ≈ %56). "
            "2D'de ~100 bin hücre, çekirdek başına ~10 bin hücreye düştüğünde iletişim maliyeti baskın hâle gelir. Bu yüzden "
            "Ankara'nın 8 çekirdeği <b>2 bağımsız işçi × 4 çekirdek</b> olarak kullanılır; toplam verim ≈ 1,8× artar.")]
    s += [table([
        ["Kalem", "Hesap", "Sonuç"],
        ["4 çekirdekli işçi hız katsayısı", "≈ 215/191 (İstanbul 10 çek. süresine göre)", "×1,13"],
        ["Geometri başına (ana)", "v1–v4 soğuk + v5–v11 warm: 11 × 3,2 dk; transonik 7 × ~4,5 dk; süpersonik 2 × 4,5 dk = ~76 dk × 1,13", "≈ 86 dk"],
        ["Ana kampanya", "80 geometri × 86 dk", "≈ 115 işçi-saati"],
        ["Ön optimizasyon", "92 aday × (v5, v10, v15 soğuk + v19 warm ≈ 17,2 dk × 1,13)", "≈ 30 işçi-saati"],
        ["Toplam, 2 işçi", "(115 + 30) / 2", "<b>≈ 72 saat ≈ 3 gün</b>"],
        ["Başlangıç tahmini (karşılaştırma)", "tek işçi, CFL 5, warm-start yok", "~15 gün"],
    ], widths=[1.3, 3, 0.9])]
    s += [box("Transonik warm-start zinciri (v12 → v18) orkestratörde uçtan uca henüz ölçülmedi; 4,5 dk varsayımdır "
              "(v17 warm testinde ~500 iterasyonda oturdu). Ankara'daki ilk geometride doğrulanacak.", "warn", "Belirsizlik")]

    # 9
    s += [H1("9. Ön optimizasyon")]
    s += [table([
        ["Profil", "Parametre", "Adaylar", "Aday sayısı (L başına)"],
        ["02 / 08 küresel körleştirilmiş", "rn / R", "0,05; 0,10; 0,20; 0,30", "4 + 4"],
        ["03 bi-konik", "L1 / L × R1 / R", "{0,3; 0,5; 0,7} × {0,6; 0,75; 0,85}, dışbükeylik süzgeci", "8"],
        ["04 meplatlı konik", "Rt / R", "0,05; 0,10; 0,20; 0,30", "4"],
        ["19 hiperbolik", "a / L", "0,05; 0,25; 1,0", "3"],
    ], widths=[1.4, 0.9, 2.2, 1])]
    s += [P("Toplam 92 aday geometri × 4 temsili hız (v5 M 0,31; v10 M 0,62; v15 M 0,94; v19 M 1,19) = 368 koşu. Amaç fonksiyonu "
            "ana çalışmayla aynıdır (K<sub>kayıp</sub>, PCHIP). <b>92/92 aday mesh</b> üretildi, Fluent kontrolünden geçti "
            "(min orthogonal quality 0,23) ve Git'e eklendi. Ana kampanya, bu beş "
            "profilin 20 geometrisini ön optimizasyon seçim yapana kadar kuyruğa almaz (geçici parametrelerle boşa koşu önlenir).")]

    # 10
    s += [H1("10. Doğrulanmış sonuçlar (P16_L300, Von Kármán, L = 300 mm)")]
    vr = {int(r["vel_idx"]): r for r in facts["validation_runs"]}
    rows = [["Hız", "Mach", "Durum", "Cd", "Başlatma / not"]]
    notes = {1: "soğuk, 1000 it, 3,2 dk", 2: "kurtarma zinciriyle (bkz. 7.1)", 3: "otomatik soğuk (oran 2,0), 950 it",
             5: "otomatik soğuk (oran 2,5), 900 it", 6: "warm (oran 1,2), 1001 it, 3,0 dk", 15: "transonik soğuk, 1950 it, 6,4 dk"}
    for v, r in sorted(vr.items()):
        rows.append([f"v{v:02d}", f2(r["mach"], 3), r["status"], f2(r["cd"], 4), notes.get(v, "")])
    for v, cd, note in ((17, 0.4913, "deney: warm, enhanced-CASM + CFL 50"), (19, 0.4734, "deney: warm, ±%0,35"),
                        (20, 0.4616, "deney: warm, ±%0,22")):
        rows.append([f"v{v:02d}", "", "deney", f2(cd, 4), note])
    s += [table(rows, widths=[0.5, 0.6, 0.9, 0.6, 2.4])]
    s += image(A / "cd_mach_P16_L300.png", 0.9, "Şekil 5 — Doğrulama noktalarında Cd(M)")
    s += image(A / "cfd_vs_semiempirical.png", 0.9, "Şekil 6 — Ses altı: CFD ile Barrowman/OpenRocket yarı-ampirik tahmini")
    s += [P("CFD, yarı-ampirik yöntemin <b>%3,6–6,8 altında</b> ve Reynolds sayısıyla aynı eğilimi gösteriyor. Ayrıntılı "
            "belirsizlik analizi ayrı <i>Sonuç Hassasiyet Raporu</i>'ndadır.")]

    # 11
    s += [H1("11. Karşılaşılan sorunlar ve çözümleri")]
    s += [table([
        ["Sorun", "Kök neden", "Çözüm"],
        ["PyFluent 0.43 Fluent 24.1'i başlatmadı", "0.38+ yalnızca 24.2+ destekliyor", "ansys-fluent-core==0.37.2 sabitlendi"],
        ["session.exit() sonrası açık süreçler", "v241 fluent.exe + cx2410.exe'yi bırakıyor", "fluent_session.py: başlatma sonrası doğan süreçleri temizler"],
        ["Gmsh mesh'i saatlerce takıldı", "Threshold SizeMax tüm alana uygulanıyor", "StopAtDistMax = 1"],
        ["Taban-eksen köşesinde bozuk hücreler", "Gmsh BoundaryLayer alanı", "Yapısal BL (Python) + Gmsh dış üçgen"],
        ["Fluent tüm hücreleri negatif hacimli gördü", "Yüz yönü kuralı ters", "c0 solda kuralı; Fluent'le doğrulandı"],
        ["Meplat köşesinde OQ 0,047", "BL üst kenarında aralık sıçraması", "Köşe boyutu 0,3 mm → OQ 0,23"],
        ["Warm-start 50 it sonra yanlış \"done\"", "Fluent iterasyon sayacı veri dosyasından sürüyor", "Deneme içi iterasyon = cd.out satır sayısı"],
        ["Warm-start'ta yanlış ıraksama alarmı", "Göreli residual artışı ölçütü", "Mutlak ölçüt (residual > 10, |Cd| > 50, NaN)"],
        ["Transonik çok yavaş (27 dk)", "Küresel bilginin CFL 5 ile yavaş yayılması", "enhanced-CASM + CFL 50 (8×)"],
        ["v1 → v2 warm-start her ayarda ıraksadı", "Düşük Mach'ta ×2 hız sıçraması", "Hız oranı > 1,3 ise soğuk başlatma"],
        ["Bozuk Fluent ayar adları", "v241 API farkları", "Roe-FDS/AUSM, turbulent_viscosity_ratio_real, amg-c anahtarları"],
        ["SSH kopunca süreç ölebilir", "OpenSSH Job Object", "WMI Win32_Process.Create ile başlatma"],
        ["NumPy 2.4'te trapz yok", "API kaldırıldı", "np.trapezoid"],
        ["Aday P08_L200_c04'te dejenere hücre", "Körleştirme başlangıcındaki 1e-10 m yuvarlama kalıntısı 'meplat' sanıldı", "Meplat eşiği 1e-5·L (en küçük gerçek meplat 2,45 mm); 80 ana geometri değişmedi"],
    ], widths=[1.6, 1.6, 1.8], font_size=7.8)]

    # 12
    s += [H1("12. Açık konular ve riskler")]
    s += bullets([
        "<b>Mesh bağımsızlığı çalışması yapılmadı.</b> Ağ hatası tahminidir; Hassasiyet Raporu'nda bant olarak verildi. "
        "Öneri: 2–3 geometri için 3 düzeyli GCI çalışması (ana koşu sonrasında, ~10 saat).",
        "Transonik warm-start zinciri ve 4 çekirdekli işçi süresi Ankara'nın ilk geometrisinde doğrulanacak.",
        "Ankara lisansı iki eş zamanlı Fluent oturumuna izin vermezse süre ~2 katına (~6 gün) çıkar; sistem tek işçiyle aynen çalışır.",
        "<i>done_flagged</i> sonuçlar (kalıcı salınım, ortalama alınmış) raporda işaretli tutulur; denetçi komşu hızlarla tutarlılığı kontrol eder.",
        "Depo herkese açık görünüyor; gizli tutulacaksa özel yapılmalı ve Ankara'da token kullanılmalı.",
        "Son işleme betiği hazır; nihai sıralama 1.600 koşu tamamlandığında üretilecek.",
    ])

    # 13
    s += [H1("13. Mimari belgeden bilinçli sapmalar")]
    s += [table([
        ["Mimari belge", "Uygulama", "Gerekçe"],
        ["Gmsh → MSH2 → Fluent", "Fluent ASCII .msh.gz (kendi yazıcımız)", "Fluent MSH2 okumaz"],
        ["Gmsh inflation", "Yapısal BL (Python)", "Eksen birleşiminde bozuk hücre"],
        ["Start-Process ile arka plan", "WMI Win32_Process.Create", "SSH Job Object süreçleri öldürebilir"],
        ["Inlet hızı + Reference Velocity", "pressure-far-field (Mach, p, T) + tüm Reference Values", "M ≤ 1,26 sıkıştırılabilir akış"],
        ["Yalnızca ilk hızda hybrid-init", "Hız oranı > 1,3 ise soğuk başlatma", "Düşük Mach warm-start ıraksaması"],
        ["Tek işçi, tüm çekirdekler", "2 işçi × 4 çekirdek", "Ölçülen zayıf ölçeklenme"],
        ["SQLite: pending/running/done/diverged/mesh_error", "Genişletilmiş durum makinesi + attempts/events/control/claims", "Denetimli kurtarma ve izlenebilirlik"],
    ], widths=[1.5, 1.8, 1.6])]

    # 14
    s += [H1("14. Klasör yapısı ve komut referansı")]
    s += [code(r'''
C:\RocketCFD\
  CLAUDE.md                      proje anayasası (Claude Code her oturumda okur)
  config\                        physics.json (kilit), solver_profiles\, recovery_policy.json,
                                 mesh_settings.json, nose_params.json,
                                 velocities.json, flight_profile.csv
  inputs\                        raw\ (ham girdiler), nose_cones\ (20 profil denklemi)
  meshes\                        80 ana mesh (.msh.gz); preopt\ 92 aday mesh
  src\00_preopt.py               ön optimizasyon: --plan / --build / --select
  src\01_mesh_gen.py             geometri -> mesh (--geom / --all)
  src\02_fluent_solver.py        ham tekli koşu (DB'siz)
  src\03_orchestrator.py         --mode single | batch, --campaign, --worker
  src\04_postprocess.py          sıralama, Cd(v), Cd(t) grafikleri
  src\rcfd.py                    denetçi CLI
  src\common\                    geometry, mesher, fluent_msh, fluent_case,
                                 fluent_session, db, metrics ...
  scripts\                       setup_env.ps1, start_batch.ps1
  docs\                          ankara_setup.md, runbook_supervisor.md, pdf\, mesh\, geometry\
  data\  logs\                   (Git dışı) results.db, alan dosyaları, loglar
''')]
    s += [code(r'''
# İstanbul: tek koşu
.venv\Scripts\python.exe src\03_orchestrator.py --mode single --geom P16_L300 --vel 5
# Ankara: ön optimizasyon koşularını kaydet (mesh'ler hazır), sonra işçileri başlat
.venv\Scripts\python.exe src\00_preopt.py --build
powershell -ExecutionPolicy Bypass -File scripts\start_batch.ps1 -Campaign preopt -Workers 1
powershell -ExecutionPolicy Bypass -File scripts\start_batch.ps1 -Campaign main -Workers 1
# İzleme / müdahale (kısayol fonksiyonu)
function rcfd { & .venv\Scripts\python.exe src\rcfd.py @args }
rcfd status
rcfd --campaign preopt status
rcfd failures
rcfd inspect P16_L300:17
rcfd retry P16_L300:17 --init neighbor --set courant_end=25 --reason "..."
rcfd stop
''')]
    return s


def main() -> int:
    out = DOCS_DIR / "pdf" / "Sistem_Raporu.pdf"
    build(out, story(), "Sistem Detaylı Raporu", "Mimari, optimizasyon çalışmaları, kurallar, hesaplar ve sonuçlar")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
