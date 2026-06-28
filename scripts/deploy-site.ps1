#requires -Version 5.1
[CmdletBinding()]
param(
  [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$webDir = Join-Path $repoRoot "web"

if (-not (Test-Path $webDir)) { throw "web/ not found at $webDir" }

Push-Location $webDir
try {
  Write-Host "==> Installing dependencies (npm ci)" -ForegroundColor Cyan
  npm ci
  if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }

  if (-not $SkipTests) {
    Write-Host "==> Unit suite (vitest)" -ForegroundColor Cyan
    npm run test
    if ($LASTEXITCODE -ne 0) { throw "vitest failed - deploy preflight aborted" }

    Write-Host "==> Typecheck (tsc --noEmit)" -ForegroundColor Cyan
    npm run typecheck
    if ($LASTEXITCODE -ne 0) { throw "typecheck failed - deploy preflight aborted" }
  }

  Write-Host "==> Build (next build -> out/)" -ForegroundColor Cyan
  npm run build
  if ($LASTEXITCODE -ne 0) { throw "build failed" }
  if (-not (Test-Path (Join-Path $webDir "out/index.html"))) { throw "out/index.html missing - export did not produce a site" }

  Write-Host "==> Preflight complete. Push the private GitHub deploy repo; Cloudflare Pages Git integration deploys it." -ForegroundColor Green
}
finally {
  Pop-Location
}
