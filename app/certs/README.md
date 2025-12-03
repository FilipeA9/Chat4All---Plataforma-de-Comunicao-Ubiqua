# TLS/SSL Certificates Directory

This directory contains SSL certificates for enabling HTTPS/TLS on the FastAPI application.

## Development Environment

For local development, use self-signed certificates:

### Linux/macOS:
```bash
chmod +x generate_certs.sh
./generate_certs.sh
```

### Windows (PowerShell):
```powershell
.\generate_certs.ps1
```

This will generate:
- `server.crt` - Self-signed certificate
- `server.key` - Private key
- `server.pfx` - Certificate bundle (Windows)

## Production Environment

**⚠️ DO NOT use self-signed certificates in production!**

For production, use one of these options:

### Option 1: Let's Encrypt (Recommended)
```bash
# Using certbot
certbot certonly --standalone -d yourdomain.com -d api.yourdomain.com
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ./server.crt
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ./server.key
```

### Option 2: Organization CA
Contact your organization's security team to obtain signed certificates.

### Option 3: Cloud Provider Managed Certificates
Use AWS Certificate Manager, Azure Key Vault, or GCP Certificate Manager and configure your load balancer for TLS termination.

## Security Notes

1. **Private Key Protection**: Never commit `server.key` to version control
2. **Permissions**: Ensure `server.key` has restricted permissions (600)
3. **Rotation**: Rotate certificates before expiration
4. **TLS Version**: Application enforces TLS 1.3 minimum
5. **Cipher Suites**: Strong cipher suites only (see main.py configuration)

## Files in This Directory

- `generate_certs.sh` - Bash script for generating self-signed certificates
- `generate_certs.ps1` - PowerShell script for Windows
- `README.md` - This file
- `server.crt` - Certificate (generated, not committed)
- `server.key` - Private key (generated, not committed, in .gitignore)
- `server.pfx` - PFX bundle for Windows (generated, not committed)

## Verification

Test your certificates:

```bash
# Verify certificate
openssl x509 -in server.crt -text -noout

# Test HTTPS connection
curl -k https://localhost:8000/health

# Check TLS version
openssl s_client -connect localhost:8000 -tls1_3
```

## Docker Compose Integration

Certificates are mounted as volumes in `docker-compose.yml`:

```yaml
volumes:
  - ./certs:/app/certs:ro
environment:
  - SSL_CERT_FILE=/app/certs/server.crt
  - SSL_KEY_FILE=/app/certs/server.key
```

## Troubleshooting

### "Permission denied" error
```bash
chmod 600 server.key
chmod 644 server.crt
```

### "Certificate verify failed" in development
Use `-k` flag with curl or configure your HTTP client to skip verification for self-signed certificates.

### Certificate expired
Regenerate certificates using the generation scripts.
