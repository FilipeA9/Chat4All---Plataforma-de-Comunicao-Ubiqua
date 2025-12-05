import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Lê variáveis do .env (injetadas pelo Docker)
DB_USER = os.getenv("POSTGRES_USER", "chat_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "chat_password")
DB_HOST = os.getenv("POSTGRES_HOST", "postgres")
DB_NAME = os.getenv("POSTGRES_DB", "chat4all_db")

SQLALCHEMY_DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependência para injetar sessão do banco nas rotas
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()