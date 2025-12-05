import asyncio
import json
import os
import logging
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
from models import Message, MessageStatus

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RouterWorker")

# Garante que as tabelas existam (caso o worker suba antes da API)
Base.metadata.create_all(bind=engine)

# Configurações do Kafka via variáveis de ambiente
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BROKER", "localhost:9092")
TOPIC_MESSAGES = os.getenv("KAFKA_TOPIC_MESSAGES", "messages")
TOPIC_WA = os.getenv("KAFKA_TOPIC_WA", "whatsapp_outbox")
TOPIC_INSTA = os.getenv("KAFKA_TOPIC_INSTA", "instagram_outbox")

async def process_message(msg_json: dict, db: Session, producer: AIOKafkaProducer):
    """
    Lógica de negócio: Salvar no banco e rotear para conectores
    """
    msg_id = msg_json.get("message_id")
    logger.info(f"Processando mensagem {msg_id} de {msg_json.get('from')}")

    try:
        # 1. Persistência (PostgreSQL)
        # Cria objeto da mensagem
        new_message = Message(
            id=msg_id,
            conversation_id=msg_json.get("conversation_id"),
            sender=msg_json.get("from"),
            # Pega o primeiro canal ou define como 'multi' se houver vários, 
            # mas salva a lista completa nos metadados para auditoria
            channel=msg_json.get("channels", ["chat4all"])[0], 
            content_type=msg_json.get("payload", {}).get("type", "text"),
            payload=msg_json.get("payload"),
            status=MessageStatus.SENT.value,
            metadata_info={
                "target_channels": msg_json.get("channels"),
                "original_meta": msg_json.get("metadata")
            }
        )
        
        db.add(new_message)
        db.commit()
        logger.info(f"Mensagem {msg_id} persistida no DB com status SENT.")

        # 2. Roteamento (Kafka)
        channels = msg_json.get("channels", [])
        
        # Se tiver WhatsApp na lista, joga no tópico do WhatsApp
        if "whatsapp" in channels:
            logger.info(f"Roteando {msg_id} para fila do WhatsApp...")
            await producer.send_and_wait(
                TOPIC_WA, 
                value=json.dumps(msg_json).encode("utf-8")
            )

        # Se tiver Instagram na lista, joga no tópico do Instagram
        if "instagram" in channels:
            logger.info(f"Roteando {msg_id} para fila do Instagram...")
            await producer.send_and_wait(
                TOPIC_INSTA, 
                value=json.dumps(msg_json).encode("utf-8")
            )
            
    except Exception as e:
        logger.error(f"Erro ao processar mensagem {msg_id}: {e}")
        db.rollback()
        # Em prod, aqui enviariamos para uma Dead Letter Queue (DLQ)

async def consume():
    logger.info("Iniciando Router Worker...")
    
    # Consumidor: Lê do tópico 'messages'
    consumer = AIOKafkaConsumer(
        TOPIC_MESSAGES,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id="chat4all-router-group", # Importante para controle de offset
        auto_offset_reset='earliest'
    )

    # Produtor: Escreve nos tópicos de conectores (WA/Insta)
    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)

    await consumer.start()
    await producer.start()
    
    try:
        # Loop infinito de processamento
        async for msg in consumer:
            db = SessionLocal()
            try:
                msg_data = json.loads(msg.value.decode('utf-8'))
                await process_message(msg_data, db, producer)
            except Exception as e:
                logger.error(f"Erro fatal no loop: {e}")
            finally:
                db.close()
    finally:
        await consumer.stop()
        await producer.stop()

if __name__ == "__main__":
    asyncio.run(consume())