#requires -Version 5.1
[CmdletBinding()]
param(
  [ValidateSet("Private", "Public", "Auto")]
  [string]$ExpectedMode = "Private",

  [string]$BypassTokenPath,

  [switch]$RequireCloudflareAuth,

  [switch]$WriteState
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$ProjectName = "local-bench"
$SuiteId = "core-text-v1"
$SuiteHash = "6b7b80de59bee3e7098ba82e994c1d90954929554486fe8504654bc524f3d179"
$HttpTimeoutSec = 15
$SubmissionProbeNote = "not probed by smoke (state-mutating: tickets create D1 rows); verified out-of-band 2026-07-03 with secrets present - see docs/deploy/live-state.md"
$KnownDeploymentIds = @(
  "049f238e", # current gated production deployment
  "5a325e77", # prior gated deployment
  "494f03cd", # deleted pre-gate leak deployment
  "ccedf382"  # deleted pre-gate leak deployment
)

$script:PassCount = 0
$script:WarnCount = 0
$script:FailCount = 0
$script:Redactions = @()
$script:Observations = @()
$script:DetectedMode = "Unknown"
$script:DeploymentAliasIds = @()

function Redact-Text {
  param([AllowNull()][string]$Text)

  if ($null -eq $Text) { return "" }
  $redacted = [string]$Text
  foreach ($secret in $script:Redactions) {
    if (-not [string]::IsNullOrWhiteSpace($secret)) {
      $redacted = $redacted.Replace($secret, "[REDACTED]")
    }
  }
  return $redacted
}

function Limit-Text {
  param(
    [AllowNull()][string]$Text,
    [int]$MaxLength = 220
  )

  $safe = (Redact-Text $Text) -replace "\s+", " "
  if ($safe.Length -le $MaxLength) { return $safe }
  return $safe.Substring(0, $MaxLength) + "..."
}

function Add-CheckResult {
  param(
    [ValidateSet("PASS", "WARN", "FAIL")]
    [string]$Status,
    [string]$Name,
    [string]$Message
  )

  switch ($Status) {
    "PASS" { $script:PassCount++; $color = "Green" }
    "WARN" { $script:WarnCount++; $color = "Yellow" }
    "FAIL" { $script:FailCount++; $color = "Red" }
  }

  $safeMessage = Redact-Text $Message
  Write-Host ("{0}: {1} - {2}" -f $Status, $Name, $safeMessage) -ForegroundColor $color
  $script:Observations += [pscustomobject]@{
    status = $Status
    name = $Name
    message = $safeMessage
  }
}

function Convert-Headers {
  param($Headers)

  $map = @{}
  if ($null -eq $Headers) { return $map }

  if ($Headers -is [System.Net.WebHeaderCollection]) {
    foreach ($key in $Headers.AllKeys) {
      $map[$key.ToLowerInvariant()] = [string]$Headers[$key]
    }
    return $map
  }

  if ($Headers -is [System.Collections.IDictionary]) {
    foreach ($key in $Headers.Keys) {
      $name = [string]$key
      $map[$name.ToLowerInvariant()] = [string]($Headers[$key] -join ", ")
    }
    return $map
  }

  return $map
}

function Get-HeaderValue {
  param(
    [hashtable]$Headers,
    [string]$Name
  )

  $key = $Name.ToLowerInvariant()
  if ($Headers.ContainsKey($key)) { return [string]$Headers[$key] }
  return ""
}

function Invoke-Http {
  param(
    [string]$Uri,
    [hashtable]$Headers = @{}
  )

  try {
    $response = Invoke-WebRequest `
      -Uri $Uri `
      -Headers $Headers `
      -TimeoutSec $HttpTimeoutSec `
      -UseBasicParsing `
      -MaximumRedirection 0

    return [pscustomobject]@{
      uri = $Uri
      status_code = [int]$response.StatusCode
      headers = Convert-Headers $response.Headers
      body = [string]$response.Content
      error = $null
    }
  }
  catch {
    $webResponse = $_.Exception.Response
    if ($null -ne $webResponse) {
      $body = ""
      try {
        $stream = $webResponse.GetResponseStream()
        if ($null -ne $stream) {
          $reader = New-Object System.IO.StreamReader($stream)
          $body = $reader.ReadToEnd()
        }
      }
      catch {
        $body = ""
      }

      return [pscustomobject]@{
        uri = $Uri
        status_code = [int]$webResponse.StatusCode
        headers = Convert-Headers $webResponse.Headers
        body = $body
        error = $null
      }
    }

    return [pscustomobject]@{
      uri = $Uri
      status_code = 0
      headers = @{}
      body = ""
      error = (Redact-Text $_.Exception.Message)
    }
  }
}

function Test-PrivateHttpSignature {
  param(
    [string]$Name,
    [string]$Uri
  )

  $result = Invoke-Http -Uri $Uri
  $cacheControl = Get-HeaderValue -Headers $result.headers -Name "cache-control"
  $robots = Get-HeaderValue -Headers $result.headers -Name "x-robots-tag"
  $hasPrivateSignature = (
    $result.status_code -eq 503 -and
    $cacheControl -match "(?i)\bno-store\b" -and
    $robots -match "(?i)\bnoindex\b"
  )

  if ($hasPrivateSignature) {
    Add-CheckResult "PASS" $Name "private signature present (HTTP 503, cache-control:no-store, x-robots-tag:noindex)"
    return "Private"
  }

  $details = "HTTP $($result.status_code); cache-control='$cacheControl'; x-robots-tag='$robots'"
  if ($result.status_code -eq 200) {
    Add-CheckResult "FAIL" $Name "public 200 leak; $details"
    return "Public"
  }

  if ($result.status_code -eq 0) {
    Add-CheckResult "FAIL" $Name "request failed; $($result.error)"
    return "Unknown"
  }

  Add-CheckResult "FAIL" $Name "missing private signature; $details; body='$(Limit-Text $result.body)'"
  return "Unknown"
}

function Test-HealthPublic {
  param(
    [string]$Name,
    [string]$Uri,
    [hashtable]$Headers = @{}
  )

  $result = Invoke-Http -Uri $Uri -Headers $Headers
  if ($result.status_code -ne 200) {
    Add-CheckResult "FAIL" $Name "expected HTTP 200 health payload; got HTTP $($result.status_code); body='$(Limit-Text $result.body)'"
    return $false
  }

  try {
    $payload = $result.body | ConvertFrom-Json
  }
  catch {
    Add-CheckResult "FAIL" $Name "health response is not JSON; body='$(Limit-Text $result.body)'"
    return $false
  }

  # storage.queue is expected false: the dead VERIFICATION_QUEUE producer binding was
  # removed deliberately (Pages cannot consume queues).
  $storage = $payload.storage
  $storageOk = (
    $payload.service -eq "localbench" -and
    $payload.status -eq "ok" -and
    $null -ne $storage -and
    $storage.d1 -eq $true -and
    $storage.queue -eq $false -and
    $storage.r2 -eq $true
  )

  if ($storageOk) {
    Add-CheckResult "PASS" $Name "health payload matches service/status/storage expectations"
    return $true
  }

  Add-CheckResult "FAIL" $Name "unexpected health payload; body='$(Limit-Text $result.body)'"
  return $false
}

function Get-ManifestFileCount {
  param($Files)

  if ($null -eq $Files) { return $null }
  if ($Files -is [int]) { return $Files }
  if ($Files -is [long]) { return [int]$Files }
  if ($Files -is [array]) { return $Files.Count }
  return @($Files).Count
}

function Test-ManifestPublic {
  param(
    [string]$Name,
    [string]$Uri,
    [hashtable]$Headers = @{}
  )

  $result = Invoke-Http -Uri $Uri -Headers $Headers
  if ($result.status_code -ne 200) {
    Add-CheckResult "FAIL" $Name "expected HTTP 200 suite manifest; got HTTP $($result.status_code); body='$(Limit-Text $result.body)'"
    return $false
  }

  try {
    $payload = $result.body | ConvertFrom-Json
  }
  catch {
    Add-CheckResult "FAIL" $Name "suite manifest is not JSON; body='$(Limit-Text $result.body)'"
    return $false
  }

  $fileCount = Get-ManifestFileCount $payload.files
  $manifestOk = (
    $payload.suite_id -eq $SuiteId -and
    $payload.suite_hash -eq $SuiteHash -and
    $fileCount -eq 11
  )

  if ($manifestOk) {
    Add-CheckResult "PASS" $Name "manifest matches suite_id=$SuiteId, files=11, suite_hash=$SuiteHash"
    return $true
  }

  Add-CheckResult "FAIL" $Name "unexpected manifest facts; suite_id='$($payload.suite_id)', files='$fileCount', suite_hash='$($payload.suite_hash)'"
  return $false
}

function Test-Status200 {
  param(
    [string]$Name,
    [string]$Uri
  )

  $result = Invoke-Http -Uri $Uri
  if ($result.status_code -eq 200) {
    Add-CheckResult "PASS" $Name "HTTP 200"
    return $true
  }

  Add-CheckResult "FAIL" $Name "expected HTTP 200; got HTTP $($result.status_code); body='$(Limit-Text $result.body)'"
  return $false
}

function Test-DnsResolution {
  param(
    [string]$HostName,
    [string]$Server
  )

  try {
    if ([string]::IsNullOrWhiteSpace($Server)) {
      $answers = Resolve-DnsName -Name $HostName -ErrorAction Stop
    }
    else {
      $answers = Resolve-DnsName -Name $HostName -Server $Server -ErrorAction Stop
    }
    return ($null -ne ($answers | Select-Object -First 1))
  }
  catch {
    return $false
  }
}

function Test-DnsHost {
  param([string]$HostName)

  $defaultOk = Test-DnsResolution -HostName $HostName -Server $null
  $cloudflareOk = Test-DnsResolution -HostName $HostName -Server "1.1.1.1"

  if ($defaultOk -and $cloudflareOk) {
    Add-CheckResult "PASS" "DNS $HostName" "default resolver and 1.1.1.1 resolve"
  }
  elseif ($cloudflareOk) {
    Add-CheckResult "WARN" "DNS $HostName" "default resolver failed but 1.1.1.1 resolves; likely resolver cache lag"
  }
  else {
    Add-CheckResult "FAIL" "DNS $HostName" "1.1.1.1 failed to resolve"
  }
}

function Get-WranglerPath {
  $repoRoot = Split-Path -Parent $PSScriptRoot
  $localWrangler = Join-Path $repoRoot "web\node_modules\.bin\wrangler.cmd"
  if (Test-Path -LiteralPath $localWrangler) { return $localWrangler }

  $globalWrangler = Get-Command "wrangler" -ErrorAction SilentlyContinue
  if ($null -ne $globalWrangler) { return $globalWrangler.Source }

  return $null
}

function Get-WranglerDeploymentIds {
  $repoRoot = Split-Path -Parent $PSScriptRoot
  $webRoot = Join-Path $repoRoot "web"
  $wrangler = Get-WranglerPath
  $output = ""
  $exitCode = 1

  if (-not [string]::IsNullOrWhiteSpace($wrangler)) {
    try {
      $lines = & $wrangler pages deployment list --project-name $ProjectName 2>&1
      $exitCode = $LASTEXITCODE
      $output = [string]::Join("`n", @($lines))
    }
    catch {
      $exitCode = 1
      $output = $_.Exception.Message
    }
  }

  if ($exitCode -ne 0) {
    $npxOutput = ""
    try {
      Push-Location -LiteralPath $webRoot
      try {
        $lines = & npx wrangler pages deployment list --project-name $ProjectName 2>&1
        $npxExitCode = $LASTEXITCODE
        $npxOutput = [string]::Join("`n", @($lines))
      }
      finally {
        Pop-Location
      }
    }
    catch {
      $npxExitCode = 1
      $npxOutput = $_.Exception.Message
    }

    if ($npxExitCode -eq 0) {
      $exitCode = 0
      $output = $npxOutput
    }
    elseif ([string]::IsNullOrWhiteSpace($wrangler)) {
      $output = $npxOutput
    }
    elseif (-not [string]::IsNullOrWhiteSpace($npxOutput)) {
      $output = "$output`nnpx fallback:`n$npxOutput"
    }
  }

  if ($exitCode -ne 0) {
    if ([string]::IsNullOrWhiteSpace($wrangler)) {
      if ($RequireCloudflareAuth) {
        Add-CheckResult "FAIL" "Cloudflare deployment enumeration" "Wrangler is unavailable and -RequireCloudflareAuth was set"
      }
      else {
        Add-CheckResult "WARN" "Cloudflare deployment enumeration" "Wrangler is unavailable; cannot enumerate Pages deployments"
      }
    }
    else {
      if ($RequireCloudflareAuth) {
        Add-CheckResult "FAIL" "Cloudflare deployment enumeration" "wrangler list failed and -RequireCloudflareAuth was set; output='$(Limit-Text $output)'"
      }
      else {
        Add-CheckResult "WARN" "Cloudflare deployment enumeration" "wrangler list failed; cannot enumerate Pages deployments; output='$(Limit-Text $output)'"
      }
    }
    return @()
  }

  $ids = @()
  foreach ($match in [regex]::Matches($output, "https://([a-z0-9-]+)\.$ProjectName\.pages\.dev", "IgnoreCase")) {
    $ids += $match.Groups[1].Value
  }
  foreach ($match in [regex]::Matches($output, "(?im)^\s*([0-9a-f]{8})\b")) {
    $ids += $match.Groups[1].Value
  }

  $ids = @($ids | Where-Object { $_ -match "^[a-z0-9-]+$" } | Select-Object -Unique)
  Add-CheckResult "PASS" "Cloudflare deployment enumeration" ("wrangler returned {0} deployment alias id(s)" -f $ids.Count)
  return $ids
}

function Test-DeploymentAliases {
  $enumeratedIds = Get-WranglerDeploymentIds
  $ids = @(($KnownDeploymentIds + $enumeratedIds) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
  $script:DeploymentAliasIds = $ids

  foreach ($id in $ids) {
    $uri = "https://$id.$ProjectName.pages.dev/"
    $result = Invoke-Http -Uri $uri

    if ($result.status_code -eq 200) {
      Add-CheckResult "FAIL" "Deployment alias $id" "unauthenticated request returned HTTP 200; deployment alias leak"
    }
    elseif ($result.status_code -eq 0) {
      Add-CheckResult "WARN" "Deployment alias $id" "request failed; cannot prove alias is closed; $($result.error)"
    }
    else {
      Add-CheckResult "PASS" "Deployment alias $id" "unauthenticated request returned HTTP $($result.status_code), not 200"
    }
  }
}

function Test-BypassToken {
  if ([string]::IsNullOrWhiteSpace($BypassTokenPath)) { return }

  if (-not (Test-Path -LiteralPath $BypassTokenPath)) {
    Add-CheckResult "WARN" "Owner bypass" "bypass token path was provided but no token file exists; owner bypass not tested"
    return
  }

  try {
    $token = (Get-Content -LiteralPath $BypassTokenPath -Raw).Trim()
  }
  catch {
    Add-CheckResult "WARN" "Owner bypass" "bypass token file could not be read; owner bypass not tested"
    return
  }

  if ([string]::IsNullOrWhiteSpace($token)) {
    Add-CheckResult "WARN" "Owner bypass" "bypass token file is empty after trimming; owner bypass not tested"
    return
  }

  $script:Redactions += $token
  $headers = @{ "x-localbench-bypass" = $token }
  Test-HealthPublic -Name "Owner bypass health" -Uri "https://local-bench.ai/api/health" -Headers $headers | Out-Null
  Test-ManifestPublic -Name "Owner bypass manifest" -Uri "https://local-bench.ai/api/suites/$SuiteId/manifest" -Headers $headers | Out-Null
}

function Test-AutoMode {
  param([array]$Endpoints)

  $modes = @()
  foreach ($endpoint in $Endpoints) {
    $result = Invoke-Http -Uri $endpoint.Uri
    $cacheControl = Get-HeaderValue -Headers $result.headers -Name "cache-control"
    $robots = Get-HeaderValue -Headers $result.headers -Name "x-robots-tag"
    $isPrivate = (
      $result.status_code -eq 503 -and
      $cacheControl -match "(?i)\bno-store\b" -and
      $robots -match "(?i)\bnoindex\b"
    )

    if ($isPrivate) {
      $modes += "Private"
      Add-CheckResult "PASS" $endpoint.Name "detected Private signature"
    }
    elseif ($result.status_code -eq 200) {
      $modes += "Public"
      Add-CheckResult "PASS" $endpoint.Name "detected Public HTTP 200"
    }
    else {
      $modes += "Unknown"
      Add-CheckResult "FAIL" $endpoint.Name "could not classify mode; HTTP $($result.status_code)"
    }
  }

  $distinctModes = @($modes | Select-Object -Unique)
  $publicPrivateModes = @($distinctModes | Where-Object { $_ -eq "Private" -or $_ -eq "Public" })
  if ($publicPrivateModes.Count -gt 1) {
    $script:DetectedMode = "Mixed"
    Add-CheckResult "FAIL" "Detected mode" "mixed public/private endpoint results"
  }
  elseif ($distinctModes.Count -eq 1) {
    $script:DetectedMode = $distinctModes[0]
    Add-CheckResult "PASS" "Detected mode" $script:DetectedMode
  }
  else {
    $script:DetectedMode = "Unknown"
    Add-CheckResult "FAIL" "Detected mode" ("mixed or unknown endpoint results: {0}" -f ($distinctModes -join ", "))
  }
}

function Add-SubmissionAdminWarnings {
  Add-CheckResult "WARN" "Submission/admin legs" $SubmissionProbeNote
}

function Write-LiveStateJson {
  $repoRoot = Split-Path -Parent $PSScriptRoot
  $path = Join-Path $repoRoot "docs\deploy\live-state.generated.json"
  $state = [pscustomobject]@{
    generated = (Get-Date).ToString("o")
    expected_mode = $ExpectedMode
    detected_mode = $script:DetectedMode
    expires_for_decision_making = "24h"
    hosts = @("local-bench.ai", "www.local-bench.ai", "local-bench.pages.dev")
    suite = [pscustomobject]@{
      suite_id = $SuiteId
      suite_hash = $SuiteHash
      expected_file_count = 11
    }
    production_deployment = [pscustomobject]@{
      id = "unverified (wrangler unauthenticated)"
      commit = "40423f4"
      branch = "main"
      as_of = "2026-07-03"
    }
    submission_admin_probe = $SubmissionProbeNote
    deployment_aliases_checked = $script:DeploymentAliasIds
    checks = $script:Observations
  }

  $state | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding UTF8
  Add-CheckResult "PASS" "WriteState" "wrote docs/deploy/live-state.generated.json"
}

$publicEndpoints = @(
  [pscustomobject]@{ Name = "Apex health"; Uri = "https://local-bench.ai/api/health"; Kind = "health" },
  [pscustomobject]@{ Name = "Pages health"; Uri = "https://local-bench.pages.dev/api/health"; Kind = "health" },
  [pscustomobject]@{ Name = "Core-text-v1 manifest"; Uri = "https://local-bench.ai/api/suites/$SuiteId/manifest"; Kind = "manifest" },
  [pscustomobject]@{ Name = "Root page"; Uri = "https://local-bench.ai/"; Kind = "root" }
)

Write-Host ("Launch smoke: ExpectedMode={0}" -f $ExpectedMode) -ForegroundColor Cyan

switch ($ExpectedMode) {
  "Private" {
    $modes = @()
    foreach ($endpoint in $publicEndpoints) {
      $modes += Test-PrivateHttpSignature -Name $endpoint.Name -Uri $endpoint.Uri
    }
    if (@($modes | Where-Object { $_ -eq "Private" }).Count -eq $publicEndpoints.Count) {
      $script:DetectedMode = "Private"
    }
    elseif (@($modes | Where-Object { $_ -eq "Public" }).Count -gt 0) {
      $script:DetectedMode = "Mixed"
    }
    else {
      $script:DetectedMode = "Unknown"
    }
  }
  "Public" {
    Test-HealthPublic -Name "Apex health" -Uri "https://local-bench.ai/api/health" | Out-Null
    Test-HealthPublic -Name "Pages health" -Uri "https://local-bench.pages.dev/api/health" | Out-Null
    Test-ManifestPublic -Name "Core-text-v1 manifest" -Uri "https://local-bench.ai/api/suites/$SuiteId/manifest" | Out-Null
    Test-Status200 -Name "Root page" -Uri "https://local-bench.ai/" | Out-Null
    if ($script:FailCount -eq 0) { $script:DetectedMode = "Public" }
  }
  "Auto" {
    Test-AutoMode -Endpoints $publicEndpoints
  }
}

Test-DnsHost -HostName "local-bench.ai"
Test-DnsHost -HostName "www.local-bench.ai"
Test-DeploymentAliases
Test-BypassToken
Add-SubmissionAdminWarnings

if ($WriteState) {
  Write-LiveStateJson
}

Write-Host ("SUMMARY: PASS={0} WARN={1} FAIL={2} detected mode={3}" -f $script:PassCount, $script:WarnCount, $script:FailCount, $script:DetectedMode) -ForegroundColor Cyan

if ($script:FailCount -gt 0) {
  exit 1
}

exit 0
