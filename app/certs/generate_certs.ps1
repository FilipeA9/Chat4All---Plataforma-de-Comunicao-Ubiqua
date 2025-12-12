$ErrorActionPreference = "Stop"

# 1. Configurações
$CertDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DaysValid = 365
$CN = "localhost"
$DNSNames = @("localhost", "api", "*.api.local")
$CertPath = Join-Path $CertDir "server.crt"
$KeyPath = Join-Path $CertDir "server.key"
$PfxPath = Join-Path $CertDir "server.pfx"
$Password = ConvertTo-SecureString -String "changeme" -Force -AsPlainText

Write-Host "--- Gerando Certificados SSL ---" -ForegroundColor Cyan

# 2. Parâmetros do Certificado (Splatting)
$certParams = @{
    Subject = "CN=$CN"
    DnsName = $DNSNames
    KeyAlgorithm = "RSA"
    KeyLength = 4096
    NotAfter = (Get-Date).AddDays($DaysValid)
    CertStoreLocation = "Cert:\CurrentUser\My"
    KeyExportPolicy = "Exportable"
    KeyUsage = "DigitalSignature", "KeyEncipherment"
    TextExtension = @("2.5.29.37={text}1.3.6.1.5.5.7.3.1")
    HashAlgorithm = "SHA256"
}

# 3. Gerar Certificado
$Cert = New-SelfSignedCertificate @certParams
$CertThumbprint = $Cert.Thumbprint

# 4. Exportar PFX
Export-PfxCertificate -Cert "Cert:\CurrentUser\My\$CertThumbprint" -FilePath $PfxPath -Password $Password | Out-Null
Write-Host "PFX criado." -ForegroundColor Green

# 5. Exportar CRT (Público)
$CertBytes = $Cert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert)
$CertBase64 = [System.Convert]::ToBase64String($CertBytes, [System.Base64FormattingOptions]::InsertLineBreaks)
$CertPem = "-----BEGIN CERTIFICATE-----`n$CertBase64`n-----END CERTIFICATE-----"
$CertPem | Out-File -FilePath $CertPath -Encoding ASCII
Write-Host "CRT criado." -ForegroundColor Green

# 6. Tentar Exportar Key (Privada) via OpenSSL
if (Get-Command openssl -ErrorAction SilentlyContinue) {
    Write-Host "OpenSSL encontrado. Extraindo chave privada..." -ForegroundColor Cyan
    try {
        # Executa o comando e espera terminar
        $process = Start-Process -FilePath "openssl" -ArgumentList "pkcs12 -in `"$PfxPath`" -nocerts -nodes -out `"$KeyPath`" -passin pass:changeme" -PassThru -Wait -NoNewWindow
        
        if ($process.ExitCode -eq 0) {
            Write-Host "KEY criada com sucesso via OpenSSL." -ForegroundColor Green
        } else {
            Write-Host "Erro ao extrair KEY com OpenSSL." -ForegroundColor Red
        }
    } catch {
        Write-Host "Falha ao executar OpenSSL." -ForegroundColor Red
    }
} else {
    Write-Host "AVISO: OpenSSL não encontrado." -ForegroundColor Yellow
    Write-Host "O arquivo server.key não foi gerado automaticamente." -ForegroundColor Yellow
    Write-Host "Use o arquivo server.pfx se necessário." -ForegroundColor Yellow
}

# 7. Limpeza
Remove-Item "Cert:\CurrentUser\My\$CertThumbprint" -Force