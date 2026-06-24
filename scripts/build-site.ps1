#requires -Version 5.1
<#
.SYNOPSIS
  Rebuild the local-bench site data from data_sources.json, then verify it builds.

.DESCRIPTION
  The single "I changed/added a model, refresh the site" command. It:
    1. Regenerates web/public/data/* from web/data_sources.json (+ model_catalog.json)
       and the frozen board_v1.json, via the CLI venv (web/build_data.py, which also
       refreshes the experimental agentic.json column).
    2. Unless -DataOnly, runs the gates (vitest + typecheck) and the static build, so you
       know the site is green before you commit web/public/data or deploy.

  It deliberately does NOT:
    - re-cut the immutable board (that is a conscious `localbench board` re-lock), or
    - deploy (that is scripts/deploy-site.ps1, which ships the COMMITTED data).

.EXAMPLE
  .\scripts\build-site.ps1            # regenerate data + vitest + typecheck + static build
  .\scripts\build-site.ps1 -DataOnly  # just regenerate data (the dev server hot-reloads it)
  .\scripts\build-site.ps1 -SkipTests # regenerate data + build, skip the gates
#>
[CmdletBinding()]
param(
  [switch]$DataOnly,
  [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

# Repo root = parent of this script's folder.
$repoRoot = Split-Path -Parent $PSScriptRoot
$webDir = Join-Path $repoRoot "web"
$venvPython = Join-Path $repoRoot "cli\.venv\Scripts\python.exe"

if (-not (Test-Path $webDir)) { throw "web/ not found at $webDir" }
if (-not (Test-Path $venvPython)) {
  throw "CLI venv python not found at $venvPython - create it first (see docs/REPRODUCE.md)."
}

Write-Host "==> Regenerating site data (web/build_data.py -> web/public/data)" -ForegroundColor Cyan
Push-Location $repoRoot
try {
  & $venvPython (Join-Path $webDir "build_data.py")
  if ($LASTEXITCODE -ne 0) { throw "build_data.py failed" }
}
finally {
  Pop-Location
}

if ($DataOnly) {
  Write-Host "==> Data regenerated (-DataOnly). The dev server hot-reloads it; skipping build." -ForegroundColor Green
  return
}

Push-Location $webDir
try {
  if (-not $SkipTests) {
    Write-Host "==> Unit suite (vitest)" -ForegroundColor Cyan
    npm run test
    if ($LASTEXITCODE -ne 0) { throw "vitest failed" }

    Write-Host "==> Typecheck (tsc --noEmit)" -ForegroundColor Cyan
    npx tsc --noEmit
    if ($LASTEXITCODE -ne 0) { throw "typecheck failed" }
  }

  Write-Host "==> Build (next build -> out/)" -ForegroundColor Cyan
  npm run build
  if ($LASTEXITCODE -ne 0) { throw "next build failed" }
  if (-not (Test-Path (Join-Path $webDir "out\index.html"))) {
    throw "out/index.html missing - static export did not produce a site"
  }

  Write-Host "==> Site rebuilt and green. Review + commit web/public/data, then deploy with scripts/deploy-site.ps1." -ForegroundColor Green
}
finally {
  Pop-Location
}
