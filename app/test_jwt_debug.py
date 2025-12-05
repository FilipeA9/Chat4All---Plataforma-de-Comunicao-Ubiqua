"""Test JWT encoding/decoding to debug authentication issue."""
from jose import jwt
from datetime import datetime, timedelta
import os

# Use the exact same configuration from .env
JWT_SECRET_KEY = "changeme-in-production-use-openssl-rand-hex-32"
JWT_ALGORITHM = "HS256"

print("=" * 60)
print("JWT DEBUG TEST")
print("=" * 60)
print(f"JWT_SECRET_KEY: {JWT_SECRET_KEY}")
print(f"JWT_ALGORITHM: {JWT_ALGORITHM}")
print(f"Key length: {len(JWT_SECRET_KEY)} chars")
print(f"Key type: {type(JWT_SECRET_KEY)}")
print()

# Test 1: Basic encoding
print("Test 1: Basic JWT encoding...")
try:
    payload = {
        "user_id": 1,
        "tenant_id": "default",
        "scope": "read write",
        "iat": int(datetime.utcnow().timestamp()),
        "exp": int((datetime.utcnow() + timedelta(minutes=15)).timestamp()),
        "type": "access"
    }
    
    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    print(f"✅ SUCCESS: Token generated")
    print(f"   Token: {token[:50]}...")
    print(f"   Token type: {type(token)}")
    print()
    
    # Test 2: Decoding
    print("Test 2: JWT decoding...")
    decoded = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    print(f"✅ SUCCESS: Token decoded")
    print(f"   Decoded payload: {decoded}")
    print()
    
except Exception as e:
    print(f"❌ FAILED: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    print()

# Test 3: Check if it's a jose version issue
print("Test 3: Check jose version and backend...")
try:
    import jose
    print(f"python-jose version: {jose.__version__ if hasattr(jose, '__version__') else 'unknown'}")
    
    # Check which cryptography backend is being used
    from jose import jws
    print(f"JWS module: {jws.__file__}")
    
except Exception as e:
    print(f"Error checking jose: {e}")

print()
print("=" * 60)
