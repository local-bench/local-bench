#requires -Version 5.1
[CmdletBinding()]
param(
  [switch]$DataOnly,
  [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$webDir = Join-Path $repoRoot "web"
$venvPython = Join-Path $repoRoot "cli\.venv\Scripts\python.exe"

if (-not (Test-Path $webDir)) { throw "web/ not found at $webDir" }
if (-not (Test-Path $venvPython)) {
  throw "CLI venv python not found at $venvPython - create it first."
}

Push-Location $repoRoot
try {
  Write-Host "==> Rebuilding scorer board" -ForegroundColor Cyan
  & $venvPython -m localbench.cli board --no-check-parity
  if ($LASTEXITCODE -ne 0) { throw "localbench board failed" }

  Write-Host "==> Regenerating site data" -ForegroundColor Cyan
  & $venvPython (Join-Path $webDir "build_data.py")
  if ($LASTEXITCODE -ne 0) { throw "build_data.py failed" }

  Write-Host "==> Checking site data freshness" -ForegroundColor Cyan
  & $venvPython (Join-Path $webDir "check_data_freshness.py")
  if ($LASTEXITCODE -ne 0) { throw "site data freshness check failed" }

  if (-not $SkipTests) {
    Write-Host "==> Site-board parity" -ForegroundColor Cyan
    & $venvPython -m pytest cli/tests/test_site_parity.py -q
    if ($LASTEXITCODE -ne 0) { throw "site-board parity failed" }
  }
}
finally {
  Pop-Location
}

if ($DataOnly) {
  Write-Host "==> Site data refreshed." -ForegroundColor Green
  return
}

Push-Location $webDir
try {
  if (-not $SkipTests) {
    Write-Host "==> Unit suite" -ForegroundColor Cyan
    npm run test
    if ($LASTEXITCODE -ne 0) { throw "npm run test failed" }

    Write-Host "==> Typecheck" -ForegroundColor Cyan
    npm run typecheck
    if ($LASTEXITCODE -ne 0) { throw "npm run typecheck failed" }
  }

  Write-Host "==> Static build" -ForegroundColor Cyan
  npm run build
  if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
  if (-not (Test-Path (Join-Path $webDir "out\index.html"))) {
    throw "out/index.html missing - static export did not produce a site"
  }
}
finally {
  Pop-Location
}

Write-Host "==> Site data refreshed and verified." -ForegroundColor Green
