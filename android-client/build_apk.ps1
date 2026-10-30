$ErrorActionPreference = "Stop"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Building Share COC Android App (Google Drive)" -ForegroundColor Yellow
Write-Host "========================================================" -ForegroundColor Cyan

$env:JAVA_HOME = "C:\Users\tohiba\.android_build_tools\jdk-17.0.12+7"
$env:ANDROID_HOME = "C:\Users\tohiba\.android_build_tools\android-sdk"
$gradleBat = "C:\Users\tohiba\.android_build_tools\gradle-8.7\bin\gradle.bat"
$env:PATH = "$env:JAVA_HOME\bin;C:\Users\tohiba\.android_build_tools\gradle-8.7\bin;$env:PATH"

Write-Host "[1/3] Checking environment..." -ForegroundColor Green
& "$env:JAVA_HOME\bin\java.exe" -version

Set-Location "$PSScriptRoot"

Write-Host "[2/3] Compiling and packaging APK..." -ForegroundColor Green
& $gradleBat assembleDebug --no-daemon --stacktrace

$apkPath = "$PSScriptRoot\app\build\outputs\apk\debug\app-debug.apk"
if (Test-Path $apkPath) {
    Write-Host "========================================================" -ForegroundColor Green
    Write-Host "  [3/3] APK Built Successfully!" -ForegroundColor Green
    Write-Host "  APK Location: $apkPath" -ForegroundColor Yellow
    $sizeMb = [math]::Round((Get-Item $apkPath).Length / 1MB, 2)
    Write-Host "  File Size: $sizeMb MB" -ForegroundColor Cyan
    Write-Host "========================================================" -ForegroundColor Green
} else {
    Write-Host "[!] APK file not found after build." -ForegroundColor Red
}
