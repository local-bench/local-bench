#requires -Version 5.1
<#
.SYNOPSIS
  Build and deploy the local-bench static board to Cloudflare Pages (local-bench.ai).

.DESCRIPTION
  Path A direct-upload deploy (see docs/deploy/cloudflare-pages.md). Gates on the
  unit suite + typecheck, builds the Next.js static export, then uploads web/out
  via Wrangler. Deploys the COMMITTED web/public/data — does not regenerate data.

.PREREQUISITES
  $env:CLOUDFLARE_ACCOUNT_ID and $env:CLOUDFLARE_API_TOKEN must be set
  (scoped "Edit Cloudflare Pages" token). See the runbook for how to create them.

.EXAMPLE
  .\scripts\deploy-site.ps1
  .\scripts\deploy-site.ps1 -SkipTests   # build + deploy only (not recommended)
#>
[CmdletBinding()]
param(
  [string]$ProjectName = "local-bench",
  [string]$Branch = "main",
  [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

# Repo root = parent of this script's folder; web/ is the Next.js app.
$repoRoot = Split-Path -Parent $PSScriptRoot
$webDir = Join-Path $repoRoot "web"

if (-not (Test-Path $webDir)) { throw "web/ not found at $webDir" }
if (-not $env:CLOUDFLARE_API_TOKEN) { throw "CLOUDFLARE_API_TOKEN is not set (see docs/deploy/cloudflare-pages.md)." }
if (-not $env:CLOUDFLARE_ACCOUNT_ID) { throw "CLOUDFLARE_ACCOUNT_ID is not set (see docs/deploy/cloudflare-pages.md)." }

Push-Location $webDir
try {
  Write-Host "==> Installing dependencies (npm ci)" -ForegroundColor Cyan
  npm ci
  if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }

  if (-not $SkipTests) {
    Write-Host "==> Unit suite (vitest)" -ForegroundColor Cyan
    npm run test
    if ($LASTEXITCODE -ne 0) { throw "vitest failed - deploy aborted" }

    Write-Host "==> Typecheck (tsc --noEmit)" -ForegroundColor Cyan
    npx tsc --noEmit
    if ($LASTEXITCODE -ne 0) { throw "typecheck failed - deploy aborted" }
  }

  Write-Host "==> Build (next build -> out/)" -ForegroundColor Cyan
  npm run build
  if ($LASTEXITCODE -ne 0) { throw "build failed" }
  if (-not (Test-Path (Join-Path $webDir "out/index.html"))) { throw "out/index.html missing - export did not produce a site" }

  # Create the Pages project on first run; ignore "already exists".
  Write-Host "==> Ensuring Pages project '$ProjectName' exists" -ForegroundColor Cyan
  npx wrangler pages project create $ProjectName --production-branch $Branch 2>$null | Out-Null

  Write-Host "==> Deploying to Cloudflare Pages" -ForegroundColor Cyan
  npx wrangler pages deploy out --project-name=$ProjectName --branch=$Branch --commit-dirty=true
  if ($LASTEXITCODE -ne 0) { throw "wrangler deploy failed" }

  Write-Host "==> Done. If this was the first deploy, attach local-bench.ai in the dashboard (see runbook)." -ForegroundColor Green
}
finally {
  Pop-Location
}
