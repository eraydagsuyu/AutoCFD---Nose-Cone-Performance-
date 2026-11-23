# RocketCFD Python ortam kurulumu (İstanbul ve Ankara'da aynı).
# Kullanım (proje kökünden):  powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Sanal ortam oluşturuluyor (.venv)..."
    python -m venv .venv
}
& .venv\Scripts\python.exe -m pip install --upgrade pip -q
& .venv\Scripts\python.exe -m pip install -r requirements.txt -q

if (-not (Test-Path "machine_config.json")) {
    Copy-Item machine_config.example.json machine_config.json
    Write-Host "machine_config.json oluşturuldu — bu makineye göre düzenleyin (machine_name, fluent_exe, fluent_cores, allow_batch)."
    exit 0
}

& .venv\Scripts\python.exe src\tools\check_env.py
exit $LASTEXITCODE
