$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $projectRoot '.cache\uv'
$env:ASTOCK_DATA_DIR = Join-Path $projectRoot 'data'
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.venv\Scripts\pythonw.exe'))) {
    uv sync --frozen --python 3.12
    if ($LASTEXITCODE -ne 0) { throw '依赖安装失败' }
}
Start-Process -FilePath (Join-Path $projectRoot '.venv\Scripts\pythonw.exe') -ArgumentList '-m', 'astock' -WorkingDirectory $projectRoot -WindowStyle Normal
