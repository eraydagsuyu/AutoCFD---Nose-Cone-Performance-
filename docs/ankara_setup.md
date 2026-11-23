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
  "fluent_cores": 8,
  "python_exe": "C:\\RocketCFD\\.venv\\Scripts\\python.exe",
  "solver_interface": "pyfluent",
  "allow_batch": true
}
```
`fluent_cores` = A1'deki **fizik** çekirdek sayısı. Sonra testi tekrar çalıştırın:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1
```
**Kontrol:** `SONUÇ: BAŞARILI` ve "artık süreç yok".

### B3. Duman testi (tek koşu, ~8 dk)
```powershell
.venv\Scripts\python.exe src\03_orchestrator.py --mode single --geom P16_L300 --vel 5
.venv\Scripts\python.exe src\rcfd.py inspect P16_L300:5
```
**Kontrol:** `done`, Cd ≈ 0,364 (İstanbul: 0,3638). Süreyi not edin (İstanbul 10 çekirdek: 7,3 dk).

### B4. Toplu koşuyu başlatma
```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_batch.ps1
.venv\Scripts\python.exe src\rcfd.py status
```
SSH'ı kapatın, 2 dk sonra yeniden bağlanıp `rcfd status` → kalp atışı güncel olmalı (SSH kopmasına dayanıklılık testi).

### B5. Denetçi (Claude Code) — Ankara'da
```powershell
npm install -g @anthropic-ai/claude-code    # Node.js yoksa: https://nodejs.org (LTS)
cd C:\RocketCFD
claude
```
Claude Code'da ilk mesaj:
> CLAUDE.md ve docs/runbook_supervisor.md'yi oku. Sen Ankara denetçisisin. `/loop 30m` ile runbook Bölüm 1'deki döngüyü uygula.

---
## C. Günlük işler
- İlerleme: `ssh ankara "cd C:\RocketCFD; .venv\Scripts\python.exe src\rcfd.py status"`
- Sonuçları İstanbul'a almak: Ankara'da `rcfd export` + commit/push → İstanbul'da `git pull`.
- Durdurma: `rcfd stop` (mevcut koşu bitince). Devam: `rcfd resume` + `scripts\start_batch.ps1`.
