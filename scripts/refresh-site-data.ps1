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

  # A board re-cut changes the board sha. Publication (scripts/publish-board.ps1) validates the
  # committed board against the launch-freeze pin and refuses to re-cut, so a stale pin here
  # means the re-locked board cannot ship until the pin is updated and committed with it.
  $freezePath = Join-Path $webDir "components\launch-freeze.ts"
  $newBoardSha = (Get-FileHash -Algorithm SHA256 -Path (Join-Path $repoRoot "cli\runs\board\board_v2.json")).Hash.ToLowerInvariant()
  $freezePin = (Select-String -Path $freezePath -Pattern 'boardSha256:\s*"([0-9a-f]{64})"').Matches[0].Groups[1].Value
  if ($freezePin -ne $newBoardSha) {
    Write-Host "==> Board re-cut: new sha $newBoardSha" -ForegroundColor Yellow
    Write-Host "    launch-freeze pin is now stale. Re-pin web/components/launch-freeze.ts boardSha256" -ForegroundColor Yellow
    Write-Host "    and commit board + manifest + pin + data together BEFORE scripts/publish-board.ps1." -ForegroundColor Yellow
  }

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
