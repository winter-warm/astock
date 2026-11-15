param([switch]$Online, [string]$ArchivePath = '')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $projectRoot '.venv\Scripts\python.exe') (Join-Path $projectRoot 'tools\check_learning_content.py') --prebuild
if ($LASTEXITCODE -ne 0) { throw '长期课程未完成，不能通过正式发布验收' }
$qaRoot = Join-Path $projectRoot ('output\release-check-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $qaRoot | Out-Null
$version = & (Join-Path $projectRoot '.venv\Scripts\python.exe') -c 'from astock import __version__; print(__version__)'
if ($LASTEXITCODE -ne 0) { throw '读取版本失败' }
if (-not $ArchivePath) { $ArchivePath = Join-Path $projectRoot "dist\AStock-$version-Windows-x64.zip" }
$archivePath = [IO.Path]::GetFullPath($ArchivePath)
Expand-Archive -LiteralPath $archivePath -DestinationPath (Join-Path $qaRoot '解压 验收')
$exe = Join-Path $qaRoot '解压 验收\AStock\AStock.exe'
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
$env:PYTHONPATH = ''
$env:ASTOCK_DATA_DIR = ''
$env:QT_QPA_PLATFORM = 'windows'
$results = @()
$coursePath = Join-Path $qaRoot 'courses'
New-Item -ItemType Directory -Path $coursePath | Out-Null
$process = Start-Process -FilePath $exe -ArgumentList @('--course-smoke', '--screenshot', (Join-Path $coursePath 'courses.png'), '--width', '1280', '--height', '760') -WorkingDirectory $coursePath -WindowStyle Hidden -PassThru
if (-not $process.WaitForExit(60000)) {
    $process.Kill($true)
    throw '软件包长期课程验收超过 60 秒'
}
if ($process.ExitCode -ne 0) { throw '软件包长期课程验收失败，请检查 course-result.json' }
$courses = Get-Content -Raw -LiteralPath (Join-Path $coursePath 'course-result.json') | ConvertFrom-Json
if (-not $courses.passed -or $courses.lesson_count -ne 72 -or $courses.notebooks -ne 72) { throw '软件包教程资源、练习或导出未通过' }
foreach ($mode in @('backtest', 'replay', 'equity')) {
    $casePath = Join-Path $qaRoot $mode
    New-Item -ItemType Directory -Path $casePath | Out-Null
    $theme = if ($mode -eq 'backtest') { 'dark' } else { 'light' }
    $argsList = @('--smoke', '--smoke-mode', $mode, '--screenshot', (Join-Path $casePath 'desktop.png'),
                  '--width', '1280', '--height', '760', '--theme', $theme)
    # No --data-dir: verify the portable.flag default and independence of the working directory.
    $process = Start-Process -FilePath $exe -ArgumentList $argsList -WorkingDirectory $casePath -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(60000)) { throw "软件包 $mode 测试超过 60 秒，PID=$($process.Id)" }
    if ($process.ExitCode -ne 0) { throw "软件包 $mode 测试失败，退出码=$($process.ExitCode)；检查 startup-error.log" }
    $result = Get-Content -Raw -LiteralPath (Join-Path $casePath 'smoke-result.json') | ConvertFrom-Json
    if ($result.status -ne 'COMPLETED' -or -not $result.engine_alive -or $result.trades -lt 1 -or
        -not $result.preview_ready -or $result.trade_rows -ne $result.trades) {
        throw "软件包 $mode 未完成交易流程"
    }
    if ($mode -eq 'equity' -and ($result.equity_entries -ne 2 -or $result.equity_rows -ne 2 -or
        $result.statistics.dividends_paid -ne 100 -or $result.available_positions.'600000.SH' -ne 200)) {
        throw '软件包权益教学未完成登记、到账和份额解锁'
    }
    $results += $result
}
$catalogPath = Join-Path $qaRoot 'catalog'
New-Item -ItemType Directory -Path $catalogPath | Out-Null
$catalogArgs = @('--catalog-smoke', '--screenshot', (Join-Path $catalogPath 'catalog.png'))
if ($Online) { $catalogArgs += '--catalog-refresh' }
$process = Start-Process -FilePath $exe -ArgumentList $catalogArgs -WorkingDirectory $catalogPath -WindowStyle Hidden -PassThru
if (-not $process.WaitForExit(110000)) {
    $process.Kill($true)
    throw '软件包证券目录验收超过 110 秒'
}
if ($process.ExitCode -ne 0) { throw '软件包证券目录验收失败，请检查 catalog-result.json' }
$catalog = Get-Content -Raw -LiteralPath (Join-Path $catalogPath 'catalog-result.json') | ConvertFrom-Json
if (-not $catalog.passed) { throw '软件包搜索/添加未完成' }
$qualityPath = Join-Path $qaRoot 'quality'
New-Item -ItemType Directory -Path $qualityPath | Out-Null
$process = Start-Process -FilePath $exe -ArgumentList @('--quality-smoke', '--screenshot', (Join-Path $qualityPath 'quality.png')) -WorkingDirectory $qualityPath -WindowStyle Hidden -PassThru
if (-not $process.WaitForExit(60000)) {
    $process.Kill($true)
    throw '软件包数据覆盖验收超过 60 秒'
}
if ($process.ExitCode -ne 0) { throw '软件包数据覆盖验收失败，请检查 quality-result.json' }
$quality = Get-Content -Raw -LiteralPath (Join-Path $qualityPath 'quality-result.json') | ConvertFrom-Json
if (-not $quality.passed -or $quality.quality.counts.missing_bars_total -ne 114) { throw '软件包缺口检查未完成' }
$rulesPath = Join-Path $qaRoot 'rules'
New-Item -ItemType Directory -Path $rulesPath | Out-Null
$process = Start-Process -FilePath $exe -ArgumentList @('--rules-smoke', '--screenshot', (Join-Path $rulesPath 'rules.png'), '--width', '1280', '--height', '760') -WorkingDirectory $rulesPath -WindowStyle Hidden -PassThru
if (-not $process.WaitForExit(60000)) {
    $process.Kill($true)
    throw '软件包证券规则验收超过 60 秒'
}
if ($process.ExitCode -ne 0) { throw '软件包证券规则验收失败，请检查 rules-result.json' }
$rules = Get-Content -Raw -LiteralPath (Join-Path $rulesPath 'rules-result.json') | ConvertFrom-Json
if (-not $rules.passed -or -not $rules.source_preserved) { throw '证券规则修订或原数据保护未通过' }
$operationsPath = Join-Path $qaRoot 'operations'
New-Item -ItemType Directory -Path $operationsPath | Out-Null
$process = Start-Process -FilePath $exe -ArgumentList @('--operations-smoke', '--screenshot', (Join-Path $operationsPath 'operations.png')) -WorkingDirectory $operationsPath -WindowStyle Hidden -PassThru
if (-not $process.WaitForExit(60000)) {
    $process.Kill($true)
    throw '软件包后台操作验收超过 60 秒'
}
if ($process.ExitCode -ne 0) { throw '软件包后台操作验收失败，请检查 operations-result.json' }
$operations = Get-Content -Raw -LiteralPath (Join-Path $operationsPath 'operations-result.json') | ConvertFrom-Json
if (-not $operations.passed) { throw '软件包导出、对比或录制整理未完成' }
$learningPath = Join-Path $qaRoot 'learning'
New-Item -ItemType Directory -Path $learningPath | Out-Null
$learningArgs = @('--learning-smoke', '--screenshot', (Join-Path $learningPath 'learning.png'), '--width', '1280', '--height', '760')
if ($Online) { $learningArgs += '--learning-online' }
$process = Start-Process -FilePath $exe -ArgumentList $learningArgs -WorkingDirectory $learningPath -WindowStyle Hidden -PassThru
if (-not $process.WaitForExit(60000)) {
    $process.Kill($true)
    throw '软件包四课学习流程超过 60 秒'
}
if ($process.ExitCode -ne 0) { throw '软件包四课学习流程失败，请检查 learning-result.json' }
$learning = Get-Content -Raw -LiteralPath (Join-Path $learningPath 'learning-result.json') | ConvertFrom-Json
if (-not $learning.passed -or $learning.course_count -ne 4) { throw '软件包未完成四课实际操作' }
$minute = $null
$historicalStatus = $null
$liveRules = $null
if ($Online) {
    $liveRulesPath = Join-Path $qaRoot 'live-rules'
    New-Item -ItemType Directory -Path $liveRulesPath | Out-Null
    $process = Start-Process -FilePath $exe -ArgumentList @('--live-rules-smoke', '--screenshot', (Join-Path $liveRulesPath 'live-rules.png'), '--width', '1280', '--height', '760') -WorkingDirectory $liveRulesPath -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(120000)) {
        $process.Kill($true)
        throw '软件包当日 ETF 规则账户验收超过 120 秒'
    }
    if ($process.ExitCode -ne 0) { throw '软件包当日 ETF 规则账户验收失败' }
    $liveRules = Get-Content -Raw -LiteralPath (Join-Path $liveRulesPath 'live-rules-result.json') | ConvertFrom-Json
    if (-not $liveRules.passed -or -not $liveRules.source_is_real) { throw '当日 ETF 资料与账户流程未通过' }
    $statusPath = Join-Path $qaRoot 'status'
    New-Item -ItemType Directory -Path $statusPath | Out-Null
    $process = Start-Process -FilePath $exe -ArgumentList @('--status-smoke', '--screenshot', (Join-Path $statusPath 'status.png'), '--width', '1280', '--height', '760') -WorkingDirectory $statusPath -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(90000)) {
        $process.Kill($true)
        throw '软件包真实历史状态验收超过 90 秒'
    }
    if ($process.ExitCode -ne 0) { throw '软件包历史状态验收失败，请检查 status-result.json' }
    $historicalStatus = Get-Content -Raw -LiteralPath (Join-Path $statusPath 'status-result.json') | ConvertFrom-Json
    if (-not $historicalStatus.passed -or -not $historicalStatus.source_is_real -or -not $historicalStatus.source_preserved) { throw '历史状态获取或原数据保护未通过' }
    $minutePath = Join-Path $qaRoot 'minute'
    New-Item -ItemType Directory -Path $minutePath | Out-Null
    $process = Start-Process -FilePath $exe -ArgumentList @('--minute-smoke', '--screenshot', (Join-Path $minutePath 'minute.png'), '--width', '1280', '--height', '760') -WorkingDirectory $minutePath -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(60000)) {
        $process.Kill($true)
        throw '软件包真实分钟下载验收超过 60 秒'
    }
    if ($process.ExitCode -ne 0) { throw '软件包真实分钟下载或回测失败，请检查 minute-result.json' }
    $minute = Get-Content -Raw -LiteralPath (Join-Path $minutePath 'minute-result.json') | ConvertFrom-Json
    if (-not $minute.passed -or -not $minute.source_is_real -or $minute.statistics.trades -lt 4) { throw '真实分钟数据验收未通过' }
    $process = Start-Process -FilePath $exe -ArgumentList @('--probe') -WorkingDirectory $qaRoot -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(30000) -or $process.ExitCode -ne 0) { throw '打包版公开行情探测失败' }
    $reportPath = Get-ChildItem -LiteralPath (Join-Path $qaRoot '解压 验收\AStock\data\reports') -Filter 'market-validation-*.json' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $market = Get-Content -Raw -LiteralPath $reportPath.FullName | ConvertFrom-Json
    if (-not $market.connectivity_passed) { throw '行情源未返回有效报价' }
    Copy-Item -LiteralPath $reportPath.FullName -Destination (Join-Path $qaRoot 'market-validation.json')
}
@{ archive_sha256=(Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash; cases=$results;
   portable_data_created=(Test-Path -LiteralPath (Join-Path $qaRoot '解压 验收\AStock\data'));
   catalog=$catalog; quality=$quality; rules=$rules; operations=$operations; learning=$learning; courses=$courses; minute=$minute; historical_status=$historicalStatus; live_rules=$liveRules; online_probe=[bool]$Online; one_hour_market_acceptance=$false } |
    ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $qaRoot 'release-result.json') -Encoding utf8
Write-Output $qaRoot
