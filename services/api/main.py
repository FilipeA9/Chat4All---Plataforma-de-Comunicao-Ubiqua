import json
import os
import asyncio
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from aiokafka import AIOKafkaProducer

from database import engine, Base, get_db
from models import Message, Conversation
import auth
from pydantic import BaseModel
from typing import List, Dict, Any

# Cria tabelas ao iniciar (simples para dev)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Chat4All API", version="1.0.0")

# --- Configuração Kafka ---
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BROKER", "localhost:9092")
producer = None

@app.on_event("startup")
async def startup_event():
    global producer
    # Tenta conectar ao Kafka (pode precisar de retry na vida real)
    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
    try:
        await producer.start()
    except Exception as e:
        print(f"Erro ao conectar Kafka: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    if producer:
        await producer.stop()

# --- Schemas Pydantic (Input/Output) ---
class TokenResponse(BaseModel):
    access_token: str
    expires_in: int

class LoginRequest(BaseModel):
    client_user: str
    client_password: str

class MessagePayload(BaseModel):
    type: str
    text: str = None
    file_id: str = None

class MessageInput(BaseModel):
    conversation_id: str
    message_id: str = None # Opcional, geramos se não vier
    to: List[str]
    channels: List[str]
    payload: MessagePayload
    metadata: Dict[str, Any] = {}

# --- Endpoints ---

@app.post("/auth/token", response_model=TokenResponse)
def login(creds: LoginRequest):
    # Mock de validação de usuário (aceita qualquer coisa por enquanto)
    if creds.client_user and creds.client_password:
        token = auth.create_access_token(data={"sub": creds.client_user})
        return {"access_token": token, "expires_in": 3600}
    raise HTTPException(status_code=400, detail="Credenciais inválidas")

@app.post("/v1/messages")
async def send_message(
    msg: MessageInput, 
    user: str = Depends(auth.verify_token),
    db: Session = Depends(get_db)
):
    """
    Recebe mensagem, valida e publica no Kafka.
    NÃO salva no banco síncronamente (isso é job do Worker).
    """
    if not producer:
        raise HTTPException(status_code=503, detail="Kafka indisponível")

    # Garante ID
    import uuid
    msg_id = msg.message_id or str(uuid.uuid4())
    
    # Estrutura do evento para o Kafka
    kafka_event = {
        "event_type": "NEW_MESSAGE",
        "message_id": msg_id,
        "conversation_id": msg.conversation_id,
        "from": user,
        "to": msg.to,
        "channels": msg.channels,
        "payload": msg.payload.dict(),
        "metadata": msg.metadata,
        "timestamp": str(datetime.now())
    }

    # Publica no tópico 'messages' particionado por conversation_id
    # Isso garante ordem de mensagens na mesma conversa
    await producer.send_and_wait(
        topic=os.getenv("KAFKA_TOPIC_MESSAGES", "messages"),
        value=json.dumps(kafka_event).encode("utf-8"),
        key=msg.conversation_id.encode("utf-8")
    )

    return {"status": "accepted", "message_id": msg_id}

@app.get("/")
def health_check():
    return {"status": "ok", "service": "Chat4All API"}