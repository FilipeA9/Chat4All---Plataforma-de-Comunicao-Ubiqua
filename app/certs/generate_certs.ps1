# PowerShell script to generate self-signed SSL certificates for development
# For production, use Let's Encrypt or your organization's CA

$ErrorActionPreference = "Stop"

$CertDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DaysValid = 365
$CN = "localhost"
$DNSNames = @("localhost", "api", "*.api.local")

Write-Host "Generating self-signed SSL certificates for TLS 1.3..." -ForegroundColor Cyan

# Generate self-signed certificate
$Cert = New-SelfSignedCertificate `
    -Subject "CN=$CN" `
    -DnsName $DNSNames `
    -KeyAlgorithm RSA `
    -KeyLength 4096 `
    -NotAfter (Get-Date).AddDays($DaysValid) `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -KeyExportPolicy Exportable `
    -KeyUsage DigitalSignature, KeyEncipherment `
    -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.1") `
    -HashAlgorithm SHA256

$CertThumbprint = $Cert.Thumbprint

# Export certificate
$CertPath = Join-Path $CertDir "server.crt"
$KeyPath = Join-Path $CertDir "server.key"
$PfxPath = Join-Path $CertDir "server.pfx"
$Password = ConvertTo-SecureString -String "changeme" -Force -AsPlainText

# Export PFX
Export-PfxCertificate -Cert "Cert:\CurrentUser\My\$CertThumbprint" `
    -FilePath $PfxPath `
    -Password $Password | Out-Null

# Export CRT (Base64 encoded)
$CertBytes = $Cert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert)
$CertBase64 = [System.Convert]::ToBase64String($CertBytes, [System.Base64FormattingOptions]::InsertLineBreaks)
$CertPem = "-----BEGIN CERTIFICATE-----`n$CertBase64`n-----END CERTIFICATE-----"
$CertPem | Out-File -FilePath $CertPath -Encoding ASCII

# Export private key (requires extraction from PFX)
# Note: This is complex in PowerShell, we'll use OpenSSL if available
if (Get-Command openssl -ErrorAction SilentlyContinue) {
    & openssl pkcs12 -in $PfxPath -nocerts -nodes -out $KeyPath -passin pass:changeme 2>$null
    Write-Host "✓ Private key exported using OpenSSL" -ForegroundColor Green
} else {
    Write-Host "⚠️  OpenSSL not found. Install OpenSSL to export private key in PEM format." -ForegroundColor Yellow
    Write-Host "   Alternatively, use the PFX file: $PfxPath (password: changeme)" -ForegroundColor Yellow
}

# Remove certificate from store
Remove-Item "Cert:\CurrentUser\My\$CertThumbprint" -Force

Write-Host ""
Write-Host "✓ SSL certificates generated successfully:" -ForegroundColor Green
Write-Host "  - Certificate: $CertPath" -ForegroundColor White
if (Test-Path $KeyPath) {
    Write-Host "  - Private key: $KeyPath" -ForegroundColor White
}
Write-Host "  - PFX bundle: $PfxPath (password: changeme)" -ForegroundColor White
Write-Host "  - Valid for: $DaysValid days" -ForegroundColor White
Write-Host ""
Write-Host "⚠️  IMPORTANT: These are self-signed certificates for DEVELOPMENT ONLY" -ForegroundColor Yellow
Write-Host "    For production, use Let's Encrypt or your organization's CA" -ForegroundColor Yellow
