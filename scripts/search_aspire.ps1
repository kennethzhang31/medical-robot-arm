param(
    [ValidateSet('scalpel', 'scissor', 'love_retractor', 'kelly', 'scalpel_type2')]
    [string]$Target = 'scissor',
    [ValidateSet('sam3', 'rfdetr')][string]$Perception = 'sam3',
    [ValidateRange(1, 16)][int]$Candidates = 8,
    [ValidateRange(1, 10)][int]$Iterations = 3,
    [string]$Model = 'claude-secondary/claude-opus-4-6',
    [string]$Out = '',
    [string]$IsaacPython = 'C:\isaac-sim-450\python.bat',
    [switch]$FinalEvaluation,
    [switch]$Plan,
    [switch]$Gui
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $repoRoot
try {
    if (-not $Out) {
        $taskTimestamp = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, 'Taipei Standard Time').ToString('yyyyMMdd_HHmmss')
        $Out = "logs\search_${Target}_$taskTimestamp"
    }
    if (-not $Plan -and (Test-Path -LiteralPath $Out)) { throw 'Use a new output directory.' }
    $searchArgs = @('scripts\aspire.py', 'search', '--python', $IsaacPython,
        '--config', "configs\aspire\search\$Target-$Perception.json",
        '--code', "examples\aspire\translated\$Target.py", '--out', $Out,
        '--candidates', $Candidates, '--iterations', $Iterations,
        '--model', $Model, '--base-url', 'https://cgv.cs.nthu.edu.tw:9128/v1',
        '--api-key-env', 'API_KEY', '--env-file', '.env', '--max-output-tokens', '128000')
    if (-not $FinalEvaluation) { $searchArgs += '--development-only' }
    if ($Plan) { $searchArgs += '--plan' }
    if ($Gui) { $searchArgs += '--gui' }
    & $IsaacPython @searchArgs
    if ($LASTEXITCODE -ne 0) { throw "ASPIRE search exited with code $LASTEXITCODE; inspect report.json." }
} finally {
    Pop-Location
}
