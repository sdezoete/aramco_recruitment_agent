<#
.SYNOPSIS
  SERVER (no internet). Creates .venv, installs from wheels\, and creates .env on first install.

.DESCRIPTION
  - Finds Python 3.11 x64 (py launcher, then common install paths, then PATH).
  - Creates .venv if it is missing or not 3.11.
  - pip install --no-index --find-links wheels -r requirements.txt, then pip check.
  - If .env does not exist: copies .env.example and sets PRODUCTION=True. Never overwrites an existing .env.
  - Lists the installed SQL Server ODBC drivers.
#>
$ErrorActionPreference = 'Stop'
$root   = Split-Path -Parent $PSScriptRoot
$wheels = Join-Path $root 'wheels'
$req    = Join-Path $root 'requirements.txt'
$venv   = Join-Path $root '.venv'
$vpy    = Join-Path $venv 'Scripts\python.exe'

function Test-Py311([string]$exe, [string[]]$pre = @()) {
    try {
        $out = & $exe @pre -c "import sys,struct;print('%d.%d %d' % (sys.version_info[0], sys.version_info[1], struct.calcsize('P')*8))" 2>$null
        return ($out -eq '3.11 64')
    } catch { return $false }
}

# 1. Find Python 3.11 x64.
$basePy = $null; $basePre = @()
if ((Get-Command py -ErrorAction SilentlyContinue) -and (Test-Py311 'py' @('-3.11'))) { $basePy = 'py'; $basePre = @('-3.11') }
if (-not $basePy) {
    $candidates = @(
        "$env:ProgramFiles\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        'C:\Python311\python.exe'
    )
    foreach ($c in $candidates) { if ((Test-Path $c) -and (Test-Py311 $c)) { $basePy = $c; break } }
}
if (-not $basePy -and (Get-Command python -ErrorAction SilentlyContinue) -and (Test-Py311 'python')) { $basePy = 'python' }
if (-not $basePy) { throw "Python 3.11 x64 not found. Install python-3.11.x-amd64.exe from the USB stick." }
Write-Host "Python 3.11 x64: $basePy $basePre"

# 2. venv
if ((Test-Path $vpy) -and -not (Test-Py311 $vpy)) {
    Write-Warning ".venv is not Python 3.11 x64; recreating it."
    Remove-Item $venv -Recurse -Force
}
if (-not (Test-Path $vpy)) {
    & $basePy @basePre -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "Creating .venv failed." }
}

# 3. Offline install
if (-not (Test-Path $wheels)) { throw "wheels\ folder missing; the release package is incomplete." }
& $vpy -m pip install --no-index --find-links $wheels -r $req
if ($LASTEXITCODE -ne 0) { throw "Offline install failed." }
& $vpy -m pip check
if ($LASTEXITCODE -ne 0) { throw "pip check reported problems." }

# 4. First-run .env (never overwrite)
$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) {
    $text = [IO.File]::ReadAllText((Join-Path $root '.env.example'))
    $text = [regex]::Replace($text, '(?m)^PRODUCTION=.*$', 'PRODUCTION=True')
    [IO.File]::WriteAllText($envFile, $text, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Created .env with PRODUCTION=True. Fill in DB_*, LLM_*, HOST, PORT and TLS_* before starting." -ForegroundColor Yellow
} else {
    Write-Host ".env exists, left unchanged."
}

# 5. Checks
$drivers = @(Get-OdbcDriver -Platform 64-bit | Where-Object { $_.Name -like 'ODBC Driver * for SQL Server' } | ForEach-Object { $_.Name })
if ($drivers.Count -eq 0) { Write-Warning "No 'ODBC Driver xx for SQL Server' installed. Install msodbcsql (server prerequisite)." }
else { Write-Host ("ODBC drivers: " + ($drivers -join ', ')) }
$verFile = Join-Path $root 'VERSION.txt'
if (Test-Path $verFile) { Write-Host ("Version: " + (Get-Content $verFile -TotalCount 1)) }
Write-Host "Install OK." -ForegroundColor Green
