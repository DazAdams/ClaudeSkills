#requires -Version 7
<#
.SYNOPSIS
  Encrypt / decrypt a file with a passphrase (PBKDF2-SHA256 + AES-256-GCM). No dependencies.
  Intended for the Chrome password-export CSV: encrypt it, then the plaintext is deleted.
.EXAMPLE
  .\Protect-File.ps1 -Action encrypt -Path "$env:USERPROFILE\Downloads\Chrome Passwords.csv" -OutDir D:\Backups
  .\Protect-File.ps1 -Action decrypt -Path D:\Backups\Chrome-Passwords.csv.enc -OutDir $env:TEMP
.NOTES
  The passphrase is read from a secure prompt, never from a parameter, so it does not land in
  shell history or in the transcript. File format: "CBE1" | salt(16) | nonce(12) | tag(16) | ciphertext
#>
param(
  [Parameter(Mandatory)][ValidateSet('encrypt','decrypt')][string]$Action,
  [Parameter(Mandatory)][string]$Path,
  [Parameter(Mandatory)][string]$OutDir,
  [switch]$KeepOriginal   # encrypt only: by default the plaintext source is overwritten and deleted
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Path)) { throw "Not found: $Path" }
New-Item -ItemType Directory -Force $OutDir | Out-Null

function Read-Passphrase([string]$prompt) {
  $s = Read-Host $prompt -AsSecureString
  [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
}
function New-Key([string]$pass, [byte[]]$salt) {
  [Security.Cryptography.Rfc2898DeriveBytes]::Pbkdf2($pass, $salt, 600000, 'SHA256', 32)
}

$pass = Read-Passphrase 'Passphrase'
if ($Action -eq 'encrypt') {
  if ($pass.Length -lt 12) { throw 'Use a passphrase of at least 12 characters.' }
  if ($pass -ne (Read-Passphrase 'Repeat passphrase')) { throw 'Passphrases do not match.' }
  $plain = [IO.File]::ReadAllBytes($Path)
  $salt = [byte[]]::new(16); [Security.Cryptography.RandomNumberGenerator]::Fill($salt)
  $nonce = [byte[]]::new(12); [Security.Cryptography.RandomNumberGenerator]::Fill($nonce)
  $key = New-Key $pass $salt
  $cipher = [byte[]]::new($plain.Length); $tag = [byte[]]::new(16)
  $aes = [Security.Cryptography.AesGcm]::new($key, 16)
  $aes.Encrypt($nonce, $plain, $cipher, $tag)
  $aes.Dispose()
  $out = Join-Path $OutDir (([IO.Path]::GetFileName($Path) -replace '\s+','-') + '.enc')
  $ms = [IO.MemoryStream]::new()
  $ms.Write([Text.Encoding]::ASCII.GetBytes('CBE1'), 0, 4)
  foreach ($b in @($salt, $nonce, $tag, $cipher)) { $ms.Write($b, 0, $b.Length) }
  [IO.File]::WriteAllBytes($out, $ms.ToArray())

  # Prove it decrypts before touching the plaintext.
  $check = [byte[]]::new($plain.Length)
  $aes = [Security.Cryptography.AesGcm]::new((New-Key $pass $salt), 16)
  $aes.Decrypt($nonce, $cipher, $tag, $check); $aes.Dispose()
  if (-not [Linq.Enumerable]::SequenceEqual($check, $plain)) { Remove-Item $out; throw 'Verification failed; plaintext left in place.' }

  if (-not $KeepOriginal) {
    # Best-effort overwrite then delete. On SSDs/journaling filesystems this cannot guarantee
    # the old blocks are gone; the encrypted copy plus BitLocker is the real protection.
    $fs = [IO.File]::Open($Path, 'Open', 'Write'); $zero = [byte[]]::new($plain.Length); $fs.Write($zero, 0, $zero.Length); $fs.Dispose()
    Remove-Item -LiteralPath $Path -Force
    "Plaintext deleted: $Path"
  }
  "Encrypted: $out"
} else {
  $all = [IO.File]::ReadAllBytes($Path)
  if ([Text.Encoding]::ASCII.GetString($all, 0, 4) -ne 'CBE1') { throw 'Not a CBE1 file.' }
  $salt = $all[4..19]; $nonce = $all[20..31]; $tag = $all[32..47]; $cipher = $all[48..($all.Length - 1)]
  $plain = [byte[]]::new($cipher.Length)
  $aes = [Security.Cryptography.AesGcm]::new((New-Key $pass ([byte[]]$salt)), 16)
  try { $aes.Decrypt([byte[]]$nonce, [byte[]]$cipher, [byte[]]$tag, $plain) } catch { throw 'Wrong passphrase or corrupted file.' }
  $out = Join-Path $OutDir ([IO.Path]::GetFileNameWithoutExtension($Path))
  [IO.File]::WriteAllBytes($out, $plain)
  "Decrypted: $out  (plaintext - delete it when finished)"
}
