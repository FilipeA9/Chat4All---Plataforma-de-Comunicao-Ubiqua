#!/bin/bash

# Generate self-signed SSL certificates for development
# For production, use Let's Encrypt or your organization's CA

set -e

CERT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DAYS_VALID=365
COUNTRY="BR"
STATE="State"
CITY="City"
ORG="Chat4All"
OU="Development"
CN="localhost"

echo "Generating self-signed SSL certificates for TLS 1.3..."

# Generate private key
openssl genrsa -out "${CERT_DIR}/server.key" 4096

# Generate certificate signing request
openssl req -new -key "${CERT_DIR}/server.key" \
    -out "${CERT_DIR}/server.csr" \
    -subj "/C=${COUNTRY}/ST=${STATE}/L=${CITY}/O=${ORG}/OU=${OU}/CN=${CN}"

# Generate self-signed certificate
openssl x509 -req -days ${DAYS_VALID} \
    -in "${CERT_DIR}/server.csr" \
    -signkey "${CERT_DIR}/server.key" \
    -out "${CERT_DIR}/server.crt" \
    -extensions v3_req \
    -extfile <(cat <<EOF
[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = api
DNS.3 = *.api.local
IP.1 = 127.0.0.1
IP.2 = ::1
EOF
)

# Set proper permissions
chmod 600 "${CERT_DIR}/server.key"
chmod 644 "${CERT_DIR}/server.crt"

# Clean up CSR
rm "${CERT_DIR}/server.csr"

echo "✓ SSL certificates generated successfully:"
echo "  - Private key: ${CERT_DIR}/server.key"
echo "  - Certificate: ${CERT_DIR}/server.crt"
echo "  - Valid for: ${DAYS_VALID} days"
echo ""
echo "⚠️  IMPORTANT: These are self-signed certificates for DEVELOPMENT ONLY"
echo "    For production, use Let's Encrypt or your organization's CA"
