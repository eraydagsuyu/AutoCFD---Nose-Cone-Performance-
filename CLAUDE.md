# RocketCFD — Proje Anayasası (Claude Code için)

Bu dosya her oturumda okunur. Buradaki kurallar ve sabitler bağlayıcıdır; değiştirmeden önce kullanıcıya sor.
İletişim dili: **Türkçe** (teknik terimler ve kod tanımlayıcıları orijinal hâliyle).

## 0. Güncel Durum ve Sonraki Oturum (son güncelleme: 24.11.2026 02:45)
**Durum:** Geometri (80/80), mesh (80 ana + 92 ön optimizasyon adayı, hepsi Fluent kontrolünden geçti, Git'te), çözücü,
orkestratör (çoklu işçi), `rcfd`, runbook ve belgeler (`docs/pdf/` 3 PDF, `README.md`) **hazır ve push'landı**.
Üretim koşusu henüz başlamadı. İstanbul'daki `data/results.db` yalnızca test verisi içerir (P16_L300 v1,2,3,5,6,15); Ankara temiz başlar.

**Sonraki oturum: 24.11.2026, 22:45–23:00 — Ankara kurulumu.**
- Önce: arkadaş `docs/pdf/Talimatlar.pdf` adımlarını uygular (Tailscale, OpenSSH, Git/Python 3.11/Node, clone, setup_env, Claude Code).
- Eray'ın önceden göndermesi gerekenler: Tailscale daveti, SSH açık anahtarı (`docs/ankara_setup.md` B1). Depo herkese açık görünüyor;
  gizliye alınırsa Ankara'da `git clone` için token gerekir.
- Oturumda sıra (`docs/ankara_setup.md` B1–B5): SSH bağlantısı → `machine_config.json` (machine_name ankara, allow_batch true,
  workers/fluent_cores B3b lisans testine göre: 2×4 veya 1×8) → duman testi (P16_L300 v5, Cd ≈ 0,3633) → iki oturum lisans testi →
  `src\00_preopt.py --build` → `start_batch.ps1 -Campaign preopt` + `-Campaign main` → SSH kopma testi → Ankara'da Claude Code denetçi (`/loop 30m`).
- İlk geometride doğrulanacaklar: transonik warm-start zinciri süresi (~4,5 dk varsayımı), 4 çekirdekli işçi süresi, `rcfd status` ETA (~3 gün hedef).

**Açık konular:** ön optimizasyon bitince `--select` + 20 mesh yenileme + main yeniden başlatma (kullanıcı onayı, runbook 6b);
mesh bağımsızlığı (GCI) ve y⁺ çıkarımı (ana koşu sonrası öneri); nihai `04_postprocess.py` raporu.

## 0b. Ankara Otonom Dönemi (25.11.2026 → koşu bitene kadar; kullanıcı onaylı)
Kullanıcı (Eray) bu dönemde **ulaşılamaz**. Ankara'daki Claude Code (Yiğit'in terminalinde, Yiğit'in Pro hesabı) tek denetçidir.
Kullanıcı ~3–5 gün sonra SSH ile bağlanıp sonuçları alacak.
- **Döngü:** `/loop 1h` ile `docs/runbook_supervisor.md` Bölüm 1. Pro kullanım kotasını korumak için her turda kısa ol;
  sorun yoksa tek satır durum yaz. Kota dolarsa `autoContinueAtUsageLimit` ile kendiliğinden devam edilir; batch denetçisiz de çalışır.
- **Ek yetki (yalnızca bu dönem):** runbook **6b** (preopt bitince `--select` → 20 mesh üretimi → Fluent mesh kontrolü →
  `--enqueue-only` → `main_w2`) kullanıcıyı beklemeden yapılır. Diğer bütün yasaklar (fizik, domain, R/L, sınır adları,
  `done` sonuç silme, `src/` düzenleme) aynen geçerli.
- **Git:** yalnızca yerel commit; **push yok** (Ankara'nın GitHub yazma yetkisi yok). `git pull` gerekmez.
- **Kayıt:** her önemli karar/müdahale `docs/ankara_notes.md`'ye zaman damgasıyla bir satır (kullanıcı dönünce okuyacak).
- **İşçi düzeni (ölçümle, 25.11):** 2 işçi × 4 çekirdek, **CPU sabitlemeli** (`machine_config.json` → `cpu_affinity`):
  `preopt_w1` → P çekirdekleri [0,2,4,6], `main_w1` → E çekirdekleri [8–11], preopt bitince `main_w2` → [0,2,4,6].
  Ankara Intel Core 5 210H = 4P(HT)+4E. Ölçüm (P16_L300 v5, s/iterasyon): 1×4 sabitlemesiz 0,52; 1×8 ~1,8; 2×4 sabitlemesiz
  1,43 + 1,43; **2×4 sabitlemeli 0,30 (P) + 0,43 (E) → ~3× toplam verim**. `I_MPI_PIN_PROCESSOR_LIST` Fluent'te etkisiz;
  sabitleme `fluent_session._pin` ile süreç affinity'si olarak yapılır. **Asla 2'den fazla Fluent oturumu açma.**
- **Fluent süreç sahipliği:** başlatmalar `data/fluent_launch.lock` ile sıralı; her oturum yalnızca kendi süreçlerini temizler
  (eski kod, diğer işçinin Fluent'ini öldürebiliyordu — 25.11 düzeltildi).
- **Kesinti sonrası:** Görev Zamanlayıcı `RocketCFD-Resume` (oturum açılınca) `scripts\resume_batch.ps1`'i çalıştırır.
  Denetçi oturumu kesintiden sonra Yiğit'in yeniden başlatmasını bekler; işçi yoksa denetçi de `resume_batch.ps1`'i çalıştırabilir.
- **Sonuç yedeği:** `data/results_log.csv` (her koşu sonrası, fsync'li) + `data/results.db`. `rcfd export` günde bir kez (yerel).
- **Ankara'da yapılmaması gereken:** Fluent GUI açma, ağır program, `rcfd stop` (yalnızca bir işçiyi durdurur).

## 1. Proje Özeti
- Amaç: Model roket burun konisi seçimi. Her geometri için 2D **eksenel simetrik** Ansys Fluent analiziyle Cd(v) elde edilir, uçuş profili v(t) ile Cd(t)'ye çevrilir, **K_kayıp = ∫ Cd(t) dt** (trapez) hesaplanır; en düşük K_kayıp kazanır.
- Ana referans belge: `Model Roket Burun Konisi Parametrik CFD Otomasyon Mimarisi.pdf` (mimari, fazlar, SQLite şeması, klasör yapısı).
- Ham girdiler: `Nosecone_eq.txt` (20 profil denklemi, MATLAB sözdizimi), `Vt_graph.txt` (20 hız noktası, ondalık ayırıcı **virgül**).
- Onaylı plan: `C:\Users\Eray\.claude\plans\glittery-snacking-pnueli-of-e8598dce-f6f5-47ba-837b-b9e1a2a58534.md`

## 2. Sabit Tasarım Parametreleri (DEĞİŞTİRİLEMEZ)
| Parametre | Değer |
|---|---|
| Gövde ve burun dış yarıçapı `R` | **49 mm** (0,049 m) — tüm geometrilerde aynı |
| Burun konisi toplam uzunluğu `L` | **200, 300, 400, 500 mm** (4 değer) |
| Gövde uzunluğu (burun arkası, düz silindir) | **2,0 m** |
| Mesh uç radyusu `rn_mesh` (singularity önleme) | **1 mm** — yalnızca singularity oluşturan profillere |
| Profil sayısı | 20 |
| Geometri sayısı | 20 profil × 4 L = **80** |
| Hız noktası | 20 (`Vt_graph.txt`) |
| Ana analiz matrisi | 80 × 20 = **1.600** koşu |

Kurallar:
- `R` ve `L` hiçbir optimizasyonda dışarı çıkamaz: profil hiçbir noktada `y > R` olamaz, burnun toplam eksenel uzunluğu tam olarak `L` olmalıdır.
- 1 mm uç yuvarlatması **yalnızca mesh'te singularity oluşacak profillere** uygulanır (kullanıcı kararı):
  (a) uçta sonlu eğimli sivri tepe → 01, 03, 05, 06, 07, 10, 11, 12;
  (b) uçta eğrilik yarıçapı < 1 mm (y ~ x^(2/3), x^(3/4)) → 14, 15, 16, 17, 18, 20;
  19 hiperbolik için uç eğrilik yarıçapı `R²a/(L²+2aL)` kodda kontrol edilir.
  Uygulanmaz: 02 ve 08 (kendi körleştirme yarıçapları var), 04 (düz meplat yüzeyi), 09 ve 13 (uç eğrilik yarıçapı ≥ 2,4 mm).
  Sınıflandırma `config/nose_params.json`'da; `01_mesh_gen.py` bunu sayısal olarak yeniden doğrular.
- Yuvarlatma: profile teğet, merkezi eksen üzerinde bir çember yayı. Yuvarlatma ucu kısalttığından, toplam uzunluk `L` olacak şekilde keskin profil uzunluğu `L'` iteratif olarak ayarlanır (`L' − δ(L') = L`).
- Koordinatlar: burun ucu x = 0, akış +x yönünde, roket ekseni **y = 0** (`axis`). Birimler SI (m, m/s, Pa, K); mm yalnızca dosya/ID adlarında.

## 3. Profil Denklemleri ve Türetilen Parametreler
`Nosecone_eq.txt` MATLAB sözdizimindedir (`.*`, `.^`, `./`). Python'a çevirirken `eval` yalnızca kısıtlı NumPy isim alanıyla kullanılır.
- `rho` (tanjant ogive yarıçapı) = (R² + L²) / (2R). Sekant ogive'ler (06, 07) bu `rho`'yu 1,5 / 0,75 katsayısıyla kullanır.
- `th` (Haack, 16–18) = arccos(1 − 2x/L).
- `xtc, x0c` (02) ve `xto, x0o` (08): `rn` küresinin koni/ogive'e teğet noktası ve küre merkezi — kodda analitik olarak hesaplanır.
- Profil ID formatı: `P{NN}_L{LLL}` (ör. `P16_L300`). Bu ID SQLite'taki `nose_cone_id`'dir.
- Geometri yalnızca `src/common/geometry.py` ile üretilir (`build_geometry` / `build_all`). Serbest parametre: `nose_params.json` → `selected["L200"]` varsa o, yoksa `provisional`.
- Doğrulanmış durum (2026-11-23): 80/80 geometri geçerli, uç sınıflandırması beklenenle birebir; uzunluk hatası < 0,001 µm; R'yi aşan geometri yok.
- **Kullanıcı kararı:** Orijinal 07 (şişkin sekant ogive, ρ = 0,75ρt) R'yi ~1 mm aştığı için **ρ = 1,25ρt orta sekant ogive** ile değiştirildi (`inputs/raw/Nosecone_eq.txt` güncellendi; kökteki orijinal dosya değiştirilmedi). ρ < ρt olan sekant ogive'ler R'yi aşar — kullanılmaz.

### Ön optimizasyonla belirlenecek serbest parametreler (Claude belirler)
| Profil | Parametre | Aday aralığı (başlangıç) | Kısıt |
|---|---|---|---|
| 02 / 08 Küresel körleştirilmiş | `rn` | rn/R ∈ {0,05; 0,10; 0,20; 0,30} | rn < R |
| 03 Bi-konik | `L1`, `R1` | L1/L ∈ {0,3…0,7}, R1/R ∈ {0,5…0,85} | 0<L1<L, 0<R1<R, dışbükeylik: R1/L1 > (R−R1)/(L−L1) |
| 04 Meplatlı konik | `Rt` | Rt/R ∈ {0,05; 0,10; 0,15; 0,20; 0,30} | Rt ≥ rn, Rt < R |
| 19 Hiperbolik | `a` | a/L ∈ {0,05; 0,1; 0,25; 0,5; 1,0} | a > 0 |

- Her `L` için ayrı optimize edilir (parametreler L'ye göre boyutsuz tutulur ama sonuç L başına seçilir).
- Ön optimizasyon amaç fonksiyonu: ana çalışmayla **aynı** K_kayıp metriği, ancak azaltılmış hız kümesiyle (rejimleri temsil eden ~4 nokta: ses altı düşük, ses altı yüksek, transonik, süpersonik). Gerekirse ikinci aşamada en iyi adayın çevresinde ince tarama.
- Seçilen değerler `config/nose_params.json` içine yazılır; seçim gerekçesi ve sonuç tablosu `docs/preopt_report.md`'ye kaydedilir.
- 02 ve 08'in körleştirme yarıçapı `rn`, 1 mm mesh radyusundan bağımsız bir tasarım parametresidir ve ön optimizasyonla seçilir.

## 4. Fizik ve Çözücü Kuralları
- Ansys **2024 R1** (v241). Fluent her zaman headless: `fluent 2ddp -g -t<N>` — **GUI asla açılmaz**.
- Arayüz: PyFluent **`ansys-fluent-core==0.37.2`** (24.1'i destekleyen son sürüm; 0.38+ yalnızca 24.2+ destekler — **yükseltme**). Gerekirse yedek yol: Python dinamik `.jou` üretir ve `-i run.jou` ile çalıştırır.
- Fluent oturumu **yalnızca** `src/common/fluent_session.py` → `fluent_solver(...)` context manager ile açılır. `session.exit()` v241'de `fluent.exe` + `cx2410.exe` süreçlerini açık bırakabiliyor; yardımcı modül başlatmadan sonra doğan artık süreçleri temizler. Doğrudan `pyfluent.launch_fluent` çağırma.
- Model: **Axisymmetric**, ideal gaz hava + enerji denklemi, k-ω SST. Mach 0,06–1,26 aralığı nedeniyle sıkıştırılabilir çözüm zorunludur (density-based veya pressure-based coupled).
- Dış sınır şartı: `pressure-far-field` (Mach + statik p, T). Statik p, T her hız noktası için o noktanın irtifasında **ISA** atmosferinden hesaplanır.
- **Reference Values** her hız adımında güncellenir: velocity, density, temperature, pressure; **area = π·R²**, length = L. Unutulursa tüm Cd'ler hatalıdır.
- Mesh başına tek Fluent oturumu; hızlar artan sırada; ilk hızda başlatma (profilde tanımlı: hybrid/FMG), sonrakilerde warm-start. Mesh değişince oturum kapatılır.
- Cd, drag report `.out` dosyasından son N iterasyon ortalamasıyla okunur. Yakınsama: residual + Cd penceresi (bağıl std). Ayrıntı: Bölüm 10.
- Transonik bölge (Mach ≈ 0,9–1,1) zor yakınsar: ayrı rejim profili (düşük CFL, uzun rampa, yüksek iterasyon limiti).
- `.dat.h5` yalnızca her mesh'in en düşük ve en yüksek hızı için saklanır; "son iyi durum" checkpoint'i koşu bitince silinir.

## 5. Mesh Kuralları (hibrit: yapısal BL + Gmsh üçgen → Fluent .msh)
- Sınır isimleri sabit sözleşmedir: **`inlet`, `outlet`, `farfield`, `wall_rocket`, `axis`** (hücre bölgesi: `fluid`). Değiştirilemez.
  BC tipleri dosyaya gömülü: inlet/outlet/farfield = `pressure-far-field`, wall_rocket = `wall`, axis = `axis`.
- Gövde arkası (taban) `wall_rocket`'e dahildir. Çıktı **Fluent'in kendi ASCII `.msh` formatı, gzip'li** (`meshes/<ID>.msh.gz`, Fluent doğrudan okur), `src/common/fluent_msh.py` yazar.
- **Mesh'ler Git'te tutulur** (80 × ~2,3 MB ≈ 180 MB; kullanıcı kararı: Ankara'da yeniden üretimle vakit kaybedilmesin). Geometri/mesh ayarı değişirse ilgili `.msh.gz` yeniden üretilip commit'lenir.
  Ön optimizasyon sonrası serbest parametreli profiller (02, 03, 04, 08, 19 → 20 mesh) yeniden üretilecektir.
  PDF'teki "Fluent MSH2 okur" bilgisi yanlıştır (MSH2 Gmsh formatıdır) — Gmsh çıktısı Fluent'e doğrudan verilmez.
- **Gmsh BoundaryLayer alanı kullanılmaz**: duvarın eksenle buluştuğu noktada bozuk fan üretiyor (minSJ ≈ 0,001). Sınır tabakası
  `src/common/mesher.py` içinde yapısal olarak örülür: duvar düğümleri → dış normal boyunca geometrik katmanlar
  (h1 = 1 µm, oran ≈ 1,2, kalınlık 4 mm, 37 katman), küçük kırıklarda açıortay normali, dışbükey köşelerde (taban köşesi, meplat köşesi) fan.
  Uç ve taban-eksen kolonları eksen üzerindedir. Dış bölge: Gmsh Frontal-Delaunay üçgen; BL üst kenarı sabit sınırdır.
- Gmsh `Threshold` alanlarında **`StopAtDistMax = 1` zorunlu** — yoksa SizeMax tüm alana uygulanır ve mesh milyarlarca hücreye gider.
- Fluent yüz yönü (2D): n0→n1 yönünde c0 **solda**. Ters yazılırsa tüm hücreler negatif hacimli görünür.
- Ayarlar `config/mesh_settings.json`'da. Domain: önde 2·Lb, radyal 2·Lb, arkada 5·Lb (Lb = L + 2 m).
- Kalite kapısı: Python'da negatif alan = 0 ve max equiangle skewness ≤ 0,90; Fluent'te min orthogonal quality ≥ 0,05
  (`src/tools/check_mesh_fluent.py`). Geçemeyen mesh kaydedilmez → `mesh_error`.
- Referans sonuç P16_L300: 104 bin hücre, max skewness 0,75 (fan ilk katmanı), Fluent min OQ 0,31, `mesh/check` temiz.
- **Doğrulanmış durum (2026-11-23):** 80/80 mesh Fluent 2024 R1 `mesh/check` + `mesh/quality` geçti; min OQ = 0,14 (tümü), 92–128 bin hücre. Rapor: `docs/mesh/fluent_mesh_check.csv`.
- Meplat (04) köşesinde duvar boyutu `tip_region` (0,3 mm) olmalı; `tip_arc` (50 µm) kullanılırsa BL üst kenarında aralık sıçrar ve OQ < 0,05 olur.

## 6. Çalışma Ortamı ve Makine Kuralları
- Python her zaman `.venv\Scripts\python.exe` ile çalıştırılır; yollar `src/common/config.py`'den alınır. Yeni makinede kurulum: `scripts\setup_env.ps1`.
- Windows + PowerShell uyumlu komutlar. Kodda sabit mutlak yol yok: makineye özel her şey `machine_config.json`'dan okunur (fluent.exe yolu, çekirdek sayısı, Python yolu). Git'te yalnızca `machine_config.example.json` tutulur.
- **İstanbul (yerel, geliştirme):** yalnızca `--mode single` (1 mesh × 1 hız). Toplu döngü yerelde **başlatılmaz**.
- **Ankara (uzak, üretim):** Tailscale + OpenSSH ile erişim; `git pull` → `--mode batch`. Toplu koşu SSH'tan bağımsız arka plan süreci olarak (`Start-Process`) başlatılır, tüm çıktı `logs/` altına.
- Durum takibi: `data/results.db` (SQLite) — şema ve durum makinesi Bölüm 10'da. Yeniden başlatmada yalnızca bekleyen (ve yarım kalmış `running`) koşular çözülür; tamamlananlar tekrarlanmaz.
- Her istisna yakalanır ve SQLite'a (`attempts.error_msg`) + `logs/events.jsonl` + log dosyasına yazılır; tek bir koşu hatası tüm batch'i durdurmaz.
- **Sonuç yedeği:** her koşu kesinleştiğinde (`done`, `done_flagged`, `needs_review:<sınıf>`) orkestratör `data/results_log.csv`'ye
  bir satır ekler (`src/common/results_log.py`; kilitli, fsync'li, çoklu işçi güvenli). SQLite asıl kayıttır; CSV kesintiye karşı okunabilir yedektir.
- **`.ps1` dosyaları UTF-8 BOM'lu kaydedilmeli:** Windows PowerShell 5.1 BOM'suz dosyayı ANSI (Ankara: cp1254) okur; Türkçe karakter
  ve `—` ayrıştırmayı bozar (2026-11-24 Ankara'da `setup_env.ps1` ve `start_batch.ps1` çalışmadı, düzeltildi).

## 7. Klasör Yapısı
```
C:\RocketCFD\
├── CLAUDE.md
├── .gitignore                    # machine_config.json, data/, logs/, düz *.msh hariç
├── machine_config.example.json
├── machine_config.json           # Git'e girmez
├── requirements.txt
├── config\  velocities.json, flight_profile.csv, nose_params.json, mesh_settings.json,
│            recovery_policy.json, solver_profiles\ (base + subsonic/transonic/supersonic)
├── inputs\raw\                   # Ham girdiler: Nosecone_eq.txt, Vt_graph.txt (elle düzenlenmez)
├── inputs\nose_cones\            # 20 profil denklemi (.txt) — src/tools/prepare_inputs.py üretir
├── .venv\                        # Python 3.11 sanal ortamı (Git'e girmez) — scripts\setup_env.ps1 kurar
├── src\
│   ├── common\                   # config.py (yollar + json okuma), fluent_session.py (güvenli oturum),
│   │                             # geometry.py (denklem → profil, uç sınıflandırma, 1 mm yay, L' iterasyonu)
│   │                             # mesher.py (yapısal BL + Gmsh üçgen), fluent_msh.py (Fluent .msh yazıcı)
│   ├── tools\check_geometry.py   # 80 geometri doğrulaması + docs/geometry/ grafikleri
│   ├── tools\check_mesh_fluent.py # .msh -> headless Fluent mesh/check + quality
│   ├── tools\prepare_inputs.py   # raw -> config/ + nose_cones/ dönüşümü (tekrarlanabilir)
│   ├── tools\check_env.py        # paket + headless Fluent başlat/kapat testi
│   ├── 00_preopt.py              # rn (02/08), L1/R1, Rt, a ön optimizasyonu
│   ├── 01_mesh_gen.py
│   ├── 02_fluent_solver.py       # tek koşu: profil+override -> izleme -> sınıflandırma -> Cd
│   ├── 03_orchestrator.py        # --mode single | batch; kuyruk + otomatik kurtarma
│   ├── 04_postprocess.py
│   └── rcfd.py                   # denetçi CLI: status, failures, inspect, retry, skip, pause, resume
├── scripts\                      # setup_env.ps1, start_batch.ps1
├── docs\                         # runbook_supervisor.md, preopt_report.md, sonuç raporları
├── meshes\                      # <ID>.msh.gz — Git'te tutulur
├── data\  logs\                # Git'e girmez
```

## 8. Geliştirme Sırası (küçük, test edilebilir adımlar)
1. ✅ İskelet + config dosyaları.
2. ✅ Geometri: 80 profil (y ≤ R, uzunluk = L, uç yuvarlatma teğetliği).
3. ✅ Mesh: 80/80 Fluent kontrolünden geçti, Git'te.
4. ✅ Çözücü: profiller, izleme, sınıflandırma, checkpoint; hızlandırma (enhanced-CASM + CFL 50) ölçümle seçildi.
5. ✅ Orkestratör: SQLite, kuyruk, warm-start zinciri, hız oranı kuralı, kurtarma basamakları, çoklu işçi.
6. ✅ `rcfd.py` + runbook; kurtarma zinciri gerçek bir ıraksamayla (v2) uçtan uca doğrulandı.
7. ⏳ Ön optimizasyon: 92 aday mesh hazır (`meshes/preopt/`), 368 koşu — Ankara'da `preopt` kampanyası; sonra `--select` + 20 mesh.
8. ⏳ Ankara: kurulum (`docs/ankara_setup.md`), denetçi Claude Code, batch.
9. Son işleme (`04_postprocess.py`, henüz yazılmadı; `common/metrics.py` hazır): Cd(v) → Cd(t), K_kayıp, ∫v²·Cd dt, sıralama, grafikler.

Her adımın sonunda doğrulama yapılmadan sonrakine geçilmez.

## 10. Denetimli Çözüm Mimarisi (kullanıcı onaylı, 2026-11-23)
**İlke:** Batch denetçi olmadan da uçtan uca çalışır. Rutin kurtarmayı Python yapar; denetçi (Ankara'daki Claude Code)
yalnızca otomatik basamakların çözemediği koşulara müdahale eder ve bunu **kod değil veri** değiştirerek yapar.

Katmanlar:
- **Çözücü** (`02_fluent_solver.py`): tek koşu. Ayarlar `config/solver_profiles/` (base + rejim) + koşuya özel override'dan birleşir.
  Her N iterasyonda Cd ve residual okunur; başarısızlık sınıflandırılır; "son iyi durum" checkpoint'i tutulur.
  Residual/Cd geçmişi `logs/runs/<run_id>/<attempt>/history.csv` dosyasına yazılır.
- **Orkestratör** (`03_orchestrator.py`): SQLite kuyruğu, `config/recovery_policy.json` basamakları, `control` tablosunu koşular arasında okur
  (pause / stop-after-current / öncelik). Fluent yazarken asla kesilmez.
- **Denetçi** (Claude Code, Ankara): `/loop` ile düzenli `rcfd status` + `logs/events.jsonl`; yalnızca `src/rcfd.py` ile müdahale eder.

Başarısızlık sınıfları: `diverged` (NaN / FPE / residual patlaması), `oscillating` (Cd sınırlı salınım), `stalled` (residual düşmüyor, Cd sürükleniyor),
`crash`, `timeout`; salınım genliği < %1 ise ortalama Cd kabul edilir → `done_flagged`.

Durum makinesi (`runs.status`): `pending → running → done | done_flagged | retry_pending → running … → needs_review | skipped | mesh_error`.

SQLite tabloları: `runs` (geom_id, vel_idx, mach, altitude, status, cd, mesh_version), `attempts` (run_id, attempt_no, profile_hash,
overrides_json, outcome, iterations, cd, cd_rel_std, log_dir, decided_by = auto|agent|human, reason), `events`, `control`.

**Geçerlilik kuralı:** `done` sayılan her Cd ikinci derece ayrıklaştırma ve tam yakınsama ölçütüyle elde edilmiş olmalı — kurtarma yolu sonucu etkilemez.

**Fizik kilidi:** Override yalnızca izin listesindeki sayısal anahtarlarda yapılabilir (CFL ve rampası, ayrıklaştırma geçiş iterasyonu,
under-relaxation, başlatma yöntemi, iterasyon limiti, yakınsama penceresi, çözücü tipi). Türbülans modeli, domain, mesh, BC tipi,
Reference Values, gaz modeli override edilemez (80 geometrinin Cd'leri karşılaştırılabilir kalmalı).

### Doğrulanmış tekli koşular (İstanbul, 10 çekirdek, i5-12450H)
| Koşu | Rejim | Sonuç | Cd | İterasyon | Süre | Not |
|---|---|---|---|---|---|---|
| P16_L300 v05 (M 0,31) | subsonic | done | 0,3638 | 1750 | 7,3 dk | residual 5–8 mertebe düştü; el hesabıyla tutarlı (sürtünme ~0,23 + taban ~0,13) |
| P16_L300 v16 (M 0,999) | transonic | done_flagged | 0,4689 | 8000 (max) | 27 dk | Cd ±%0,43 salınım, süreklilik residual'ı ~4e-3'te plato — taban izi/şok kararsızlığı |

| P16_L300 v17 (M 1,062) | transonic, warm-start (v16'dan) | done_flagged | 0,4913 | 4451 | 12,8 dk | ortalama yakınsaması; soğuk v16'nın yarı süresi |

- Fluent v241 settings API notları: flux adları `Roe-FDS` / `AUSM` (büyük harf); far-field TVR anahtarı `turbulent_viscosity_ratio_real`;
  DBNS ayrıklaştırma anahtarları `amg-c`, `k`, `omega`; FMG yalnızca hybrid init sonrası aktif; FAS multigrid implicit DBNS'de pasif;
  CASM: `methods.convergence_acceleration_for_stretched_meshes.convergence_acceleration_type` ∈ {disable-casm, casm, enhanced-casm}.
- **Fluent iterasyon sayacı** veri dosyasından / önceki hızdan devam eder → deneme içi iterasyon daima bu denemenin `cd.out` satır sayısıdır
  (mutlak numara kullanma; kullanılırsa warm-start 50 it sonra yanlış "done" verir — yaşandı, düzeltildi).
- Fluent'e verilen dosya yolları **mutlak** olmalı (Fluent kendi cwd'sinden okur).
- **Ortalama yakınsaması** (`mean_window`, `mean_rel_change`, `mean_max_amp`): kalıcı salınımlı transonik akışlar için. Soğuk başlatmada
  yavaş iz gelişimi platolarında erken durabilir (2,6 % hata gözlendi) → eşikler sıkı (500 it / %0,1) ve asıl hızlandırma warm-start.
- Warm-start profil anahtarları `warm_*`: yakınsamış alandan başlarken 1. derece aşaması atlanır, kısa CFL rampası.
- **Hızlandırma kararı (2026-11-24, ölçümle):** tüm rejimlerde `casm = enhanced-casm`, `courant_end = 50`.
  v17 warm-start karşılaştırması (referans Cd 0,4913): CFL 5 → ~4000 it; CFL 20 → ~1000 it; CASM+CFL 5 → ~1500 it;
  **enhanced-CASM + CFL 50 → ~500 it** (8× hızlanma). Doğrulama: v05 soğuk 900 it/3,3 dk (Cd 0,3633, önceki ayarla fark %0,14),
  v19/v20 süpersonik warm 1401 it/4,4 dk, ıraksama yok. Iraksarsa kurtarma basamakları CFL'yi yarıya indirir.
- **Düşük Mach + büyük hız sıçraması:** v1 (M 0,062) → v2 (×2 hız) warm-start; CASM açık/kapalı, CFL 1,5–50 **hepsi ıraksadı**;
  soğuk başlatma sorunsuz. Kural: `warm_max_velocity_ratio = 1,3` — kaynak alanın hızıyla oran > 1,3 ise otomatik soğuk (hybrid)
  başlatma (pratikte v2, v3, v4 soğuk; v5 ve sonrası warm). Orkestratör `_auto_warm_ok`.
- **Iraksama ölçütü mutlak olmalı** (`div_residual_abs = 10`, `div_cd_abs = 50`, NaN/Inf): göreli residual artışı warm-start'ta
  yanlış alarm üretti (yakınsamış alanın küçük residual'ları hız değişince normal olarak birkaç mertebe yükselir).
- `solver_type = pressure-based` izin listesinden çıkarıldı (v241'de ayar yolu doğrulanmadı).
- Kurtarma zinciri uçtan uca doğrulandı (v2): diverged → last_good → neighbor → hybrid → stalled → previous → done_flagged.
  Python hatası (`crash`) → oturum yeniden açılır (≤ 3), artık Fluent süreçleri temizlenir, koşu `needs_review` olur.

### Çekirdek ölçeklenmesi ve çoklu işçi (2026-11-24, ölçümle)
- v1 soğuk koşu: 5 çekirdek 215 s, 10 çekirdek 191 s → 2D ~100 bin hücrede ölçeklenme zayıf. **8 çekirdekte 2 işçi × 4 çekirdek**.
- İşçiler geometriyi atomik sahiplenir (`claims` tablosu); ölü işçinin sahiplenmesi düşer ve yarım koşusu `retry_pending` olur.
  İşçi adı `<kampanya>_w<i>`; kilit `data/orchestrator_<işçi>.lock`; kalp atışı `control.heartbeat:<işçi>`.
- Fluent hiç açılamazsa (lisans) koşular cezalandırılmaz; işçi 3 denemeden sonra `worker_exit` olayıyla çıkar.
- Ana kampanya yalnızca **kesin** geometrileri kuyruğa alır (`main_geoms(final_only)`): 02/03/04/08/19, ön optimizasyon o L için
  `selected` yazana kadar dışarıda (60 sabit geometri). Seçim + mesh yenileme sonrası orkestratör yeniden başlatılınca eklenir.

### Süre tahmini (Ankara, 2 işçi × 4 çekirdek; İstanbul ölçümlerinden ×1,13)
| İş | Birim süre | Toplam |
|---|---|---|
| Ana: geometri başına (v1–v4 soğuk, v5–v11 warm ~3,2 dk; transonik/süpersonik warm ~4,5 dk) | ~86 dk | 80 × 86 dk ≈ 115 işçi-saati |
| Ön optimizasyon: aday başına (v5, v10, v15 soğuk; v19 warm) | ~19,5 dk | 92 × 19,5 dk ≈ 30 işçi-saati |
| **Toplam (2 işçi)** | | **≈ 72 saat ≈ 3 gün** |
Transonik warm zinciri (v12→v18) orkestratörde henüz uçtan uca ölçülmedi (v17 warm testi: ~500 it); Ankara'nın ilk geometrisinde doğrulanır.
Önerilen başlangıç: önce `src\00_preopt.py --build` (92 aday mesh Git'te hazır; yalnızca 368 koşuyu yeni makinenin DB'sine kaydeder —
**atlanırsa preopt kampanyası "kuyruk boş" deyip çıkar**), sonra `start_batch.ps1 -Campaign preopt -Workers 1` + `start_batch.ps1 -Campaign main -Workers 1`.

### Belgeler (PDF)
- `docs/pdf/Talimatlar.pdf` (Ankara sıfırdan kurulum, arkadaş için), `Sistem_Raporu.pdf`, `Sonuc_Hassasiyet_Raporu.pdf`.
- Üretim: `src\tools\report_figures.py` (veri + şekiller → `docs/report_assets/`), ardından `build_talimatlar.py`,
  `build_sistem_raporu.py`, `build_hassasiyet_raporu.py`. Stil: `src/tools/pdf_style.py` (Arial TTF; Unicode üst simgeler
  otomatik `<super>`'e çevrilir; kod kutusu satırı ≤ 100 karakter, aşılırsa hata verir).
- Hassasiyet raporunun ana iddiası: sıralama güvenilir (K farkı > %3), mutlak Cd gerçek uçuş Cd'si değil (kanatçık/egzoz yok).
  **Mesh bağımsızlığı (GCI) yapılmadı** — ağ hatası tahmindir; ana koşu sonrası önerilir.
- Aday mesh hatası (düzeltildi): küresel körleştirme başlangıcındaki ~1e-10 m yuvarlama kalıntısı "meplat" sanılıyordu →
  meplat eşiği `1e-5·L` (`geometry.classify_tip`). 92/92 aday mesh Fluent kontrolünden geçti (min OQ 0,23).

### Çalıştırma ve araçlar
- Tekli (İstanbul): `src\03_orchestrator.py --mode single --geom P16_L300 --vel 5` (DB'ye yazar, kurtarma basamaklarıyla).
  Ham tekli test (DB'siz): `src\02_fluent_solver.py --geom ... --vel ... [--set k=v] [--init-file x.dat.h5]`.
- Batch (Ankara): `scripts\start_batch.ps1` — süreç **WMI `Win32_Process.Create`** ile başlatılır; `Start-Process` kullanma
  (Windows OpenSSH, oturumdan başlatılan süreçleri Job Object'le birlikte sonlandırabilir).
- Orkestratör: geometri başına tek oturum, hızlar artan sırada; başlatma `previous` (oturumdaki yakınsamış alan) → `neighbor`
  (`data/fields/<geom>/latest.dat.h5`) → `hybrid`. Kilit: `data/orchestrator.lock`; kalp atışı `control.heartbeat`.
- Denetçi: `src\rcfd.py` (status, failures, inspect, events, profile, export, retry, requeue, skip, priority, pause, resume, stop).
  Rehber: `docs/runbook_supervisor.md`. Ankara kurulumu: `docs/ankara_setup.md`.

### Ankara denetçisi yetkileri (kullanıcı onaylı)
- **Kendi başına yapabilir:** koşuya özel sayısal override ile `rcfd retry`; `rcfd skip` (gerekçeyle); pause/resume;
  aynı düzeltme çok koşuda işe yarıyorsa rejim profilini değiştirip gerekçeli commit + push ve etkilenen koşuları yeniden kuyruğa alma.
- **Kullanıcıya sormadan yapamaz:** fizik/mesh/domain değişikliği, mesh yeniden üretimi, `R`/`L`/sınır isimleri, `done` sonuçların silinmesi.
- Her müdahalede `--reason` zorunludur; `attempts.decided_by = agent` olarak kaydedilir. Teşhis rehberi: `docs/runbook_supervisor.md`.

## 9. Yapma Listesi
- Fluent'i GUI ile açma; yerelde batch başlatma.
- Sınır isimlerini, `R`, `L` değerlerini veya `rn`'yi kendi başına değiştirme.
- Sabit yol gömme; `machine_config.json`'u, `data/`, `logs/` klasörlerini ve sıkıştırılmamış `.msh` dosyalarını commit'leme.
- Reference Values güncellemesini atlama.
