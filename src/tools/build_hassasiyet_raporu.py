"""Sonuç hassasiyet raporu PDF'i -> docs/pdf/Sonuc_Hassasiyet_Raporu.pdf"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pdf_style import H1, H2, P, PageBreak, box, build, bullets, image, table  # noqa: E402

from common.config import DOCS_DIR  # noqa: E402

A = DOCS_DIR / "report_assets"
MEAS = "<font color='#3E9B4F'><b>Ölçüldü</b></font>"
EST = "<font color='#E8A33D'><b>Tahmin</b></font>"
NOTM = "<font color='#C0392B'><b>Modellenmedi</b></font>"


def f(x, n=1):
    return f"{x:.{n}f}".replace(".", ",")


def story() -> list:
    facts = json.loads((A / "facts.json").read_text(encoding="utf-8"))
    s = []
    s += [P("Sonuç Hassasiyet Raporu", "title"),
          P("Model Roket Burun Konisi CFD — elde edilen Cd ve K<sub>kayıp</sub> değerlerinin gerçeğe yakınlığı<br/>"
            "Durum tarihi: 24.11.2026 &nbsp;•&nbsp; Kapsam: tamamlanan doğrulama koşuları ve yöntemin tamamı", "subtitle")]
    s += [box("Bu raporun her yüzdelik bandı üç türden birine aittir: "
              f"{MEAS} (bu projede deneyle ölçüldü), {EST} (literatür ve mühendislik yargısına dayalı, bu projede ölçülmedi), "
              f"{NOTM} (modelde hiç yer almayan fiziksel etki). Bantlar ±1σ değil, <b>makul üst sınır</b> olarak verilmiştir. "
              "Mesh bağımsızlığı (GCI) çalışması henüz yapılmamıştır; bu yüzden ağ hatası bir tahmindir.", "warn",
              "Okuma kılavuzu — dürüstlük notu")]

    s += [H1("Özet: yüzdelik bantlar")]
    s += [table([
        ["Büyüklük", "Ses altı (M < 0,7)", "Transonik (0,7–1,15)", "Süpersonik (≥ 1,15)", "Tür"],
        ["Aynı modelin tekrarlanabilirliği (iteratif + ayar)", "±0,1 %", "±0,5 %", "±0,5 %", MEAS],
        ["Model içi toplam sayısal hata (iteratif + ayar + ağ + domain)", "±2–4 %", "±4–8 %", "±3–6 %", f"{MEAS} + {EST}"],
        ["Modellenen gövde+burun için fiziksel gerçeğe göre Cd (finsiz, egzozsuz, pürüzsüz, α = 0)", "±8–15 %", "±15–25 %", "±10–20 %", EST],
        ["Gerçek uçuştaki roketin Cd'si (kanatçık, egzoz, pürüzlülük dâhil)", "doğrudan karşılaştırılamaz", "doğrudan karşılaştırılamaz", "doğrudan karşılaştırılamaz", NOTM],
    ], widths=[2.4, 0.9, 0.95, 0.95, 0.9])]
    s += [table([
        ["K<sub>kayıp</sub> ile ilgili büyüklük", "Bant", "Açıklama"],
        ["K<sub>kayıp</sub> mutlak değeri (model içi sayısal)", "±3–6 %", "Rejim ağırlıkları: ses altı %40, transonik %38, süpersonik %23 (zaman ağırlıklı)"],
        ["K<sub>kayıp</sub> mutlak değeri (modellenen konfigürasyon için fiziksel)", "±10–20 %", "Taban sürüklemesi, türbülans modeli ve tam türbülanslı varsayım baskın"],
        ["İki burun arasındaki K<sub>kayıp</sub> <b>farkı</b>", "±0,5–1,5 %", "Ortak (korelasyonlu) hatalar birbirini götürür; kalan: burun bölgesi ağ hatası + iteratif gürültü"],
        ["<b>Sıralama güveni</b>", "fark > %3: güvenilir<br/>%1–3: işaret eder<br/>< %1: eşdeğer", "Projenin asıl çıktısı olan burun seçimi için geçerli karar ölçütü"],
    ], widths=[2.2, 1.1, 2.8])]
    s += [box("Bu çalışma <b>burun konilerini birbirine göre sıralamak</b> için güvenilirdir: tüm geometriler aynı mesh "
              "topolojisi, aynı fizik ve aynı çözücüyle çözüldüğü için hataların büyük kısmı ortaktır ve karşılaştırmada birbirini "
              "götürür. <b>Mutlak Cd</b> ise gerçek roketin uçuş Cd'si değildir: kanatçık ve motor egzozu modelde yoktur, "
              "bu iki etki mutlak değeri %30–100 değiştirebilir.", "info", "Tek cümlelik sonuç")]
    s.append(PageBreak())

    # 1
    s += [H1("1. Tanımlar ve hata kaynaklarının sınıflandırılması")]
    s += [table([
        ["Seviye", "Soru", "Bu projedeki karşılığı"],
        ["Sayısal doğruluk", "Seçilen denklemler ne kadar doğru çözüldü?", "İteratif yakınsama, sayısal ayar, ağ, domain"],
        ["Model doğruluğu", "Denklemler gerçek fiziği ne kadar temsil ediyor?", "RANS k-ω SST, tam türbülanslı akış, sürekli (steady) çözüm, ISA"],
        ["Temsil doğruluğu", "Modellenen nesne gerçek roket mi?", "Eksenel simetrik burun + 2 m gövde; kanatçık, egzoz, pürüzlülük yok"],
    ], widths=[1.1, 2, 2.4])]
    s += [P("Mutlak hata (Cd'nin kendisi) ile göreli hata (iki burun arasındaki fark) ayrı değerlendirilir. Proje kararı "
            "(en iyi burun) göreli hataya bağlıdır.")]

    # 2
    s += [H1("2. Ölçülen sayısal hata bileşenleri")]
    s += [table([
        ["Bileşen", "Nasıl ölçüldü", "Sonuç", "Tür"],
        ["İteratif yakınsama (done)", "Son 300 iterasyonda Cd bağıl std ve kayma (kabul ölçütü)", "std < 0,02 %, kayma < 0,05 % → ±0,05 %", MEAS],
        ["Kalıcı salınım (done_flagged)", "v2, v15, v17, v19, v20 salınım genliği; 1000 iterasyon ortalaması", "±0,14–0,55 % salınım; ortalama ±0,1–0,3 %", MEAS],
        ["Sayısal ayar bağımlılığı", "Aynı koşu CFL 5 ile enhanced-CASM + CFL 50", "v05: 0,3638 → 0,3633 (0,14 %); v17: 0,4913 → 0,4912–0,4919 (≤ 0,12 %)", MEAS],
        ["Erken durma riski (ortalama ölçütü)", "Soğuk M = 1 geçmişinde ölçüt canlandırması", "eski eşiklerle 2,6 %; seçilen eşiklerle ≤ 0,5–0,7 %", MEAS],
        ["Çekirdek sayısı", "Aynı koşu 5 ve 10 çekirdek", "Cd birebir aynı (0,43226)", MEAS],
        ["Başlatma yolu", "v1 soğuk, v2 kurtarma zinciri, v3/v5 soğuk, v6 warm", "Cd(M) düzgün ve monoton (Şekil 1)", MEAS],
    ], widths=[1.3, 1.9, 2, 0.6])]
    s += image(A / "cd_mach_P16_L300.png", 0.85, "Şekil 1 — P16_L300 doğrulama noktaları: farklı başlatma yollarından gelen değerler düzgün bir Cd(M) eğrisi oluşturur")
    s += image(A / "accel_convergence.png", 0.85, "Şekil 2 — Beş farklı sayısal ayar aynı nihai Cd'ye (0,4913) yakınsar: sonuç ayardan bağımsızdır")

    # 3
    s += [H1("3. Tahmin edilen sayısal hata bileşenleri (ölçülmedi)")]
    s += [table([
        ["Bileşen", "Gerekçe", "Ses altı", "Transonik", "Süpersonik"],
        ["Ağ (ayrıklaştırma) hatası", "37 katmanlı yapısal BL, h1 = 1 µm (hedef y⁺ ≈ 1), burunda 1 mm teğetsel hücre; şok bölgesinde 4 mm üçgen. GCI yapılmadı.", "±1–3 %", "±3–6 %", "±2–4 %"],
        ["Domain boyutu", "Far-field: önde ve radyalde 2·L<sub>b</sub> ≈ 4,4–5 m (~45–50 çap), arkada 5·L<sub>b</sub>", "< ±0,5 %", "±0,5–1,5 %", "< ±0,5 %"],
        ["1 mm uç yuvarlatması", "Uç alanı A<sub>ref</sub>'in %0,04'ü; ses altında basınç sürüklemesi küçük", "< ±0,1 %", "< ±0,3 %", "< ±0,3 %"],
        ["y⁺ hedefinden sapma", "y⁺ ≈ 1 en yüksek hız için tasarlandı; düşük hızlarda y⁺ < 1 (daha iyi). Gerçek y⁺ henüz çıkarılmadı.", "±0,5 %", "±1 %", "±1 %"],
    ], widths=[1.1, 2.6, 0.6, 0.65, 0.65])]
    s += [P(f"Tür: {EST}. Ağ hatası bu projedeki en büyük sayısal belirsizlik kaynağıdır ve ölçülmemiştir. Bölüm 8'deki GCI "
            "çalışması bu bandı ölçülmüş bir değere çevirir.", "small")]

    # 4
    s += [H1("4. Fiziksel model belirsizliği")]
    s += [table([
        ["Etki", "Açıklama", "Toplam Cd'ye etkisi", "Tür"],
        ["Tam türbülanslı akış varsayımı", "Gerçekte burun üzerinde laminer bölge var (geçiş Re<sub>x</sub> ≈ 5·10⁵–10⁶). En düşük hızda (Re/m = 1,3·10⁶) laminer bölge 0,4–0,8 m olabilir → sürtünme fazla tahmin edilir. Yüksek hızlarda etki birkaç %.", "v1–v4: +5–15 % (fazla)<br/>v10+: +1–4 %", EST],
        ["Sürtünme modeli (k-ω SST)", "Düz levha korelasyonlarına göre tipik sapma", "±3–5 %", EST],
        ["Taban sürüklemesi (sürekli RANS)", "Küt taban arkasındaki ayrılmış akış RANS'ta zayıf tahmin edilir; taban basıncı hatası %10–30, taban payı toplamın ~1/3'ü", "±3–10 %", EST],
        ["Transonik şok / ayrılma", "Sürekli RANS'ta şok konumu ve şok-sınır tabaka etkileşimi", "±5–15 % (transonik)", EST],
        ["Atmosfer (ISA ↔ gerçek gün)", "±10 K sıcaklık farkı → Mach ±%2, Re ±%3. Transonikte dCd/dM büyük olduğundan daha hassas.", "ses altı ±0,5–1 %, transonik ±2–5 %", EST],
        ["Serbest akış türbülansı", "TI = %0,1, μ<sub>t</sub>/μ = 10 (sabit, tüm geometrilerde aynı)", "< ±1 %", EST],
    ], widths=[1.2, 2.6, 1.2, 0.6])]

    # 5
    s += [H1("5. Temsil farkları: modelde olmayan etkiler")]
    s += [table([
        ["Etki", "Gerçekte", "Mutlak Cd'ye etkisi", "Sıralamaya etkisi"],
        ["Kanatçıklar (fins)", "Model roketlerde toplam sürüklemenin tipik olarak %20–40'ı", "Gerçek Cd daha yüksek: +25–65 %", "Yok (tüm burunlarda aynı)"],
        ["Motor egzozu (plume)", "Uçuş profilinde (t = 0,12–3,80 s) hız sürekli arttığından bu evre <b>büyük olasılıkla motorun yanma evresidir</b> (doğrulanması gerekir). Yanma sırasında egzoz taban bölgesini doldurur ve taban sürüklemesini büyük ölçüde azaltır. Model egzozsuz (motor kapalı) taban sürüklemesi hesaplar.", "Yanma evresiyse modelin Cd'si ~%25–35 fazla", "Küçük (taban geometrisi aynı; burunun sınır tabaka kalınlığı üzerinden zayıf etkileşim)"],
        ["Yüzey pürüzlülüğü", "Boyalı/zımparalı yüzeyler sürtünmeyi artırır", "+5–20 % sürtünme", "Küçük"],
        ["Fırlatma pabucu, eklem yerleri", "Ek çıkıntı sürüklemesi", "+2–10 %", "Yok"],
        ["Hücum açısı, dönme", "Model α = 0, dönmesiz", "Rüzgârlı uçuşta artış", "Küçük"],
    ], widths=[1.1, 2.3, 1.3, 1.3])]
    s += [box("Projenin amacı ‘hangi burun daha az kayıp üretir’ sorusunu yanıtlamaktır. Yukarıdaki etkilerin hepsi tüm burunlar "
              "için aynı ya da çok benzerdir; bu yüzden <b>seçim kararını değiştirmez</b>. Ancak buradan çıkan Cd değerleri "
              "OpenRocket gibi uçuş simülasyonlarına doğrudan girilmemelidir; bunun için kanatçık ve egzoz katkısı eklenmelidir.",
              "info", "Bu ne anlama geliyor?")]

    # 6
    s += [H1("6. Bağımsız kontrol: yarı-ampirik yöntemle karşılaştırma")]
    s += [P("Deneysel veri olmadığından, ses altı noktalar OpenRocket'in de kullandığı Barrowman yöntemiyle karşılaştırıldı: "
            "türbülanslı düz levha sürtünmesi c<sub>f</sub> = 0,455 / (log<sub>10</sub>Re<sub>L</sub>)<super>2,58</super> "
            "(ıslak alan geometriden hesaplandı) + taban sürüklemesi C<sub>Db</sub> = 0,12 + 0,13·M².")]
    rows = [["Hız", "Mach", "Re<sub>L</sub>", "CFD Cd", "Sürtünme (BE)", "Taban (BE)", "Yarı-ampirik", "Fark"]]
    for r in facts["semiempirical"]:
        rows.append([f"v{int(r['vel_idx']):02d}", f(r["mach"], 3), f"{r['Re_L']:.2e}", f(r["cd_cfd"], 4), f(r["cd_friction_be"], 4),
                     f(r["cd_base_be"], 4), f(r["cd_semi"], 4), f"{f(r['diff_pct'], 1)} %"])
    s += [table(rows, widths=[0.5, 0.6, 0.85, 0.7, 0.85, 0.75, 0.85, 0.6])]
    s += image(A / "cfd_vs_semiempirical.png", 0.85, "Şekil 3 — CFD ile yarı-ampirik tahmin (ses altı)")
    s += bullets([
        "CFD, yarı-ampirik tahminin <b>%3,6–6,8 altında</b> ve Reynolds sayısıyla aynı eğilimi izliyor. Yarı-ampirik yöntemin "
        "kendi belirsizliği ±%10–15 olduğundan iki sonuç birbiriyle <b>uyumludur</b>.",
        "Farkın Mach ile artması beklenir: Barrowman taban formülü genel bir korelasyondur; CFD bu gövdeye özgü taban basıncını çözer.",
        "Bu bir <b>doğrulama değil, tutarlılık kontrolüdür</b>: her iki taraf da modeldir. Gerçek doğrulama için rüzgâr tüneli "
        "veya uçuş verisi gerekir (Bölüm 8).",
    ])

    # 7
    s += [H1("7. Bileşik bantların hesabı")]
    s += [P("Bağımsız kabul edilen bileşenler kareler toplamının karekökü (RSS) ile birleştirilir; üst sınır için doğrusal "
            "toplam da verilir. Örnek, ses altı model içi sayısal hata:")]
    s += [table([
        ["Bileşen (ses altı)", "Bant"],
        ["İteratif + ayar (ölçüldü)", "±0,15 %"],
        ["Ağ (tahmin)", "±1–3 %"],
        ["Domain + uç + y⁺ (tahmin)", "±0,6–1 %"],
        ["RSS / doğrusal toplam", "≈ ±1,2–3,2 % / ±1,8–4,2 % → <b>±2–4 %</b>"],
    ], widths=[3, 2])]
    s += [P("K<sub>kayıp</sub> zaman integrali olduğundan rejim bantları zaman ağırlıklarıyla (ses altı %39,8; transonik %37,6; "
            "süpersonik %22,6) birleştirilir: model içi sayısal ±3–6 %. Dinamik basınç ağırlıklı yardımcı gösterge (∫v²·Cd dt) "
            "transonik ve süpersonik rejime daha duyarlıdır (ağırlıklar %10,6 / %45,7 / %43,8) ve bu yüzden bandı daha geniştir (±4–7 %).")]
    s += [P("<b>Göreli fark</b> için ortak hatalar (taban, gövde sürtünmesi, türbülans modeli, domain, atmosfer) birbirini götürür; "
            "geriye burun bölgesinin ağ hatasının geometriye bağlı kısmı (±0,5–1 %) ve iteratif/salınım gürültüsü (±0,1–0,5 %) "
            "kalır → <b>±0,5–1,5 %</b>. İki burun arasındaki fark bu bandın yaklaşık iki katını (%3) aştığında sıralama güvenilirdir.")]

    # 8
    s += [H1("8. Hassasiyeti artırmak için öneriler")]
    s += [table([
        ["Öneri", "Neyi ölçer / daraltır", "Maliyet"],
        ["GCI mesh çalışması: 3 geometri (ör. en iyi 2 + bir küt profil) × 3 ağ düzeyi × 4 temsili hız", "Ağ hatasını ölçülmüş değere çevirir (en büyük tahmin)", "~10 saat (2 işçi)"],
        ["Duvar y⁺ dağılımının her koşuda raporlanması", "y⁺ varsayımını doğrular", "Kod değişikliği, ek süre yok"],
        ["Geçiş modeli (γ-Re<sub>θ</sub> / transition SST) ile 2–3 düşük hız koşusu", "Tam türbülanslı varsayımın etkisini ölçer", "~2 saat"],
        ["done_flagged koşuların 2× uzun ortalamayla tekrarı", "Salınım belirsizliğini daraltır", "Koşu başına +5 dk"],
        ["Literatürdeki bir dönel gövde rüzgâr tüneli verisiyle (ör. NACA/AGARD eksenel simetrik gövde) aynı kurulumla doğrulama", "Mutlak model doğruluğunu ölçer", "1 geometri, ~2 saat"],
        ["Kazanan burun için kanatçık + egzoz etkisinin OpenRocket'te eklenmesi", "Gerçek uçuş Cd'sine köprü", "Düşük"],
    ], widths=[2.6, 1.9, 1.1])]

    # 9
    s += [H1("9. Sonuç")]
    s += bullets([
        "<b>Sayısal olarak</b> sonuçlar tekrarlanabilir ve ayardan bağımsızdır (ölçülen fark ≤ %0,15). Kabul edilen her Cd ikinci "
        "derece ayrıklaştırmayla ve tanımlı bir yakınsama ölçütüyle elde edilir.",
        "<b>Modellenen konfigürasyon için</b> mutlak Cd'nin gerçeğe yakınlığı ses altında ±%8–15, transonikte ±%15–25, "
        "süpersonikte ±%10–20 mertebesindedir (tahmin; baskın kaynak taban akışı ve türbülans modeli).",
        "<b>Proje kararı için</b> (burunların sıralaması) göreli belirsizlik ±%0,5–1,5'tir: K<sub>kayıp</sub> farkı %3'ü aşan "
        "burunlar güvenle ayırt edilir, %1'in altındaki farklar eşdeğer kabul edilmelidir.",
        "Nihai raporda her geometri için tamamlanmış nokta sayısı ve done_flagged sayısı sıralama tablosunda verilecektir "
        "(<i>04_postprocess.py</i>); bu bayraklar ilgili geometrinin bandını genişletir.",
    ])
    return s


def main() -> int:
    out = DOCS_DIR / "pdf" / "Sonuc_Hassasiyet_Raporu.pdf"
    build(out, story(), "Sonuç Hassasiyet Raporu", "Cd ve K_kayıp sonuçlarının belirsizlik bantları")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
