<#
.SYNOPSIS
  DEV MACHINE ONLY (needs internet). Builds wheels\ for the air-gapped server and verifies it.

.DESCRIPTION
  - Uses .venv's Python, which must be 3.11 x64 (the same as the server).
  - pip wheel resolves requirements.txt including transitive deps. Packages that only exist as
    source archives (.tar.gz/.zip) are built into .whl files here.
  - Fails if wheels\ contains anything other than .whl, or a wheel for the wrong platform.
  - Verifies an offline install into a fresh temporary venv, followed by pip check.
#>
param(
    [string[]]$SmokeImports = @()
)
$ErrorActionPreference = 'Stop'
$root   = Split-Path -Parent $PSScriptRoot
$py     = Join-Path $root '.venv\Scripts\python.exe'
$req    = Join-Path $root 'requirements.txt'
$wheels = Join-Path $root 'wheels'

if (-not (Test-Path $py)) { throw "No .venv found at $py. Create it with Python 3.11 x64 first." }
$info = & $py -c "import sys,struct;print('%d.%d %d' % (sys.version_info[0], sys.version_info[1], struct.calcsize('P')*8))"
if ($info -ne '3.11 64') { throw "The .venv Python must be 3.11 64-bit to match the server (found: $info)." }

# Warn about unpinned requirements (the standard requires == pins before a release).
$unpinned = Get-Content $req | Where-Object { $_ -match '^\s*[A-Za-z0-9]' -and $_ -notmatch '==' }
if ($unpinned) { Write-Warning ("Unpinned requirements (pin with == before a release): " + ($unpinned -join ', ')) }

# Fresh wheels folder.
if (Test-Path $wheels) { Remove-Item (Join-Path $wheels '*') -Recurse -Force }
else { New-Item -ItemType Directory $wheels | Out-Null }

Write-Host "Building wheels into $wheels ..."
& $py -m pip wheel --prefer-binary -r $req -w $wheels
if ($LASTEXITCODE -ne 0) { throw "pip wheel failed." }

# Only .whl allowed.
$bad = Get-ChildItem $wheels -File | Where-Object { $_.Extension -ne '.whl' }
if ($bad) { throw ("Non-wheel files in wheels\: " + ($bad.Name -join ', ')) }

# Platform / ABI check: name-version(-build)?-pytag-abitag-plattag.whl
$wrong = @()
foreach ($w in Get-ChildItem $wheels -Filter *.whl) {
    $parts = $w.BaseName.Split('-')
    $plat = $parts[-1]; $abi = $parts[-2]; $pyt = $parts[-3]
    $platOk = ($plat -eq 'any') -or ($plat -split '\.' -contains 'win_amd64')
    $abiOk  = ($abi -eq 'none') -or ($abi -eq 'abi3') -or ($abi -eq 'cp311') -or ($pyt -split '\.' -contains 'cp311')
    if (-not ($platOk -and $abiOk)) { $wrong += $w.Name }
}
if ($wrong) { throw ("Wheels not compatible with win_amd64 / cp311: " + ($wrong -join ', ')) }

# Offline install into a clean temporary venv.
$tmp = Join-Path $env:TEMP ("wheelcheck_" + [guid]::NewGuid().ToString('N'))
Write-Host "Verifying offline install in $tmp ..."
& $py -m venv $tmp
$tpy = Join-Path $tmp 'Scripts\python.exe'
try {
    & $tpy -m pip install --no-index --find-links $wheels -r $req --quiet
    if ($LASTEXITCODE -ne 0) { throw "Offline install from wheels\ failed." }
    & $tpy -m pip check
    if ($LASTEXITCODE -ne 0) { throw "pip check reported problems." }
    foreach ($m in $SmokeImports) {
        & $tpy -c "import $m"
        if ($LASTEXITCODE -ne 0) { throw "Import smoke test failed: $m" }
    }
} finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

$list = Get-ChildItem $wheels -Filter *.whl | Sort-Object Name
Write-Host ""
Write-Host ("OK: {0} wheels, offline install + pip check clean." -f $list.Count) -ForegroundColor Green
$list | ForEach-Object { Write-Host ("  " + $_.Name) }
