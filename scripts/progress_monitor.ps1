# Ankara ilerleme penceresi: her 5 dakikada bir tamamlanma yüzdesini gösterir (salt okunur).
# Görev Zamanlayıcı "RocketCFD-Progress" oturum açılınca bu pencereyi açar. Pencereyi kapatmak analizi durdurmaz.
# Elle: powershell -ExecutionPolicy Bypass -File scripts\progress_monitor.ps1
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Host.UI.RawUI.WindowTitle = "RocketCFD - Analiz İlerlemesi"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$py = Join-Path $Root ".venv\Scripts\python.exe"
while ($true) {
    $out = & $py (Join-Path $Root "src\tools\progress.py") 2>&1 | Out-String
    Clear-Host
    Write-Host $out
    Start-Sleep -Seconds 300
}
