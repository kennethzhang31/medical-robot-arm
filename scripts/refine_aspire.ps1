param(
    [string]$Out = 'logs\opus_development_01',
    [string]$Model = 'claude-secondary/claude-opus-4-6',
    [int]$Rounds = 3,
    [string]$ReasoningEffort = '',
    [int]$MaxOutputTokens = 128000,
    [switch]$Gui
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    $refinementArgs = @(
        'scripts\aspire.py', 'refine',
        '--config', 'configs\aspire\pilot-scissor.json',
        '--code', 'examples\aspire\visual_pick_place.py',
        '--base-url', 'https://cgv.cs.nthu.edu.tw:9128/v1',
        '--model', $Model,
        '--max-output-tokens', $MaxOutputTokens,
        '--api-key-env', 'API_KEY', '--env-file', '.env',
        '--development-only', '--rounds', $Rounds, '--out', $Out
    )
    if ($ReasoningEffort) { $refinementArgs += @('--reasoning-effort', $ReasoningEffort) }
    if ($Gui) { $refinementArgs += '--gui' }
    & C:\isaac-sim-450\python.bat @refinementArgs
    if ($LASTEXITCODE -ne 0) { throw "ASPIRE refinement exited with code $LASTEXITCODE" }
} finally {
    Pop-Location
}
