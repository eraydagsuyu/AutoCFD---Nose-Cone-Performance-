# Yeniden başlatma / elektrik kesintisi sonrası toplu koşuyu kaldığı yerden sürdürür (Ankara).
#
# Windows oturumu açılınca Görev Zamanlayıcı ("RocketCFD-Resume", ONLOGON + 2 dk gecikme) bu betiği çalıştırır;
# elle de çalıştırılabilir. start_batch.ps1 çalışan işçileri atladığı için tekrar çalıştırmak zararsızdır.
#
# Karar:
#   preopt'ta bitmemiş koşu (pending / retry_pending / running / needs_review) varsa -> preopt_w1 + main_w1
#   preopt bitti ama 6b (seçim + 20 mesh) yapılmadı                                 -> yalnızca main_w1
#        (2. lisans 6b'nin Fluent mesh kontrolüne kalır)
#   6b yapıldı                                                                     -> main_w1 + main_w2
# Görev Zamanlayıcı ayrıca her 30 dk'da çalıştırır ("RocketCFD-Resume-30dk"): ölen/çıkan işçi kendiliğinden yeniden başlar.
# Toplam Fluent oturumu her durumda machine_config.json "workers" (2) kadardır.
#
# Kullanım: powershell -ExecutionPolicy Bypass -File scripts\resume_batch.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
New-Item -ItemType Directory -Force logs | Out-Null
$log = Join-Path $Root "logs\resume_batch.log"
function Write-Log($m) { $s = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m"; Write-Host $s; Add-Content -Path $log -Value $s -Encoding UTF8 }

# 6b sürerken (denetçi data\6b_in_progress oluşturur) işçi başlatma: main işçisi başlarken kesin geometrileri
# kuyruğa ekler; --select sonrası mesh'ler yenilenmeden eklenirse eski mesh'le çözülür. 3 saatten eski işaret yok sayılır.
$marker = Join-Path $Root "data\6b_in_progress"
if ((Test-Path $marker) -and ((Get-Date) - (Get-Item $marker).LastWriteTime).TotalHours -lt 3) {
    Write-Log "resume: 6b sürüyor (data\6b_in_progress) -> işçi başlatılmadı"
    exit 0
}

$py = Join-Path $Root ".venv\Scripts\python.exe"
# preopt/main bitmemiş koşu sayısı ve 6b seçimi yapıldı mı (src\tools\batch_state.py, salt okunur)
$counts = (& $py (Join-Path $Root "src\tools\batch_state.py")).Trim() -split '\s+'
$preoptLeft, $mainLeft, $selected = [int]$counts[0], [int]$counts[1], [int]$counts[2]
# Kullanıcı/denetçi bilerek durdurduysa (rcfd stop / pause) otomatik yeniden başlatma yapılmaz; devam için `rcfd resume`.
if ($counts.Count -gt 3 -and $counts[3] -ne "-") {
    Write-Log "resume: kontrol bayrağı açık ($($counts[3])) -> işçi başlatılmadı (devam için: rcfd resume)"
    exit 0
}
Write-Log "resume: preopt bitmemiş=$preoptLeft, main bitmemiş=$mainLeft, seçim yapıldı=$selected"

$sb = Join-Path $PSScriptRoot "start_batch.ps1"
if ($preoptLeft -gt 0) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $sb -Campaign preopt -Workers 1 | ForEach-Object { Write-Log $_ }
    & powershell -NoProfile -ExecutionPolicy Bypass -File $sb -Campaign main -Workers 1 | ForEach-Object { Write-Log $_ }
} elseif ($counts.Count -gt 4 -and [int]$counts[4] -gt 0) {
    # GCI çalışması (27.11): main_w1 (E çekirdekleri) + gci_w1 (P çekirdekleri). GCI bitince gci_w1 çıkar;
    # bir sonraki 30 dk'lık çalıştırma aşağıdaki son dala düşer ve main_w2'yi başlatır.
    Write-Log "resume: gci bitmemiş=$($counts[4]) -> main_w1 + gci_w1"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $sb -Campaign main -Workers 1 | ForEach-Object { Write-Log $_ }
    & powershell -NoProfile -ExecutionPolicy Bypass -File $sb -Campaign gci -Workers 1 | ForEach-Object { Write-Log $_ }
} elseif ($selected -eq 0) {
    Write-Log "resume: preopt bitti, 6b bekleniyor (denetçi) -> yalnızca main_w1"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $sb -Campaign main -Workers 1 | ForEach-Object { Write-Log $_ }
} else {
    # main işçisi başlarken kesinleşen geometrileri kendisi kuyruğa ekler (ön optimizasyon seçimi yapılmışsa 80'e tamamlanır)
    & powershell -NoProfile -ExecutionPolicy Bypass -File $sb -Campaign main -Workers 2 | ForEach-Object { Write-Log $_ }
}
Write-Log "resume: tamam"
