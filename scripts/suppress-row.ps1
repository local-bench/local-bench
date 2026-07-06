#requires -Version 5.1
<#
.SYNOPSIS
  Suppress one accepted submission row through the admin API.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)]
  [string]$SubmissionId,

  [Parameter(Mandatory=$true)]
  [string]$Reason,

  [Parameter(Mandatory=$true)]
  [string]$AdminSecretFile
)

$ErrorActionPreference = "Stop"

$secretPath = Resolve-Path -LiteralPath $AdminSecretFile
$adminSecret = ([System.IO.File]::ReadAllText($secretPath)).Trim()
if ([string]::IsNullOrWhiteSpace($adminSecret)) { throw "Admin secret file is empty" }

$body = @{ reason = $Reason } | ConvertTo-Json -Compress
$uri = "https://local-bench.ai/api/admin/submissions/$SubmissionId/suppress"
$headers = @{ "x-localbench-admin-secret" = $adminSecret }

try {
  $response = Invoke-WebRequest -UseBasicParsing -Method Post -Uri $uri -Headers $headers -ContentType "application/json" -Body $body
  Write-Host "==> Suppress response: HTTP $($response.StatusCode)" -ForegroundColor Green
  Write-Host $response.Content
} catch [System.Net.WebException] {
  $statusCode = [int]$_.Exception.Response.StatusCode
  $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
  $content = $reader.ReadToEnd()
  Write-Host "==> Suppress response: HTTP $statusCode" -ForegroundColor Yellow
  Write-Host $content
}

Write-Host "==> Follow-up commands (not run):" -ForegroundColor Cyan
Write-Host "powershell -ExecutionPolicy Bypass -File scripts\publish-board.ps1"
Write-Host "powershell -ExecutionPolicy Bypass -File scripts\publish-snapshot.ps1"
