# GAtraking — Installation Windows (PowerShell, execute en tant qu'administrateur)
# Usage : powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
Write-Host "=== GAtraking : installation Windows ===" -ForegroundColor Cyan

# 1. Python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "Python introuvable : installer Python 3.10+ depuis https://python.org" -ForegroundColor Red
    exit 1
}
python --version

# 2. Environnement virtuel + dependances
python -m venv .venv
.\.venv\Scripts\pip install --upgrade pip
.\.venv\Scripts\pip install -r requirements.txt

# 3. Configuration initiale guidee
.\.venv\Scripts\python deploy\configure.py

# 4. Schema de base de donnees
.\.venv\Scripts\python -m ga.cli migrate

# 5. Detection du materiel (CPU/GPU)
.\.venv\Scripts\python -m ga.cli hardware

Write-Host ""
Write-Host "Installation terminee." -ForegroundColor Green
Write-Host "Demarrage : .\run.ps1   (console : http://localhost:8000)"
Write-Host "IMPORTANT : changer le mot de passe admin au premier login."
