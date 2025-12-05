# Usa uma imagem leve do Python 3.11
FROM python:3.11-slim

# Garante que os logs do Python apareçam imediatamente no console do Docker
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instala dependências do sistema necessárias para compilar bibliotecas (como psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala as dependências do Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código da pasta local para o container
COPY . .

# Expõe a porta (informativo)
EXPOSE 8000

# Comando para iniciar a API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]