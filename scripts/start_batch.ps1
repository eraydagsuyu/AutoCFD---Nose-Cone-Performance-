# Toplu koşu işçilerini SSH oturumundan TAMAMEN bağımsız süreçler olarak başlatır (Ankara).
#
# Neden Start-Process değil: Windows OpenSSH sunucusu, oturumdan başlatılan tüm süreçleri bir Job Object'e
# koyar ve bağlantı kopunca hepsini sonlandırabilir. Win32_Process.Create (WMI) ile başlatılan süreç
# WmiPrvSE altında doğar; SSH oturumunun Job Object'i dışında kalır ve bağlantı kopsa da çalışmaya devam eder.
#
# İşçi sayısı ve işçi başına çekirdek machine_config.json'dan: "workers" (varsayılan 1), "fluent_cores".
# Ölçüm (İstanbul, 2D ~100 bin hücre): 5 çekirdek 215 s, 10 çekirdek 191 s -> 8 çekirdekte 2 işçi × 4 çekirdek önerilir
# (her işçi ayrı Fluent çözücü lisansı kullanır — lisans yetmezse 2. işçi 'worker_exit' olayı yazıp çıkar).
#
# Kullanım (proje kökünden):
#   powershell -ExecutionPolicy Bypass -File scripts\start_batch.ps1 [-Campaign main] [-Workers 2] [-Cores 4] [-ExtraArgs "..."]
# Durum:   .venv\Scripts\python.exe src\rcfd.py status
# Durdur:  .venv\Scripts\python.exe src\rcfd.py stop     (TÜM işçiler mevcut koşusu bitince; yeniden başlatmadan önce `rcfd resume`)
param(
    [string]$Campaign = "main",
    [int]$Workers = 0,
    [int]$Cores = 0,
    [string]$ExtraArgs = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$cfg = Get-Content machine_config.json -Raw | ConvertFrom-Json
if (-not $cfg.allow_batch) {
    Write-Error "machine_config.json: allow_batch = false. Batch yalnızca üretim makinesinde (Ankara) açılır."
    exit 2
}
if ($Workers -le 0) { $Workers = if ($cfg.workers) { [int]$cfg.workers } else { 1 } }
if ($Cores -le 0) { $Cores = [int]$cfg.fluent_cores }

New-Item -ItemType Directory -Force logs | Out-Null
$py = Join-Path $Root ".venv\Scripts\python.exe"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

for ($i = 1; $i -le $Workers; $i++) {
    $w = "${Campaign}_w$i"
    $lock = Join-Path $Root "data\orchestrator_$w.lock"
    if (Test-Path $lock) {
        $lockPid = [int](Get-Content $lock -Raw).Trim()
        if (Get-Process -Id $lockPid -ErrorAction SilentlyContinue) {
            Write-Host "İşçi $w zaten çalışıyor (PID $lockPid) — atlandı."
            continue
        }
    }
    # Makine geneli sınır (28.11): tüm kampanyalardaki canlı işçi sayısı machine_config "workers"a ulaştıysa başlatma.
    # (Ör. main_w2 çalışırken preopt_w1 başlatılırsa 3 Fluent oturumu olurdu — ölçüm: verim düşer, lisans 2.)
    $maxW = if ($cfg.workers) { [int]$cfg.workers } else { 1 }
    $live = @(Get-ChildItem (Join-Path $Root "data") -Filter "orchestrator_*.lock" -ErrorAction SilentlyContinue | Where-Object {
        $p = 0; [int]::TryParse((Get-Content $_.FullName -Raw).Trim(), [ref]$p) | Out-Null
        $p -gt 0 -and ((Get-Process -Id $p -ErrorAction SilentlyContinue).ProcessName -like "python*") })
    if ($live.Count -ge $maxW) {
        Write-Host "İşçi $w başlatılmadı: makinede zaten $($live.Count) canlı işçi var (sınır $maxW): $(($live | ForEach-Object { $_.BaseName -replace '^orchestrator_' }) -join ', ')"
        continue
    }
    $log = Join-Path $Root "logs\batch_${stamp}_$w.console.log"
    $cmd = "cmd.exe /c `"`"$py`" -u src\03_orchestrator.py --mode batch --campaign $Campaign --worker $w --cores $Cores $ExtraArgs > `"$log`" 2>&1`""
    $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine      = $cmd
        CurrentDirectory = $Root
    }
    if ($r.ReturnValue -ne 0) {
        Write-Error "İşçi $w başlatılamadı (Win32_Process.Create ReturnValue=$($r.ReturnValue))"
        exit 1
    }
    Write-Host "İşçi $w başlatıldı ($Cores çekirdek, cmd PID $($r.ProcessId)); konsol logu: $log"
    Start-Sleep -Seconds 20   # Fluent lisans/başlatma çakışmasını önlemek için kademeli başlatma
}
Write-Host "Ayrıntılı log: logs\orchestrator.log, olaylar: logs\events.jsonl"
Write-Host "Durum için: .venv\Scripts\python.exe src\rcfd.py status"
