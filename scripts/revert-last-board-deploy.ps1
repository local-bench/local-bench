#requires -Version 5.1
<#
.SYNOPSIS
  Revert the last deploy/main commit that touched web/public/data.

.PARAMETER Confirm
  Required to create the temp branch, revert, and push to deploy/main.
#>
[CmdletBinding()]
param(
  [switch]$Confirm
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$remote = "deploy"
$branch = "main"
$ref = "$remote/$branch"

Push-Location $repoRoot
try {
  Write-Host "==> Fetching $ref" -ForegroundColor Cyan
  & git fetch $remote $branch
  if ($LASTEXITCODE -ne 0) { throw "git fetch $remote $branch failed" }

  $sha = (& git log $ref -1 --format=%H -- web/public/data).Trim()
  if ([string]::IsNullOrWhiteSpace($sha)) { throw "No deploy commit touching web/public/data found on $ref" }

  Write-Host "==> Last deploy data commit" -ForegroundColor Cyan
  & git log $ref -1 --stat -- web/public/data
  if ($LASTEXITCODE -ne 0) { throw "git log failed" }

  if (-not $Confirm) {
    Write-Host "==> Dry run only. Re-run with -Confirm to revert $sha and push to $ref." -ForegroundColor Yellow
    Write-Host "Would run: git checkout -B revert-board-$($sha.Substring(0, 12)) $ref"
    Write-Host "Would run: git revert --no-edit $sha"
    Write-Host "Would run: git push $remote HEAD:$branch"
    return
  }

  $tempBranch = "revert-board-$($sha.Substring(0, 12))"
  Write-Host "==> Creating $tempBranch from $ref" -ForegroundColor Cyan
  & git checkout -B $tempBranch $ref
  if ($LASTEXITCODE -ne 0) { throw "git checkout failed" }

  Write-Host "==> Reverting $sha" -ForegroundColor Cyan
  & git revert --no-edit $sha
  if ($LASTEXITCODE -ne 0) { throw "git revert failed" }

  Write-Host "==> Pushing revert to $remote/$branch" -ForegroundColor Cyan
  & git push $remote HEAD:$branch
  if ($LASTEXITCODE -ne 0) { throw "git push failed" }
}
finally {
  Pop-Location
}
