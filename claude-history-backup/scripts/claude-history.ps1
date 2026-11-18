#requires -Version 5.1
<#
.SYNOPSIS
  Back up or restore Claude Code history (~/.claude) as a zip archive.
.EXAMPLE
  .\claude-history.ps1 -Action backup  -Destination D:\Backups
  .\claude-history.ps1 -Action list    -Archive D:\Backups\claude-history-20261118-101500.zip
  .\claude-history.ps1 -Action restore -Archive D:\Backups\claude-history-20261118-101500.zip
  .\claude-history.ps1 -Action restore -Archive ... -Overwrite
#>
param(
  [Parameter(Mandatory)][ValidateSet('backup','restore','list')][string]$Action,
  [string]$Destination = (Join-Path $env:USERPROFILE 'claude-history-backups'),
  [string]$Archive,
  [string]$ClaudeDir = (Join-Path $env:USERPROFILE '.claude'),
  [switch]$Overwrite
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem

# What counts as "history". Credentials/settings/plugins are deliberately excluded.
$Items = @('projects','history.jsonl','file-history','plans','todos','sessions','stats-cache.json')

function Get-Rel([string]$full) { $full.Substring($ClaudeDir.TrimEnd('\').Length + 1) -replace '\\','/' }

if ($Action -eq 'backup') {
  if (-not (Test-Path $ClaudeDir)) { throw "Not found: $ClaudeDir" }
  New-Item -ItemType Directory -Force $Destination | Out-Null
  $out = Join-Path $Destination ("claude-history-{0:yyyyMMdd-HHmmss}.zip" -f (Get-Date))
  $fs = [IO.File]::Open($out, 'CreateNew')
  $zip = New-Object IO.Compression.ZipArchive($fs, 'Create')
  $n = 0; $bytes = 0; $skipped = 0
  try {
    foreach ($item in $Items) {
      $p = Join-Path $ClaudeDir $item
      if (-not (Test-Path $p)) { continue }
      $files = if ((Get-Item $p).PSIsContainer) { Get-ChildItem $p -Recurse -File -Force } else { Get-Item $p }
      foreach ($f in $files) {
        try {
          # Open with sharing so a live session's transcript can still be read.
          $in = [IO.File]::Open($f.FullName,'Open','Read','ReadWrite')
          try {
            $e = $zip.CreateEntry((Get-Rel $f.FullName), 'Optimal')
            $e.LastWriteTime = $f.LastWriteTime
            $s = $e.Open(); try { $in.CopyTo($s) } finally { $s.Dispose() }
          } finally { $in.Dispose() }
          $n++; $bytes += $f.Length
        } catch { $skipped++; Write-Warning "Skipped $($f.FullName): $($_.Exception.Message)" }
      }
    }
  } finally { $zip.Dispose(); $fs.Dispose() }
  "Backed up $n files ($([math]::Round($bytes/1MB,1)) MB raw), skipped $skipped"
  "Archive: $out ($([math]::Round((Get-Item $out).Length/1MB,1)) MB)"
  return
}

if (-not $Archive) { throw "-Archive is required for $Action" }
if (-not (Test-Path $Archive)) { throw "Not found: $Archive" }
$zip = [IO.Compression.ZipFile]::OpenRead($Archive)
try {
  if ($Action -eq 'list') {
    $zip.Entries | Group-Object { $_.FullName.Split('/')[0] } |
      ForEach-Object { '{0,-20} {1,6} files  {2,8:N1} MB' -f $_.Name, $_.Count, (($_.Group | Measure-Object Length -Sum).Sum/1MB) }
    return
  }

  # restore: never delete anything; skip files that are already same-or-newer unless -Overwrite
  $root = [IO.Path]::GetFullPath($ClaudeDir).TrimEnd('\') + '\'
  $restored = 0; $kept = 0
  foreach ($e in $zip.Entries) {
    if ($e.FullName.EndsWith('/')) { continue }
    $target = [IO.Path]::GetFullPath((Join-Path $ClaudeDir ($e.FullName -replace '/','\')))
    if (-not $target.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { Write-Warning "Blocked path outside target: $($e.FullName)"; continue }
    if ((Test-Path $target) -and -not $Overwrite) {
      if ((Get-Item $target).LastWriteTime -ge $e.LastWriteTime.LocalDateTime) { $kept++; continue }
    }
    New-Item -ItemType Directory -Force (Split-Path $target) | Out-Null
    [IO.Compression.ZipFileExtensions]::ExtractToFile($e, $target, $true)
    $restored++
  }
  "Restored $restored files, left $kept existing files untouched"
} finally { $zip.Dispose() }
