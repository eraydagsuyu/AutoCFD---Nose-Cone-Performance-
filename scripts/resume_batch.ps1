# Yeniden başlatma / elektrik kesintisi sonrası toplu koşuyu kaldığı yerden sürdürür (Ankara).
#
# Windows oturumu açılınca Görev Zamanlayıcı ("RocketCFD-Resume", ONLOGON + 2 dk gecikme) bu betiği çalıştırır;
# elle de çalıştırılabilir. start_batch.ps1 çalışan işçileri atladığı için tekrar çalıştırmak zararsızdır.
#
# Karar:
#   preopt'ta bitmemiş koşu (pending / retry_pending / running / needs_review) varsa -> preopt_w1 + main_w1
#   yoksa                                                                          -> main_w1 + main_w2
# Toplam Fluent oturumu her durumda machine_config.json "workers" (2) kadardır.
#
# Kullanım: powershell -ExecutionPolicy Bypass -File scripts\resume_batch.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
New-Item -ItemType Directory -Force logs | Out-Null
$log = Join-Path $Root "logs\resume_batch.log"
function Write-Log($m) { $s = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m"; Write-Host $s; Add-Content -Path $log -Value $s -Encoding UTF8 }

$py = Join-Path $Root ".venv\Scripts\python.exe"
$q = "import sqlite3,sys; c=sqlite3.connect(r'data\results.db'); " +
     "f=lambda k: c.execute(""SELECT COUNT(*) FROM runs WHERE campaign=? AND status IN ('pending','retry_pending','running','needs_review')"",(k,)).fetchone()[0]; " +
     "print(f('preopt'), f('main'))"
$counts = (& $py -c $q).Trim() -split '\s+'
$preoptLeft, $mainLeft = [int]$counts[0], [int]$counts[1]
Write-Log "resume: preopt bitmemiş=$preoptLeft, main bitmemiş=$mainLeft"

$sb = Join-Path $PSScriptRoot "start_batch.ps1"
if ($preoptLeft -gt 0) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $sb -Campaign preopt -Workers 1 | ForEach-Object { Write-Log $_ }
    & powershell -NoProfile -ExecutionPolicy Bypass -File $sb -Campaign main -Workers 1 | ForEach-Object { Write-Log $_ }
} else {
    # main işçisi başlarken kesinleşen geometrileri kendisi kuyruğa ekler (ön optimizasyon seçimi yapılmışsa 80'e tamamlanır)
    & powershell -NoProfile -ExecutionPolicy Bypass -File $sb -Campaign main -Workers 2 | ForEach-Object { Write-Log $_ }
}
Write-Log "resume: tamam"
