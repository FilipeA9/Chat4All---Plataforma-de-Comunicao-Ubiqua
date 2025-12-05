import asyncio
import json
import os
import logging
from fastapi import FastAPI, BackgroundTasks
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from datetime import datetime

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='[WhatsApp Mock] %(message)s')
logger = logging.getLogger("ConnectorWA")

app = FastAPI(title="WhatsApp Connector Mock")

# Configurações Kafka
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BROKER", "localhost:9092")
TOPIC_OUTBOX = os.getenv("KAFKA_TOPIC_WA", "whatsapp_outbox") # Onde lemos mensagens para enviar
TOPIC_INBOX = os.getenv("KAFKA_TOPIC_MESSAGES", "messages")   # Onde jogamos mensagens recebidas

# Variáveis globais para os clientes Kafka
consumer = None
producer = None

@app.on_event("startup")
async def startup_event():
    global consumer, producer
    
    # 1. Iniciar Producer (Para enviar mensagens recebidas do WA para o Chat4All)
    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
    await producer.start()

    # 2. Iniciar Consumer (Para ler mensagens do Chat4All e "enviar" para o WA)
    consumer = AIOKafkaConsumer(
        TOPIC_OUTBOX,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id="connector-wa-group"
    )
    await consumer.start()
    
    # Inicia a tarefa de consumo em background
    asyncio.create_task(consume_messages())

@app.on_event("shutdown")
async def shutdown_event():
    if consumer: await consumer.stop()
    if producer: await producer.stop()

async def consume_messages():
    """Lê a fila de saída e simula o envio para o WhatsApp Real"""
    try:
        async for msg in consumer:
            payload = json.loads(msg.value.decode('utf-8'))
            message_id = payload.get("message_id")
            recipient = payload.get("to")
            text = payload.get("payload", {}).get("text")
            
            # SIMULAÇÃO DE ENVIO
            logger.info(f">>> A ENVIAR mensagem {message_id} para {recipient}...")
            await asyncio.sleep(1) # Simula latência de rede
            logger.info(f"VVV [ENTREGUE] Mensagem enviada com sucesso: '{text}'")
            
            # TODO: Aqui poderia chamar a API principal para atualizar status para DELIVERED
            # requests.patch(f"http://api:8000/v1/messages/{message_id}/status", json={"status": "DELIVERED"})
            
    except Exception as e:
        logger.error(f"Erro no consumidor: {e}")

# --- Endpoints para Simulação ---

@app.post("/webhook/receive")
async def receive_fake_message(from_number: str, text: str):
    """
    Simula o recebimento de uma mensagem vinda do WhatsApp.
    O utilizador chama este endpoint para fingir que alguém falou no WA.
    """
    import uuid
    
    # Constrói a mensagem no formato interno do Chat4All
    internal_message = {
        "event_type": "INCOMING_MESSAGE",
        "message_id": str(uuid.uuid4()),
        "conversation_id": f"conv_{from_number}", # Simplificação: conversation baseada no numero
        "from": from_number,
        "to": ["chat4all-admin"], # Destinatário padrão
        "channels": ["whatsapp"],
        "payload": {"type": "text", "text": text},
        "metadata": {"origin": "webhook_mock"},
        "timestamp": str(datetime.now())
    }
    
    # Publica no tópico central de mensagens
    # O Router-Worker vai ler isto e guardar na BD
    await producer.send_and_wait(
        TOPIC_INBOX,
        value=json.dumps(internal_message).encode("utf-8")
    )
    
    return {"status": "received_by_connector", "forwarded_to_kafka": True}