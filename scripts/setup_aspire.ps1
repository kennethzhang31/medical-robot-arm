param([string]$IsaacPython = 'C:\isaac-sim-450\python.bat')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $taskRoot
try {
    if (-not (Test-Path -LiteralPath $IsaacPython)) { throw "Isaac Sim 4.5 Python launcher missing: $IsaacPython" }
    git submodule update --init third_party/ASPIRE
    if ($LASTEXITCODE -ne 0) { throw 'ASPIRE submodule initialization failed' }
    $aspirePatch = Join-Path $taskRoot 'patches/aspire-local.patch'
    $ErrorActionPreference = 'Continue'
    git -C third_party/ASPIRE apply --reverse --check $aspirePatch 2>$null
    $patchAlreadyApplied = $LASTEXITCODE -eq 0
    $ErrorActionPreference = 'Stop'
    if (-not $patchAlreadyApplied) {
        git -C third_party/ASPIRE apply --check $aspirePatch
        if ($LASTEXITCODE -ne 0) { throw 'ASPIRE local patch conflicts with the checkout' }
        git -C third_party/ASPIRE apply $aspirePatch
        if ($LASTEXITCODE -ne 0) { throw 'ASPIRE local patch failed' }
    }
    if (-not (Test-Path -LiteralPath '.local/IsaacLab')) {
        git clone --depth 1 --branch v2.1.1 https://github.com/isaac-sim/IsaacLab.git .local/IsaacLab
        if ($LASTEXITCODE -ne 0) { throw 'IsaacLab download failed' }
    }
    & $IsaacPython -m pip install --target .local/aspire-python --no-deps --no-build-isolation -r requirements/aspire-isaac45.txt
    if ($LASTEXITCODE -ne 0) { throw 'Local dependency installation failed' }
    & $IsaacPython scripts/aspire.py preflight --python $IsaacPython
    if ($LASTEXITCODE -ne 0) { throw 'Preflight failed' }
} finally { Pop-Location }
