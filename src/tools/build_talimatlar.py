"""Ankara kurulum talimatları PDF'i -> docs/pdf/Talimatlar.pdf"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pdf_style import H1, H2, P, PageBreak, Spacer, box, build, bullets, code, mm, numbered, table  # noqa: E402

from common.config import DOCS_DIR  # noqa: E402

REPO = "https://github.com/eraydagsuyu/AutoCFD---Nose-Cone-Performance-.git"


def step_header(n: str, title: str, minutes: str, who: str = "Siz") -> list:
    return [H1(f"Adım {n} — {title}"),
            P(f"<font color='#5A6470'>Tahmini süre: {minutes} &nbsp;•&nbsp; Yapan: {who}</font>", "small"), Spacer(1, 4)]


def story() -> list:
    s = []
    s += [P("Ankara Bilgisayarı Kurulum Talimatları", "title"),
          P("Model Roket Burun Konisi CFD Otomasyonu — üretim makinesinin sıfırdan hazırlanması<br/>"
            "Hazırlanma: 24.11.2026 &nbsp;•&nbsp; Hedef: kurulum <b>24.11.2026 saat 22:45</b>'ten önce tamamlanmış olmalı", "subtitle")]
    s += [box("Bu belge, Ankara'daki bilgisayarı Eray'ın uzaktan (İstanbul'dan) bağlanıp aerodinamik analizleri günlerce "
              "kesintisiz çalıştırabileceği hâle getirir. Adımları <b>yazıldığı sırayla ve harfiyen</b> uygulayın. Her adımın "
              "sonunda bir <b>Kontrol</b> kutusu vardır; kontrol başarılı olmadan bir sonraki adıma geçmeyin. Takıldığınız yerde "
              "ekran görüntüsünü Eray'a gönderin.", "info", "Bu belge ne işe yarar?"), Spacer(1, 6)]

    s += [H2("Başlamadan önce gerekenler")]
    s += [table([
        ["Gereksinim", "Açıklama"],
        ["Windows 10 veya 11 (64-bit)", "Bilgisayarın yönetici (Administrator) yetkili bir kullanıcı hesabı olmalı."],
        ["Ansys 2024 R1 kurulu ve lisanslı", "Varsayılan yol: C:\\Program Files\\ANSYS Inc\\v241. Farklıysa Adım 1'de not edin."],
        ["Kesintisiz internet", "Mümkünse kablolu (Ethernet). Analiz 3 gün kadar sürecek; bilgisayar sürekli açık kalacak."],
        ["Boş disk alanı", "C: sürücüsünde en az 30 GB."],
        ["Eray'dan gelecek 2 bilgi", "(1) Tailscale davet bağlantısı, (2) ssh-ed25519 ile başlayan tek satırlık SSH anahtarı."],
    ], widths=[1.1, 2.6])]
    s += [Spacer(1, 6), box("Tüm komutlar <b>PowerShell</b> içinde çalıştırılır. Başlat menüsüne <b>PowerShell</b> yazın. "
                            "Bir adımda <b>(Yönetici)</b> yazıyorsa: <i>Windows PowerShell</i> üzerine sağ tıklayın → "
                            "<b>Yönetici olarak çalıştır</b>. Komut kutusundaki metni olduğu gibi kopyalayıp yapıştırın ve Enter'a basın. "
                            "Birden fazla satır varsa hepsini birlikte yapıştırabilirsiniz.", "warn", "PowerShell nasıl açılır?")]
    s += [Spacer(1, 4), H2("Genel akış"), table([
        ["Adım", "İş", "Süre"],
        ["1", "Bilgisayar bilgilerini topla", "3 dk"],
        ["2", "Uyku, güç ve güncelleme ayarları", "5 dk"],
        ["3", "Tailscale (güvenli uzak bağlantı ağı)", "5 dk"],
        ["4", "OpenSSH Sunucusu (uzaktan komut satırı)", "5 dk"],
        ["5", "Eray'ın SSH anahtarını tanımla", "3 dk"],
        ["6", "Git, Python 3.11 ve Node.js kurulumu", "15 dk"],
        ["7", "Proje dosyalarını indir ve Python ortamını kur", "10–15 dk"],
        ["8", "Claude Code kurulumu", "3 dk"],
        ["9", "Eray'a bilgileri gönder", "2 dk"],
    ], widths=[0.5, 3.2, 0.8])]
    s.append(PageBreak())

    # ---- 1
    s += step_header("1", "Bilgisayar bilgilerini toplayın", "3 dk")
    s += [P("Normal PowerShell açın ve aşağıdaki komutları yapıştırın:")]
    s += [code(r'''
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors
"RAM (GB): " + [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1)
"C: boş alan (GB): " + [math]::Round((Get-PSDrive C).Free/1GB,1)
$fl = "C:\Program Files\ANSYS Inc\v241\fluent\ntbin\win64\fluent.exe"
"Ansys 2024 R1 Fluent: " + (Test-Path $fl)
whoami
''')]
    s += [box("Ekranın fotoğrafını veya ekran görüntüsünü alın (Adım 9'da Eray'a gönderilecek). Şunlara dikkat edin:<br/>"
              "• <b>NumberOfCores</b>: fiziksel çekirdek sayısı (Eray'a göre 8 olması bekleniyor).<br/>"
              "• <b>Ansys 2024 R1 Fluent: True</b> olmalı. <b>False</b> ise Ansys farklı bir klasördedir; "
              "Ansys'in kurulu olduğu klasörü Eray'a bildirin.<br/>"
              "• Boş alan 30 GB'tan az ise yer açın.<br/>"
              "• <b>whoami</b> çıktısı (ör. <i>masaustu-abc\\ali</i>): ters bölüden sonraki kısım Windows kullanıcı adınızdır.",
              "ok", "Kontrol")]

    # ---- 2
    s += step_header("2", "Uyku, güç ve güncelleme ayarları", "5 dk")
    s += [P("Analizler günlerce sürecek. Bilgisayar uykuya geçer, ağ kartı kapanır veya Windows güncelleme için yeniden "
            "başlarsa çalışma yarıda kalır. <b>PowerShell (Yönetici)</b> açın ve yapıştırın:")]
    s += [code(r'''
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change disk-timeout-ac 0
powercfg /change monitor-timeout-ac 30
powercfg /hibernate off
$u = "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings"
reg add $u /v ActiveHoursStart /t REG_DWORD /d 0 /f
reg add $u /v ActiveHoursEnd /t REG_DWORD /d 23 /f
$p = "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU"
reg add $p /v NoAutoRebootWithLoggedOnUsers /t REG_DWORD /d 1 /f
''')]
    s += [P("Sonra fare ile şu iki ayarı yapın:")]
    s += numbered([
        "<b>Windows Update'i duraklatın:</b> Ayarlar → Windows Update → <i>Güncellemeleri duraklat</i> → mümkün olan en uzun süre (ör. 5 hafta).",
        "<b>Ağ kartının uyumasını engelleyin:</b> Başlat'a sağ tık → <i>Aygıt Yöneticisi</i> → <i>Ağ bağdaştırıcıları</i> → "
        "kullandığınız kart (Ethernet veya Wi-Fi) üzerine çift tık → <i>Güç Yönetimi</i> sekmesi → "
        "<i>Güç tasarrufu için bilgisayarın bu aygıtı kapatmasına izin ver</i> işaretini <b>kaldırın</b> → Tamam.",
        "Dizüstü bilgisayarsa: şarj kablosu sürekli takılı kalsın; Denetim Masası → Güç Seçenekleri → "
        "<i>Kapağı kapatınca</i> → prize takılıyken <b>Hiçbir şey yapma</b>.",
    ])
    s += [box("Yönetici PowerShell'de çalıştırın: <font name='Consolas'>powercfg /query SCHEME_CURRENT SUB_SLEEP</font> — "
              "çıktıda <i>Current AC Power Setting Index: 0x00000000</i> satırları görünmeli (uyku kapalı).", "ok", "Kontrol")]

    # ---- 3
    s += step_header("3", "Tailscale (güvenli uzak bağlantı ağı)", "5 dk")
    s += [P("Tailscale, İstanbul ve Ankara bilgisayarlarını modem ayarı yapmadan, şifreli bir özel ağda buluşturur.")]
    s += numbered([
        "Tarayıcıda <b>https://tailscale.com/download/windows</b> adresine gidin, indirip kurun (varsayılan seçenekler).",
        "Eray'ın size gönderdiği <b>Tailscale davet bağlantısını</b> açın ve daveti kabul edin "
        "(Google/Microsoft hesabınızla giriş yapabilirsiniz).",
        "Kurulum sonunda Tailscale giriş isterse, davet edildiğiniz ağa (tailnet) giriş yapın.",
        "Saatin yanındaki Tailscale simgesinin üzerinde <i>Connected</i> görünmeli.",
    ])
    s += [P("Normal PowerShell'de Tailscale adresinizi öğrenin:")]
    s += [code("tailscale ip -4")]
    s += [box("Çıktı <b>100.</b> ile başlayan bir adres olmalı (ör. 100.87.12.34). Bu adresi not edin (Adım 9). "
              "<font name='Consolas'>tailscale status</font> komutu Eray'ın bilgisayarını da listeliyorsa bağlantı tamamdır.",
              "ok", "Kontrol")]

    # ---- 4
    s += step_header("4", "OpenSSH Sunucusu (uzaktan komut satırı)", "5 dk")
    s += [P("Eray bu bilgisayara bu servis üzerinden bağlanacak. <b>PowerShell (Yönetici)</b> açın ve yapıştırın:")]
    s += [code(r'''
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd
New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell `
  -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -PropertyType String -Force
if (-not (Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server (sshd)" `
    -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 }
Get-Service sshd
''')]
    s += [P("İlk satır birkaç dakika sürebilir; bitmesini bekleyin.", "small")]
    s += [box("Son komutun çıktısında <b>Status: Running</b> ve <b>Name: sshd</b> görünmeli.", "ok", "Kontrol")]

    # ---- 5
    s += step_header("5", "Eray'ın SSH anahtarını tanımlayın", "3 dk")
    s += [P("SSH anahtarı, Eray'ın şifre girmeden ve güvenli biçimde bağlanmasını sağlar. Eray size "
            "<b>ssh-ed25519 AAAA...</b> ile başlayan <b>tek satırlık</b> bir metin gönderecek. "
            "<b>PowerShell (Yönetici)</b> açın. Aşağıdaki komutta <font name='Consolas'>BURAYA_ANAHTAR</font> yazan yeri, "
            "Eray'ın gönderdiği satırın <b>tamamıyla</b> değiştirin (tırnak işaretleri kalsın):")]
    s += [code(r'''
$key = "BURAYA_ANAHTAR"
$f = "C:\ProgramData\ssh\administrators_authorized_keys"
Add-Content -Path $f -Value $key
icacls $f /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F"
New-Item -ItemType Directory -Force "$env:USERPROFILE\.ssh" | Out-Null
Add-Content -Path "$env:USERPROFILE\.ssh\authorized_keys" -Value $key
Restart-Service sshd
Get-Content $f
''')]
    s += [box("Son komut, Eray'ın anahtar satırını göstermeli. Satır bölünmemiş ve başında/sonunda fazladan boşluk olmamalı. "
              "Anahtar iki dosyaya da eklenir: yönetici hesapları için ilki, standart hesaplar için ikincisi kullanılır.",
              "ok", "Kontrol")]

    # ---- 6
    s += step_header("6", "Git, Python 3.11 ve Node.js kurulumu", "15 dk")
    s += [H2("6a. Git")]
    s += [P("<b>https://git-scm.com/download/win</b> → <i>64-bit Git for Windows Setup</i> indirin ve kurun. "
            "Tüm ekranlarda <b>varsayılan seçenekleri</b> bırakıp <i>Next</i> deyin.")]
    s += [H2("6b. Python 3.11 (önemli: sürüm 3.11 olmalı)")]
    s += numbered([
        "<b>https://www.python.org/downloads/release/python-3119/</b> sayfasının en altından "
        "<i>Windows installer (64-bit)</i> dosyasını indirin.",
        "Kurulumun <b>ilk ekranında</b> en alttaki <b>Add python.exe to PATH</b> kutusunu <b>işaretleyin</b>, sonra "
        "<i>Install Now</i> deyin.",
        "Son ekranda <i>Disable path length limit</i> çıkarsa tıklayın.",
    ])
    s += [H2("6c. Node.js (Claude Code için)")]
    s += [P("<b>https://nodejs.org</b> → <b>LTS</b> sürümünü (Windows Installer, .msi) indirip varsayılan seçeneklerle kurun.")]
    s += [P("Kurulumlar bitince <b>tüm PowerShell pencerelerini kapatıp yeni bir PowerShell açın</b> ve doğrulayın:")]
    s += [code("git --version\npython --version\nnode --version\nnpm --version")]
    s += [box("Dört satır da bir sürüm numarası yazmalı; <b>python --version</b> mutlaka <b>Python 3.11.x</b> olmalı.<br/>"
              "<b>Sorun:</b> <i>Python was not found; run without arguments to install from the Microsoft Store</i> yazıyorsa: "
              "Ayarlar → Uygulamalar → Gelişmiş uygulama ayarları → <i>Uygulama yürütme diğer adları</i> → "
              "<b>python.exe</b> ve <b>python3.exe</b> anahtarlarını <b>kapatın</b>, PowerShell'i yeniden açın.<br/>"
              "<b>Sorun:</b> Python 3.12/3.13 görünüyorsa: 3.11.9'u kurun ve <font name='Consolas'>py -3.11 --version</font> "
              "ile doğrulayın; durumu Eray'a bildirin.", "ok", "Kontrol")]

    # ---- 7
    s += step_header("7", "Proje dosyalarını indirin ve Python ortamını kurun", "10–15 dk")
    s += [P("Normal PowerShell açın ve yapıştırın (indirme ~200 MB'tır, birkaç dakika sürebilir):")]
    s += [code(f'''
cd C:\\
git clone {REPO} RocketCFD
cd C:\\RocketCFD
powershell -ExecutionPolicy Bypass -File scripts\\setup_env.ps1
''')]
    s += [P("Bu ilk çalıştırma Python paketlerini kurar ve sonunda <i>machine_config.json oluşturuldu</i> der. "
            "Şimdi <b>aynı komutu bir kez daha</b> çalıştırın. Bu sefer Fluent'i arka planda açıp kapatarak test eder "
            "(1–2 dakika sürer, ekranda Fluent penceresi açılmaz):")]
    s += [code("cd C:\\RocketCFD\npowershell -ExecutionPolicy Bypass -File scripts\\setup_env.ps1")]
    s += [box("Çıktının sonunda şunlar görünmeli:<br/>"
              "<font name='Consolas'>[OK]   Fluent başlatıldı</font><br/>"
              "<font name='Consolas'>[OK]   Oturum temiz kapatıldı, artık süreç yok</font><br/>"
              "<font name='Consolas'>SONUÇ: BAŞARILI</font><br/>"
              "Bu ekranın görüntüsünü alın. <b>BAŞARISIZ</b> veya <i>fluent.exe bulunamadı</i> yazıyorsa ekran görüntüsünü Eray'a "
              "gönderin; Ansys yolu farklı olabilir, Eray bağlandığında düzeltir. <b>machine_config.json</b> dosyasını "
              "değiştirmenize gerek yok, onu Eray ayarlayacak.", "ok", "Kontrol")]

    # ---- 8
    s += step_header("8", "Claude Code kurulumu", "3 dk")
    s += [P("Claude Code, Eray'ın bu bilgisayarda analizleri izleyip yöneteceği yapay zekâ asistanıdır. "
            "Normal PowerShell'de:")]
    s += [code("npm install -g @anthropic-ai/claude-code\nclaude --version")]
    s += [box("<b>claude --version</b> bir sürüm numarası yazmalı. <b>Giriş yapmayın</b>; oturumu Eray SSH üzerinden açacak.",
              "ok", "Kontrol")]

    # ---- 9
    s += step_header("9", "Eray'a bilgileri gönderin", "2 dk")
    s += [P("Aşağıdaki tabloyu doldurup Eray'a iletin (mesaj veya ekran görüntüleriyle):")]
    s += [table([
        ["Bilgi", "Nereden", "Değer"],
        ["Windows kullanıcı adı", "Adım 1 — whoami (ters bölüden sonrası)", ""],
        ["Tailscale IP adresi", "Adım 3 — tailscale ip -4 (100.x.y.z)", ""],
        ["Fiziksel çekirdek sayısı", "Adım 1 — NumberOfCores", ""],
        ["RAM ve boş disk", "Adım 1", ""],
        ["Ansys yolu doğru mu?", "Adım 1 — True / False", ""],
        ["setup_env sonucu", "Adım 7 — BAŞARILI / BAŞARISIZ (ekran görüntüsü)", ""],
        ["claude --version", "Adım 8", ""],
    ], widths=[1.3, 2.2, 1.3])]

    s += [H1("Kurulumdan sonra — analiz süresince (yaklaşık 3 gün)")]
    s += bullets([
        "Bilgisayarı <b>kapatmayın, yeniden başlatmayın, uyku moduna almayın</b>; dizüstüyse kapağı kapatmayın ve şarjda tutun.",
        "Analiz arka planda çalışır; ekranda bir şey görünmemesi normaldir. Görev Yöneticisi'nde <i>fluent</i>, <i>cx2410</i>, "
        "<i>fl_mpi2410</i> ve <i>python</i> süreçleri görünür ve işlemci kullanımı yüksek olur. Bu süreçleri <b>kapatmayın</b>.",
        "Ağır programlar (oyun, video işleme) çalıştırmayın; analiz yavaşlar. Web/ofis kullanımı sorun değildir.",
        "Ansys Fluent'i bu süre içinde ayrıca açmayın; lisans çakışabilir.",
        "<b>C:\\RocketCFD</b> klasöründe hiçbir dosyayı silmeyin veya taşımayın.",
        "Elektrik veya internet kesilirse sorun değildir: Eray yeniden bağlanıp analizleri kaldığı yerden sürdürür. "
        "Bilgisayar kapandıysa açıp oturumu açmanız yeterlidir.",
    ])
    s += [H1("Sık karşılaşılan sorunlar")]
    s += [table([
        ["Belirti", "Çözüm"],
        ["“... is not recognized as the name of a cmdlet” (git/python/node)", "Kurulumdan sonra PowerShell'i kapatıp yeniden açın. Hâlâ öyleyse ilgili programı yeniden kurun (Python'da PATH kutusu)."],
        ["“running scripts is disabled on this system”", "Komutu belgedeki gibi <font name='Consolas'>powershell -ExecutionPolicy Bypass -File ...</font> biçimiyle çalıştırın."],
        ["Add-WindowsCapability hata verdi", "PowerShell'in <b>Yönetici</b> olarak açıldığından emin olun; internet bağlantısını kontrol edin ve tekrar deneyin."],
        ["git clone: “Repository not found” / kimlik sorar", "Depo gizliye alınmış olabilir. Eray'dan erişim anahtarı (token) isteyin."],
        ["setup_env: “fluent.exe bulunamadı”", "Ansys farklı klasörde. Ekran görüntüsünü Eray'a gönderin; Eray bağlandığında ayarlar."],
        ["setup_env: lisans hatası (license)", "Ansys lisansının bu bilgisayarda çalıştığını kontrol edin: Fluent'i bir kez normal açıp kapatın."],
        ["Tailscale “Logged out” / bağlanmıyor", "Tailscale simgesine sağ tık → Log in. Eray'ın davet ettiği ağa giriş yapın."],
    ], widths=[1.6, 2.6])]
    s += [Spacer(1, 8), box("Hazırlayan: RocketCFD otomasyonu (Claude Code), 24.11.2026. "
                            "Teknik ayrıntılar: depo içindeki <b>README.md</b> ve <b>docs/ankara_setup.md</b>.", "info")]
    return s


def main() -> int:
    out = DOCS_DIR / "pdf" / "Talimatlar.pdf"
    build(out, story(), "Ankara Kurulum Talimatları", "Ankara üretim makinesinin sıfırdan kurulumu")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
