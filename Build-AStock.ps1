param([switch]$SkipTests, [string]$OutputDirectory = 'dist')
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$releaseRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot $OutputDirectory))
if (-not $releaseRoot.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw '构建输出必须位于项目目录内'
}
$existingData = Join-Path $releaseRoot 'AStock\data'
if (Test-Path -LiteralPath $existingData) {
    throw "构建目录中存在运行数据：$existingData。为保留账户与策略，停止覆盖构建；请先将完整软件目录备份到其他位置。"
}
$env:UV_CACHE_DIR = Join-Path $projectRoot '.cache\uv'
$env:PYTHONUTF8 = '1'
uv sync --frozen --python 3.12
if ($LASTEXITCODE -ne 0) { throw '依赖同步失败' }
if (-not $SkipTests) {
    & '.\.venv\Scripts\python.exe' -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw '测试失败，停止打包' }
}
& '.\.venv\Scripts\python.exe' tools/check_learning_content.py --prebuild
if ($LASTEXITCODE -ne 0) { throw '教程内容或版本复核未通过，停止正式打包；SkipTests 不跳过教程适配检查' }
& '.\.venv\Scripts\python.exe' tools/make_icon.py
if ($LASTEXITCODE -ne 0) { throw '图标生成失败' }
& '.\.venv\Scripts\pyinstaller.exe' --noconfirm --distpath $releaseRoot AStock.spec
if ($LASTEXITCODE -ne 0) { throw '打包失败' }
$releaseDir = Join-Path $releaseRoot 'AStock'
Set-Content -LiteralPath (Join-Path $releaseDir 'portable.flag') -Value 'AStock portable data directory' -Encoding utf8
Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md') -Destination (Join-Path $releaseDir '使用说明.md')
Copy-Item -LiteralPath (Join-Path $projectRoot 'docs') -Destination (Join-Path $releaseDir 'docs') -Recurse -Force
$version = & '.\.venv\Scripts\python.exe' -c 'from astock import __version__; print(__version__)'
if ($LASTEXITCODE -ne 0) { throw '读取版本失败' }
$archivePath = Join-Path $releaseRoot "AStock-$version-Windows-x64.zip"
Compress-Archive -LiteralPath $releaseDir -DestinationPath $archivePath -Force
$archiveHash = Get-FileHash -LiteralPath $archivePath -Algorithm SHA256
Set-Content -LiteralPath "$archivePath.sha256" -Value ($archiveHash.Hash + '  ' + (Split-Path -Leaf $archivePath)) -Encoding utf8
$archiveHash | Format-List
& '.\.venv\Scripts\python.exe' tools/package_source.py
if ($LASTEXITCODE -ne 0) { throw '源码归档失败' }
