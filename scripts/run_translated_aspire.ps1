param(
    [ValidateSet('scalpel', 'scissor', 'love_retractor', 'kelly', 'scalpel_type2')]
    [string]$Target = 'scissor',
    [ValidateSet('rfdetr', 'sam3')][string]$Perception = 'rfdetr',
    [ValidateSet('run', 'evaluate', 'refine', 'search')][string]$Command = 'run',
    [Parameter(Mandatory = $true)][string]$Out,
    [int]$Seed = 501,
    [ValidateSet('dev', 'eval')][string]$Split = 'dev',
    [ValidateRange(1, 10)][int]$Rounds = 3,
    [ValidateRange(1, 16)][int]$Candidates = 8,
    [ValidateRange(1, 10)][int]$Iterations = 3,
    [string]$Model = 'claude-secondary/claude-opus-4-6',
    [string]$IsaacPython = 'C:\isaac-sim-450\python.bat',
    [switch]$Gui
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $repoRoot
try {
    if (-not (Test-Path -LiteralPath $IsaacPython)) { throw "Missing Isaac Sim Python launcher: $IsaacPython" }
    if (Test-Path -LiteralPath $Out) { throw 'Use a new output directory to preserve existing trials.' }
    $protocolPath = if ($Command -eq 'search') { "configs\aspire\search\$Target-$Perception.json" } else { "configs\aspire\translated\$Target-$Perception.json" }
    $protocol = Get-Content -LiteralPath $protocolPath -Raw | ConvertFrom-Json
    $serviceUrl = if ($Perception -eq 'sam3') { $protocol.task.sam3_url } else { $protocol.task.rfdetr_url }
    try {
        $health = Invoke-RestMethod -Uri "$serviceUrl/health" -TimeoutSec 10
        if (-not $health.ready) { throw 'Service is not ready.' }
    } catch {
        throw "Start the $Perception perception service at $serviceUrl before running the skill. See docs/ASPIRE_TRANSLATION.md. $($_.Exception.Message)"
    }
    $trialArgs = @('scripts\aspire.py', $Command, '--python', $IsaacPython,
        '--config', $protocolPath, '--code', "examples\aspire\translated\$Target.py", '--out', $Out)
    if ($Command -eq 'run') { $trialArgs += @('--seed', $Seed) }
    if ($Command -eq 'evaluate') { $trialArgs += @('--split', $Split) }
    if ($Command -in @('refine', 'search')) {
        $trialArgs += @('--model', $Model, '--base-url', 'https://cgv.cs.nthu.edu.tw:9128/v1',
            '--api-key-env', 'API_KEY', '--env-file', '.env',
            '--max-output-tokens', '128000', '--development-only')
        if ($Command -eq 'search') { $trialArgs += @('--candidates', $Candidates, '--iterations', $Iterations) }
        else { $trialArgs += @('--rounds', $Rounds) }
    }
    if ($Gui) { $trialArgs += '--gui' }
    & $IsaacPython @trialArgs
    if ($LASTEXITCODE -ne 0) { throw "ASPIRE exited with code $LASTEXITCODE; inspect the trial result and worker log." }
} finally {
    Pop-Location
}
