param([string]$Device = 'cuda:0', [int]$Port = 8114)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$samPython = Join-Path $repoRoot '.local\sam3-python\python.exe'
$samHf = Join-Path $repoRoot '.local\sam3-python\Scripts\hf.exe'
if (-not (Test-Path -LiteralPath $samPython)) {
    throw 'SAM3 environment missing. See docs/SAM3_WINDOWS.md for installation.'
}
Set-Location -LiteralPath $repoRoot
Write-Host 'Native Windows SAM3: separate environment from Isaac Sim.'
& $samPython -c 'from huggingface_hub import get_token; raise SystemExit(0 if get_token() else 1)'
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Authenticate locally below. First request access at https://huggingface.co/facebook/sam3'
    & $samHf auth login
    if ($LASTEXITCODE -ne 0) { throw 'Hugging Face authentication did not complete.' }
}
& $samPython -u scripts\serve_sam3_windows.py --device $Device --port $Port
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Server stopped. Check model access, CUDA, and the error above.'
}
