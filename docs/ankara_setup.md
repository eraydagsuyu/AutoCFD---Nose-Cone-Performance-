# Ankara Kurulum Rehberi (üretim makinesi)

Sıra önemlidir; her adımın sonundaki **Kontrol** satırı geçmeden sonrakine geçmeyin.
Komutlar Windows PowerShell içindir. "(Yönetici)" yazanlar yönetici PowerShell'de çalıştırılır.

---
## A. Ankara makinesinde (arkadaşınızın yapacağı, ~30 dk)

### A1. Makine bilgisi
```powershell
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors
Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize
Get-PSDrive C | Select-Object Used, Free
Test-Path "C:\Program Files\ANSYS Inc\v241\fluent\ntbin\win64\fluent.exe"
```
**Kontrol:** Fizik çekirdek sayısını (`NumberOfCores`) not edin; Fluent bu kadar çekirdekle çalışacak. Boş disk ≥ 50 GB. Son satır `True` olmalı (Ansys 2024 R1 yolu farklıysa not edin).

### A2. Tailscale
1. https://tailscale.com/download/windows → kurun → İstanbul'daki ile **aynı hesapla** oturum açın.
2. Tailscale simgesi → makinenin `100.x.y.z` adresini not edin.

**Kontrol:** İstanbul'da `tailscale status` çıktısında Ankara makinesi görünür.

### A3. OpenSSH Server (Yönetici)
```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd
Get-NetFirewallRule -Name *OpenSSH-Server* | Select-Object Name, Enabled
```
**Kontrol:** `Get-Service sshd` → `Running`.

### A4. Güç ve güncelleme kilidi (Yönetici)
```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change disk-timeout-ac 0
powercfg /change monitor-timeout-ac 30
# Windows Update otomatik yeniden başlatmayı engelle (aktif saatleri genişlet)
reg add "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" /v ActiveHoursStart /t REG_DWORD /d 0 /f
reg add "HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings" /v ActiveHoursEnd /t REG_DWORD /d 23 /f
reg add "HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU" /v NoAutoRebootWithLoggedOnUsers /t REG_DWORD /d 1 /f
```
Ayrıca: Aygıt Yöneticisi → Ağ bağdaştırıcısı → Özellikler → Güç Yönetimi → "Güç tasarrufu için bilgisayar bu aygıtı kapatabilir" işaretini kaldırın.
Ayarlar → Windows Update → "Güncellemeleri duraklat" (en uzun süre).

**Kontrol:** `powercfg /query SCHEME_CURRENT SUB_SLEEP` → uyku süreleri 0.

### A5. Yazılımlar
- Git: https://git-scm.com/download/win (varsayılan seçenekler)
- Python **3.11** (64-bit): https://www.python.org/downloads/release/python-3119/ → "Add python.exe to PATH" işaretli
- Ansys 2024 R1 lisansının bu makinede çalıştığından emin olun (Fluent'i bir kez açıp kapatmak yeterli).

**Kontrol:** yeni PowerShell'de `git --version` ve `python --version` → `Python 3.11.x`.

---
## B. İstanbul'dan (SSH ile — siz)

### B1. SSH anahtarı (İstanbul)
```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\rocketcfd_ankara -N '""'
Get-Content $env:USERPROFILE\.ssh\rocketcfd_ankara.pub
```
Açık anahtar satırını Ankara'ya iletin. Ankara'da (Yönetici; kullanıcı yönetici grubundaysa bu dosya kullanılır):
```powershell
Add-Content -Path "C:\ProgramData\ssh\administrators_authorized_keys" -Value "<açık anahtar satırı>"
icacls "C:\ProgramData\ssh\administrators_authorized_keys" /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F"
```
İstanbul'da `~\.ssh\config` dosyasına:
```
Host ankara
    HostName 100.x.y.z
    User <ankara_kullanıcı_adı>
    IdentityFile ~/.ssh/rocketcfd_ankara
    ServerAliveInterval 30
```
**Kontrol:** `ssh ankara hostname` parola sormadan makine adını yazar.

### B2. Depoyu çekme ve ortam (SSH içinde)
```powershell
ssh ankara
cd C:\
git clone https://github.com/eraydagsuyu/AutoCFD---Nose-Cone-Performance-.git RocketCFD
cd C:\RocketCFD
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1
```
İlk çalıştırmada `machine_config.json` oluşturulur. Düzenleyin:
```powershell
notepad machine_config.json   # veya: Claude Code'a düzenletin
```
```json
{
  "machine_name": "ankara",
  "ansys_version": "24.1",
  "awp_root": "C:\\Program Files\\ANSYS Inc\\v241",
  "fluent_exe": "C:\\Program Files\\ANSYS Inc\\v241\\fluent\\ntbin\\win64\\fluent.exe",
  "fluent_cores": 4,
  "workers": 2,
  "python_exe": "C:\\RocketCFD\\.venv\\Scripts\\python.exe",
  "solver_interface": "pyfluent",
  "allow_batch": true
}
```
**İşçi düzeni:** `workers × fluent_cores` = A1'deki **fizik** çekirdek sayısı. 2D ~100 bin hücrede çekirdek ölçeklenmesi zayıf
(İstanbul: 5 çekirdek 215 s, 10 çekirdek 191 s) → 8 çekirdekte **2 işçi × 4 çekirdek** toplam verimi ~1,8× artırır.
Her işçi ayrı bir Fluent çözücü lisansı kullanır (B3b'de kontrol). Sonra testi tekrar çalıştırın:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1
```
**Kontrol:** `SONUÇ: BAŞARILI` ve "artık süreç yok".

### B3. Duman testi (tek koşu, ~3 dk)
```powershell
.venv\Scripts\python.exe src\03_orchestrator.py --mode single --geom P16_L300 --vel 5
.venv\Scripts\python.exe src\rcfd.py inspect P16_L300:5
```
**Kontrol:** `done`, Cd ≈ 0,3633 (İstanbul: 0,3633, 900 it). Süreyi not edin (İstanbul 10 çekirdek: 2,8 dk).

### B3b. İki eş zamanlı Fluent lisans kontrolü (~1 dk)
```powershell
$p1 = Start-Process .venv\Scripts\python.exe -ArgumentList "src\tools\check_env.py" -PassThru -NoNewWindow
Start-Sleep 5
.venv\Scripts\python.exe src\tools\check_env.py
$p1.WaitForExit()
```
**Kontrol:** İkisi de `SONUÇ: BAŞARILI` → `"workers": 2`. İkincisi lisans hatası verirse → `"workers": 1, "fluent_cores": 8`.

### B4. Toplu koşuyu başlatma
```powershell
# 1) Ön optimizasyon koşularını bu makinenin veritabanına kaydet (92 aday mesh Git'te hazır; saniyeler sürer).
#    Atlanırsa preopt kampanyası "kuyruk boş" deyip çıkar.
.venv\Scripts\python.exe src\00_preopt.py --build
# 2) İşçileri başlat (lisans 2 oturuma izin veriyorsa ikisi birden; vermiyorsa önce preopt)
powershell -ExecutionPolicy Bypass -File scripts\start_batch.ps1 -Campaign preopt -Workers 1
powershell -ExecutionPolicy Bypass -File scripts\start_batch.ps1 -Campaign main -Workers 1
.venv\Scripts\python.exe src\rcfd.py status
.venv\Scripts\python.exe src\rcfd.py --campaign preopt status
```
SSH'ı kapatın, 2 dk sonra yeniden bağlanıp `rcfd status` → tüm işçilerin kalp atışı güncel olmalı (SSH kopmasına dayanıklılık testi).

**Önerilen sıra:** önce ön optimizasyon kampanyası (serbest parametreli 20 ana mesh buna bağlı), aynı anda ana kampanyanın
sabit 60 geometrisi. Ayrıntı ve süre tahmini: `CLAUDE.md` Bölüm 10 ("Süre tahmini").

### B5. Denetçi (Claude Code) — Ankara'da
```powershell
npm install -g @anthropic-ai/claude-code    # Node.js yoksa: https://nodejs.org (LTS)
cd C:\RocketCFD
claude
```
Claude Code'da ilk mesaj:
> CLAUDE.md ve docs/runbook_supervisor.md'yi oku. Sen Ankara denetçisisin. `/loop 30m` ile runbook Bölüm 1'deki döngüyü uygula.

---
## B6. Gerçekleşen kurulum (25.11.2026) — yukarıdakinden farklar
- **B3:** Cd 0,36335 ✔ (7,1 dk, 4 çekirdek). **B3b:** 2 eşzamanlı lisans ✔.
- **Çekirdek ölçümü (Core 5 210H, 4P HT + 4E):** 1×4 0,52 s/it; 1×8 ~1,8 s/it; 2×4 sabitlemesiz 1,43+1,43 s/it;
  2×4 sabitlemeli 0,30 (P) + 0,43 (E) s/it → `machine_config.json`:
  `"workers": 2, "fluent_cores": 4, "cpu_affinity": {"preopt_w1": [0,2,4,6], "main_w1": [8,9,10,11], "main_w2": [0,2,4,6]}`.
- **B4:** `start_batch.ps1` yerine `scripts\resume_batch.ps1` (kampanya durumuna göre işçileri seçer; 6b sırasında
  `data\6b_in_progress` varken işçi başlatmaz).
- **Görev Zamanlayıcı:** makine kullanıcısı kendi PowerShell'inde `scripts\install_tasks.ps1` çalıştırır (SSH'tan kalıcı görev
  oluşturma yapılmadı). `schtasks /RU <kısa ad>` bilgisayar adı = kullanıcı adı olduğunda "UserId" hatası verir — betik tam adı kullanır.
- **B5:** denetçi `/loop 1h` (Pro kotası), izinler `.claude/settings.local.json` (Git dışı; rcfd/preopt/mesh/start_batch izinli,
  `git push`, `src/` düzenleme, `Stop-Process` yasak), `autoContinueAtUsageLimit: true`.
- `.ps1` dosyaları **UTF-8 BOM'lu** olmalı (PS 5.1, cp1254); aksi hâlde ayrıştırma hatası.

## C. Günlük işler
- İlerleme: `ssh ankara "cd C:\RocketCFD; .venv\Scripts\python.exe src\tools\progress.py"` (ayrıntı: `src\rcfd.py status`)
- Dönüşte sonuçları alma prosedürü: `CLAUDE.md` Bölüm 0 "Dönüşte".
- Sonuçları İstanbul'a almak: Ankara'da `rcfd export` + commit/push → İstanbul'da `git pull`.
- Durdurma: `rcfd stop` (mevcut koşu bitince). Devam: `rcfd resume` + `scripts\start_batch.ps1`.
