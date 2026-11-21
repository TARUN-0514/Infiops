# Creates .env from .env.example with fresh random secrets. Run once from the repo root:
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
if (Test-Path .env) { Write-Host ".env already exists; leaving it alone."; exit 0 }

function New-Secret([int]$bytes) {
  $buf = New-Object byte[] $bytes
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buf)
  return [Convert]::ToBase64String($buf)
}

$jwt = (New-Secret 48).Replace("+", "-").Replace("/", "_").TrimEnd("=")
$key = New-Secret 32
(Get-Content .env.example) `
  -replace '^NEXUS_JWT_SECRET=.*', "NEXUS_JWT_SECRET=$jwt" `
  -replace '^NEXUS_ENCRYPTION_KEY=.*', "NEXUS_ENCRYPTION_KEY=$key" |
  Set-Content -Encoding utf8 .env
Write-Host "Created .env with new secrets."
