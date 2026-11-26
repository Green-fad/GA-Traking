# GAtraking — desinstallation propre (ne supprime pas les donnees sans confirmation)
$ErrorActionPreference = "Stop"
Write-Host "=== Desinstallation GAtraking ==="
if (Test-Path "data") {
    $r = Read-Host "Supprimer aussi les donnees (base, medias, rapports) ? (o/N)"
    if ($r -eq "o") { Remove-Item -Recurse -Force data ; Write-Host "Donnees supprimees." }
    else { Write-Host "Donnees conservees dans ./data" }
}
if (Test-Path ".venv") { Remove-Item -Recurse -Force .venv }
Write-Host "Environnement supprime. Le dossier du projet peut etre supprime manuellement."
