#requires -Version 5.1
<#
.SYNOPSIS
  Export and verify the final local-bench v1 static archive.

.DESCRIPTION
  Creates one UTC-stamped archive under C:\Users\Michael\lb-archive-v1,
  snapshots every public read-only API surface, copies web/public/data, exports
  production D1, inventories both production R2 buckets, and downloads the
  public-artifacts bucket when it is smaller than 2 GiB.

  Wrangler 4.x has no public `r2 object list` command. R2 inventory therefore
  uses Wrangler for authentication/account discovery and bucket metadata, then
  calls Cloudflare's read-only R2 inventory endpoint with the same credential.
  Object bodies are still fetched with `wrangler r2 object get --remote`.

.PARAMETER Verify
  Verify an existing archive instead of creating a new one.

.PARAMETER ArchivePath
  Archive to verify. With -Verify and no path, the latest stamped directory is
  selected.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\archive-v1-export.ps1

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\archive-v1-export.ps1 -Verify -ArchivePath C:\Users\Michael\lb-archive-v1\20260802-120000
#>
[CmdletBinding()]
param(
    [switch]$Verify,
    [string]$ArchivePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ArchiveRoot = 'C:\Users\Michael\lb-archive-v1'
$ArchiveTag = 'v1-final-archive-2026-08-02'
$PublicArtifactsLimitBytes = 2GB
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-TextUtf8([string]$Path, [string]$Content) {
    $parent = [System.IO.Path]::GetDirectoryName($Path)
    if ($parent) { [void][System.IO.Directory]::CreateDirectory($parent) }
    [System.IO.File]::WriteAllText($Path, $Content, $Utf8NoBom)
}

function Write-JsonFile([string]$Path, $Value, [int]$Depth = 12) {
    $json = ConvertTo-Json -InputObject $Value -Depth $Depth
    Write-TextUtf8 $Path ($json + "`n")
}

function Protect-WranglerLog([string]$Content) {
    $redacted = [regex]::Replace($Content, 'https://\S+\?X-Amz-\S+', '<redacted-presigned-url>')
    $redacted = [regex]::Replace($redacted, '(?im)(Authorization:\s*(?:Bearer|Basic)\s+)\S+', '$1<redacted>')
    return $redacted
}

function Get-RelativeArchivePath([string]$Root, [string]$Path) {
    $rootPrefix = $Root.TrimEnd('\') + '\'
    if (-not $Path.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside archive root: $Path"
    }
    return $Path.Substring($rootPrefix.Length).Replace('\', '/')
}

function Get-FilesRecursively([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return @() }
    return @(Get-ChildItem -LiteralPath $Path -File -Recurse -Force)
}

function Get-ArchiveMetrics([string]$Root) {
    $payloadFiles = @(Get-FilesRecursively $Root | Where-Object {
        $_.Name -ne 'SHA256SUMS' -and $_.Name -ne 'archive-manifest.json'
    })
    $dbFiles = @(Get-FilesRecursively (Join-Path $Root 'db'))
    $apiFiles = @(Get-FilesRecursively (Join-Path $Root 'api'))
    $staticFiles = @(Get-FilesRecursively (Join-Path $Root 'static-data'))
    $r2Files = @(Get-FilesRecursively (Join-Path $Root 'r2'))
    $downloadedObjects = @(Get-FilesRecursively (Join-Path $Root 'r2\localbench-public-artifacts'))

    [long]$totalBytes = 0
    foreach ($file in $payloadFiles) { $totalBytes += [long]$file.Length }

    [long]$inventoryObjects = 0
    $inventoryFiles = @(Get-FilesRecursively (Join-Path $Root 'r2') | Where-Object { $_.Name -like '*-inventory.json' })
    foreach ($inventoryFile in $inventoryFiles) {
        $inventory = Get-Content -LiteralPath $inventoryFile.FullName -Raw | ConvertFrom-Json
        $inventoryObjects += @($inventory).Count
    }

    return [ordered]@{
        files = $payloadFiles.Count
        db_files = $dbFiles.Count
        api_snapshot_files = $apiFiles.Count
        static_data_files = $staticFiles.Count
        r2_files = $r2Files.Count
        r2_inventory_objects = $inventoryObjects
        r2_downloaded_objects = $downloadedObjects.Count
        total_bytes = $totalBytes
    }
}

function Resolve-ArchiveToVerify([string]$RequestedPath) {
    if ($RequestedPath) {
        if (-not (Test-Path -LiteralPath $RequestedPath -PathType Container)) {
            throw "Archive directory not found: $RequestedPath"
        }
        return (Resolve-Path -LiteralPath $RequestedPath).ProviderPath.TrimEnd('\')
    }
    if (-not (Test-Path -LiteralPath $ArchiveRoot -PathType Container)) {
        throw "Archive root not found: $ArchiveRoot"
    }
    $candidates = @(Get-ChildItem -LiteralPath $ArchiveRoot -Directory | Where-Object {
        $_.Name -match '^\d{8}-\d{6}$'
    } | Sort-Object Name -Descending)
    if ($candidates.Count -eq 0) { throw "No stamped archives found under $ArchiveRoot" }
    return $candidates[0].FullName
}

function Test-Archive([string]$Root) {
    $errors = New-Object 'System.Collections.Generic.List[string]'
    $sumsPath = Join-Path $Root 'SHA256SUMS'
    $manifestPath = Join-Path $Root 'archive-manifest.json'
    if (-not (Test-Path -LiteralPath $sumsPath -PathType Leaf)) { $errors.Add('SHA256SUMS is missing') }
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { $errors.Add('archive-manifest.json is missing') }
    if ($errors.Count -gt 0) {
        $errors | ForEach-Object { Write-Host "VERIFY ERROR: $_" -ForegroundColor Red }
        throw "archive verification failed with $($errors.Count) error(s)"
    }

    $expectedPaths = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    $sumLines = @((Get-Content -LiteralPath $sumsPath -Raw) -split "`r?`n" | Where-Object { $_ })
    foreach ($line in $sumLines) {
        if ($line -notmatch '^([0-9a-f]{64})  (.+)$') {
            $errors.Add("invalid SHA256SUMS line: $line")
            continue
        }
        $expectedHash = $Matches[1]
        $relativePath = $Matches[2]
        if (-not $expectedPaths.Add($relativePath)) {
            $errors.Add("duplicate checksum path: $relativePath")
            continue
        }
        $candidate = [System.IO.Path]::GetFullPath((Join-Path $Root $relativePath.Replace('/', '\')))
        $rootPrefix = $Root.TrimEnd('\') + '\'
        if (-not $candidate.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            $errors.Add("checksum path escapes archive: $relativePath")
            continue
        }
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            $errors.Add("missing file: $relativePath")
            continue
        }
        $actualHash = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $expectedHash) {
            $errors.Add("SHA256 mismatch: $relativePath (expected $expectedHash, got $actualHash)")
        }
    }

    $actualFiles = @(Get-FilesRecursively $Root | Where-Object { $_.Name -ne 'SHA256SUMS' })
    foreach ($file in $actualFiles) {
        $relativePath = Get-RelativeArchivePath $Root $file.FullName
        if (-not $expectedPaths.Contains($relativePath)) { $errors.Add("file missing from SHA256SUMS: $relativePath") }
    }
    foreach ($relativePath in $expectedPaths) {
        $candidate = Join-Path $Root $relativePath.Replace('/', '\')
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        if (@($actualFiles | Where-Object { $_.FullName -eq $candidate }).Count -eq 0) {
            $errors.Add("checksum references non-archive file: $relativePath")
        }
    }

    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $metrics = Get-ArchiveMetrics $Root
    foreach ($name in @('files', 'db_files', 'api_snapshot_files', 'static_data_files', 'r2_files', 'r2_inventory_objects', 'r2_downloaded_objects')) {
        $manifestValue = [long]$manifest.counts.$name
        $actualValue = [long]$metrics[$name]
        if ($manifestValue -ne $actualValue) {
            $errors.Add("manifest count mismatch for $name (expected $manifestValue, got $actualValue)")
        }
    }
    if ([long]$manifest.total_bytes -ne [long]$metrics.total_bytes) {
        $errors.Add("manifest total_bytes mismatch (expected $($manifest.total_bytes), got $($metrics.total_bytes))")
    }
    if ([long]$manifest.sections.db.file_count -ne [long]$metrics.db_files) { $errors.Add('manifest DB section count mismatch') }
    if ([long]$manifest.sections.api_snapshots.file_count -ne [long]$metrics.api_snapshot_files) { $errors.Add('manifest API section count mismatch') }
    if ([long]$manifest.sections.static_data.file_count -ne [long]$metrics.static_data_files) { $errors.Add('manifest static-data section count mismatch') }
    if ([long]$manifest.sections.r2.file_count -ne [long]$metrics.r2_files) { $errors.Add('manifest R2 section count mismatch') }

    if ($errors.Count -gt 0) {
        Write-Host "Archive verification failed: $Root" -ForegroundColor Red
        $errors | ForEach-Object { Write-Host " - $_" -ForegroundColor Red }
        throw "archive verification failed with $($errors.Count) error(s)"
    }
    Write-Host "Archive verification passed: $Root" -ForegroundColor Green
    Write-Host ("Verified {0} checksums; {1} payload files; {2} bytes." -f $expectedPaths.Count, $metrics.files, $metrics.total_bytes)
}

if ($Verify) {
    Test-Archive (Resolve-ArchiveToVerify $ArchivePath)
    return
}
if ($ArchivePath) { throw '-ArchivePath is valid only with -Verify' }

$RepoRoot = Split-Path -Parent $PSScriptRoot
$WebDir = Join-Path $RepoRoot 'web'
$StaticSource = Join-Path $WebDir 'public\data'
if (-not (Test-Path -LiteralPath (Join-Path $WebDir 'wrangler.jsonc') -PathType Leaf)) { throw 'web/wrangler.jsonc is missing' }
if (-not (Test-Path -LiteralPath $StaticSource -PathType Container)) { throw 'web/public/data is missing' }

$cutoff = [DateTime]::UtcNow
do {
    $stamp = $cutoff.ToString('yyyyMMdd-HHmmss')
    $ArchiveDir = Join-Path $ArchiveRoot $stamp
    if (Test-Path -LiteralPath $ArchiveDir) {
        Start-Sleep -Milliseconds 200
        $cutoff = [DateTime]::UtcNow
    }
} while (Test-Path -LiteralPath $ArchiveDir)

[void][System.IO.Directory]::CreateDirectory($ArchiveDir)
$DbDir = Join-Path $ArchiveDir 'db'
$ApiDir = Join-Path $ArchiveDir 'api'
$StaticDir = Join-Path $ArchiveDir 'static-data'
$R2Dir = Join-Path $ArchiveDir 'r2'
foreach ($directory in @($DbDir, $ApiDir, $StaticDir, $R2Dir)) { [void][System.IO.Directory]::CreateDirectory($directory) }

$notes = New-Object 'System.Collections.Generic.List[string]'
$notes.Add('counts and total_bytes cover payload files; archive-manifest.json and SHA256SUMS are integrity metadata')
$notes.Add('SHA256SUMS covers every archive file except SHA256SUMS itself, which cannot self-hash')
$apiFailures = New-Object 'System.Collections.Generic.List[string]'
$r2InstructionsNeeded = $false
$dbExportStatus = 'pending-auth'
$wranglerVersion = 'unavailable'
$nodeVersion = 'unavailable'

$script:WranglerExecutable = $null
$script:WranglerPrefix = @()
$wranglerCommand = Get-Command 'wrangler.cmd' -ErrorAction SilentlyContinue
if ($null -eq $wranglerCommand) { $wranglerCommand = Get-Command 'wrangler' -ErrorAction SilentlyContinue }
if ($null -ne $wranglerCommand) {
    $script:WranglerExecutable = $wranglerCommand.Source
} else {
    $npxCommand = Get-Command 'npx.cmd' -ErrorAction SilentlyContinue
    if ($null -ne $npxCommand) {
        $script:WranglerExecutable = $npxCommand.Source
        $script:WranglerPrefix = @('--no-install', 'wrangler')
    }
}

function Invoke-Wrangler([string[]]$Arguments) {
    if ($null -eq $script:WranglerExecutable) {
        return [pscustomobject]@{ ExitCode = 127; Output = 'wrangler executable not found' }
    }
    $nativeArguments = New-Object 'System.Collections.Generic.List[string]'
    foreach ($argument in $script:WranglerPrefix) { $nativeArguments.Add($argument) }
    foreach ($argument in $Arguments) { $nativeArguments.Add($argument) }
    $invokeArguments = $nativeArguments.ToArray()
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $outputLines = @(& $script:WranglerExecutable @invokeArguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldPreference
    }
    $outputText = ($outputLines | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
    return [pscustomobject]@{ ExitCode = $exitCode; Output = $outputText }
}

function Last-NonEmptyLine([string]$Text) {
    $lines = @($Text -split "`r?`n" | Where-Object { $_.Trim().Length -gt 0 })
    if ($lines.Count -eq 0) { return 'no diagnostic output' }
    return $lines[$lines.Count - 1].Trim()
}

$oldLogPath = $env:WRANGLER_LOG_PATH
$oldMetrics = $env:WRANGLER_SEND_METRICS
$env:WRANGLER_LOG_PATH = Join-Path $ArchiveDir 'wrangler.log'
$env:WRANGLER_SEND_METRICS = 'false'

try {
    $wranglerVersionResult = Invoke-Wrangler @('--version')
    if ($wranglerVersionResult.ExitCode -eq 0) { $wranglerVersion = (Last-NonEmptyLine $wranglerVersionResult.Output) }
    try { $nodeVersion = (& node --version).Trim() } catch { $nodeVersion = 'unavailable' }

    # D1: remote export with schema and data (the default when neither --no-* flag is supplied).
    $dbPath = Join-Path $DbDir 'localbench_prod.sql'
    Push-Location $WebDir
    try {
        $dbResult = Invoke-Wrangler @('d1', 'export', 'localbench_prod', '--remote', '--output', $dbPath, '--skip-confirmation')
    } finally {
        Pop-Location
    }
    Write-TextUtf8 (Join-Path $DbDir 'wrangler-export.log') ((Protect-WranglerLog $dbResult.Output) + "`n")
    if ($dbResult.ExitCode -eq 0 -and (Test-Path -LiteralPath $dbPath -PathType Leaf) -and (Get-Item -LiteralPath $dbPath).Length -gt 0) {
        $dbExportStatus = 'complete'
    } else {
        $dbExportStatus = 'pending-auth'
        $notes.Add("D1 export pending: $(Last-NonEmptyLine $dbResult.Output)")
        $dbInstructions = @"
# D1 export pending authentication

Wrangler could not complete the production D1 export. Do not add a hand-made or local database export to this archive.

From the repository root, authenticate Wrangler and rerun the exporter so a new, fully sealed archive is created:

    Set-Location "$RepoRoot"
    npx --no-install wrangler login
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\archive-v1-export.ps1

The exporter will run this production command from web/:

    npx --no-install wrangler d1 export localbench_prod --remote --output "<new-archive>\db\localbench_prod.sql" --skip-confirmation
"@
        Write-TextUtf8 (Join-Path $DbDir 'EXPORT-INSTRUCTIONS.md') $dbInstructions
    }

    # Public GET endpoints audited from web/functions/api. Admin, auth-flow, and
    # POST/mutating endpoints are intentionally excluded. Dynamic suite manifests
    # and public submission-status endpoints are expanded from their list APIs.
    function Save-ApiSnapshot([string]$Url, [string]$RelativeBase) {
        $bodyPath = Join-Path $ApiDir ($RelativeBase + '.json')
        $headersPath = Join-Path $ApiDir ($RelativeBase + '.headers.json')
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -Method Get -TimeoutSec 60 -MaximumRedirection 5
            Write-TextUtf8 $bodyPath $response.Content
            $headerMap = [ordered]@{}
            foreach ($key in @($response.Headers.Keys)) {
                $values = @($response.Headers[$key])
                if ($values.Count -eq 1) { $headerMap[$key] = $values[0] } else { $headerMap[$key] = $values }
            }
            Write-JsonFile $headersPath ([ordered]@{ url = $Url; status = [int]$response.StatusCode; headers = $headerMap })
            return [pscustomobject]@{ Content = $response.Content; StatusCode = [int]$response.StatusCode; Success = $true }
        } catch {
            $apiFailures.Add("$Url - $($_.Exception.Message)")
            return [pscustomobject]@{ Content = $null; StatusCode = 0; Success = $false }
        }
    }

    [void](Save-ApiSnapshot 'https://local-bench.ai/api/board/community.json' 'board-community')
    [void](Save-ApiSnapshot 'https://local-bench.ai/api/feed/accepted.json' 'feed-accepted')
    [void](Save-ApiSnapshot 'https://local-bench.ai/api/health' 'health')
    [void](Save-ApiSnapshot 'https://local-bench.ai/api/publication-snapshot' 'publication-snapshot')

    $suitesResult = Save-ApiSnapshot 'https://local-bench.ai/api/suites' 'suites'
    if ($suitesResult.Success) {
        try {
            $suitesPayload = $suitesResult.Content | ConvertFrom-Json
            foreach ($suite in @($suitesPayload.suites)) {
                $suiteId = [string]$suite.id
                $safeSuiteId = [regex]::Replace($suiteId, '[^A-Za-z0-9._-]', '_')
                $suiteUrl = 'https://local-bench.ai/api/suites/' + [Uri]::EscapeDataString($suiteId) + '/manifest'
                [void](Save-ApiSnapshot $suiteUrl (Join-Path 'suite-manifests' $safeSuiteId))
            }
        } catch {
            $apiFailures.Add("suite manifest enumeration - $($_.Exception.Message)")
        }
    }

    $submissionIds = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    $seenCursors = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
    $cursor = $null
    $pageNumber = 1
    do {
        $listUrl = 'https://local-bench.ai/api/submissions/list'
        if ($null -ne $cursor) { $listUrl += '?cursor=' + [Uri]::EscapeDataString($cursor) }
        $listResult = Save-ApiSnapshot $listUrl ('submission-list-page-{0:D4}' -f $pageNumber)
        if (-not $listResult.Success) { break }
        try {
            $listPayload = $listResult.Content | ConvertFrom-Json
            foreach ($submission in @($listPayload.submissions)) {
                if ($submission.submission_id) { [void]$submissionIds.Add([string]$submission.submission_id) }
            }
            $nextCursor = $listPayload.next_cursor
            if ($null -eq $nextCursor) { $cursor = $null } else { $cursor = [string]$nextCursor }
            if ($null -ne $cursor -and -not $seenCursors.Add($cursor)) { throw "duplicate pagination cursor: $cursor" }
            $pageNumber++
            if ($pageNumber -gt 10000) { throw 'submission pagination exceeded 10000 pages' }
        } catch {
            $apiFailures.Add("submission list enumeration - $($_.Exception.Message)")
            break
        }
    } while ($null -ne $cursor)

    foreach ($submissionId in @($submissionIds | Sort-Object)) {
        $safeSubmissionId = [regex]::Replace($submissionId, '[^A-Za-z0-9._-]', '_')
        $statusUrl = 'https://local-bench.ai/api/submissions/' + [Uri]::EscapeDataString($submissionId)
        [void](Save-ApiSnapshot $statusUrl (Join-Path 'submission-status' $safeSubmissionId))
    }
    if ($apiFailures.Count -gt 0) {
        foreach ($failure in $apiFailures) { $notes.Add("API snapshot failed: $failure") }
    }

    # Local static data copy: file-by-file avoids Copy-Item's directory nesting
    # ambiguity and preserves every file under web/public/data recursively.
    $sourcePrefix = $StaticSource.TrimEnd('\') + '\'
    foreach ($sourceFile in @(Get-FilesRecursively $StaticSource)) {
        $relativePath = $sourceFile.FullName.Substring($sourcePrefix.Length)
        $destination = Join-Path $StaticDir $relativePath
        [void][System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($destination))
        [System.IO.File]::Copy($sourceFile.FullName, $destination, $false)
    }

    function Get-WranglerApiHeaders {
        $headers = @{}
        if ($env:CLOUDFLARE_API_TOKEN) {
            $headers['Authorization'] = 'Bearer ' + $env:CLOUDFLARE_API_TOKEN
            return $headers
        }
        if ($env:CLOUDFLARE_API_KEY -and $env:CLOUDFLARE_EMAIL) {
            $headers['X-Auth-Key'] = $env:CLOUDFLARE_API_KEY
            $headers['X-Auth-Email'] = $env:CLOUDFLARE_EMAIL
            return $headers
        }
        $wranglerConfig = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.wrangler\config\default.toml'
        if (Test-Path -LiteralPath $wranglerConfig -PathType Leaf) {
            $configText = Get-Content -LiteralPath $wranglerConfig -Raw
            $tokenMatch = [regex]::Match($configText, '(?m)^oauth_token\s*=\s*"([^"]+)"')
            if ($tokenMatch.Success) {
                $headers['Authorization'] = 'Bearer ' + $tokenMatch.Groups[1].Value
                return $headers
            }
        }
        return $null
    }

    $whoamiResult = Invoke-Wrangler @('whoami', '--json')
    $accountId = $env:CLOUDFLARE_ACCOUNT_ID
    if ($whoamiResult.ExitCode -eq 0) {
        try {
            $whoami = $whoamiResult.Output | ConvertFrom-Json
            $accounts = @($whoami.accounts)
            if (-not $accountId -and $accounts.Count -eq 1) { $accountId = [string]$accounts[0].id }
        } catch {
            $notes.Add("Wrangler account discovery failed: $($_.Exception.Message)")
        }
    }
    $apiHeaders = Get-WranglerApiHeaders
    $bucketSections = [ordered]@{}
    $publicArtifactsTotal = $null
    $publicArtifactsObjects = @()

    foreach ($bucketName in @('localbench-submissions', 'localbench-public-artifacts')) {
        $bucketLogPath = Join-Path $R2Dir ($bucketName + '-bucket-info.log')
        $bucketInfo = Invoke-Wrangler @('r2', 'bucket', 'info', $bucketName)
        Write-TextUtf8 $bucketLogPath ($bucketInfo.Output + "`n")
        $bucketState = [ordered]@{ inventory = 'pending-auth'; download = 'not-applicable'; object_count = 0; total_bytes = 0 }
        if ($bucketName -eq 'localbench-submissions') { $bucketState.download = 'inventory-only-policy' }

        try {
            if ($bucketInfo.ExitCode -ne 0) { throw "wrangler bucket info failed: $(Last-NonEmptyLine $bucketInfo.Output)" }
            if (-not $accountId) { throw 'Cloudflare account id is unavailable; set CLOUDFLARE_ACCOUNT_ID when Wrangler has multiple accounts' }
            if ($null -eq $apiHeaders) { throw 'Wrangler/API authentication credential is unavailable' }
            $encodedBucket = [Uri]::EscapeDataString($bucketName)
            $inventoryBaseUri = "https://api.cloudflare.com/client/v4/accounts/$accountId/r2/buckets/$encodedBucket/objects"
            $rawObjectList = New-Object 'System.Collections.Generic.List[object]'
            $inventoryCursors = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::Ordinal)
            $inventoryCursor = $null
            $inventoryPage = 1
            do {
                $inventoryUri = $inventoryBaseUri + '?per_page=1000'
                if ($null -ne $inventoryCursor) { $inventoryUri += '&cursor=' + [Uri]::EscapeDataString($inventoryCursor) }
                $inventoryResponse = Invoke-RestMethod -UseBasicParsing -Method Get -Uri $inventoryUri -Headers $apiHeaders -TimeoutSec 120
                if (-not $inventoryResponse.success) { throw 'Cloudflare R2 inventory API returned success=false' }
                foreach ($rawObject in @($inventoryResponse.result)) { $rawObjectList.Add($rawObject) }
                $resultInfoProperty = $inventoryResponse.PSObject.Properties['result_info']
                $inventoryTruncated = $null -ne $resultInfoProperty -and $resultInfoProperty.Value.is_truncated -eq $true
                if ($inventoryTruncated) {
                    $inventoryCursor = [string]$resultInfoProperty.Value.cursor
                    if (-not $inventoryCursor) { throw 'R2 inventory response is truncated without a cursor' }
                    if (-not $inventoryCursors.Add($inventoryCursor)) { throw 'R2 inventory response repeated a cursor' }
                } else {
                    $inventoryCursor = $null
                }
                $inventoryPage++
                if ($inventoryPage -gt 10000) { throw 'R2 inventory pagination exceeded 10000 pages' }
            } while ($null -ne $inventoryCursor)
            $rawObjects = $rawObjectList.ToArray()
            $expectedCountMatch = [regex]::Match($bucketInfo.Output, '(?m)^object_count:\s+(\d+)\s*$')
            if (-not $expectedCountMatch.Success) { throw 'wrangler bucket info did not report object_count' }
            $expectedCount = [int64]$expectedCountMatch.Groups[1].Value
            if ($rawObjects.Count -ne $expectedCount) {
                throw "inventory count $($rawObjects.Count) does not match wrangler object_count $expectedCount"
            }

            $inventory = New-Object 'System.Collections.Generic.List[object]'
            [long]$bucketBytes = 0
            foreach ($object in @($rawObjects | Sort-Object key)) {
                $key = [string]$object.key
                $keyBytes = $Utf8NoBom.GetBytes($key)
                $sha = [System.Security.Cryptography.SHA256]::Create()
                try { $archiveName = ([System.BitConverter]::ToString($sha.ComputeHash($keyBytes))).Replace('-', '').ToLowerInvariant() + '.object' } finally { $sha.Dispose() }
                [long]$size = $object.size
                $bucketBytes += $size
                $inventory.Add([ordered]@{
                    key = $key
                    size = $size
                    etag = [string]$object.etag
                    uploaded = [string]$object.last_modified
                    archive_path = if ($bucketName -eq 'localbench-public-artifacts') { 'localbench-public-artifacts/' + $archiveName } else { $null }
                })
            }
            Write-JsonFile (Join-Path $R2Dir ($bucketName + '-inventory.json')) $inventory.ToArray()
            $bucketState.inventory = 'complete'
            $bucketState.object_count = $inventory.Count
            $bucketState.total_bytes = $bucketBytes
            if ($bucketName -eq 'localbench-public-artifacts') {
                $publicArtifactsTotal = $bucketBytes
                $publicArtifactsObjects = $inventory.ToArray()
            }
        } catch {
            $r2InstructionsNeeded = $true
            $bucketState.inventory = 'pending-auth'
            $notes.Add("R2 inventory pending for ${bucketName}: $($_.Exception.Message)")
        }
        $bucketSections[$bucketName] = $bucketState
    }

    if ($null -ne $publicArtifactsTotal) {
        if ($publicArtifactsTotal -lt $PublicArtifactsLimitBytes) {
            $downloadDir = Join-Path $R2Dir 'localbench-public-artifacts'
            [void][System.IO.Directory]::CreateDirectory($downloadDir)
            $downloadFailures = New-Object 'System.Collections.Generic.List[string]'
            Push-Location $WebDir
            try {
                foreach ($object in @($publicArtifactsObjects)) {
                    $destination = Join-Path $R2Dir ([string]$object.archive_path).Replace('/', '\')
                    $getResult = Invoke-Wrangler @('r2', 'object', 'get', ('localbench-public-artifacts/' + [string]$object.key), '--remote', '--file', $destination)
                    if ($getResult.ExitCode -ne 0) {
                        $downloadFailures.Add("$($object.key): $(Last-NonEmptyLine $getResult.Output)")
                        continue
                    }
                    if (-not (Test-Path -LiteralPath $destination -PathType Leaf) -or (Get-Item -LiteralPath $destination).Length -ne [long]$object.size) {
                        $downloadFailures.Add("$($object.key): downloaded size does not match inventory")
                    }
                }
            } finally {
                Pop-Location
            }
            if ($downloadFailures.Count -eq 0) {
                $bucketSections['localbench-public-artifacts'].download = 'complete'
            } else {
                $bucketSections['localbench-public-artifacts'].download = 'partial'
                foreach ($failure in $downloadFailures) { $notes.Add("R2 download failed: $failure") }
            }
        } else {
            $bucketSections['localbench-public-artifacts'].download = 'inventory-only-size-threshold'
            $notes.Add("localbench-public-artifacts is $publicArtifactsTotal bytes (at least 2 GiB); inventory only")
        }
    }

    if ($r2InstructionsNeeded) {
        $r2Instructions = @"
# R2 inventory pending authentication

Wrangler could not complete one or both production R2 inventories. Do not invent object keys or substitute a local bucket.

From the repository root, authenticate Wrangler and rerun the exporter so a new, fully sealed archive is created:

    Set-Location "$RepoRoot"
    npx --no-install wrangler login
    npx --no-install wrangler r2 bucket info localbench-submissions
    npx --no-install wrangler r2 bucket info localbench-public-artifacts
    powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\archive-v1-export.ps1

If Wrangler reports multiple accounts, set CLOUDFLARE_ACCOUNT_ID before rerunning. A scoped CLOUDFLARE_API_TOKEN with D1 read and R2 read permissions may be used instead of interactive OAuth.
"@
        Write-TextUtf8 (Join-Path $R2Dir 'EXPORT-INSTRUCTIONS.md') $r2Instructions
    }

    $gitShaResult = @(& git -C $RepoRoot rev-parse HEAD 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "git rev-parse HEAD failed: $($gitShaResult -join ' ')" }
    $gitSha = ($gitShaResult -join '').Trim()
    $branchResult = @(& git -C $RepoRoot branch --show-current 2>&1)
    if ($LASTEXITCODE -ne 0) { throw "git branch --show-current failed: $($branchResult -join ' ')" }
    $branch = ($branchResult -join '').Trim()

    $wranglerLogPath = Join-Path $ArchiveDir 'wrangler.log'
    if (Test-Path -LiteralPath $wranglerLogPath -PathType Leaf) {
        Write-TextUtf8 $wranglerLogPath (Protect-WranglerLog (Get-Content -LiteralPath $wranglerLogPath -Raw))
    }

    $metrics = Get-ArchiveMetrics $ArchiveDir
    $r2Status = 'complete'
    if ($r2InstructionsNeeded) { $r2Status = 'pending-auth' }
    if ($bucketSections['localbench-public-artifacts'].download -eq 'partial') { $r2Status = 'partial' }
    $apiStatus = if ($apiFailures.Count -eq 0) { 'complete' } else { 'partial' }
    $manifest = [ordered]@{
        cutoff_utc = $cutoff.ToString('o')
        git_sha = $gitSha
        branch = $branch
        tag = $ArchiveTag
        tool_versions = [ordered]@{
            wrangler = $wranglerVersion
            node = $nodeVersion
            pwsh = $PSVersionTable.PSVersion.ToString()
        }
        sections = [ordered]@{
            db = [ordered]@{ db_export = $dbExportStatus; file_count = $metrics.db_files }
            api_snapshots = [ordered]@{ status = $apiStatus; file_count = $metrics.api_snapshot_files; failed_requests = $apiFailures.Count }
            static_data = [ordered]@{ status = 'complete'; file_count = $metrics.static_data_files }
            r2 = [ordered]@{ status = $r2Status; file_count = $metrics.r2_files; buckets = $bucketSections }
        }
        counts = [ordered]@{
            files = $metrics.files
            db_files = $metrics.db_files
            api_snapshot_files = $metrics.api_snapshot_files
            static_data_files = $metrics.static_data_files
            r2_files = $metrics.r2_files
            r2_inventory_objects = $metrics.r2_inventory_objects
            r2_downloaded_objects = $metrics.r2_downloaded_objects
        }
        total_bytes = $metrics.total_bytes
        notes = $notes.ToArray()
    }
    Write-JsonFile (Join-Path $ArchiveDir 'archive-manifest.json') $manifest 16

    $checksumFiles = @(Get-FilesRecursively $ArchiveDir | Where-Object { $_.Name -ne 'SHA256SUMS' } | Sort-Object FullName)
    $checksumLines = New-Object 'System.Collections.Generic.List[string]'
    foreach ($file in $checksumFiles) {
        $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $relativePath = Get-RelativeArchivePath $ArchiveDir $file.FullName
        $checksumLines.Add("$hash  $relativePath")
    }
    Write-TextUtf8 (Join-Path $ArchiveDir 'SHA256SUMS') (($checksumLines -join "`n") + "`n")

    Test-Archive $ArchiveDir
    Write-Host "Archive created: $ArchiveDir" -ForegroundColor Green
} finally {
    if ($null -eq $oldLogPath) { Remove-Item Env:WRANGLER_LOG_PATH -ErrorAction SilentlyContinue } else { $env:WRANGLER_LOG_PATH = $oldLogPath }
    if ($null -eq $oldMetrics) { Remove-Item Env:WRANGLER_SEND_METRICS -ErrorAction SilentlyContinue } else { $env:WRANGLER_SEND_METRICS = $oldMetrics }
}
