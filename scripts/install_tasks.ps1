# Ankara Görev Zamanlayıcı kurulumu (bir kez, Ankara kullanıcısının kendi PowerShell'inde çalıştırılır).
#   RocketCFD-Resume       : oturum açılınca (2 dk gecikme) scripts\resume_batch.ps1 — kesinti sonrası devam
#   RocketCFD-Resume-30dk  : her 30 dk resume_batch.ps1 — ölen/çıkan işçiyi yeniden başlatır (çalışanlar atlanır)
#   RocketCFD-Progress     : oturum açılınca (3 dk gecikme) ilerleme penceresi; kurulumdan hemen sonra da açılır
# Kullanıcı tam adıyla (BİLGİSAYAR\kullanıcı) verilir: bilgisayar adı = kullanıcı adı olduğunda kısa ad "UserId" hatası verir.
# Süre sınırı kapalı (varsayılan 72 saat ilerleme penceresini 3. günde kapatırdı).
#
# Kullanım: powershell -ExecutionPolicy Bypass -File C:\RocketCFD\scripts\install_tasks.ps1
#   -DryRun : yalnızca söz dizimi testi (zararsız cmd.exe görevleri kurar ve hemen siler)
param([switch]$DryRun)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$user = "$env:USERDOMAIN\$env:USERNAME"
$ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

function Register-RcfdTask([string]$Name, [string]$Exe, [string]$TaskArgs, $Trigger) {
    $action = New-ScheduledTaskAction -Execute $Exe -Argument $TaskArgs -WorkingDirectory $Root
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $Trigger -Principal $principal `
        -Settings $settings -Force | Out-Null
    Write-Host "[OK] $Name ($user)"
}

$pfx = if ($DryRun) { "RocketCFD-TEST-" } else { "RocketCFD-" }
$resumeArgs = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Root\scripts\resume_batch.ps1`""
$progArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$Root\scripts\progress_monitor.ps1`""
$exeR, $exeP = $ps, $ps
if ($DryRun) { $exeR = $exeP = "$env:SystemRoot\System32\cmd.exe"; $resumeArgs = $progArgs = "/c exit 0" }

$tLogon = New-ScheduledTaskTrigger -AtLogOn -User $user
$tLogon.Delay = "PT2M"
Register-RcfdTask "${pfx}Resume" $exeR $resumeArgs $tLogon

$tRep = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Minutes 30)
Register-RcfdTask "${pfx}Resume-30dk" $exeR $resumeArgs $tRep

$tLogon2 = New-ScheduledTaskTrigger -AtLogOn -User $user
$tLogon2.Delay = "PT3M"
Register-RcfdTask "${pfx}Progress" $exeP $progArgs $tLogon2

Start-ScheduledTask -TaskName "${pfx}Progress"
Write-Host "[OK] ${pfx}Progress başlatıldı"

Get-ScheduledTask -TaskName "${pfx}*" | ForEach-Object {
    $i = $_ | Get-ScheduledTaskInfo
    Write-Host ("     {0,-28} durum={1,-8} sonraki={2}" -f $_.TaskName, $_.State, $i.NextRunTime)
}
if ($DryRun) {
    Get-ScheduledTask -TaskName "${pfx}*" | Unregister-ScheduledTask -Confirm:$false
    Write-Host "DryRun: test görevleri silindi. SONUÇ: BAŞARILI"
} else {
    Write-Host "SONUÇ: BAŞARILI — 'RocketCFD - Analiz İlerlemesi' penceresi birkaç saniye içinde açılır."
}
