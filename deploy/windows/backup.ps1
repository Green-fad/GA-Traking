# GAtraking — sauvegarde : base + medias + configuration + rapports
param([string]$Output = "backups")
$ErrorActionPreference = "Stop"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$dest = Join-Path $Output "gatraking_$stamp"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
if (Test-Path "data/gatraking.db") { Copy-Item "data/gatraking.db" $dest }
if (Test-Path "data/media") { Copy-Item -Recurse "data/media" "$dest/media" }
if (Test-Path "data/reports") { Copy-Item -Recurse "data/reports" "$dest/reports" }
if (Test-Path "config/gatraking.yaml") { Copy-Item "config/gatraking.yaml" $dest }
Compress-Archive -Path "$dest\*" -DestinationPath "$dest.zip" -Force
Remove-Item -Recurse -Force $dest
Write-Host "Sauvegarde : $dest.zip"
