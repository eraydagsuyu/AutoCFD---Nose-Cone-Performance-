# Toplu koşuyu SSH oturumundan TAMAMEN bağımsız bir süreç olarak başlatır (Ankara).
#
# Neden Start-Process değil: Windows OpenSSH sunucusu, oturumdan başlatılan tüm süreçleri bir Job Object'e
# koyar ve bağlantı kopunca hepsini sonlandırabilir. Win32_Process.Create (WMI) ile başlatılan süreç
# WmiPrvSE altında doğar; SSH oturumunun Job Object'i dışında kalır ve bağlantı kopsa da çalışmaya devam eder.
#
# Kullanım (proje kökünden):
#   powershell -ExecutionPolicy Bypass -File scripts\start_batch.ps1 [-Campaign main] [-ExtraArgs "--geoms P01_L200"]
# Durum:   .venv\Scripts\python.exe src\rcfd.py status
# Durdur:  .venv\Scripts\python.exe src\rcfd.py stop     (mevcut koşu bitince)
param(
    [string]$Campaign = "main",
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

$lock = Join-Path $Root "data\orchestrator.lock"
if (Test-Path $lock) {
    $lockPid = [int](Get-Content $lock -Raw).Trim()
    if (Get-Process -Id $lockPid -ErrorAction SilentlyContinue) {
        Write-Host "Orkestratör zaten çalışıyor (PID $lockPid)."
        exit 0
    }
}

New-Item -ItemType Directory -Force logs | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$log = Join-Path $Root "logs\batch_$stamp.console.log"
$py = Join-Path $Root ".venv\Scripts\python.exe"
$cmd = "cmd.exe /c `"`"$py`" -u src\03_orchestrator.py --mode batch --campaign $Campaign $ExtraArgs > `"$log`" 2>&1`""

$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine      = $cmd
    CurrentDirectory = $Root
}
if ($r.ReturnValue -ne 0) {
    Write-Error "Süreç başlatılamadı (Win32_Process.Create ReturnValue=$($r.ReturnValue))"
    exit 1
}
Write-Host "Orkestratör başlatıldı (cmd PID $($r.ProcessId)); SSH kopsa da çalışmaya devam eder."
Write-Host "  konsol logu: $log"
Write-Host "  ayrıntılı log: logs\orchestrator.log, olaylar: logs\events.jsonl"
Write-Host "Durum için: .venv\Scripts\python.exe src\rcfd.py status"
