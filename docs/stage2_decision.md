# GCI sonucu ve ön optimizasyon 2. aşama kararı (28.11.2026, otomatik döngü)

## GCI (docs/gci/gci_report.md)
- 3 geometri (P01, P04, P16; L300) × 3 ağ (r ≈ 1,5) × 4 hız. 12 noktanın 10'unda **salınımlı ağ yakınsaması** → Richardson
  ekstrapolasyonu yok, belirsizlik bandı (1,25 × en büyük fark) kullanıldı: %0,4–2,8.
- İnce (g1) ile ana ağ (g2) Cd farkı: P01 %0,2–1,2; P16 %0,2–1,7; **P04 (meplatlı) %1,3–1,6, ince ağ sistematik olarak yüksek**
  → P04'ün ana ağdaki Cd'si ~%1,3–1,6 düşük tahmin edilmiş olabilir (meplat köşesi çözünürlüğü). Sıralamada P04 için not düşülmeli.
- Ana ağ belirsizliği tipik **u_K ≈ %1**. Bu düzeyin altındaki K farkları ağ gürültüsü içindedir.

## 2. aşama kuralı ve kapsam
Sınırda seçilmiş (profil, L) için en iyi ile ikinci aday arasındaki K farkı > 2·u_K = %2 ise 2. aşama.
- **Girenler:** P02_L200 (fark %3,56, rn/R 0,30 üst sınır), P19_L200 (fark %6,55, a/L 1,0 üst sınır).
- Sınırda ama fark < %2 (mevcut seçim korunur): P02_L300/L400/L500, P03_L200/L300/L400/L500, P04_L400/L500, P08_L200 (%1,78),
  P08_L300/L400, P19_L300 (%1,97). P08_L200 ve P19_L300 sınıra yakın — istenirse sonradan eklenebilir.
- Adaylar: P02_L200 rn/R ∈ {0,25; 0,40} (0,50 geometrik olarak kurulamadı: L' iterasyonu yakınsamadı);
  P19_L200 a/L ∈ {0,5; 2,0; 4,0}. 5 aday × 4 hız = 20 koşu. Mesh: Python kalite + ayrı Fluent kontrolü OK (min OQ 0,20–0,32).

## Sonra
2. aşama bitince `--select`; seçimi değişen geometri en fazla 2 (P02_L200, P19_L200). P02_L200 ana analizde çözülmüş →
arşivle + mesh yenile + yeniden kuyruğa al (kullanıcı onaylı; kullanıcıyla birlikte yapılacak). P19_L200 henüz çözülmedi (öncelik -1).

## 2. aşama sonucu (28.11 10:59, 20/20 koşu)
| (profil, L) | mevcut seçim (K) | 2. aşamanın en iyisi (K) | kazanç | not |
|---|---|---|---|---|
| P02_L200 | rn/R 0,30 (1,57310) | rn/R 0,40 (1,56238) | %0,68 | 0,50 geometrik olarak yok → 0,40 yeni sınır; monoton |
| P19_L200 | a/L 1,0 (1,53047) | a/L 4,0 (1,51357) | %1,10 | **monoton değil**: a/L 2,0 (1,54722) ikisinden de kötü → ağ gürültüsü |

Her iki kazanç da 2·u_K = %2'nin altında → istatistiksel olarak ayırt edilemez. Öneri: mevcut seçimleri koru (yeniden koşu yok).
Tam tablo (yerel): data/preopt_report_with_stage2.md. nose_params.json DEĞİŞTİRİLMEDİ (karar kullanıcıda).
