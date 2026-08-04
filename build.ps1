# Empacota o DevRecap num executável único com PyInstaller.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venv = Join-Path $root ".venv"
$py = Join-Path $venv "Scripts\python.exe"
$work = Join-Path $env:TEMP "DevRecap-build"

if (-not (Test-Path $py)) {
    Write-Host "Rode .\setup.ps1 primeiro (ambiente virtual ausente)." -ForegroundColor Red
    exit 1
}

Write-Host "Instalando PyInstaller (se necessario) ..."
& $py -m pip install pyinstaller --disable-pip-version-check

Write-Host "Empacotando DevRecap.exe ..."
& $py -m PyInstaller `
    --noconfirm --windowed --onefile --name DevRecap `
    --icon (Join-Path $root "assets\icon.ico") `
    --add-data "$(Join-Path $root 'assets\icon.png');assets" `
    --add-data "$(Join-Path $root 'devrecap\ui\web');devrecap/ui/web" `
    --hidden-import pystray._win32 `
    --hidden-import clr `
    --hidden-import webview.platforms.edgechromium `
    --collect-all clr_loader `
    --collect-all google.genai `
    --copy-metadata google-genai `
    --collect-all apscheduler `
    --collect-all tzlocal `
    --distpath (Join-Path $root "dist") `
    --workpath $work `
    --specpath $work `
    (Join-Path $root "run.py")

Write-Host ""
Write-Host "Pronto: dist\DevRecap.exe" -ForegroundColor Green
