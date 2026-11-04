param(
    [Parameter(Mandatory=$true)][string]$Checkpoint,
    [ValidateSet('nano','small','medium','large')][string]$Model = 'small',
    [string]$Device = 'cuda:0',
    [int]$Port = 8115,
    [double]$Threshold = 0.5
)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$detectorPython = Join-Path $repoRoot '.venv-rfdetr\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $detectorPython)) {
    throw 'RF-DETR environment missing. Run .\RUNME.ps1 -Mode rfdetr-setup first.'
}
$checkpointPath = (Resolve-Path -LiteralPath $Checkpoint).Path
Push-Location -LiteralPath $repoRoot
try {
    & $detectorPython -u scripts\serve_rfdetr.py --checkpoint $checkpointPath --model $Model --device $Device --port $Port --threshold $Threshold
    if ($LASTEXITCODE -ne 0) { throw 'RF-DETR server failed. See docs/ASPIRE_RFDETR.md.' }
} finally {
    Pop-Location
}
