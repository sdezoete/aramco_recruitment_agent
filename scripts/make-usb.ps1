<#
.SYNOPSIS
  DEV MACHINE. Builds usb_x_y_z\recruitment-agent\ (+ DEPLOY-NOTES.md) for the air-gapped server.

.DESCRIPTION
  Version comes from __version__ in app\__init__.py (1.2.3 -> usb_1_2_3).
  Refuses if DEPLOY-NOTES.md has no "## <version>" section, if wheels\ is missing or holds non-.whl
  files, or if the target folder already exists. Warns on uncommitted changes or a missing tag.
  Ships git-tracked files only (minus the exclusions below), plus wheels\ and VERSION.txt.
  Never ships .env, .venv, logs, certs or local data.
#>
param([switch]$AllowNoGit)
$ErrorActionPreference = 'Stop'
$root    = Split-Path -Parent $PSScriptRoot
$appName = 'recruitment-agent'
$exclude = @('^\.env$', '^\.venv/', '^wheels/', '^usb_', '^logs/', '^certs/', '^work/', '^data/private/',
             '^docs_other_project/', '^\.claude/',
             '^scripts/seed_dev_db\.py$', '^sql/01_dev_')   # dev-only: fake data + dev copy of server tables

# Version
$init = Get-Content (Join-Path $root 'app\__init__.py') -Raw
$m = [regex]::Match($init, '__version__\s*=\s*"(\d+\.\d+\.\d+)"')
if (-not $m.Success) { throw "__version__ not found in app\__init__.py" }
$version = $m.Groups[1].Value
$usbDir  = Join-Path $root ('usb_' + $version.Replace('.', '_'))
$target  = Join-Path $usbDir $appName

# DEPLOY-NOTES section
$notes = Join-Path $root 'DEPLOY-NOTES.md'
if (-not (Select-String -Path $notes -Pattern ('^##\s+' + [regex]::Escape($version) + '\s*$') -Quiet)) {
    throw "DEPLOY-NOTES.md has no '## $version' section. Add one (write 'Server settings: none.' if there are none)."
}

# Wheels
$wheels = Join-Path $root 'wheels'
if (-not (Test-Path $wheels) -or -not (Get-ChildItem $wheels -Filter *.whl)) { throw "wheels\ is empty. Run scripts\1-build-wheels.ps1 first." }
$bad = Get-ChildItem $wheels -File | Where-Object { $_.Extension -ne '.whl' }
if ($bad) { throw ("Non-wheel files in wheels\: " + ($bad.Name -join ', ')) }

if (Test-Path $target) { throw "$target already exists. Bump the version or delete that folder deliberately." }

# File list
$commit = 'no-git'
Push-Location $root
try {
    $isGit = Test-Path (Join-Path $root '.git')
    if ($isGit) {
        $files = @(git ls-files)
        if (git status --porcelain) { Write-Warning "Uncommitted changes. A release should come from a clean, tagged commit." }
        $commit = (git rev-parse --short HEAD)
        $tags = @(git tag --points-at HEAD)
        if ($tags -notcontains "v$version") { Write-Warning "HEAD is not tagged v$version." }
    } elseif ($AllowNoGit) {
        Write-Warning "Not a git repo: using the fallback include list."
        $files = @('app','static','scripts','data','docs','requirements.txt','.env.example','DEPLOY.md','DEPLOY-NOTES.md','CLAUDE.md','README.md') |
            Where-Object { Test-Path $_ } |
            ForEach-Object { if (Test-Path $_ -PathType Container) { Get-ChildItem $_ -Recurse -File | Where-Object { $_.FullName -notmatch '__pycache__' } | Resolve-Path -Relative } else { $_ } } |
            ForEach-Object { ($_ -replace '^\.\\', '') -replace '\\', '/' }
    } else {
        throw "Not a git repository. Run 'git init' and commit, or pass -AllowNoGit."
    }
} finally { Pop-Location }

$files = $files | Where-Object { $f = $_; -not ($exclude | Where-Object { $f -match $_ }) }

# Copy
New-Item -ItemType Directory $target -Force | Out-Null
foreach ($f in $files) {
    $src = Join-Path $root $f
    if (-not (Test-Path $src -PathType Leaf)) { continue }
    $dst = Join-Path $target $f
    New-Item -ItemType Directory (Split-Path $dst -Parent) -Force | Out-Null
    Copy-Item $src $dst
}
Copy-Item $wheels (Join-Path $target 'wheels') -Recurse
"$version`r`ncommit $commit`r`nbuilt $(Get-Date -Format 'yyyy-MM-dd HH:mm')" | Set-Content (Join-Path $target 'VERSION.txt') -Encoding ASCII
Copy-Item $notes (Join-Path $usbDir 'DEPLOY-NOTES.md')

if (Test-Path (Join-Path $target '.env')) { throw "Safety check failed: .env ended up in the package." }

$whlCount = (Get-ChildItem (Join-Path $target 'wheels') -Filter *.whl).Count
Write-Host ""
Write-Host "Release $version built: $usbDir" -ForegroundColor Green
Write-Host ("  {0} files, {1} wheels, commit {2}" -f $files.Count, $whlCount, $commit)
Write-Host "  Copy '$appName' and DEPLOY-NOTES.md (plus the Python and ODBC installers if needed) to the USB stick."
