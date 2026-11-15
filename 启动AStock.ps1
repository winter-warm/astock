param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$indexPath = Join-Path $projectRoot 'dist\交付记录.json'
if (-not (Test-Path -LiteralPath $indexPath -PathType Leaf)) {
    throw "缺少当前交付索引：$indexPath"
}
$release = Get-Content -LiteralPath $indexPath -Raw -Encoding utf8 | ConvertFrom-Json
$appPath = [IO.Path]::GetFullPath((Join-Path $projectRoot $release.current_app))
$dataPath = [IO.Path]::GetFullPath((Join-Path $projectRoot $release.current_data))
foreach ($path in @($appPath, $dataPath)) {
    if (-not $path.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "启动路径必须位于项目目录内：$path"
    }
}
if (-not (Test-Path -LiteralPath $appPath -PathType Leaf)) {
    throw "找不到当前程序：$appPath"
}
if ($CheckOnly) {
    [pscustomobject]@{ Version = $release.version; Application = $appPath; Data = $dataPath }
    return
}
# 隐藏外层 PowerShell 控制台即可；GUI 自身必须正常显示。
Start-Process -FilePath $appPath -ArgumentList @('--data-dir', ('"' + $dataPath + '"')) -WorkingDirectory $projectRoot -WindowStyle Normal
