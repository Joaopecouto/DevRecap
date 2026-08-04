# Cria o ambiente virtual e instala as dependências do DevRecap.
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venv = Join-Path $root ".venv"

Write-Host "Criando ambiente virtual em $venv ..."
if (-not (Test-Path $venv)) { python -m venv $venv }

$py = Join-Path $venv "Scripts\python.exe"
Write-Host "Instalando dependencias ..."
& $py -m pip install --upgrade pip --disable-pip-version-check
& $py -m pip install -r (Join-Path $root "requirements.txt") --disable-pip-version-check

Write-Host ""
Write-Host "Pronto! Para rodar:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\pythonw.exe run.py   (sem console)"
Write-Host "  .\.venv\Scripts\python.exe run.py    (com logs no console)"
