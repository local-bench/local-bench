<#
.SYNOPSIS
  Build a clean PUBLIC snapshot of the local-bench repo (fresh directory, no git
  history) ready to become github.com/local-bench/local-bench (Apache-2.0).

.DESCRIPTION
  Wave-4 public-repo snapshot tool. Deterministic given an identical source tree:

    1. COPY the working tree to -OutDir, excluding git history, dependency/build
       caches, run artifacts (except the frozen board fixture
       cli/runs/board/board_v1.json, which the test suite requires), private ops
       docs (docs/deploy/, docs/briefs/), local scratch dirs, and any file whose
       NAME matches a secret-ish pattern (*secret*, *token*, *.pem, .env*, *.key).
       When git is available, gitignored files are additionally filtered out.
       This script excludes ITSELF from the snapshot (it embeds the private scrub
       terms and machine-specific paths).

    2. SCRUB CHECK (report only -- never edits): scans the SNAPSHOT for
         (a) "clarityconsultive"            (work email identity)
         (b) "Papa-midnight-dev"            (private deploy repo name)
         (c) secret-env literal VALUES      (ADMIN_API_SECRET-family assignments;
                                             the env var NAME alone is fine)
         (d) absolute paths containing      C:\Users\Michael (any slash style,
                                             incl. JSON-escaped)
         (e) secret-named files             (*.pem / *token* / *secret* / .env* /
                                             *.key that slipped through the copy)
         (f) well-known credential formats  (sk-ant-, ghp_, github_pat_, AKIA,
                                             xox?-, BEGIN PRIVATE KEY)
       plus non-blocking ADVISORIES (personal name/email fragments, deployment
       ids). Findings are printed as a table and written to a scrub report NEXT TO
       the snapshot (never inside it).

    3. LICENSE: if the snapshot has no LICENSE file, writes the full Apache-2.0
       text with the line "Copyright 2026 local-bench contributors". An existing
       LICENSE is NEVER overwritten -- its status is reported instead (the current
       repo LICENSE is a "NOT YET CHOSEN" placeholder, which is a publish
       blocker until the owner replaces it with Apache-2.0).

    4. SUMMARY: file count, total size, license status, scrub verdict.

.PARAMETER SourceRoot
  Repo root to snapshot. Default: the parent of this script's directory.

.PARAMETER OutDir
  Snapshot destination. Default: C:\Users\Michael\local-bench-public-snapshot
  Must be OUTSIDE the source tree. If it exists and is non-empty, pass -Force to
  wipe and rebuild it. A directory containing .git is never deleted.

.PARAMETER Force
  Delete an existing non-empty OutDir before copying.

.OUTPUTS
  Exit 0 = snapshot built, scrub clean, license OK (Apache-2.0 present/created).
  Exit 2 = scrub findings present (see <OutDir>-scrub-report.md). BLOCKER.
  Exit 3 = scrub clean but LICENSE is a placeholder / not Apache-2.0. BLOCKER.
  Exit 1 = usage or fatal error.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\publish-snapshot.ps1 -Force
#>
[CmdletBinding()]
param(
    [string]$SourceRoot,
    [string]$OutDir = 'C:\Users\Michael\local-bench-public-snapshot',
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$ScriptVersion = '1.2.0 (wave-4)'
$SelfRelPath   = 'scripts\publish-snapshot.ps1'   # excluded from the snapshot

# --------------------------------------------------------------------------
# Exclusion rules (documented in docs/deploy/public-snapshot-manifest.md)
# --------------------------------------------------------------------------

# Whole directories, matched by path relative to the source root (case-insensitive).
$PathPrunes = @(
    '.git',                    # git history -- snapshot is history-free by design
    'web\node_modules',        # npm dependency cache
    'web\.next',               # Next.js build output
    'web\out',                 # static export output
    'web\.e2e-artifacts',      # local Playwright artifacts
    'web\.qa',                 # local QA scratch
    'cli\.venv',               # Python virtualenv
    'cli\build',               # Python build artifacts
    'cli\$tmpdir',             # stray literal $tmpdir scratch dir
    'cli\runs',                # run artifacts (board_v1.json re-added explicitly)
    'docs\deploy',             # private ops docs (deployment ids, token paths)
    'docs\briefs',             # internal agent build briefs (machine paths)
    'runs',                    # top-level local run/monitor artifacts
    'tmp',                     # local scratch
    'data',                    # local dataset cache (data\cache)
    'suite\v0\private',        # private held-out items -- never publish
    '.agents', '.omo', '.codegraph', '.superpowers',
    '.pytest-review', '.pytest-tmp', '.pytest_cache', '.ruff_cache'
)

# Directories pruned wherever they appear, by name.
$NamePrunes = @(
    '.git', 'node_modules', '__pycache__', '.pytest_cache', '.ruff_cache',
    '.mypy_cache', '.venv', '.idea', '.vscode', '.next', '.wrangler',
    '.vercel', '.turbo'
)
$NamePruneWildcards = @('*.egg-info')

# Files excluded wherever they appear, by leaf name (case-insensitive wildcards).
# ALWAYS applies, even to git-tracked files (secret-ish names must never ship).
$FileExcludeAlways = @(
    '*secret*', '*token*', '*.pem', '.env*', '*.key',
    'thumbs.db', '.ds_store', 'desktop.ini'
)
# Applies only to files NOT tracked by git (local noise). Tracked files matching
# these are intentional fixtures (e.g. cli/tests/fixtures/kld/*.log) and ship.
$FileExcludeUntrackedOnly = @(
    '*.log', '*.pyc', '*.pyo', '*.tsbuildinfo', '*.run.json'
)

# Dot-files allowed at the snapshot ROOT (all other root dot-files are local state).
$RootDotFileAllow = @('.gitignore', '.gitattributes', '.editorconfig')
# Dot-dirs allowed at the snapshot ROOT.
$RootDotDirAllow  = @('.github')

# Single-file re-include: frozen board fixture required by cli tests
# (cli/tests/test_site_parity.py, cli/tests/submissions/test_wave2_static_composite.py).
$ReIncludeRel = 'cli\runs\board\board_v1.json'

# File extensions treated as binary (skipped by the content scrub).
$BinaryExtensions = @(
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.bmp', '.svgz',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    '.pdf', '.zip', '.gz', '.tgz', '.tar', '.7z', '.rar',
    '.exe', '.dll', '.pyd', '.so', '.dylib', '.wasm', '.jar', '.class',
    '.gguf', '.bin', '.pt', '.onnx', '.npz', '.npy', '.parquet',
    '.sqlite', '.db', '.mp3', '.mp4', '.webm', '.mov'
)
$MaxScanBytes = 50MB

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

function Write-Step([string]$msg) { Write-Host "[publish-snapshot] $msg" }

function Invoke-GitQuiet {
    param([string[]]$GitArgs)
    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & git @GitArgs 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        return $out
    } catch {
        return $null
    } finally {
        $ErrorActionPreference = $old
    }
}

function Copy-FileRobust([string]$src, [string]$dst) {
    $dstDir = [System.IO.Path]::GetDirectoryName($dst)
    try {
        [void][System.IO.Directory]::CreateDirectory($dstDir)
        [System.IO.File]::Copy($src, $dst, $false)
    } catch [System.IO.PathTooLongException] {
        [void][System.IO.Directory]::CreateDirectory('\\?\' + $dstDir)
        [System.IO.File]::Copy('\\?\' + $src, '\\?\' + $dst, $false)
    }
}

function Read-TextRobust([string]$path) {
    try {
        return [System.IO.File]::ReadAllText($path)
    } catch [System.IO.PathTooLongException] {
        try { return [System.IO.File]::ReadAllText('\\?\' + $path) } catch { return $null }
    } catch {
        return $null
    }
}

function Write-TextLf([string]$path, [string]$content) {
    $enc = New-Object System.Text.UTF8Encoding($false)   # UTF-8, no BOM
    [System.IO.File]::WriteAllText($path, $content, $enc)
}

# Escape a snippet for a one-row-per-finding markdown table.
function Format-Snippet([string]$lineText, [int]$colInLine) {
    $s = $lineText.Trim()
    if ($s.Length -gt 160) {
        $center = [Math]::Max(0, [Math]::Min($colInLine, $s.Length - 1))
        $start  = [Math]::Max(0, $center - 70)
        $len    = [Math]::Min(150, $s.Length - $start)
        $s = '...' + $s.Substring($start, $len) + '...'
    }
    $s = $s -replace '\|', '\|'
    $s = $s -replace '`', "'"
    return $s
}

# --------------------------------------------------------------------------
# Resolve + validate paths
# --------------------------------------------------------------------------

if (-not $SourceRoot) {
    $SourceRoot = Split-Path -Parent $PSScriptRoot
}
if (-not (Test-Path -LiteralPath $SourceRoot -PathType Container)) {
    Write-Error "SourceRoot not found: $SourceRoot"; exit 1
}
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).ProviderPath.TrimEnd('\')
if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot 'README.md')) -or
    -not (Test-Path -LiteralPath (Join-Path $SourceRoot 'cli'))) {
    Write-Error "SourceRoot does not look like the local-bench repo root: $SourceRoot"; exit 1
}

$OutDir = [System.IO.Path]::GetFullPath($OutDir).TrimEnd('\')
$srcCmp = $SourceRoot.ToLowerInvariant() + '\'
$outCmp = $OutDir.ToLowerInvariant() + '\'
if ($outCmp -eq $srcCmp -or $outCmp.StartsWith($srcCmp)) {
    Write-Error "OutDir must be OUTSIDE the source tree (got: $OutDir)"; exit 1
}
if ($srcCmp.StartsWith($outCmp)) {
    Write-Error "OutDir contains the source tree -- refusing (got: $OutDir)"; exit 1
}

if (Test-Path -LiteralPath $OutDir) {
    if (Test-Path -LiteralPath (Join-Path $OutDir '.git')) {
        Write-Error "OutDir contains a .git directory -- refusing to touch it: $OutDir"; exit 1
    }
    $existing = @(Get-ChildItem -LiteralPath $OutDir -Force -ErrorAction SilentlyContinue)
    if ($existing.Count -gt 0) {
        if (-not $Force) {
            Write-Error "OutDir exists and is not empty. Pass -Force to wipe and rebuild: $OutDir"; exit 1
        }
        Write-Step "Removing existing snapshot: $OutDir"
        Remove-Item -LiteralPath $OutDir -Recurse -Force
    }
}
[void][System.IO.Directory]::CreateDirectory($OutDir)

$ReportPath = "$OutDir-scrub-report.md"

# --------------------------------------------------------------------------
# Provenance (recorded in the report; no wall-clock values, so re-runs on an
# identical tree produce an identical report)
# --------------------------------------------------------------------------

$gitHead   = Invoke-GitQuiet @('-C', $SourceRoot, 'rev-parse', 'HEAD')
$gitBranch = Invoke-GitQuiet @('-C', $SourceRoot, 'rev-parse', '--abbrev-ref', 'HEAD')
$gitDirty  = Invoke-GitQuiet @('-C', $SourceRoot, 'status', '--porcelain')
$dirtyCount = 0
if ($null -ne $gitDirty) { $dirtyCount = @($gitDirty).Count }
if ($null -eq $gitHead)   { $gitHead = 'unavailable (git not found or not a repo)' }
if ($null -eq $gitBranch) { $gitBranch = 'unavailable' }

Write-Step "Source : $SourceRoot"
Write-Step "HEAD   : $gitHead ($gitBranch, $dirtyCount dirty file(s) at copy time)"
Write-Step "OutDir : $OutDir"

# Tracked-file set (used to exempt tracked fixtures from the noise-pattern
# excludes). Empty when git is unavailable, in which case noise patterns apply
# to every file.
$trackedSet = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
$lsFiles = Invoke-GitQuiet @('-C', $SourceRoot, 'ls-files')
if ($null -ne $lsFiles) {
    foreach ($t in @($lsFiles)) {
        if ($t) { [void]$trackedSet.Add($t.Replace('/', '\')) }
    }
}

# --------------------------------------------------------------------------
# 1) Walk the working tree, applying exclusions
# --------------------------------------------------------------------------

$candidates    = New-Object System.Collections.Generic.List[object]
$prunedDirs    = New-Object System.Collections.Generic.List[string]
$excludedFiles = New-Object System.Collections.Generic.List[string]
$reparseSkips  = New-Object System.Collections.Generic.List[string]
$walkErrors    = New-Object System.Collections.Generic.List[string]

$namePruneSet = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
foreach ($n in $NamePrunes) { [void]$namePruneSet.Add($n) }
$pathPruneSet = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
foreach ($p in $PathPrunes) { [void]$pathPruneSet.Add($p) }

$stack = New-Object 'System.Collections.Generic.Stack[string]'
$stack.Push($SourceRoot)

while ($stack.Count -gt 0) {
    $dir = $stack.Pop()
    $entries = $null
    try {
        $entries = [System.IO.Directory]::GetFileSystemEntries($dir)
    } catch {
        $walkErrors.Add("ENUMERATE-FAILED: $dir ($($_.Exception.Message))")
        continue
    }
    [Array]::Sort($entries, [StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in $entries) {
        $rel  = $entry.Substring($SourceRoot.Length).TrimStart('\')
        $leaf = [System.IO.Path]::GetFileName($entry)
        $attr = $null
        try { $attr = [System.IO.File]::GetAttributes($entry) } catch {
            $walkErrors.Add("ATTR-FAILED: $rel ($($_.Exception.Message))")
            continue
        }
        if (($attr -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            $reparseSkips.Add($rel)
            continue
        }
        $isDir = (($attr -band [System.IO.FileAttributes]::Directory) -ne 0)
        $isRootLevel = (-not $rel.Contains('\'))

        if ($isDir) {
            if ($pathPruneSet.Contains($rel)) { $prunedDirs.Add("$rel  [path-prune]"); continue }
            if ($namePruneSet.Contains($leaf)) { $prunedDirs.Add("$rel  [name-prune: $leaf]"); continue }
            $wildHit = $false
            foreach ($w in $NamePruneWildcards) {
                if ($leaf -like $w) { $prunedDirs.Add("$rel  [name-prune: $w]"); $wildHit = $true; break }
            }
            if ($wildHit) { continue }
            if ($isRootLevel -and $leaf.StartsWith('.') -and ($RootDotDirAllow -notcontains $leaf)) {
                $prunedDirs.Add("$rel  [root-dot-dir]"); continue
            }
            $stack.Push($entry)
        } else {
            if ($rel -ieq $SelfRelPath) { $excludedFiles.Add("$rel  [self: publish tooling stays private]"); continue }
            if ($isRootLevel -and $leaf.StartsWith('.') -and ($RootDotFileAllow -notcontains $leaf)) {
                $excludedFiles.Add("$rel  [root-dot-file]"); continue
            }
            $patHit = $null
            foreach ($pat in $FileExcludeAlways) {
                if ($leaf -like $pat) { $patHit = $pat; break }
            }
            if ($null -ne $patHit) { $excludedFiles.Add("$rel  [file-pattern: $patHit]"); continue }
            if (-not $trackedSet.Contains($rel)) {
                foreach ($pat in $FileExcludeUntrackedOnly) {
                    if ($leaf -like $pat) { $patHit = $pat; break }
                }
                if ($null -ne $patHit) { $excludedFiles.Add("$rel  [file-pattern, untracked: $patHit]"); continue }
            }
            $len = 0
            try { $len = ([System.IO.FileInfo]::new($entry)).Length } catch { $len = 0 }
            $candidates.Add([pscustomobject]@{ Rel = $rel; Full = $entry; Length = $len })
        }
    }
}

Write-Step "Walk complete: $($candidates.Count) candidate file(s) before gitignore filter."

# --------------------------------------------------------------------------
# 1b) Filter out gitignored files (belt-and-braces on top of the hard rules)
# --------------------------------------------------------------------------

$gitAvailable = ($gitHead -notlike 'unavailable*')
$ignoredSet = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
if ($gitAvailable) {
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = 'git'
        $psi.Arguments = "-C ""$SourceRoot"" check-ignore --stdin"
        $psi.RedirectStandardInput  = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError  = $true
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow  = $true
        $proc = [System.Diagnostics.Process]::Start($psi)
        $outTask = $proc.StandardOutput.ReadToEndAsync()
        $errTask = $proc.StandardError.ReadToEndAsync()
        foreach ($c in $candidates) {
            $proc.StandardInput.Write($c.Rel.Replace('\', '/') + "`n")
        }
        $proc.StandardInput.Close()
        $proc.WaitForExit()
        foreach ($line in ($outTask.Result -split "`n")) {
            $t = $line.Trim("`r", ' ')
            if ($t) { [void]$ignoredSet.Add($t.Replace('/', '\')) }
        }
    } catch {
        Write-Step "WARNING: git check-ignore filter failed ($($_.Exception.Message)); relying on hard rules only."
    }
} else {
    Write-Step 'WARNING: git unavailable; gitignore filter skipped (hard rules still applied).'
}

$copyList = New-Object System.Collections.Generic.List[object]
foreach ($c in $candidates) {
    if ($ignoredSet.Contains($c.Rel)) { $excludedFiles.Add("$($c.Rel)  [gitignored]") }
    else { $copyList.Add($c) }
}

# --------------------------------------------------------------------------
# 2) Copy
# --------------------------------------------------------------------------

$sorted = $copyList | Sort-Object -Property @{ Expression = { $_.Rel.ToLowerInvariant() } }
$copiedCount = 0
[long]$copiedBytes = 0
foreach ($c in $sorted) {
    Copy-FileRobust $c.Full (Join-Path $OutDir $c.Rel)
    $copiedCount++
    $copiedBytes += $c.Length
}

# Single-file re-include: frozen board fixture needed by cli tests.
$boardNote = ''
$boardSrc = Join-Path $SourceRoot $ReIncludeRel
if (Test-Path -LiteralPath $boardSrc -PathType Leaf) {
    Copy-FileRobust $boardSrc (Join-Path $OutDir $ReIncludeRel)
    $copiedCount++
    $copiedBytes += ([System.IO.FileInfo]::new($boardSrc)).Length
    $boardNote = "re-included: $ReIncludeRel (frozen fixture required by cli tests)"
} else {
    $boardNote = "WARNING: $ReIncludeRel NOT FOUND in source -- cli tests in the snapshot will fail without it."
}
Write-Step $boardNote
Write-Step "Copied $copiedCount file(s), $copiedBytes bytes."

# --------------------------------------------------------------------------
# 3) LICENSE (Apache-2.0) -- never overwrites an existing LICENSE
# --------------------------------------------------------------------------

$ApacheLicenseText = @'
                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

      "Licensor" shall mean the copyright owner or entity authorized by
      the copyright owner that is granting the License.

      "Legal Entity" shall mean the union of the acting entity and all
      other entities that control, are controlled by, or are under common
      control with that entity. For the purposes of this definition,
      "control" means (i) the power, direct or indirect, to cause the
      direction or management of such entity, whether by contract or
      otherwise, or (ii) ownership of fifty percent (50%) or more of the
      outstanding shares, or (iii) beneficial ownership of such entity.

      "You" (or "Your") shall mean an individual or Legal Entity
      exercising permissions granted by this License.

      "Source" form shall mean the preferred form for making modifications,
      including but not limited to software source code, documentation
      source, and configuration files.

      "Object" form shall mean any form resulting from mechanical
      transformation or translation of a Source form, including but
      not limited to compiled object code, generated documentation,
      and conversions to other media types.

      "Work" shall mean the work of authorship, whether in Source or
      Object form, made available under the License, as indicated by a
      copyright notice that is included in or attached to the work
      (an example is provided in the Appendix below).

      "Derivative Works" shall mean any work, whether in Source or Object
      form, that is based on (or derived from) the Work and for which the
      editorial revisions, annotations, elaborations, or other modifications
      represent, as a whole, an original work of authorship. For the purposes
      of this License, Derivative Works shall not include works that remain
      separable from, or merely link (or bind by name) to the interfaces of,
      the Work and Derivative Works thereof.

      "Contribution" shall mean any work of authorship, including
      the original version of the Work and any modifications or additions
      to that Work or Derivative Works thereof, that is intentionally
      submitted to Licensor for inclusion in the Work by the copyright owner
      or by an individual or Legal Entity authorized to submit on behalf of
      the copyright owner. For the purposes of this definition, "submitted"
      means any form of electronic, verbal, or written communication sent
      to the Licensor or its representatives, including but not limited to
      communication on electronic mailing lists, source code control systems,
      and issue tracking systems that are managed by, or on behalf of, the
      Licensor for the purpose of discussing and improving the Work, but
      excluding communication that is conspicuously marked or otherwise
      designated in writing by the copyright owner as "Not a Contribution."

      "Contributor" shall mean Licensor and any individual or Legal Entity
      on behalf of whom a Contribution has been received by Licensor and
      subsequently incorporated within the Work.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      (except as stated in this section) patent license to make, have made,
      use, offer to sell, sell, import, and otherwise transfer the Work,
      where such license applies only to those patent claims licensable
      by such Contributor that are necessarily infringed by their
      Contribution(s) alone or by combination of their Contribution(s)
      with the Work to which such Contribution(s) was submitted. If You
      institute patent litigation against any entity (including a
      cross-claim or counterclaim in a lawsuit) alleging that the Work
      or a Contribution incorporated within the Work constitutes direct
      or contributory patent infringement, then any patent licenses
      granted to You under this License for that Work shall terminate
      as of the date such litigation is filed.

   4. Redistribution. You may reproduce and distribute copies of the
      Work or Derivative Works thereof in any medium, with or without
      modifications, and in Source or Object form, provided that You
      meet the following conditions:

      (a) You must give any other recipients of the Work or
          Derivative Works a copy of this License; and

      (b) You must cause any modified files to carry prominent notices
          stating that You changed the files; and

      (c) You must retain, in the Source form of any Derivative Works
          that You distribute, all copyright, patent, trademark, and
          attribution notices from the Source form of the Work,
          excluding those notices that do not pertain to any part of
          the Derivative Works; and

      (d) If the Work includes a "NOTICE" text file as part of its
          distribution, then any Derivative Works that You distribute must
          include a readable copy of the attribution notices contained
          within such NOTICE file, excluding those notices that do not
          pertain to any part of the Derivative Works, in at least one
          of the following places: within a NOTICE text file distributed
          as part of the Derivative Works; within the Source form or
          documentation, if provided along with the Derivative Works; or,
          within a display generated by the Derivative Works, if and
          wherever such third-party notices normally appear. The contents
          of the NOTICE file are for informational purposes only and
          do not modify the License. You may add Your own attribution
          notices within Derivative Works that You distribute, alongside
          or as an addendum to the NOTICE text from the Work, provided
          that such additional attribution notices cannot be construed
          as modifying the License.

      You may add Your own copyright statement to Your modifications and
      may provide additional or different license terms and conditions
      for use, reproduction, or distribution of Your modifications, or
      for any such Derivative Works as a whole, provided Your use,
      reproduction, and distribution of the Work otherwise complies with
      the conditions stated in this License.

   5. Submission of Contributions. Unless You explicitly state otherwise,
      any Contribution intentionally submitted for inclusion in the Work
      by You to the Licensor shall be under the terms and conditions of
      this License, without any additional terms or conditions.
      Notwithstanding the above, nothing herein shall supersede or modify
      the terms of any separate license agreement you may have executed
      with Licensor regarding such Contributions.

   6. Trademarks. This License does not grant permission to use the trade
      names, trademarks, service marks, or product names of the Licensor,
      except as required for reasonable and customary use in describing the
      origin of the Work and reproducing the content of the NOTICE file.

   7. Disclaimer of Warranty. Unless required by applicable law or
      agreed to in writing, Licensor provides the Work (and each
      Contributor provides its Contributions) on an "AS IS" BASIS,
      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
      implied, including, without limitation, any warranties or conditions
      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
      PARTICULAR PURPOSE. You are solely responsible for determining the
      appropriateness of using or redistributing the Work and assume any
      risks associated with Your exercise of permissions under this License.

   8. Limitation of Liability. In no event and under no legal theory,
      whether in tort (including negligence), contract, or otherwise,
      unless required by applicable law (such as deliberate and grossly
      negligent acts) or agreed to in writing, shall any Contributor be
      liable to You for damages, including any direct, indirect, special,
      incidental, or consequential damages of any character arising as a
      result of this License or out of the use or inability to use the
      Work (including but not limited to damages for loss of goodwill,
      work stoppage, computer failure or malfunction, or any and all
      other commercial damages or losses), even if such Contributor
      has been advised of the possibility of such damages.

   9. Accepting Warranty or Additional Liability. While redistributing
      the Work or Derivative Works thereof, You may choose to offer,
      and charge a fee for, acceptance of support, warranty, indemnity,
      or other liability obligations and/or rights consistent with this
      License. However, in accepting such obligations, You may act only
      on Your own behalf and on Your sole responsibility, not on behalf
      of any other Contributor, and only if You agree to indemnify,
      defend, and hold each Contributor harmless for any liability
      incurred by, or claims asserted against, such Contributor by reason
      of your accepting any such warranty or additional liability.

   END OF TERMS AND CONDITIONS

   APPENDIX: How to apply the Apache License to your work.

      To apply the Apache License to your work, attach the following
      boilerplate notice, with the fields enclosed by brackets "[]"
      replaced with your own identifying information. (Don't include
      the brackets!)  The text should be enclosed in the appropriate
      comment syntax for the file format. We also recommend that a
      file or class name and description of purpose be included on the
      same "printed page" as the copyright notice for easier
      identification within third-party archives.

   Copyright 2026 local-bench contributors

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
'@

$licenseStatus = ''
$licenseBlocker = $false
$existingLicense = @(Get-ChildItem -LiteralPath $OutDir -File -Force |
    Where-Object { $_.Name -in @('LICENSE', 'LICENSE.md', 'LICENSE.txt', 'COPYING') })
if ($existingLicense.Count -eq 0) {
    Write-TextLf (Join-Path $OutDir 'LICENSE') $ApacheLicenseText
    $licenseStatus = 'CREATED: LICENSE written with full Apache-2.0 text (Copyright 2026 local-bench contributors).'
} else {
    $licFile = $existingLicense[0]
    $licText = Read-TextRobust $licFile.FullName
    if ($null -eq $licText) { $licText = '' }
    if ($licText -match 'Apache License' -and $licText -match 'Version 2\.0') {
        $licenseStatus = "PRESERVED: existing $($licFile.Name) already contains the Apache-2.0 text; not overwritten."
    } elseif ($licText -match 'NOT YET CHOSEN' -or $licText -match 'PLACEHOLDER') {
        $licenseStatus = "BLOCKER: existing $($licFile.Name) is the 'NOT YET CHOSEN' placeholder (all rights reserved). NOT overwritten. Owner must replace it with the Apache-2.0 text (locked decision) before publishing."
        $licenseBlocker = $true
    } else {
        $licenseStatus = "BLOCKER: existing $($licFile.Name) is present but is NOT Apache-2.0. NOT overwritten. Reconcile with the locked Apache-2.0 decision before publishing."
        $licenseBlocker = $true
    }
}
Write-Step "License: $licenseStatus"

# --------------------------------------------------------------------------
# 4) Scrub check (report only -- never edits the snapshot)
# --------------------------------------------------------------------------

Write-Step 'Scrub: scanning snapshot...'

$rxOpt   = [System.Text.RegularExpressions.RegexOptions]::Compiled
$rxOptCI = $rxOpt -bor [System.Text.RegularExpressions.RegexOptions]::IgnoreCase

$ContentRules = @(
    [pscustomobject]@{ Id = 'A-clarityconsultive'; Severity = 'FAIL'
        Regex = New-Object regex('clarityconsultive', $rxOptCI)
        Note  = 'work email identity' }
    [pscustomobject]@{ Id = 'B-papa-midnight-dev'; Severity = 'FAIL'
        Regex = New-Object regex('papa-midnight-dev', $rxOptCI)
        Note  = 'private deploy repo name' }
    [pscustomobject]@{ Id = 'C-secret-env-literal'; Severity = 'FAIL'
        Regex = New-Object regex('(?<name>ADMIN_API_SECRET|LOCALBENCH_ADMIN_SECRET|LOCALBENCH_PRIVATE_BYPASS_TOKEN|R2_ACCESS_KEY_ID|R2_SECRET_ACCESS_KEY)\s*(?<op>[:=])\s*(?<val>[^\r\n]{1,200})', $rxOpt)
        Note  = 'secret env var assigned a literal value (name-only references are fine)' }
    [pscustomobject]@{ Id = 'D-abs-path-michael'; Severity = 'FAIL'
        Regex = New-Object regex('C:[\\/]+Users[\\/]+Michael', $rxOptCI)
        Note  = 'absolute path tied to owner machine' }
    [pscustomobject]@{ Id = 'F-credential-format'; Severity = 'FAIL'
        Regex = New-Object regex('sk-ant-[A-Za-z0-9_\-]{10,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{35}|xox[baprs]-[A-Za-z0-9\-]{10,}', $rxOpt)
        Note  = 'well-known credential format (downgraded to ADVISORY for test fixtures)' }
    [pscustomobject]@{ Id = 'K-private-key-block'; Severity = 'FAIL'
        Regex = New-Object regex('-----BEGIN [A-Z ]*PRIVATE KEY-----', $rxOpt)
        Note  = 'PEM private-key header (FAIL only when followed by key material outside tests)' }
    [pscustomobject]@{ Id = 'G-personal-name-advisory'; Severity = 'ADVISORY'
        Regex = New-Object regex('michael\.russell|mj_russell|Michael\s+Russell|ultimatedc', $rxOptCI)
        Note  = 'personal name/email fragment (advisory)' }
    [pscustomobject]@{ Id = 'H-deploy-id-advisory'; Severity = 'ADVISORY'
        Regex = New-Object regex('"database_id"\s*:\s*"[0-9a-fA-F\-]{8,}"', $rxOpt)
        Note  = 'deployment id in config (advisory -- decide before public push)' }
)

# Rule C post-filter: a match is benign when the assigned value is clearly not a
# literal secret (env indirection, identifier, type annotation, placeholder, short).
function Test-SecretValueBenign([string]$rawVal) {
    $v = $rawVal.Trim()
    if ($v.Length -eq 0) { return $true }
    # take first token / quoted literal
    if ($v[0] -eq '"' -or $v[0] -eq "'") {
        $q = $v[0]
        $end = $v.IndexOf($q, 1)
        if ($end -lt 0) { $v = $v.Substring(1) } else { $v = $v.Substring(1, $end - 1) }
    } else {
        $v = ($v -split '[\s;,})]')[0]
    }
    if ($v.Length -lt 8) { return $true }                        # too short to be a real secret
    if ($v -match '^[\$%<\[@]') { return $true }                 # $VAR, ${VAR}, %VAR%, <placeholder>, [REDACTED]
    if ($v -match '^[A-Za-z_][A-Za-z0-9_]*$' -and $v -notmatch '[0-9]') { return $true }  # bare identifier/type
    if ($v -match '(?i)env\.|environ|process\.env|getenv|\bsecrets\.|\bconfig\.|\boptions\.') { return $true }
    if ($v -match '(?i)placeholder|example|changeme|your[-_ ]|same value|redacted|dummy|unset|not[-_ ]?set|omitted|todo|tbd|fixture|sample|test|mock|fake') { return $true }
    return $false
}

# Test-fixture context: findings here are downgraded to ADVISORY (verify by eye,
# but hardcoded fixture values in tests are expected and publishable).
function Test-IsTestPath([string]$rel) {
    $r = $rel.Replace('\', '/').ToLowerInvariant()
    if ($r -match '(^|/)tests?(/|$)') { return $true }
    if ($r -match '\.test\.|\.spec\.|(^|/)fixtures?(/|\.)|conftest\.py$') { return $true }
    return $false
}

# Central severity resolution (all downgrade heuristics live here).
function Resolve-FindingSeverity([object]$rule, [System.Text.RegularExpressions.Match]$m, [string]$text, [string]$rel) {
    if ($rule.Severity -eq 'ADVISORY') { return 'ADVISORY' }
    switch ($rule.Id) {
        'C-secret-env-literal' {
            if (Test-IsTestPath $rel) { return 'ADVISORY' }
            return 'FAIL'
        }
        'F-credential-format' {
            if ($m.Value -match '(?i)test|example|dummy|fake|sample|mock') { return 'ADVISORY' }
            if (Test-IsTestPath $rel) { return 'ADVISORY' }
            return 'FAIL'
        }
        'K-private-key-block' {
            # FAIL only if actual base64 key material follows the header (raw or
            # string-embedded with literal \n); bare headers in code/assertions
            # are advisories.
            $tailStart = $m.Index + $m.Length
            $tailLen = [Math]::Min(220, $text.Length - $tailStart)
            $tail = ''
            if ($tailLen -gt 0) { $tail = $text.Substring($tailStart, $tailLen) }
            $hasBody = ($tail -match '^\s*(\\n|\r?\n)\s*["'']?[A-Za-z0-9+/=]{40,}')
            if (-not $hasBody) { return 'ADVISORY' }
            if (Test-IsTestPath $rel) { return 'ADVISORY' }
            return 'FAIL'
        }
        default { return $rule.Severity }
    }
}

# Snapshot file inventory (also computes final stats).
$snapFiles = New-Object System.Collections.Generic.List[object]
$snapStack = New-Object 'System.Collections.Generic.Stack[string]'
$snapStack.Push($OutDir)
while ($snapStack.Count -gt 0) {
    $d = $snapStack.Pop()
    $entries = [System.IO.Directory]::GetFileSystemEntries($d)
    [Array]::Sort($entries, [StringComparer]::OrdinalIgnoreCase)
    foreach ($e in $entries) {
        $a = [System.IO.File]::GetAttributes($e)
        if (($a -band [System.IO.FileAttributes]::Directory) -ne 0) { $snapStack.Push($e) }
        else {
            $fi = [System.IO.FileInfo]::new($e)
            $snapFiles.Add([pscustomobject]@{
                Rel = $e.Substring($OutDir.Length).TrimStart('\'); Full = $e; Length = $fi.Length })
        }
    }
}
$finalCount = $snapFiles.Count
[long]$finalBytes = 0
foreach ($f in $snapFiles) { $finalBytes += $f.Length }

$findings   = New-Object System.Collections.Generic.List[object]
$scanSkips  = New-Object System.Collections.Generic.List[string]

# (e) secret-NAMED files that slipped through the copy rules
$SecretNamePatterns = @('*.pem', '*token*', '*secret*', '.env*', '*.key')
foreach ($f in ($snapFiles | Sort-Object -Property @{ Expression = { $_.Rel.ToLowerInvariant() } })) {
    $leaf = [System.IO.Path]::GetFileName($f.Rel)
    foreach ($pat in $SecretNamePatterns) {
        if ($leaf -like $pat) {
            $findings.Add([pscustomobject]@{
                Severity = 'FAIL'; Rule = 'E-secret-named-file'; File = $f.Rel; Line = 0
                Snippet = "file name matches '$pat' -- should have been excluded by the copier" })
            break
        }
    }
}

# Content scan
foreach ($f in $snapFiles) {
    $ext = [System.IO.Path]::GetExtension($f.Rel).ToLowerInvariant()
    if ($BinaryExtensions -contains $ext) { continue }
    if ($f.Length -eq 0) { continue }
    if ($f.Length -gt $MaxScanBytes) { $scanSkips.Add("$($f.Rel)  [over $([int]($MaxScanBytes/1MB))MB -- not scanned]"); continue }
    $text = Read-TextRobust $f.Full
    if ($null -eq $text) { $scanSkips.Add("$($f.Rel)  [unreadable -- not scanned]"); continue }

    $nlPositions = $null
    foreach ($rule in $ContentRules) {
        $ms = $rule.Regex.Matches($text)
        if ($ms.Count -eq 0) { continue }
        if ($null -eq $nlPositions) {
            $nlPositions = New-Object 'System.Collections.Generic.List[int]'
            foreach ($nl in ([regex]::Matches($text, "`n"))) { $nlPositions.Add($nl.Index) }
        }
        $perFileCount = 0
        foreach ($m in $ms) {
            if ($rule.Id -eq 'C-secret-env-literal') {
                if (Test-SecretValueBenign $m.Groups['val'].Value) { continue }
            }
            $perFileCount++
            if ($perFileCount -gt 50) {
                $findings.Add([pscustomobject]@{
                    Severity = $rule.Severity; Rule = $rule.Id; File = $f.Rel; Line = 0
                    Snippet = "(more matches in this file -- truncated at 50)" })
                break
            }
            $bs = $nlPositions.BinarySearch($m.Index)
            if ($bs -lt 0) { $bs = -bnot $bs }
            $lineNum = $bs + 1
            $lineStart = 0
            if ($bs -gt 0) { $lineStart = $nlPositions[$bs - 1] + 1 }
            $lineEnd = $text.Length
            if ($bs -lt $nlPositions.Count) { $lineEnd = $nlPositions[$bs] }
            $lineText = $text.Substring($lineStart, $lineEnd - $lineStart).TrimEnd("`r")
            $findings.Add([pscustomobject]@{
                Severity = (Resolve-FindingSeverity $rule $m $text $f.Rel)
                Rule = $rule.Id; File = $f.Rel; Line = $lineNum
                Snippet = (Format-Snippet $lineText ($m.Index - $lineStart)) })
        }
    }
}

$sortedFindings = @($findings | Sort-Object -Property `
    @{ Expression = { $_.Severity } }, `
    @{ Expression = { $_.File.ToLowerInvariant() } }, `
    @{ Expression = { $_.Line } }, `
    @{ Expression = { $_.Rule } })
$failFindings     = @($sortedFindings | Where-Object { $_.Severity -eq 'FAIL' })
$advisoryFindings = @($sortedFindings | Where-Object { $_.Severity -eq 'ADVISORY' })

# --------------------------------------------------------------------------
# 5) Scrub report (written NEXT TO the snapshot, never inside it)
# --------------------------------------------------------------------------

$nl = "`n"
$rep = New-Object System.Text.StringBuilder
[void]$rep.AppendLine('# local-bench public snapshot -- scrub report')
[void]$rep.AppendLine('')
[void]$rep.AppendLine("- Script: scripts/publish-snapshot.ps1 v$ScriptVersion")
[void]$rep.AppendLine("- Source: $SourceRoot")
[void]$rep.AppendLine("- Source HEAD: $gitHead (branch: $gitBranch)")
[void]$rep.AppendLine("- Working-tree dirty files at copy time: $dirtyCount")
[void]$rep.AppendLine("- Snapshot: $OutDir")
[void]$rep.AppendLine("- Files in snapshot: $finalCount")
[void]$rep.AppendLine("- Total size: $finalBytes bytes ($([Math]::Round($finalBytes/1MB, 2)) MB)")
[void]$rep.AppendLine("- Board fixture: $boardNote")
[void]$rep.AppendLine("- License: $licenseStatus")
[void]$rep.AppendLine('')

[void]$rep.AppendLine('## Scrub verdict')
[void]$rep.AppendLine('')
if ($failFindings.Count -eq 0) {
    [void]$rep.AppendLine('**PASS** -- no blocking identity/secret findings in the snapshot.')
} else {
    [void]$rep.AppendLine("**FAIL** -- $($failFindings.Count) blocking finding(s). These are the residual identity edits needed (fix in the SOURCE repo -- this tool never edits):")
}
[void]$rep.AppendLine('')

[void]$rep.AppendLine('## Blocking findings (FAIL)')
[void]$rep.AppendLine('')
if ($failFindings.Count -eq 0) {
    [void]$rep.AppendLine('None.')
} else {
    [void]$rep.AppendLine('| # | Rule | File | Line | Snippet |')
    [void]$rep.AppendLine('|---|------|------|------|---------|')
    $i = 0
    foreach ($fd in $failFindings) {
        $i++
        [void]$rep.AppendLine("| $i | $($fd.Rule) | $($fd.File.Replace('\','/')) | $($fd.Line) | ``$($fd.Snippet)`` |")
    }
}
[void]$rep.AppendLine('')

[void]$rep.AppendLine('## Advisories (non-blocking)')
[void]$rep.AppendLine('')
if ($advisoryFindings.Count -eq 0) {
    [void]$rep.AppendLine('None.')
} else {
    [void]$rep.AppendLine('| # | Rule | File | Line | Snippet |')
    [void]$rep.AppendLine('|---|------|------|------|---------|')
    $i = 0
    foreach ($fd in $advisoryFindings) {
        $i++
        [void]$rep.AppendLine("| $i | $($fd.Rule) | $($fd.File.Replace('\','/')) | $($fd.Line) | ``$($fd.Snippet)`` |")
    }
}
[void]$rep.AppendLine('')

[void]$rep.AppendLine('## Exclusions applied during copy')
[void]$rep.AppendLine('')
[void]$rep.AppendLine('### Directories pruned')
[void]$rep.AppendLine('')
foreach ($p in ($prunedDirs | Sort-Object)) { [void]$rep.AppendLine("- $p") }
[void]$rep.AppendLine('')
[void]$rep.AppendLine('### Files excluded')
[void]$rep.AppendLine('')
if ($excludedFiles.Count -eq 0) { [void]$rep.AppendLine('None.') }
foreach ($x in ($excludedFiles | Sort-Object)) { [void]$rep.AppendLine("- $x") }
[void]$rep.AppendLine('')
[void]$rep.AppendLine('### Reparse points (junctions/symlinks) skipped')
[void]$rep.AppendLine('')
if ($reparseSkips.Count -eq 0) { [void]$rep.AppendLine('None.') }
foreach ($r in ($reparseSkips | Sort-Object)) { [void]$rep.AppendLine("- $r") }
[void]$rep.AppendLine('')
[void]$rep.AppendLine('### Walk warnings')
[void]$rep.AppendLine('')
if ($walkErrors.Count -eq 0) { [void]$rep.AppendLine('None.') }
foreach ($w in ($walkErrors | Sort-Object)) { [void]$rep.AppendLine("- $w") }
[void]$rep.AppendLine('')
[void]$rep.AppendLine('### Scan skips (binary extensions are always skipped; listed here: oversize/unreadable)')
[void]$rep.AppendLine('')
if ($scanSkips.Count -eq 0) { [void]$rep.AppendLine('None.') }
foreach ($s in ($scanSkips | Sort-Object)) { [void]$rep.AppendLine("- $s") }
[void]$rep.AppendLine('')
[void]$rep.AppendLine('---')
[void]$rep.AppendLine('Rules and go-public runbook: docs/deploy/public-snapshot-manifest.md (private ops doc, not in the snapshot).')

Write-TextLf $ReportPath ($rep.ToString())

# --------------------------------------------------------------------------
# 6) Console summary + exit code
# --------------------------------------------------------------------------

Write-Host ''
Write-Host '================ publish-snapshot summary ================'
Write-Host ("Snapshot   : {0}" -f $OutDir)
Write-Host ("Files      : {0}" -f $finalCount)
Write-Host ("Total size : {0} bytes ({1} MB)" -f $finalBytes, [Math]::Round($finalBytes/1MB, 2))
Write-Host ("License    : {0}" -f $licenseStatus)
Write-Host ("Scrub      : {0} blocking finding(s), {1} advisory(ies)" -f $failFindings.Count, $advisoryFindings.Count)
Write-Host ("Report     : {0}" -f $ReportPath)

if ($failFindings.Count -gt 0) {
    Write-Host ''
    Write-Host 'Blocking findings (file:line -- rule):'
    $failFindings | ForEach-Object {
        Write-Host ("  {0}:{1}  [{2}]  {3}" -f $_.File, $_.Line, $_.Rule, $_.Snippet)
    }
    Write-Host ''
    Write-Host 'RESULT: FAIL -- snapshot is NOT publishable. Fix the findings in the source repo and re-run.'
    exit 2
}
if ($licenseBlocker) {
    Write-Host ''
    Write-Host 'RESULT: SCRUB CLEAN, but the LICENSE is not Apache-2.0 yet -- NOT publishable until replaced.'
    exit 3
}
Write-Host ''
Write-Host 'RESULT: PASS -- snapshot is clean and carries an Apache-2.0 LICENSE.'
exit 0
