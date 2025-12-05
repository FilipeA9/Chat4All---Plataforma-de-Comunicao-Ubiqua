FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Dependências de sistema (Postgres driver precisa de libpq-dev)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Não precisa de EXPOSE, pois é um worker de background

# Inicia o script Python diretamente
CMD ["python", "main.py"]