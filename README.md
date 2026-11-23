# AutoCFD — Model Roket Burun Konisi Performansı

**20 burun konisi profili × 4 burun uzunluğu = 80 geometrinin**, gerçek uçuş profilinden alınan **20 hız noktasında**
(Mach 0,06 – 1,26) Ansys Fluent ile 2D eksenel simetrik analizini uçtan uca otomatikleştiren sistem.
Amaç: uçuş boyunca toplam aerodinamik kaybı (**K<sub>kayıp</sub> = ∫ Cd(t) dt**) en düşük olan burun konisini nesnel olarak seçmek.

| | |
|---|---|
| Analiz matrisi | 80 geometri × 20 hız = **1.600 koşu** (+ 92 aday × 4 hız = 368 ön optimizasyon koşusu) |
| Çözücü | Ansys Fluent 2024 R1 (v241), density-based implicit, k-ω SST, ideal gaz, eksenel simetrik |
| Otomasyon | Python 3.11, PyFluent 0.37.2, Gmsh 4.15.2, SQLite |
| Durum (24.11.2026) | Geometri 80/80 ✔ · Mesh 80/80 + 92 aday ✔ · Çözücü/orkestratör doğrulandı ✔ · Ankara'da üretim koşusu başlıyor |
| Tahmini süre | ~3 gün (Ankara, 2 işçi × 4 çekirdek) |

## 📄 Belgeler (önce bunları okuyun)

| Belge | Kimin için | İçerik |
|---|---|---|
| [**docs/pdf/Talimatlar.pdf**](docs/pdf/Talimatlar.pdf) | Ankara makinesini kuracak kişi | Sıfırdan kurulum, adım adım, her adımda kontrol |
| [**docs/pdf/Sistem_Raporu.pdf**](docs/pdf/Sistem_Raporu.pdf) | Proje ekibi | Mimari, kurallar, geometri, mesh, fizik, optimizasyon çalışmaları, çekirdek ve süre hesapları, sorunlar |
| [**docs/pdf/Sonuc_Hassasiyet_Raporu.pdf**](docs/pdf/Sonuc_Hassasiyet_Raporu.pdf) | Sonuçları yorumlayacak herkes | Cd ve K<sub>kayıp</sub> için yüzdelik belirsizlik bantları |
| [CLAUDE.md](CLAUDE.md) | Claude Code (ve geliştirici) | Projenin bağlayıcı kuralları ve tüm teknik kararlar |
| [docs/ankara_setup.md](docs/ankara_setup.md) | Operatör | Ankara kurulumu ve toplu koşunun başlatılması (komutlar) |
| [docs/runbook_supervisor.md](docs/runbook_supervisor.md) | Ankara'daki Claude Code (denetçi) | İzleme döngüsü, teşhis tablosu, yetki sınırları |

PDF'ler kaynak verilerden yeniden üretilebilir: `src/tools/report_figures.py` → `build_talimatlar.py`, `build_sistem_raporu.py`, `build_hassasiyet_raporu.py`.

## Nasıl çalışır?

```
inputs/raw (20 denklem, uçuş profili)
   │  src/tools/prepare_inputs.py
   ▼
geometri (src/common/geometry.py)  ── 80 profil, 1 mm uç yuvarlatma (yalnızca gerekenlere), toplam uzunluk tam L
   │  src/01_mesh_gen.py
   ▼
mesh (src/common/mesher.py)        ── yapısal sınır tabakası (y⁺≈1, 37 katman) + Gmsh üçgen → Fluent .msh.gz
   │  src/03_orchestrator.py  (SQLite kuyruğu, geometri başına tek Fluent oturumu, warm-start, otomatik kurtarma)
   ▼
çözüm (src/common/fluent_case.py)  ── ISA serbest akış, pressure-far-field, Reference Values, yakınsama izleme
   │  src/04_postprocess.py
   ▼
Cd(v) → Cd(t) → K_kayıp → sıralama ve grafikler (docs/results/)
```

**Denetimli çözüm:** toplu koşu kendi başına çalışır ve rutin sorunları (`config/recovery_policy.json`) kendisi çözer.
Ankara'daki Claude Code yalnızca otomatik basamakların çözemediği koşulara `src/rcfd.py` ile, **kodu değil veriyi değiştirerek**
ve her müdahaleyi gerekçesiyle kaydederek müdahale eder. Fizik ayarları (`config/physics.json`) kilitlidir ve hiçbir koşu için
değiştirilemez; böylece 80 geometrinin sonuçları karşılaştırılabilir kalır.

## Sabit tasarım parametreleri

| Parametre | Değer |
|---|---|
| Gövde/burun yarıçapı R | 49 mm |
| Burun uzunluğu L | 200, 300, 400, 500 mm |
| Gövde | 2,0 m düz silindir, küt taban |
| Profiller | Konik, küresel körleştirilmiş konik, bi-konik, meplatlı konik, tanjant/sekant ogive, küresel körleştirilmiş tanjant ogive, eliptik, parabolik (K = 1, ¾, ½), kuvvet serisi (n = ½, ⅔, ¾), Von Kármán, LV-Haack, tanjant Haack, hiperbolik, Sears-Haack |
| Serbest parametreler | 02/08 rn, 03 L1/R1, 04 Rt, 19 a — ön optimizasyonla seçilir (`src/00_preopt.py`) |

## Hızlı başlangıç

**Kurulum (her makinede):**
```powershell
git clone https://github.com/eraydagsuyu/AutoCFD---Nose-Cone-Performance-.git C:\RocketCFD
cd C:\RocketCFD
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1   # .venv + paketler; machine_config.json oluşturur
# machine_config.json'u düzenleyin (fluent_exe, fluent_cores, workers, allow_batch), sonra tekrar:
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1   # Fluent başlat/kapat testi -> SONUÇ: BAŞARILI
```

**Tek koşu (geliştirme makinesi — yalnızca bu mod):**
```powershell
.venv\Scripts\python.exe src\03_orchestrator.py --mode single --geom P16_L300 --vel 5
```

**Toplu koşu (üretim makinesi, `allow_batch: true`):**
```powershell
.venv\Scripts\python.exe src\00_preopt.py --build    # 368 ön optimizasyon koşusunu kaydeder (mesh'ler hazır, saniyeler)
powershell -ExecutionPolicy Bypass -File scripts\start_batch.ps1 -Campaign preopt -Workers 1
powershell -ExecutionPolicy Bypass -File scripts\start_batch.ps1 -Campaign main   -Workers 1
```
İşçiler SSH oturumundan bağımsız (WMI ile) başlatılır; bağlantı kopsa da çalışmaya devam ederler.

**İzleme ve müdahale:**
```powershell
function rcfd { & .venv\Scripts\python.exe src\rcfd.py @args }
rcfd status                 # ilerleme, işçilerin kalp atışı, tahmini kalan süre
rcfd failures               # incelenmesi gereken koşular
rcfd inspect P16_L300:17    # deneme geçmişi + Cd/residual grafiği
rcfd retry P16_L300:17 --init neighbor --set courant_end=25 --reason "..."
rcfd stop                   # mevcut koşu bitince durdur
```

**Sonuçlar:**
```powershell
.venv\Scripts\python.exe src\04_postprocess.py      # docs/results/ranking.md, Cd(v), Cd(t) grafikleri
```

## Klasör yapısı

```
CLAUDE.md                proje anayasası (kurallar + kararlar)
config/                  physics.json (kilitli), solver_profiles/, recovery_policy.json, mesh_settings.json,
                         nose_params.json, velocities.json, flight_profile.csv
inputs/                  raw/ (ham girdiler), nose_cones/ (20 profil denklemi)
meshes/                  80 ana mesh (.msh.gz, Fluent doğrudan okur); preopt/ 92 aday mesh
src/00_preopt.py         ön optimizasyon (--plan / --build / --select)
src/01_mesh_gen.py       geometri → mesh
src/02_fluent_solver.py  ham tekli koşu (veritabanısız)
src/03_orchestrator.py   kuyruk + kurtarma + çoklu işçi (--mode single | batch)
src/04_postprocess.py    sıralama ve grafikler
src/rcfd.py              denetçi CLI
src/common/              geometry, mesher, fluent_msh, fluent_case, fluent_session, solver_profile,
                         atmosphere, db, metrics, config
src/tools/               ortam/geometri/mesh kontrolleri, rapor üreteçleri
scripts/                 setup_env.ps1, start_batch.ps1
docs/                    pdf/, geometry/, mesh/, preopt/, report_assets/, runbook ve kurulum rehberleri
data/, logs/             (Git dışı) results.db, alan dosyaları, loglar
```

## Öne çıkan teknik kararlar (ayrıntı: Sistem Raporu)

- **Mesh:** Gmsh'ın sınır tabakası alanı eksen birleşiminde bozuk hücre ürettiği için sınır tabakası Python'da yapısal örülür;
  çıktı Fluent'in kendi `.msh` formatındadır (Fluent, Gmsh'ın MSH2 formatını okumaz).
- **Hız:** enhanced-CASM + CFL 50 transonik yakınsamayı ~4000'den ~500 iterasyona indirdi (8×), sonuç farkı < %0,15.
- **Warm-start:** her geometrinin hızları aynı oturumda artan sırada çözülür; hız oranı > 1,3 ise (düşük hızlarda) soğuk başlatma.
- **Paralellik:** 2D'de çekirdek ölçeklenmesi zayıf (5 çek. 215 s, 10 çek. 191 s) → 8 çekirdekte 2 bağımsız işçi × 4 çekirdek.
- **Sürüm:** Fluent 2024 R1 yalnızca `ansys-fluent-core <= 0.37.x` ile desteklenir — **yükseltmeyin**.

## Sonuçların doğruluğu (özet)

| | Ses altı | Transonik | Süpersonik |
|---|---|---|---|
| Model içi sayısal hata | ±2–4 % | ±4–8 % | ±3–6 % |
| Modellenen gövde+burun için fiziksel | ±8–15 % | ±15–25 % | ±10–20 % |
| İki burun arasındaki K<sub>kayıp</sub> farkı | ±0,5–1,5 % | | |

Sıralama kuralı: K<sub>kayıp</sub> farkı **> %3** güvenilir, %1–3 işaret eder, **< %1** eşdeğer. Mutlak Cd, kanatçık ve motor
egzozu modelde olmadığından gerçek uçuş Cd'si değildir. Ayrıntı: [Sonuç Hassasiyet Raporu](docs/pdf/Sonuc_Hassasiyet_Raporu.pdf).

## Lisans ve katkı

Özel proje. Geliştirme Claude Code ile yapılmaktadır; kurallar [CLAUDE.md](CLAUDE.md) dosyasındadır.
