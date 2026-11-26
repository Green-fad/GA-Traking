# GAtraking — restauration depuis une sauvegarde zip
param([Parameter(Mandatory=$true)][string]$Archive)
$ErrorActionPreference = "Stop"
$tmp = Join-Path $env:TEMP ("ga_restore_" + [guid]::NewGuid().ToString("N").Substring(0,8))
Expand-Archive -Path $Archive -DestinationPath $tmp
if (Test-Path "$tmp/gatraking.db") { Copy-Item "$tmp/gatraking.db" "data/" -Force }
if (Test-Path "$tmp/media") { Copy-Item -Recurse -Force "$tmp/media" "data/" }
if (Test-Path "$tmp/reports") { Copy-Item -Recurse -Force "$tmp/reports" "data/" }
if (Test-Path "$tmp/gatraking.yaml") { Copy-Item "$tmp/gatraking.yaml" "config/" -Force }
Remove-Item -Recurse -Force $tmp
Write-Host "Restauration terminee depuis $Archive"
