# RocketCFD — Proje Anayasası (Claude Code için)

Bu dosya her oturumda okunur. Buradaki kurallar ve sabitler bağlayıcıdır; değiştirmeden önce kullanıcıya sor.
İletişim dili: **Türkçe** (teknik terimler ve kod tanımlayıcıları orijinal hâliyle).

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
- Mesh başına tek Fluent oturumu; hızlar artan sırada; yalnızca ilk hızda `hybrid-init`, sonrakilerde warm-start. Mesh değişince oturum kapatılır.
- Cd, drag report `.out` dosyasından son N iterasyon ortalamasıyla okunur. Yakınsama: residual + Cd bağıl değişimi. Zaman aşımı veya ıraksama → `diverged`, sıradaki adıma geçilir.
- Transonik bölge (Mach ≈ 0,9–1,1) zor yakınsar: daha yüksek iterasyon limiti / CFL rampası tanımlanır.
- `.dat.h5` yalnızca her mesh'in en düşük ve en yüksek hızı için saklanır.

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
- Durum takibi: `data/results.db` (SQLite). Yeniden başlatmada yalnızca `pending` (ve yarım kalmış `running`) satırlar çözülür. Durumlar: `pending, running, done, diverged, mesh_error`.
- Her istisna yakalanır ve SQLite'a (`error_msg`) + log dosyasına yazılır; tek bir koşu hatası tüm batch'i durdurmaz.

## 7. Klasör Yapısı
```
C:\RocketCFD\
├── CLAUDE.md
├── .gitignore                    # machine_config.json, data/, logs/, düz *.msh hariç
├── machine_config.example.json
├── machine_config.json           # Git'e girmez
├── requirements.txt
├── config\  velocities.json, flight_profile.csv, nose_params.json
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
│   ├── 02_fluent_solver.py
│   ├── 03_orchestrator.py        # --mode single | batch
│   └── 04_postprocess.py
├── scripts\                      # start_batch.ps1, status.ps1
├── docs\                         # preopt_report.md, sonuç raporları
├── meshes\                      # <ID>.msh.gz — Git'te tutulur
├── data\  logs\                # Git'e girmez
```

## 8. Geliştirme Sırası (küçük, test edilebilir adımlar)
1. İskelet + config dosyaları (Vt_graph → velocities.json / flight_profile.csv, denklemlerin bölünmesi).
2. Geometri: 80 profilin üretimi + grafiksel sağlama (y ≤ R, uzunluk = L, uç yuvarlatma teğetliği).
3. Tekil mesh doğrulaması (1 geometri).
4. Tekil Fluent doğrulaması (1 mesh × 1 hız) → Cd → SQLite.
5. Ön optimizasyon (03, 04, 19 için serbest parametreler) — Ankara'da.
6. Orkestratör + batch (1.600 koşu) — Ankara'da.
7. Son işleme: Cd(v) → Cd(t) (lineer/PCHIP), K_kayıp, yardımcı ∫v²·Cd dt, sıralama ve grafikler.

Her adımın sonunda doğrulama yapılmadan sonrakine geçilmez.

## 9. Yapma Listesi
- Fluent'i GUI ile açma; yerelde batch başlatma.
- Sınır isimlerini, `R`, `L` değerlerini veya `rn`'yi kendi başına değiştirme.
- Sabit yol gömme; `machine_config.json`'u, `data/`, `logs/` klasörlerini ve sıkıştırılmamış `.msh` dosyalarını commit'leme.
- Reference Values güncellemesini atlama.
