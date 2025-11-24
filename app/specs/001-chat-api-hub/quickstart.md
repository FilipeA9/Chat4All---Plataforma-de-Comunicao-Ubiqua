# Quickstart Guide: Chat4All API Hub

**Created**: 2025-11-24  
**Purpose**: Step-by-step instructions to set up and run Chat4All locally (without Docker)

## Overview

This guide will help you set up the complete Chat4All system on your local machine, including:
- PostgreSQL database
- Apache Kafka message broker
- MinIO object storage
- FastAPI server
- Background workers (message router, mock connectors)

**Time to complete**: ~30 minutes (constitution success criterion SC-017)

---

## Prerequisites

### System Requirements

- **OS**: Windows 10/11, macOS 10.15+, or Linux (Ubuntu 20.04+)
- **Python**: 3.11 or higher
- **RAM**: Minimum 4GB (8GB recommended)
- **Disk**: 2GB free space

### Required Software

1. **Python 3.11+**: [python.org](https://www.python.org/downloads/)
2. **PostgreSQL 15+**: [postgresql.org](https://www.postgresql.org/download/)
3. **Apache Kafka 3.5+**: [kafka.apache.org](https://kafka.apache.org/downloads)
4. **MinIO**: [min.io](https://min.io/download)

---

## Step 1: Install Dependencies

### 1.1 Verify Python Installation

```bash
python --version
# Should output: Python 3.11.x or higher
```

### 1.2 Clone Repository (if not already done)

```bash
cd /path/to/your/projects
git clone <repository-url> chat-for-all
cd chat-for-all
```

### 1.3 Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 1.4 Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Expected packages:
- fastapi==0.104.1
- uvicorn[standard]==0.24.0
- sqlalchemy==2.0.23
- psycopg2-binary==2.9.9
- kafka-python==2.0.2
- minio==7.2.0
- bcrypt==4.1.1
- pydantic==2.5.2
- pytest==7.4.3
- httpx==0.25.1

---

## Step 2: Set Up PostgreSQL

### 2.1 Install PostgreSQL

**Windows**: Download installer from postgresql.org and follow wizard  
**macOS**: `brew install postgresql@15`  
**Linux**: `sudo apt-get install postgresql-15`

### 2.2 Create Database and User

```bash
# Connect to PostgreSQL
psql -U postgres

# In psql shell:
CREATE DATABASE chat4all;
CREATE USER chat4all_user WITH ENCRYPTED PASSWORD 'chat4all_password';
GRANT ALL PRIVILEGES ON DATABASE chat4all TO chat4all_user;
\q
```

### 2.3 Verify Connection

```bash
psql -U chat4all_user -d chat4all -h localhost
# Enter password: chat4all_password
# Should connect successfully
\q
```

---

## Step 3: Set Up Apache Kafka

### 3.1 Download and Extract Kafka

```bash
# Download Kafka 3.5.1 (or latest)
cd ~/Downloads
wget https://downloads.apache.org/kafka/3.5.1/kafka_2.13-3.5.1.tgz
tar -xzf kafka_2.13-3.5.1.tgz
cd kafka_2.13-3.5.1
```

### 3.2 Start Kafka Services

**Terminal 1 - Start Zookeeper**:
```bash
bin/zookeeper-server-start.sh config/zookeeper.properties
# On Windows: bin\windows\zookeeper-server-start.bat config\zookeeper.properties
```

**Terminal 2 - Start Kafka Broker**:
```bash
bin/kafka-server-start.sh config/server.properties
# On Windows: bin\windows\kafka-server-start.bat config\server.properties
```

Wait until you see: `[KafkaServer id=0] started`

### 3.3 Create Topics

**Terminal 3**:
```bash
# Create message_processing topic
bin/kafka-topics.sh --create --topic message_processing \
  --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1

# Create whatsapp_outgoing topic
bin/kafka-topics.sh --create --topic whatsapp_outgoing \
  --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1

# Create instagram_outgoing topic
bin/kafka-topics.sh --create --topic instagram_outgoing \
  --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1

# Verify topics created
bin/kafka-topics.sh --list --bootstrap-server localhost:9092
# Should show: message_processing, whatsapp_outgoing, instagram_outgoing
```

---

## Step 4: Set Up MinIO

### 4.1 Download and Install MinIO

**Windows**:
```powershell
# Download MinIO executable
Invoke-WebRequest -Uri "https://dl.min.io/server/minio/release/windows-amd64/minio.exe" -OutFile "minio.exe"
```

**macOS**:
```bash
brew install minio/stable/minio
```

**Linux**:
```bash
wget https://dl.min.io/server/minio/release/linux-amd64/minio
chmod +x minio
sudo mv minio /usr/local/bin/
```

### 4.2 Start MinIO Server

**Terminal 4**:
```bash
# Create data directory
mkdir -p ~/minio-data

# Start MinIO server
minio server ~/minio-data --console-address ":9001"

# On Windows:
# minio.exe server C:\minio-data --console-address ":9001"
```

Expected output:
```
API: http://localhost:9000
Console: http://localhost:9001

RootUser: minioadmin
RootPass: minioadmin
```

### 4.3 Access MinIO Console

1. Open browser: `http://localhost:9001`
2. Login with credentials: `minioadmin` / `minioadmin`
3. Create bucket named `chat4all-files`
   - Go to "Buckets" → "Create Bucket"
   - Name: `chat4all-files`
   - Click "Create Bucket"

---

## Step 5: Configure Chat4All

### 5.1 Create Environment File

In the `chat-for-all/` directory, create `.env`:

```bash
# Database
DATABASE_URL=postgresql://chat4all_user:chat4all_password@localhost:5432/chat4all

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=chat4all-files
MINIO_SECURE=false

# Security
BCRYPT_ROUNDS=12
TOKEN_EXPIRY_HOURS=1

# API
API_HOST=0.0.0.0
API_PORT=8000
```

### 5.2 Initialize Database Schema

```bash
# Run database migrations
python -m db.database init

# Seed test users
python -m db.database seed
```

Expected output:
```
✓ Created tables: users, conversations, messages, file_metadata, ...
✓ Seeded 5 test users: user1, user2, user3, user4, user5
✓ Default password for all users: password123
```

---

## Step 6: Start Chat4All Services

Now start all Chat4All components in separate terminals:

### Terminal 5 - FastAPI Server

```bash
cd chat-for-all
source venv/bin/activate  # or venv\Scripts\activate on Windows
python main.py
```

Expected output:
```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

### Terminal 6 - Message Router Worker

```bash
cd chat-for-all
source venv/bin/activate
python -m workers.message_router
```

Expected output:
```
Message router started, consuming from message_processing topic...
Waiting for messages...
```

### Terminal 7 - WhatsApp Mock Connector

```bash
cd chat-for-all
source venv/bin/activate
python -m workers.whatsapp_mock
```

Expected output:
```
WhatsApp mock connector started, consuming from whatsapp_outgoing topic...
Waiting for messages...
```

### Terminal 8 - Instagram Mock Connector

```bash
cd chat-for-all
source venv/bin/activate
python -m workers.instagram_mock
```

Expected output:
```
Instagram mock connector started, consuming from instagram_outgoing topic...
Waiting for messages...
```

---

## Step 7: Verify Installation

### 7.1 Check API Documentation

Open browser: `http://localhost:8000/docs`

You should see Swagger UI with all API endpoints.

### 7.2 Test Authentication

```bash
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username": "user1", "password": "password123"}'
```

Expected response:
```json
{
  "access_token": "550e8400-e29b-41d4-a716-446655440000",
  "token_type": "bearer",
  "expires_in": 3600
}
```

Save the `access_token` for next steps.

### 7.3 Create a Conversation

```bash
export TOKEN="<your_access_token>"

curl -X POST http://localhost:8000/v1/conversations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "private",
    "members": ["<user1_id>", "<user2_id>"]
  }'
```

Expected response:
```json
{
  "conversation_id": "conv-uuid-here",
  "type": "private",
  "members": ["user1_id", "user2_id"],
  "created_at": "2025-11-24T10:00:00Z"
}
```

### 7.4 Send a Message

```bash
export CONV_ID="<conversation_id_from_above>"

curl -X POST http://localhost:8000/v1/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": "550e8400-e29b-41d4-a716-446655440001",
    "conversation_id": "'$CONV_ID'",
    "from": "<user1_id>",
    "channels": ["whatsapp"],
    "payload": {
      "type": "text",
      "text": "Hello from Chat4All!"
    }
  }'
```

Expected response:
```json
{
  "status": "accepted",
  "message_id": "550e8400-e29b-41d4-a716-446655440001"
}
```

### 7.5 Check Worker Logs

In Terminal 6 (message_router), you should see:
```
Received message: 550e8400-e29b-41d4-a716-446655440001
Routing to channels: ['whatsapp']
Published to whatsapp_outgoing
```

In Terminal 7 (whatsapp_mock), you should see:
```
INFO: Mensagem 550e8400-e29b-41d4-a716-446655440001 enviada para o usuário <user2_id> no WhatsApp
Message status updated to: delivered
```

### 7.6 Retrieve Messages

```bash
curl -X GET "http://localhost:8000/v1/conversations/$CONV_ID/messages" \
  -H "Authorization: Bearer $TOKEN"
```

Expected response:
```json
{
  "conversation_id": "<conv_id>",
  "messages": [
    {
      "message_id": "550e8400-e29b-41d4-a716-446655440001",
      "from": "<user1_id>",
      "payload": {
        "type": "text",
        "text": "Hello from Chat4All!"
      },
      "status": "delivered",
      "created_at": "2025-11-24T10:01:00Z"
    }
  ],
  "total": 1
}
```

---

## Step 8: Run Tests

### 8.1 Run Integration Tests

```bash
cd chat-for-all
pytest tests/test_api.py -v
```

Expected output:
```
tests/test_api.py::test_authentication PASSED
tests/test_api.py::test_create_conversation PASSED
tests/test_api.py::test_send_message PASSED
tests/test_api.py::test_get_messages PASSED
======================== 4 passed in 2.34s ========================
```

### 8.2 Run All Tests

```bash
pytest -v
```

---

## Troubleshooting

### Issue: Kafka Connection Refused

**Symptom**: `kafka.errors.NoBrokersAvailable`  
**Solution**: 
1. Verify Kafka is running: `netstat -an | grep 9092`
2. Check Kafka logs in Terminal 2
3. Restart Kafka if needed

### Issue: PostgreSQL Connection Failed

**Symptom**: `psycopg2.OperationalError: could not connect to server`  
**Solution**:
1. Verify PostgreSQL is running: `pg_isready`
2. Check credentials in `.env` match database setup
3. Restart PostgreSQL: `sudo service postgresql restart`

### Issue: MinIO Bucket Not Found

**Symptom**: `minio.error.S3Error: NoSuchBucket`  
**Solution**:
1. Access MinIO console: `http://localhost:9001`
2. Verify `chat4all-files` bucket exists
3. Create bucket if missing

### Issue: Workers Not Processing Messages

**Symptom**: Messages stuck in "accepted" status  
**Solution**:
1. Check worker terminals for errors
2. Verify Kafka topics exist: `bin/kafka-topics.sh --list --bootstrap-server localhost:9092`
3. Restart workers

---

## Shutdown Procedure

To safely stop all services:

1. **Stop Chat4All Components** (CTRL+C in each terminal):
   - Terminal 8: Instagram mock
   - Terminal 7: WhatsApp mock
   - Terminal 6: Message router
   - Terminal 5: FastAPI server

2. **Stop MinIO** (CTRL+C in Terminal 4)

3. **Stop Kafka** (CTRL+C in Terminals 2 and 1):
   - Terminal 2: Kafka broker
   - Terminal 1: Zookeeper

4. **PostgreSQL** (leave running or stop with):
   ```bash
   sudo service postgresql stop  # Linux
   brew services stop postgresql  # macOS
   # Windows: Use Services app
   ```

---

## Next Steps

Now that Chat4All is running:

1. **Explore API**: Visit `http://localhost:8000/docs` for interactive API documentation
2. **Test File Upload**: Try the chunked file upload flow (see [contracts/api-endpoints.md](./contracts/api-endpoints.md))
3. **Review Code**: Examine `api/endpoints.py`, `workers/message_router.py`, and `db/models.py`
4. **Run More Tests**: Execute `pytest` to see full test suite
5. **Experiment**: Create group conversations, send to multiple channels, upload files

---

## Summary

✅ You have successfully set up Chat4All with:
- PostgreSQL database with seeded test users
- Apache Kafka message broker with 3 topics
- MinIO object storage with chat4all-files bucket
- FastAPI server running on port 8000
- 3 background workers processing messages

The system demonstrates:
- Asynchronous message processing
- Event-driven architecture
- Multi-channel routing (mock WhatsApp/Instagram)
- File storage with integrity verification
- RESTful API with auto-generated documentation

**Total setup time**: Completed in ~30 minutes ✅ (SC-017)
