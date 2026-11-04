param(
    [Parameter(Mandatory=$true)][string]$Out,
    [Parameter(Mandatory=$true)][int]$MaxTotalRequests,
    [string]$BaseUrl,
    [ValidateRange(-1,2)][int]$PauseAfterRound = -1,
    [ValidateRange(-1,2)][int]$EvaluateAfterRound = -1,
    [ValidateRange(0,100)][int]$HeldoutTrials = 0,
    [switch]$ReviseHeldoutLimit,
    [switch]$RecoverInterrupted,
    [switch]$Background
)
$ErrorActionPreference = 'Stop'
if ($PauseAfterRound -ge 0 -and $EvaluateAfterRound -ge 0) {
    throw 'PauseAfterRound and EvaluateAfterRound cannot be combined.'
}
if ($PauseAfterRound -ge 0 -and $HeldoutTrials -gt 0) {
    throw 'PauseAfterRound and HeldoutTrials cannot be combined.'
}
if ($ReviseHeldoutLimit -and $HeldoutTrials -eq 0) {
    throw 'ReviseHeldoutLimit requires an explicit HeldoutTrials count.'
}
$repo = Split-Path -Parent $PSScriptRoot
$outPath = (Resolve-Path -LiteralPath $Out).Path
$logsRoot = [IO.Path]::GetFullPath((Join-Path $repo 'logs')) + [IO.Path]::DirectorySeparatorChar
if (-not $outPath.StartsWith($logsRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Output must be an existing campaign under repository logs.'
}
$launch = Get-Content -LiteralPath (Join-Path $outPath 'launch.json') -Raw | ConvertFrom-Json
if (-not $BaseUrl) { $BaseUrl = $launch.base_url }
if ($BaseUrl -notin @('https://cgv.cs.nthu.edu.tw:9128/v1', 'https://llm.igvi.cs.nthu.edu.tw/v1')) {
    throw 'Use one of the user-authorized NTHU origins.'
}
$campaignState = Get-Content -LiteralPath (Join-Path $outPath 'state.json') -Raw | ConvertFrom-Json
if ($campaignState.status -eq 'stopped_backend_switch') {
    throw 'This campaign was retired after the user changed perception backend. Start a fresh campaign with the new configuration.'
}
$used = 0
foreach ($ledger in (Get-ChildItem -LiteralPath $outPath -Directory -Filter 'provider_*')) {
    $report = Get-Content -LiteralPath (Join-Path $ledger.FullName 'report.json') -Raw | ConvertFrom-Json
    $used += [int]$report.requests
}
$supervisorPath = Join-Path $outPath 'supervisor.json'
if (Test-Path -LiteralPath $supervisorPath) {
    $supervisor = Get-Content -LiteralPath $supervisorPath -Raw | ConvertFrom-Json
    if ($supervisor.status -eq 'running' -and (Get-Process -Id $supervisor.pid -ErrorAction SilentlyContinue)) {
        throw 'The previous supervisor is still running.'
    }
}
$prior = [int]$launch.prior_requests + $used
$remaining = $MaxTotalRequests - $prior
if ($remaining -lt 1) { throw 'No authorized requests remain.' }
if ($Background) {
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss_fff'
    $stdout = Join-Path $outPath "supervisor_$stamp.stdout.log"
    $stderr = Join-Path $outPath "supervisor_$stamp.stderr.log"
    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -Out "' + $outPath + '" -MaxTotalRequests ' + $MaxTotalRequests + ' -BaseUrl "' + $BaseUrl + '"'
    if ($PauseAfterRound -ge 0) { $arguments += ' -PauseAfterRound ' + $PauseAfterRound }
    if ($EvaluateAfterRound -ge 0) { $arguments += ' -EvaluateAfterRound ' + $EvaluateAfterRound }
    if ($HeldoutTrials -gt 0) { $arguments += ' -HeldoutTrials ' + $HeldoutTrials }
    if ($ReviseHeldoutLimit) { $arguments += ' -ReviseHeldoutLimit' }
    if ($RecoverInterrupted) { $arguments += ' -RecoverInterrupted' }
    $process = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList $arguments `
        -WorkingDirectory $repo -WindowStyle Hidden -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr -PassThru
    [pscustomobject]@{pid=$process.Id;prior_requests=$prior;remaining=$remaining;stdout=$stdout;stderr=$stderr} | ConvertTo-Json
    exit 0
}
Set-Location -LiteralPath $repo
$runnerArguments = @('scripts/run_full_aspire.py', '--out', $outPath, '--resume',
    '--config', $launch.config, '--base-url', $BaseUrl, '--model', $launch.model,
    '--prior-requests', $prior, '--request-budget', $remaining, '--max-total-requests', $MaxTotalRequests)
if ($PauseAfterRound -ge 0) { $runnerArguments += @('--pause-after-round', $PauseAfterRound) }
if ($EvaluateAfterRound -ge 0) { $runnerArguments += @('--evaluate-after-round', $EvaluateAfterRound) }
if ($HeldoutTrials -gt 0) { $runnerArguments += @('--heldout-trials', $HeldoutTrials) }
if ($ReviseHeldoutLimit) { $runnerArguments += '--revise-heldout-limit' }
if ($RecoverInterrupted) { $runnerArguments += '--recover-interrupted' }
if ($launch.headless) { $runnerArguments += '--headless' }
if ($launch.python) { $runnerArguments += @('--python', $launch.python) }
& $launch.python @runnerArguments
exit $LASTEXITCODE
