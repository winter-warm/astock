$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw '未找到 uv。请按本目录“开始学习.md”安装 uv，再重新打开 PowerShell 7。'
}
uv sync --locked --python 3.12
if ($LASTEXITCODE -ne 0) { throw '环境安装失败，Notebook 尚未启动。请查看网络和错误信息后重试。' }
uv run --locked jupyter lab
if ($LASTEXITCODE -ne 0) { throw 'Jupyter 启动或运行异常。' }
