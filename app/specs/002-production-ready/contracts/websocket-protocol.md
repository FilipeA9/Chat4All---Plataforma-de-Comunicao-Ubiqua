# WebSocket Protocol Specification

**Feature**: Real-Time Communication Layer  
**Version**: 1.0.0  
**Date**: 2025-11-30

## Overview

This document specifies the WebSocket protocol for real-time bidirectional communication between clients and the Chat4All v2 platform. Clients establish persistent WebSocket connections to receive instant notifications for new messages, message status updates (DELIVERED, READ), and conversation events.

---

## Connection Establishment

### Endpoint

```
ws://api.chat4all.local/ws?token={jwt_access_token}
```

**Transport**: WebSocket (RFC 6455)  
**Authentication**: JWT access token in query parameter

### Connection Flow

1. **Client initiates WebSocket handshake** with JWT token in URL:
   ```
   GET /ws?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9... HTTP/1.1
   Host: api.chat4all.local
   Upgrade: websocket
   Connection: Upgrade
   Sec-WebSocket-Version: 13
   Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
   ```

2. **Server validates JWT token**:
   - Extract `user_id` from JWT claims
   - Verify JWT signature and expiration
   - If invalid: Close connection with status code 4001 (Unauthorized)

3. **Server accepts connection**:
   ```
   HTTP/1.1 101 Switching Protocols
   Upgrade: websocket
   Connection: Upgrade
   Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
   ```

4. **Server sends welcome message**:
   ```json
   {
     "type": "connection.established",
     "user_id": "123e4567-e89b-12d3-a456-426614174000",
     "timestamp": "2025-11-30T12:00:00Z",
     "server_instance": "api-pod-1"
   }
   ```

5. **Client subscribes to conversations** (automatically by server):
   - Server queries database: `SELECT conversation_id FROM conversation_members WHERE user_id = ?`
   - Server subscribes to Redis Pub/Sub channels: `conversation:{conversation_id}:events`

---

## Message Format

All messages are JSON-encoded. Each message has a `type` field indicating the event type.

### Message Structure

```json
{
  "type": "string",           // Event type (required)
  "timestamp": "ISO8601",     // Server timestamp (required)
  "data": { ... }             // Event-specific payload (optional)
}
```

---

## Server-to-Client Events

### 1. `connection.established`

**Description**: Sent immediately after the WebSocket connection is accepted.

**Payload**:
```json
{
  "type": "connection.established",
  "user_id": "123e4567-e89b-12d3-a456-426614174000",
  "timestamp": "2025-11-30T12:00:00Z",
  "server_instance": "api-pod-1"
}
```

**Fields**:
- `user_id`: Authenticated user's UUID
- `timestamp`: Server timestamp (ISO 8601)
- `server_instance`: API pod identifier (for debugging)

---

### 2. `message.created`

**Description**: Sent when a new message is created in a conversation the user is a member of.

**Payload**:
```json
{
  "type": "message.created",
  "timestamp": "2025-11-30T12:00:01Z",
  "data": {
    "message_id": "223e4567-e89b-12d3-a456-426614174000",
    "conversation_id": "323e4567-e89b-12d3-a456-426614174000",
    "sender_id": "423e4567-e89b-12d3-a456-426614174000",
    "sender_name": "Alice",
    "content": "Hello, Bob!",
    "channels": ["whatsapp"],
    "status": "accepted",
    "created_at": "2025-11-30T12:00:01Z"
  }
}
```

**Fields**:
- `message_id`: UUID of the new message
- `conversation_id`: UUID of the conversation
- `sender_id`: UUID of the user who sent the message
- `sender_name`: Display name of the sender
- `content`: Message content (text or file reference)
- `channels`: Array of channels the message is routed to
- `status`: Message status ('accepted', 'delivered', 'failed')
- `created_at`: Timestamp when the message was created

---

### 3. `message.status_updated`

**Description**: Sent when a message's status changes (e.g., 'accepted' → 'delivered' → 'read').

**Payload**:
```json
{
  "type": "message.status_updated",
  "timestamp": "2025-11-30T12:00:05Z",
  "data": {
    "message_id": "223e4567-e89b-12d3-a456-426614174000",
    "conversation_id": "323e4567-e89b-12d3-a456-426614174000",
    "old_status": "accepted",
    "new_status": "delivered",
    "updated_at": "2025-11-30T12:00:05Z"
  }
}
```

**Fields**:
- `message_id`: UUID of the message
- `conversation_id`: UUID of the conversation
- `old_status`: Previous status
- `new_status`: New status ('accepted', 'delivered', 'read', 'failed')
- `updated_at`: Timestamp of status change

---

### 4. `conversation.read`

**Description**: Sent when a user marks a conversation as read.

**Payload**:
```json
{
  "type": "conversation.read",
  "timestamp": "2025-11-30T12:00:10Z",
  "data": {
    "conversation_id": "323e4567-e89b-12d3-a456-426614174000",
    "user_id": "423e4567-e89b-12d3-a456-426614174000",
    "user_name": "Bob",
    "read_at": "2025-11-30T12:00:10Z"
  }
}
```

**Fields**:
- `conversation_id`: UUID of the conversation
- `user_id`: UUID of the user who marked it as read
- `user_name`: Display name of the user
- `read_at`: Timestamp when marked as read

---

### 5. `ping`

**Description**: Heartbeat message sent by the server every 30 seconds to keep the connection alive.

**Payload**:
```json
{
  "type": "ping",
  "timestamp": "2025-11-30T12:00:30Z"
}
```

**Client Response**: Client MUST respond with a `pong` message within 10 seconds. If no `pong` is received, the server MAY close the connection after 60 seconds of inactivity.

---

## Client-to-Server Events

### 1. `pong`

**Description**: Response to server's `ping` heartbeat.

**Payload**:
```json
{
  "type": "pong",
  "timestamp": "2025-11-30T12:00:30Z"
}
```

---

### 2. `subscribe` (Optional - Future Enhancement)

**Description**: Explicitly subscribe to a conversation. By default, the server auto-subscribes the client to all their conversations on connection.

**Payload**:
```json
{
  "type": "subscribe",
  "data": {
    "conversation_id": "523e4567-e89b-12d3-a456-426614174000"
  }
}
```

**Server Response**:
```json
{
  "type": "subscribed",
  "timestamp": "2025-11-30T12:00:35Z",
  "data": {
    "conversation_id": "523e4567-e89b-12d3-a456-426614174000"
  }
}
```

---

### 3. `unsubscribe` (Optional - Future Enhancement)

**Description**: Unsubscribe from a conversation to stop receiving events for it.

**Payload**:
```json
{
  "type": "unsubscribe",
  "data": {
    "conversation_id": "523e4567-e89b-12d3-a456-426614174000"
  }
}
```

**Server Response**:
```json
{
  "type": "unsubscribed",
  "timestamp": "2025-11-30T12:00:40Z",
  "data": {
    "conversation_id": "523e4567-e89b-12d3-a456-426614174000"
  }
}
```

---

## Connection Lifecycle

### Connection Timeout

- **Idle Timeout**: 60 seconds without `pong` response to `ping`
- **Action**: Server closes the connection with status code 1000 (Normal Closure)

### Reconnection Strategy (Client-Side)

1. **Detect disconnection** (onclose event or network failure)
2. **Wait with exponential backoff**: 1s, 2s, 4s, 8s, 16s (max)
3. **Retry connection** with the same JWT token (if not expired)
4. **If JWT expired**: Call POST /auth/refresh to get a new access token, then reconnect

### Error Codes

| Status Code | Name | Description |
|-------------|------|-------------|
| 1000 | Normal Closure | Connection closed gracefully (client disconnect) |
| 1001 | Going Away | Server shutting down or client navigating away |
| 4001 | Unauthorized | Invalid or expired JWT token |
| 4003 | Forbidden | User does not have permission to connect |
| 4008 | Policy Violation | Rate limit exceeded or abuse detected |

---

## Redis Pub/Sub Architecture

### Multi-Instance Fan-Out

Chat4All v2 runs multiple API instances behind a load balancer. To ensure messages reach the correct connected client regardless of which instance they're connected to, we use Redis Pub/Sub:

1. **Message Created**: When a message is created (any API instance), the instance publishes an event to Redis:
   ```
   PUBLISH conversation:323e4567-e89b-12d3-a456-426614174000:events '{"type": "message.created", ...}'
   ```

2. **All API Instances Subscribe**: Each API instance subscribes to Redis channels for conversations with active WebSocket connections:
   ```
   SUBSCRIBE conversation:323e4567-e89b-12d3-a456-426614174000:events
   ```

3. **Redis Fan-Out**: Redis broadcasts the message to all subscribed API instances.

4. **WebSocket Dispatch**: Each API instance forwards the event to its locally connected WebSocket clients in that conversation.

**Diagram**:
```
┌─────────────┐
│  Client A   │ (connected to Instance 1)
└──────┬──────┘
       │ WebSocket
       ↓
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│ API Inst 1  │←──────│   Redis     │──────→│ API Inst 2  │
│             │ Pub/Sub│  Pub/Sub    │Pub/Sub│             │
└─────────────┘       └─────────────┘       └──────┬──────┘
                                                    │ WebSocket
                                                    ↓
                                             ┌─────────────┐
                                             │  Client B   │
                                             └─────────────┘
```

**Latency**: Redis Pub/Sub adds <5ms overhead (local deployment) or <20ms (cross-region).

---

## Security Considerations

### Authentication

- **JWT Token in URL**: The JWT access token is passed as a query parameter (`?token=...`). This is secure over WSS (WebSocket Secure / TLS) but MUST NOT be used over unencrypted WS.
- **TLS 1.3 Mandatory**: All WebSocket connections MUST use WSS (wss://) with TLS 1.3+ in production.
- **Token Expiration**: If the JWT expires while the connection is active (after 15 minutes), the server SHOULD close the connection with status code 4001. The client MUST refresh the token and reconnect.

### Rate Limiting

- **Connection Limit**: Each user can have a maximum of 10 concurrent WebSocket connections (prevents abuse).
- **Message Rate Limiting**: If a client sends more than 100 messages per minute, the server MAY close the connection with status code 4008.

### Abuse Prevention

- **Auto-reconnect Throttling**: Clients MUST implement exponential backoff (max 16s delay) to prevent reconnection storms.
- **IP-based Rate Limiting**: Server MAY enforce IP-based connection limits (e.g., 100 connections per IP per minute).

---

## Example Client Implementation (JavaScript)

```javascript
class Chat4AllWebSocket {
  constructor(apiUrl, accessToken) {
    this.apiUrl = apiUrl;
    this.accessToken = accessToken;
    this.ws = null;
    this.reconnectDelay = 1000; // Start with 1 second
  }

  connect() {
    const wsUrl = `${this.apiUrl}/ws?token=${this.accessToken}`;
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.reconnectDelay = 1000; // Reset delay on successful connection
    };

    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      console.log('Received event:', message);

      switch (message.type) {
        case 'connection.established':
          console.log('Connected as user:', message.user_id);
          break;
        case 'message.created':
          this.handleNewMessage(message.data);
          break;
        case 'message.status_updated':
          this.handleStatusUpdate(message.data);
          break;
        case 'ping':
          this.sendPong();
          break;
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    this.ws.onclose = (event) => {
      console.log('WebSocket closed:', event.code, event.reason);
      if (event.code === 4001) {
        // JWT expired, refresh token and reconnect
        this.refreshTokenAndReconnect();
      } else {
        // Normal reconnection with exponential backoff
        setTimeout(() => this.connect(), this.reconnectDelay);
        this.reconnectDelay = Math.min(this.reconnectDelay * 2, 16000); // Max 16s
      }
    };
  }

  sendPong() {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'pong',
        timestamp: new Date().toISOString()
      }));
    }
  }

  async refreshTokenAndReconnect() {
    // Call POST /auth/refresh to get new access token
    const response = await fetch('/auth/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        refresh_token: this.refreshToken,
        grant_type: 'refresh_token'
      })
    });

    if (response.ok) {
      const data = await response.json();
      this.accessToken = data.access_token;
      this.connect(); // Reconnect with new token
    } else {
      console.error('Failed to refresh token, user must re-authenticate');
    }
  }

  handleNewMessage(messageData) {
    // Update UI with new message
    console.log('New message:', messageData);
  }

  handleStatusUpdate(statusData) {
    // Update message status in UI
    console.log('Status update:', statusData);
  }

  disconnect() {
    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
    }
  }
}

// Usage
const wsClient = new Chat4AllWebSocket('ws://localhost:8000', 'eyJhbGci...');
wsClient.connect();
```

---

## Performance Considerations

### Scalability

- **Connections per Instance**: Each API instance can handle 10,000 concurrent WebSocket connections (tested with FastAPI + uvicorn).
- **Redis Pub/Sub Channels**: One channel per conversation. With millions of conversations, Redis can handle millions of channels efficiently.
- **Memory Usage**: Each WebSocket connection consumes ~10KB RAM (connection object + buffers). 10,000 connections = ~100MB per instance.

### Latency

- **End-to-End Latency**: <100ms from message creation to WebSocket delivery (API → Kafka → Worker → Redis Pub/Sub → API → WebSocket).
- **Breakdown**:
  - API → Outbox → Kafka: <50ms
  - Worker processing: <20ms
  - Redis Pub/Sub: <5ms
  - WebSocket send: <10ms

---

## Monitoring

### Metrics to Track

- `websocket_connections_active`: Gauge of active WebSocket connections per instance
- `websocket_messages_sent_total`: Counter of messages sent to clients
- `websocket_messages_failed_total`: Counter of failed message deliveries (connection broken)
- `websocket_connection_duration_seconds`: Histogram of connection durations

### Health Checks

- **Readiness Probe**: API instance is ready if it can accept WebSocket connections and connect to Redis Pub/Sub.
- **Liveness Probe**: API instance is live if it can respond to HTTP health check (GET /health).

---

## Future Enhancements

1. **Binary Protocol**: Use MessagePack or Protocol Buffers for more efficient serialization (reduce bandwidth).
2. **Presence Indicators**: Track online/offline status of users.
3. **Typing Indicators**: Real-time "User X is typing..." notifications.
4. **Read Receipts**: Instant read receipt delivery when a user opens a message.
5. **WebSocket Compression**: Enable per-message deflate extension for reduced bandwidth (RFC 7692).

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-11-30 | Initial specification for production-ready platform |
