# İstanbul gece döngüsü talimatı (28.11.2026; kullanıcı uyuyor, terminal açık)

Her turda SIRAYLA. Kısa ol: kullanıcıya tek satır durum yaz; uzun analiz yalnızca iş yapılan turda.

## 0. Kota (ZORUNLU, ilk adım)
`cat ~/.claude/usage_latest.json` → `five_hour.used_percentage` (5s), `seven_day.used_percentage` (7g), `resets_at` (unix).
- 7g ≥ 97 → döngüyü DURDUR (ScheduleWakeup stop). Ankara kendi başına devam eder. Son satırda nedenini yaz.
- 7g ≥ 93 → yalnızca sağlık kontrolü (1. adım); yeni iş (GCI raporu / 2. aşama) BAŞLATMA; sonraki tur 3600 s.
- 5s ≥ 85 → yalnızca sağlık kontrolü; sonraki uyanma 5s sıfırlanmasından sonra (en fazla 3600 s).
- Aksi hâlde normal.

## 1. Sağlık kontrolü (tek SSH çağrısı, EncodedCommand)
`rcfd status`, `rcfd --campaign gci status` (ilk 4 satır), `rcfd --campaign preopt status` (ilk 4), Fluent süreç sayısı.
Müdahale YALNIZCA şu durumlarda (needs_review'u Ankara denetçisi çözer — sen dokunma):
- Hiç canlı işçi yok ve kuyrukta iş var → `scripts\resume_batch.ps1` çalıştır.
- 2'den fazla Fluent oturumu → `docs/ankara_notes.md`'ye yaz, en son başlayan işçiyi `rcfd stop --worker` ile durdur
  (NOT: Ankara'da 5b9f611 çekilmeden `stop --worker` yok; o durumda yalnızca not yaz).
- SSH erişilemiyor → bir sonraki turda tekrar dene; 3 tur üst üste erişilemiyorsa kullanıcıya not bırak, döngü devam.

## 2. GCI bittiğinde (gci 36/36 done|done_flagged, needs_review 0) — BİR KEZ
a) Ankara'da DB tutarlı kopya (sqlite backup) → İstanbul `data/ankara_gci_<tarih>.db`; `src\tools\gci_report.py --db <o dosya>`.
b) Karar kuralı (2. aşama kapsamı): ses altı/transonik/süpersonik GCI_medium (ana ağ belirsizliği) tablosundan K belirsizliği ≈
   hızların GCI_medium ortalaması (u_K). Sınırda seçilmiş (profil, L) için en iyi ile ikinci aday arasındaki K farkı > 2·u_K ise
   2. aşamaya al; değilse "ağ gürültüsü içinde" diye rapora yaz ve mevcut seçimi koru.
c) Aday üretimi (sınırın ötesine 2 adım + en iyi ile komşu arasına 1 ara nokta):
   rn/R (02, 08): üst sınırda 0,40 / 0,50 (+0,25); alt sınırda 0,025 (+0,075). Rt/R (04) alt sınırda 0,025 (+0,075).
   a/L (19) üst sınırda 2,0 / 4,0 (+0,5). 03: köşe/kenarda L1/L ∈ {0,8} ve R1/R ∈ {0,9; 0,95} kombinasyonları (dışbükeylik kodda).
   `docs/preopt/stage2_spec.json` yaz → `src\00_preopt.py --stage2 docs\preopt\stage2_spec.json` → her yeni aday için AYRI
   `src\tools\check_mesh_fluent.py meshes\preopt\<id>.msh.gz --report fluent_mesh_check_preopt.csv` (min OQ ≥ 0,05; geçmeyeni sil) →
   commit + push.
d) Ankara: `git pull` (işçiler çalışırken güvenli) → `.venv\Scripts\python.exe src\00_preopt.py --register-stage2` →
   main_w2 çalışıyorsa `rcfd stop --worker main_w2`; main_w2 çıkınca `scripts\start_batch.ps1 -Campaign preopt -Workers 1`
   (start_batch işçi sınırını uygular). `docs/ankara_notes.md`'ye satır. preopt_w1'in Fluent açtığını doğrula.
e) docs/gci_report ve karar özetini kullanıcı için `docs/stage2_decision.md`'ye yaz (commit + push).

## 3. 2. aşama bittiğinde (preopt bitmemiş = 0, stage2 adayları done) — BİR KEZ
`--select` Ankara'da çalıştırma; İstanbul'da DB kopyasıyla seçim raporu üret, değişen seçimleri `docs/stage2_decision.md`'ye yaz.
Seçim değişen geometrilerin yeniden çözümü (arşiv + mesh yenileme + requeue) kullanıcı onaylı AMA çok adımlı ve riskli →
kullanıcı uyanınca birlikte yapılacak; yalnızca hazırlık raporu yaz. preopt_w1 kendiliğinden çıkar; resume_batch main_w2'yi açar.

## Sonraki uyanma
GCI sürüyorsa 3600 s. İş yapılan turdan sonra 1800 s (Fluent başladı mı kontrolü). Her şey yolundaysa ve beklenecek bir şey yoksa 3600 s.
