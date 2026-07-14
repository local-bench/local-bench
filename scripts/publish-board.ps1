#requires -Version 5.1
<#
.SYNOPSIS
  Run the gated board publication workflow.

.DESCRIPTION
  Publication VALIDATES the committed immutable board; it never regenerates it.
  Board cutting is a separate conscious operation (scripts/refresh-site-data.ps1),
  done BEFORE the publication commit, with web/components/launch-freeze.ts re-pinned
  and board + manifest + pin + site data committed together.

  Workflow: clean-tree check -> board == manifest == launch-freeze pin -> CLI suite ->
  web preflight (npm ci, vitest, typecheck, next build via scripts/deploy-site.ps1) ->
  git push deploy HEAD:main (Cloudflare Pages Git integration) -> poll live data until
  the deployed index serves -> live health check -> public snapshot reminder.

.PARAMETER SkipTests
  Explicitly discouraged. Skips test gates where downstream scripts support it.

.PARAMETER SkipDeploy
  Run every validation, gate, and the build, but stop before pushing (rehearsal).

.PARAMETER DryRun
  Print the workflow without running it.
#>
[CmdletBinding()]
param(
  [switch]$SkipTests,
  [switch]$SkipDeploy,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$webDir = Join-Path $repoRoot "web"
$boardPath = Join-Path $repoRoot "cli\runs\board\board_v2.json"
$manifestPath = Join-Path $repoRoot "cli\runs\board\board_v2.manifest.json"
$freezePath = Join-Path $webDir "components\launch-freeze.ts"
$liveIndexUrl = "https://local-bench.ai/data/index.json"
$liveHealthUrl = "https://local-bench.ai/api/health"

if (-not (Test-Path $webDir)) { throw "web/ not found at $webDir" }

$plan = @(
  "assert clean tracked tree (untracked files are fine)",
  "assert sha256(cli/runs/board/board_v2.json) == manifest board_sha256 == launch-freeze boardSha256",
  "uv run --project cli pytest cli -q",
  "powershell scripts/deploy-site.ps1  (npm ci; vitest; typecheck; next build)",
  "git push deploy HEAD:main  (Cloudflare Pages deploys the pushed commit)",
  "poll $liveIndexUrl until the deployed index serves",
  "verify $liveHealthUrl, then print the publish-snapshot reminder"
)

if ($DryRun) {
  Write-Host "==> Dry run: publish-board plan" -ForegroundColor Cyan
  $plan | ForEach-Object { Write-Host " - $_" }
  if ($SkipTests) { Write-Host "WARNING: -SkipTests is discouraged for publication." -ForegroundColor Yellow }
  if ($SkipDeploy) { Write-Host "NOTE: -SkipDeploy stops after the build (rehearsal)." -ForegroundColor Yellow }
  return
}

# --- 1. Publication deploys the COMMITTED tree; refuse tracked modifications. ---
$statusLines = @(& git -C $repoRoot status --porcelain)
if ($LASTEXITCODE -ne 0) { throw "git status failed" }
$trackedDirt = @($statusLines | Where-Object { $_ -and (-not $_.StartsWith("??")) })
if ($trackedDirt.Count -gt 0) {
  Write-Host "==> Tracked files are modified:" -ForegroundColor Red
  $trackedDirt | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
  throw "publication deploys the COMMITTED tree - commit or restore the files above first"
}

# --- 2. Immutable-board contract: file == manifest == launch-freeze pin. ---
$boardSha = (Get-FileHash -Algorithm SHA256 -Path $boardPath).Hash.ToLowerInvariant()
$manifestSha = (Get-Content $manifestPath -Raw | ConvertFrom-Json).board_sha256
$freezeMatch = Select-String -Path $freezePath -Pattern 'boardSha256:\s*"([0-9a-f]{64})"'
if (-not $freezeMatch) { throw "boardSha256 pin not found in $freezePath" }
$freezeSha = $freezeMatch.Matches[0].Groups[1].Value
Write-Host "==> Immutable board check" -ForegroundColor Cyan
Write-Host "    board file : $boardSha"
Write-Host "    manifest   : $manifestSha"
Write-Host "    freeze pin : $freezeSha"
if ($boardSha -ne $manifestSha) { throw "board file sha != manifest board_sha256 - committed board and manifest disagree" }
if ($boardSha -ne $freezeSha) { throw "board sha != launch-freeze pin - re-pin web/components/launch-freeze.ts + commit BEFORE publishing (publication never re-cuts the board)" }

$headSha = (& git -C $repoRoot rev-parse HEAD).Trim()
$headSubject = & git -C $repoRoot log -1 --format=%s HEAD
Write-Host ("==> Publishing commit {0}: {1}" -f $headSha.Substring(0, 7), $headSubject) -ForegroundColor Cyan

Push-Location $repoRoot
try {
  # --- 3. CLI suite ---
  if (-not $SkipTests) {
    Write-Host "==> CLI suite (uv run --project cli pytest cli -q)" -ForegroundColor Cyan
    & uv run --project cli pytest cli -q
    if ($LASTEXITCODE -ne 0) { throw "CLI pytest failed" }
  } else {
    Write-Host "==> Skipping CLI tests (-SkipTests is discouraged)" -ForegroundColor Yellow
  }

  # --- 4. Web preflight: npm ci + vitest + typecheck + next build ---
  Write-Host "==> Web preflight (scripts/deploy-site.ps1)" -ForegroundColor Cyan
  $deployArgs = @("-ExecutionPolicy", "Bypass", "-File", (Join-Path $repoRoot "scripts\deploy-site.ps1"))
  if ($SkipTests) { $deployArgs += "-SkipTests" }
  & powershell @deployArgs
  if ($LASTEXITCODE -ne 0) { throw "deploy-site.ps1 preflight failed" }

  if ($SkipDeploy) {
    Write-Host "==> -SkipDeploy: every gate is green; stopping before push (rehearsal)." -ForegroundColor Yellow
    return
  }

  # --- 5. Push the exact verified commit ---
  $before = $null
  try {
    $before = (Invoke-WebRequest -UseBasicParsing -Uri $liveIndexUrl -TimeoutSec 30).Content
  } catch {
    Write-Host "    (pre-push live baseline fetch failed: $($_.Exception.Message))" -ForegroundColor Yellow
  }
  $localIndex = Get-Content (Join-Path $webDir "public\data\index.json") -Raw | ConvertFrom-Json
  $expectedVersion = $localIndex.index_version

  Write-Host ("==> Pushing {0} to deploy remote main" -f $headSha.Substring(0, 7)) -ForegroundColor Cyan
  & git -C $repoRoot push deploy HEAD:main
  if ($LASTEXITCODE -ne 0) { throw "git push deploy HEAD:main failed" }

  # --- 6. Poll until Cloudflare Pages serves the deployed data ---
  Write-Host ("==> Waiting for Cloudflare Pages (expect index_version {0}, content change)" -f $expectedVersion) -ForegroundColor Cyan
  $deadline = (Get-Date).AddMinutes(12)
  $live = $null
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 20
    try {
      $resp = Invoke-WebRequest -UseBasicParsing -Uri $liveIndexUrl -TimeoutSec 30
      $json = $resp.Content | ConvertFrom-Json
      if (($json.index_version -eq $expectedVersion) -and ($resp.Content -ne $before)) {
        $live = $json
        break
      }
      Write-Host ("    live index_version={0}; still waiting..." -f $json.index_version)
    } catch {
      Write-Host "    poll failed: $($_.Exception.Message)" -ForegroundColor Yellow
    }
  }
  if ($null -eq $live) { throw "live site did not serve index_version $expectedVersion within 12 minutes - check the Cloudflare Pages dashboard before retrying" }
  $rankedCount = @($live.models | Where-Object { $_.ranked -eq $true }).Count
  Write-Host ("==> LIVE: index_version {0}, {1} models, {2} ranked" -f $live.index_version, @($live.models).Count, $rankedCount) -ForegroundColor Green

  # --- 7. Live health ---
  $health = Invoke-WebRequest -UseBasicParsing -Uri $liveHealthUrl -TimeoutSec 30
  if ($health.StatusCode -ne 200) { throw "live health returned HTTP $($health.StatusCode)" }
  Write-Host ("==> {0} -> {1}" -f $liveHealthUrl, $health.Content) -ForegroundColor Green

  Write-Host "==> Published. Run the runbook live-verify assertions, then scripts/publish-snapshot.ps1 for the public snapshot." -ForegroundColor Yellow
}
finally {
  Pop-Location
}
