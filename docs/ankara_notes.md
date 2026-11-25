# Ankara Denetçi Notları (otonom dönem, CLAUDE.md Bölüm 0b)

Her satır: zaman damgası — gözlem/karar/müdahale.

- 2026-11-25 00:38 — Denetçi döngüsü başladı (`/loop 1h`, her saatin :07'sinde). İlk tur: main 3/1200 done, preopt 2/368 done, needs_review yok, WARNING olayı yok, disk 87 GB boş. İşçiler main_w1 (PID 19848) ve preopt_w1 (PID 19292) canlı.
- 2026-11-25 00:38 — `rcfd status`'taki "single" işçi uyarısı (kalp atışı 23:40, PID 1180 yok) duman testinden kalan eski kalp atışı; gerçek işçi değil → müdahale yok.
- 2026-11-25 01:19 — main 9/1200, preopt 10/368 (2 done_flagged, normal). needs_review/uyarı yok. Not: main sıralı ETA 63 → 141 saat (main_w1 E çekirdeklerinde, subsonic ort. 6,8 dk/koşu); preopt bitip main_w2 eklenince yeniden değerlendirilecek. Müdahale yok.
- 2026-11-25 02:19 — main 16/1200, preopt 19/368; needs_review/uyarı yok. İlk geometri doğrulaması (CLAUDE.md 0): transonik warm-start koşusu ort. ~9,7 dk (main, E çekirdekleri) / ~9,2 dk (preopt, P çekirdekleri) — varsayılan ~4,5 dk'nın ~2 katı; transoniklerin çoğu done_flagged (ortalama yakınsaması). ETA ~3 gün hedefinin üzerinde kalabilir. Fizik/ayar değişikliği yok; yalnızca gözlem.
- 2026-11-25 03:19 — main 22/1200, preopt 27/368; needs_review yok. P02_L300_c02 (run 101) 02:50'de diverged → otomatik kurtarma basamak 1/4 devrede (müdahale yok). Ölçüm: P01_L200 tam geometri (20 hız) 00:22→03:09 ≈ 167 dk (E çekirdekleri; varsayım 86 dk).
- 2026-11-25 04:19 — main 26/1200, preopt 35/368; needs_review yok. P01_L300 v05 (run 674) ve v06 (run 675) warm-start'ta diverged → otomatik kurtarma (v06 basamak 2/4, neighbor). Sübsonik warm ıraksaması şimdilik 1 geometride; ≥3 geometride tekrarlarsa Bölüm 3 değerlendirilecek. Müdahale yok.
- 2026-11-25 08:19 — main 48/1200, preopt 67/368; needs_review yok. P01_L400 run 973 diverged → otomatik basamak 2/4 ile çözüldü. Sübsonik warm ıraksaması artık 2 geometride (P01_L300, P01_L400), ikisi de otomatik kurtarıldı; 3. geometride tekrarlarsa Bölüm 3 (sübsonik warm CFL) değerlendirilecek.
- 2026-11-25 13:19 — main 76/1200, preopt 113/368; needs_review yok. P03_L300_c03 (run 137) 12:35'te Fluent Scheme hatasıyla crash ('wta(1st) to string->symbol') → oturum otomatik yeniden açıldı (1/3), 2. deneme done (Cd 0,752). Tekil/geçici; müdahale yok. P01_L500 v05/v06 ıraksamadı (sübsonik warm deseni 2 geometride kaldı).
- 2026-11-25 23:19 — Gün sonu: main 138/1200 (%11,5), preopt 191/368 (%52); gün boyunca needs_review 0, müdahale 0. Günlük rcfd export → docs/results, yerel commit (push yok).
- 2026-11-25 23:20 — Git kimliği tanımsızdı; yalnızca bu depoya yerel kimlik tanımlandı (user.name 'Ankara Denetci (Claude Code)', user.email ankara-supervisor@localhost). Global ayar değişmedi.
