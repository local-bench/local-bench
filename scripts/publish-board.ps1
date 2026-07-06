#requires -Version 5.1
<#
.SYNOPSIS
  Run the gated board publication workflow.

.DESCRIPTION
  Runs CLI tests, regenerates board/site data through scripts/refresh-site-data.ps1,
  runs web tests and typecheck, builds, runs the deploy preflight, verifies live
  data JSON, then prints the public snapshot reminder.

.PARAMETER SkipTests
  Explicitly discouraged. Skips test gates where downstream scripts support it.

.PARAMETER DryRun
  Print the workflow without running it.
#>
[CmdletBinding()]
param(
  [switch]$SkipTests,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$webDir = Join-Path $repoRoot "web"

if (-not (Test-Path $webDir)) { throw "web/ not found at $webDir" }

$plan = @(
  "uv run --project cli pytest cli -q",
  "powershell scripts/refresh-site-data.ps1",
  "cd web; npx vitest run; npx tsc --noEmit",
  "powershell scripts/build-site.ps1",
  "powershell scripts/deploy-site.ps1",
  "fetch https://local-bench.ai/data/index.json and verify JSON row count >= 1",
  "print snapshot reminder: scripts/publish-snapshot.ps1"
)

if ($DryRun) {
  Write-Host "==> Dry run: publish-board plan" -ForegroundColor Cyan
  $plan | ForEach-Object { Write-Host " - $_" }
  if ($SkipTests) { Write-Host "WARNING: -SkipTests is discouraged for publication." -ForegroundColor Yellow }
  return
}

Push-Location $repoRoot
try {
  if (-not $SkipTests) {
    Write-Host "==> CLI suite (uv run --project cli pytest cli -q)" -ForegroundColor Cyan
    & uv run --project cli pytest cli -q
    if ($LASTEXITCODE -ne 0) { throw "CLI pytest failed" }
  } else {
    Write-Host "==> Skipping CLI tests (-SkipTests is discouraged)" -ForegroundColor Yellow
  }

  Write-Host "==> Refreshing board and site data" -ForegroundColor Cyan
  $refreshArgs = @("-ExecutionPolicy", "Bypass", "-File", (Join-Path $repoRoot "scripts\refresh-site-data.ps1"))
  if ($SkipTests) { $refreshArgs += "-SkipTests" }
  & powershell @refreshArgs
  if ($LASTEXITCODE -ne 0) { throw "refresh-site-data.ps1 failed" }

  Push-Location $webDir
  try {
    if (-not $SkipTests) {
      Write-Host "==> Web unit suite (vitest)" -ForegroundColor Cyan
      & npx vitest run
      if ($LASTEXITCODE -ne 0) { throw "vitest failed" }

      Write-Host "==> Web typecheck (tsc --noEmit)" -ForegroundColor Cyan
      & npx tsc --noEmit
      if ($LASTEXITCODE -ne 0) { throw "typecheck failed" }
    } else {
      Write-Host "==> Skipping web tests (-SkipTests is discouraged)" -ForegroundColor Yellow
    }
  }
  finally {
    Pop-Location
  }

  Write-Host "==> Building site" -ForegroundColor Cyan
  $buildArgs = @("-ExecutionPolicy", "Bypass", "-File", (Join-Path $repoRoot "scripts\build-site.ps1"))
  if ($SkipTests) { $buildArgs += "-SkipTests" }
  & powershell @buildArgs
  if ($LASTEXITCODE -ne 0) { throw "build-site.ps1 failed" }

  Write-Host "==> Deploy preflight" -ForegroundColor Cyan
  $deployArgs = @("-ExecutionPolicy", "Bypass", "-File", (Join-Path $repoRoot "scripts\deploy-site.ps1"))
  if ($SkipTests) { $deployArgs += "-SkipTests" }
  & powershell @deployArgs
  if ($LASTEXITCODE -ne 0) { throw "deploy-site.ps1 failed" }

  Write-Host "==> Live data verification" -ForegroundColor Cyan
  $response = Invoke-WebRequest -UseBasicParsing -Uri "https://local-bench.ai/data/index.json"
  if ($response.StatusCode -ne 200) { throw "live data returned HTTP $($response.StatusCode)" }
  $json = $response.Content | ConvertFrom-Json
  $rowCount = 0
  if ($json -is [System.Array]) {
    $rowCount = $json.Count
  } elseif ($null -ne $json.entries) {
    $rowCount = @($json.entries).Count
  } elseif ($null -ne $json.models) {
    $rowCount = @($json.models).Count
  } elseif ($null -ne $json.rows) {
    $rowCount = @($json.rows).Count
  }
  if ($rowCount -lt 1) { throw "live data parsed but row count was $rowCount" }
  Write-Host "==> Live data OK: HTTP 200, JSON parsed, row count $rowCount" -ForegroundColor Green

  Write-Host "==> Reminder: run scripts/publish-snapshot.ps1 for the public snapshot step." -ForegroundColor Yellow
}
finally {
  Pop-Location
}
