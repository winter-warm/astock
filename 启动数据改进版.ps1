param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot '启动AStock.ps1') -CheckOnly:$CheckOnly
