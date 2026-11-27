# Denetçi Runbook'u (Ankara — Claude Code)

Bu belge Ankara'daki Claude Code'un (denetçi) toplu koşuyu nasıl izleyeceğini ve müdahale edeceğini tanımlar.
Yetki sınırları `CLAUDE.md` Bölüm 10'dadır; bu belge onları **genişletmez**.

> **Otonom dönem (CLAUDE.md Bölüm 0b) geçerliyken:** "kullanıcıya bildir" yazan her yerde → `docs/ankara_notes.md`'ye zaman
> damgalı satır yaz ve devam et; `git push` yapma (yalnızca yerel commit); 6b'yi kendin uygula. Ölen/çıkan işçiyi Görev Zamanlayıcı
> (`RocketCFD-Resume-30dk`) 30 dk içinde yeniden başlatır; acil durumda `scripts\resume_batch.ps1` çalıştır.

## 0. Temel ilke
- Orkestratör denetçi olmadan da çalışır. Rutin kurtarmayı (`config/recovery_policy.json`) kendisi yapar.
- Denetçi yalnızca `needs_review` koşulara ve sistem sağlığına bakar. Müdahale **sadece** `src/rcfd.py` ile yapılır.
- Kod dosyalarını (`src/`) toplu koşu sırasında **düzenleme**. Fizik (`config/physics.json`), mesh ve domain değişmez.
- Her müdahalede `--reason` zorunlu: ne gördün, neden bu ayarı seçtin (bir cümle).

Komut kısaltması (PowerShell, proje kökünde):
```
$r = ".venv\Scripts\python.exe src\rcfd.py"
```

## 1. Döngü (örn. `/loop 30m` ile)
0. `.venv\Scripts\python.exe src\tools\progress.py` — tek ekranda yüzde, işçiler, son Cd'ler, tahmini bitiş.
1. `rcfd status` (ve `rcfd --campaign preopt status`) — kalp atışı 15 dk'dan eskiyse → Bölüm 5 (orkestratör sağlığı).
   Eski `single` kalp atışı (24.11 duman testi) gerçek işçi değildir, yok say.
2. `rcfd events --tail 40 --level WARNING` — yeni uyarı/hata var mı?
3. `rcfd failures` — `needs_review` listesi. Boşsa dur.
4. Her biri için `rcfd inspect <run>` → `logs\inspect\<geom>_vNN.png` grafiğini oku → Bölüm 2'deki tabloya göre karar ver.
5. Aynı sorun ≥ 3 geometride aynı rejimde tekrarlıyorsa → Bölüm 3 (kalıcı profil değişikliği).

## 2. Teşhis tablosu

| Son sonuç / belirti | Olası neden | Önerilen müdahale |
|---|---|---|
| `diverged`, ilk 100–300 it, Cd NaN veya residual 3+ mertebe artış | CFL rampası agresif; şok bölgesinde ani değişim | `retry --init neighbor --set courant_end=<yarısı> --set warm_courant_ramp_iters=400 --set warm_first_order_iters=300` |
| `diverged`, tüm otomatik basamaklar dahil (AUSM, FMG) | Hız adımı çok büyük, transonik şok yerleşimi | Bir **üst** hız noktası çözülmüşse ondan başlat: önce o koşuyu bitir, sonra `retry --init neighbor` (neighbor = geometrinin en son yakınsamış alanı) |
| `oscillating` / `done_flagged` sık, salınım ±%0,5–2 | Küt taban izi veya şok kararsızlığı (fiziksel) | `retry --init previous --set mean_window=800 --set max_iters=4000`; salınım ±%1 altındaysa ortalama kabul edilir |
| `stalled`, Cd yavaş monoton sürükleniyor | İz bölgesi gelişimi bitmemiş | `retry --init previous --set max_iters=6000 --set courant_end=<×1,5>` |
| `timeout` | Makine yavaş / çok iterasyon | `retry --init previous --set timeout_s=14400` |
| `crash` (gRPC, lisans, bellek) | Fluent süreci öldü | `rcfd events` ile lisans/bellek hatasına bak; geçiciyse `retry --init neighbor` |
| `mesh_error` | Mesh dosyası yok/bozuk | **Müdahale etme** — kullanıcıya bildir (mesh yeniden üretimi kullanıcı onayı ister) |
| Cd fiziksel olarak tuhaf (komşu hızlardan > %15 sapma, negatif) | Yanlış yakınsama, şok yerleşimi | `retry --force --init neighbor --reason "..."` ve sonucu karşılaştır; tekrar ederse kullanıcıya bildir |

İzinli override anahtarları ve aralıkları: `rcfd profile <run>` çıktısının sonunda listelenir.
`--set` ile izin listesi dışında bir anahtar verilirse komut **reddedilir** (fizik kilidi).

## 3. Kalıcı profil değişikliği (rejim dosyaları)
Koşul: aynı düzeltme aynı rejimde ≥ 3 farklı geometride başarılı olduysa.
1. `config/solver_profiles/<rejim>.json` dosyasında yalnızca sayısal anahtarı değiştir (izin listesindeki anahtarlar).
2. `git commit -m "profil(<rejim>): <anahtar> <eski> -> <yeni> — gerekçe: <...>"` ve `git push`.
3. Henüz çözülmemiş koşular otomatik olarak yeni profili kullanır. Daha önce `needs_review` olanları:
   `rcfd requeue --status needs_review --regime <rejim> --reason "profil değişikliği <commit>"`.
4. **Tamamlanmış (`done`) koşuları yeniden çözme** — sonuç geçerliyse dokunma. Gerekirse kullanıcıya sor.

## 4. Yapmaman gerekenler
- `config/physics.json`, `config/mesh_settings.json`, `meshes/`, `src/` değiştirmek.
- `done` sonuçları silmek veya `--force` ile toplu yeniden çözmek (tek tek, gerekçeyle olabilir).
- Orkestratörü öldürmek. Durdurmak için `rcfd stop` (mevcut koşu bitince durur) veya `rcfd pause`.
- `skip` kullanmak: yalnızca 3+ farklı denetçi denemesi başarısız olduysa ve gerekçe yazarak.

## 5. Orkestratör sağlığı
- Birden çok işçi olabilir (`main_w1`, `preopt_w1`, ...). `rcfd status` her işçinin kalp atışını ve sahiplendiği geometriyi gösterir.
- Bir işçinin kalp atışı eski + `data\orchestrator_<işçi>.lock` içindeki PID yaşamıyorsa: işçi ölmüş.
  `logs\batch_*_<işçi>.console.log` ve `logs\orchestrator.log` son satırlarını oku, sonra yeniden başlat:
  `powershell -ExecutionPolicy Bypass -File scripts\start_batch.ps1 -Campaign <kampanya> -Workers 1`
  (çalışan işçiler atlanır; ölü işçinin sahiplenmesi düşer ve yarım kalan koşusu otomatik yeniden kuyruğa alınır).
- `worker_exit` olayı: Fluent açılamadı (çoğunlukla lisans). İkinci işçi lisans yüzünden çıktıysa tek işçiyle devam edilir — kullanıcıya bildir.
- Bilinen davranış: düşük hızlarda (v2–v4) hız oranı > 1,3 olduğundan otomatik **soğuk** başlatma yapılır — bu normaldir.
- Kalp atışı eski ama PID yaşıyor: Fluent tek koşuda takılmış olabilir (`timeout_s` dolunca kendisi keser). 2 saatten uzun sürerse kullanıcıya bildir.
- Disk: `data\fields\` geometri başına ~10–30 MB, `logs\runs\` başarısız denemelerin checkpoint'lerini tutar. Boş alan < 10 GB ise kullanıcıya bildir.

## 6. Kullanıcıya bildirim gerektiren durumlar
- `mesh_error`, `geom_abandoned` olayları; lisans hataları; disk dolması.
- Bir rejimde koşuların > %20'si `needs_review`.
- Fizik/mesh/domain değişikliği gerektiğini düşündüğün her durum (öneri yaz, uygulama).

## 6b. Ön optimizasyon bitince
**Otonom dönemde (CLAUDE.md Bölüm 0b) denetçi bunu kullanıcıyı beklemeden yapar.** Diğer zamanlarda kullanıcı onayı gerekir.

Ön koşul: `rcfd --campaign preopt status` → bitmemiş koşu yok (`needs_review` kalmışsa önce Bölüm 2 ile çöz ya da
3 başarısız denetçi denemesinden sonra gerekçeyle `skip`). `preopt_w1` kuyruk boşalınca kendiliğinden çıkar.
```
New-Item -ItemType File -Force data\6b_in_progress          # resume_batch bu sürede işçi başlatmaz (ZORUNLU, ilk adım)
.venv\Scripts\python.exe src\00_preopt.py --select          # nose_params.json 'selected' + docs/preopt_report.md
                                                            # (skipped aday varsa: --select --allow-partial)
.venv\Scripts\python.exe src\01_mesh_gen.py --geom <betiğin yazdırdığı 20 geometri>
.venv\Scripts\python.exe src\tools\check_mesh_fluent.py meshes\P02_L200.msh.gz ...   # 20 mesh; min OQ ≥ 0,05
.venv\Scripts\python.exe src\03_orchestrator.py --mode batch --enqueue-only        # 20 geometri × 20 hız kuyruğa (işçiler durmaz)
Remove-Item data\6b_in_progress
powershell -ExecutionPolicy Bypass -File scripts\start_batch.ps1 -Campaign main -Workers 2   # main_w1 atlanır, main_w2 başlar
git add config\nose_params.json docs meshes; git commit -m "Ön optimizasyon seçimi + 20 mesh (Ankara denetçisi)"
```
- 6b sırasında `main_w1` çalışmaya devam eder (zaten başlamış, yeniden kuyruğa eklemez); ikinci lisans mesh kontrolüne kalır.
  6b'yi başlatmadan önce `preopt_w1`'in çıktığını doğrula (`rcfd status` kalp atışı / `Get-Process`).
- **Push yapma** (Ankara'nın GitHub yazma yetkisi yok); kullanıcı dönünce yerel commit'i alır.
- Bir mesh kalite kapısını geçemezse (üretimde hata ya da Fluent min OQ < 0,05): `meshes\<ID>.msh.gz` hâlâ **eski geçici
  parametreli** mesh'tir ve yanlış geometriyle çözülür → `--enqueue-only`'den **önce** o dosyayı sil (Git'ten geri alınabilir);
  koşuları `mesh_error` olur, diğerleri çözülür. Başka aday seçmek geometri kararıdır → yapma, `docs/ankara_notes.md`'ye yaz.
- Her mesh'in yeniden üretildiğini doğrula: 20 dosyanın değiştirilme zamanı `--select`'ten sonra olmalı.
- `rcfd stop`: tüm işçiler mevcut koşuyu bitirince çıkar (27.11 düzeltildi); bayrak `rcfd resume`'a kadar kalır ve
  `resume_batch.ps1` stop/pause açıkken işçi başlatmaz.

## 6c. GCI çalışması (27.11.2026'dan itibaren; kullanıcı onaylı)
- Kampanya `gci`: 3 geometri (P01/P16/P04 L300) × 3 ağ seviyesi (`_g1` ince, `_g2` = ana mesh, `_g3` kaba) × 4 hız = 36 koşu.
  İşçi `gci_w1` (P çekirdekleri), `main_w1` E çekirdeklerinde devam eder. `gci_w1` kuyruk boşalınca çıkar; 30 dk'lık görev
  ardından `main_w2`'yi başlatır (resume_batch dalı). `rcfd --campaign gci status` / `failures` ile izle.
- `needs_review` → Bölüm 2 ile aynı teşhis. Ağ çok ince (`_g1`, ~230 bin hücre): koşu başına süre ~2,5× — `timeout` görürsen
  `retry --init previous --set timeout_s=<×2>`. Mesh'e, seviyelere, geometri listesine **dokunma**.
- GCI bitince **kendin bir şey başlatma**: `docs/ankara_notes.md`'ye "GCI tamam" yaz. Rapor (`src\tools\gci_report.py`) ve
  ön optimizasyon 2. aşaması kullanıcı/İstanbul tarafından yapılır.
- Ana kuyrukta serbest parametreli geometriler (P08_L400/L500, P19_*) düşük öncelikli (-1): 2. aşama seçimi değiştirebilir.
- 27.11 düzeltmeleri: FMG kurtarma basamağı artık çalışıyor (settings API); `check_mesh_fluent.py` her dosyayı ayrı oturumda
  kontrol eder; `rcfd stop` tüm işçileri durdurur.

## 7. İlerleme raporu
`rcfd export` → `docs/results/` (runs ve Cd matrisi CSV). Günde bir kez commit + push:
`git add docs/results && git commit -m "sonuçlar: <tarih> ilerleme" && git push` — İstanbul tarafı buradan izler.
