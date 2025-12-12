#!/usr/bin/env python3
"""
Chat4All - Demonstração Automática

Este script demonstra automaticamente a comunicação entre dois usuários.
Ele cria uma conversa, envia mensagens de ambos os lados e mostra o fluxo completo.

Uso:
    python demo_chat.py
"""

import requests
import time
import uuid
import json
import base64
import os
import math
import hashlib
import mimetypes
import tempfile
from datetime import datetime
from colorama import init, Fore, Style

# Inicializa colorama
init(autoreset=True)

# Configuração
BASE_URL = "http://localhost:8000"

# Usuários de demonstração (IDs serão obtidos dinamicamente)
USER1 = {"username": "user1", "password": "password123", "id": None}
USER2 = {"username": "user2", "password": "password123", "id": None}


def print_header(text: str):
    """Imprime cabeçalho formatado."""
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.CYAN}  {text}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")


def print_step(step: int, text: str):
    """Imprime passo da demonstração."""
    print(f"{Fore.YELLOW}[Passo {step}]{Style.RESET_ALL} {text}")


def print_success(text: str):
    """Imprime mensagem de sucesso."""
    print(f"  {Fore.GREEN}✓ {text}{Style.RESET_ALL}")


def print_error(text: str):
    """Imprime mensagem de erro."""
    print(f"  {Fore.RED}✗ {text}{Style.RESET_ALL}")


def print_message(sender: str, content: str, color=Fore.WHITE):
    """Imprime mensagem de chat."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"  {Fore.BLUE}[{timestamp}]{Style.RESET_ALL} {color}{sender}:{Style.RESET_ALL} {content}")


def decode_jwt_payload(token: str) -> dict:
    """Decodifica o payload de um token JWT."""
    try:
        payload_b64 = token.split('.')[1]
        # Adiciona padding se necessário
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += '=' * padding
        payload_json = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_json)
    except Exception:
        return {}


def authenticate(user: dict) -> tuple:
    """
    Autentica um usuário e retorna o access_token e user_id.
    
    Args:
        user: Dicionário com username e password
        
    Returns:
        tuple: (access_token, user_id) ou (None, None)
    """
    try:
        response = requests.post(
            f"{BASE_URL}/auth/token",
            json={
                "grant_type": "password",
                "username": user["username"],
                "password": user["password"]
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data["access_token"]
            # Extrai user_id do JWT
            payload = decode_jwt_payload(token)
            user_id = payload.get("user_id")
            return token, user_id
        else:
            print_error(f"Falha na autenticação: {response.status_code}")
            return None, None
            
    except Exception as e:
        print_error(f"Erro: {e}")
        return None, None


def create_conversation(token: str, member_ids: list) -> int:
    """
    Cria uma conversa privada.
    
    Args:
        token: Access token
        member_ids: Lista de IDs dos membros
        
    Returns:
        int: ID da conversa ou None
    """
    try:
        response = requests.post(
            f"{BASE_URL}/v1/conversations",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "type": "private",
                "member_ids": member_ids
            },
            timeout=10
        )
        
        if response.status_code == 201:
            return response.json()["id"]
        else:
            print_error(f"Falha ao criar conversa: {response.status_code}")
            print_error(f"Detalhes: {response.text}")
            return None
            
    except Exception as e:
        print_error(f"Erro: {e}")
        return None


def send_message(token: str, conversation_id: int, content: str) -> bool:
    """
    Envia uma mensagem para uma conversa.
    
    Args:
        token: Access token
        conversation_id: ID da conversa
        content: Conteúdo da mensagem
        
    Returns:
        bool: True se enviada com sucesso
    """
    try:
        message_id = str(uuid.uuid4())
        
        response = requests.post(
            f"{BASE_URL}/v1/messages",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "message_id": message_id,
                "conversation_id": conversation_id,
                "payload": {
                    "type": "text",
                    "content": content
                },
                "channels": ["all"]
            },
            timeout=10
        )
        
        return response.status_code == 202
        
    except Exception as e:
        print_error(f"Erro ao enviar: {e}")
        return False


def get_messages(token: str, conversation_id: int) -> list:
    """
    Obtém mensagens de uma conversa.
    
    Args:
        token: Access token
        conversation_id: ID da conversa
        
    Returns:
        list: Lista de mensagens
    """
    try:
        response = requests.get(
            f"{BASE_URL}/v1/conversations/{conversation_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={"limit": 50, "offset": 0},
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json().get("messages", [])
        return []
        
    except Exception as e:
        print_error(f"Erro: {e}")
        return []


def create_test_file(size_kb: int = 100) -> str:
    """
    Cria um arquivo de teste temporário.
    
    Args:
        size_kb: Tamanho do arquivo em KB
        
    Returns:
        str: Caminho do arquivo criado
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"demo_file_{timestamp}.txt"
    filepath = os.path.join(tempfile.gettempdir(), filename)
    
    # Cria conteúdo de teste
    content = f"Arquivo de demonstração do Chat4All\n"
    content += f"Criado em: {datetime.now().isoformat()}\n"
    content += "=" * 50 + "\n"
    content += "Este arquivo foi gerado automaticamente para demonstrar\n"
    content += "o sistema de upload de arquivos em chunks.\n"
    content += "=" * 50 + "\n\n"
    
    # Preenche com conteúdo para atingir o tamanho desejado
    line = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 3 + "\n"
    target_size = size_kb * 1024
    
    while len(content.encode('utf-8')) < target_size:
        content += line
    
    # Trunca para o tamanho exato
    content_bytes = content.encode('utf-8')[:target_size]
    
    with open(filepath, 'wb') as f:
        f.write(content_bytes)
    
    return filepath


def upload_file(token: str, conversation_id: int, file_path: str) -> str:
    """
    Faz upload de um arquivo em chunks.
    
    Args:
        token: Access token
        conversation_id: ID da conversa
        file_path: Caminho do arquivo
        
    Returns:
        str: Upload ID se sucesso, None se falhou
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    mime_type, _ = mimetypes.guess_type(file_path)
    mime_type = mime_type or "application/octet-stream"
    
    # Calcula hash do arquivo
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    file_hash = sha256_hash.hexdigest()
    
    # Tamanho mínimo do chunk é 1MB
    chunk_size = 1024 * 1024  # 1MB
    total_chunks = math.ceil(file_size / chunk_size)
    
    # 1. Iniciar upload
    try:
        response = requests.post(
            f"{BASE_URL}/v1/files/initiate",
            headers=headers,
            json={
                "conversation_id": conversation_id,
                "filename": filename,
                "file_size": file_size,
                "mime_type": mime_type,
                "chunk_size": chunk_size
            },
            timeout=30
        )
        
        if response.status_code != 201:
            print_error(f"Falha ao iniciar upload: {response.text}")
            return None
        
        upload_data = response.json()
        upload_id = upload_data["upload_id"]
        
    except Exception as e:
        print_error(f"Erro ao iniciar upload: {e}")
        return None
    
    # 2. Enviar chunks (dados binários via application/octet-stream)
    with open(file_path, "rb") as f:
        for chunk_num in range(1, total_chunks + 1):
            chunk_data = f.read(chunk_size)
            chunk_hash = hashlib.sha256(chunk_data).hexdigest()
            
            try:
                response = requests.post(
                    f"{BASE_URL}/v1/files/{upload_id}/chunks",
                    params={
                        "chunk_number": chunk_num,
                        "checksum_sha256": chunk_hash
                    },
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/octet-stream"
                    },
                    data=chunk_data,  # Dados binários diretamente
                    timeout=60
                )
                
                if response.status_code != 200:
                    print_error(f"Falha ao enviar chunk {chunk_num}: {response.status_code} - {response.text}")
                    return None
                    
            except Exception as e:
                print_error(f"Erro ao enviar chunk: {e}")
                return None
    
    # 3. Completar upload (sem body JSON)
    try:
        response = requests.post(
            f"{BASE_URL}/v1/files/{upload_id}/complete",
            headers={
                "Authorization": f"Bearer {token}"
            },
            timeout=30
        )
        
        if response.status_code not in (200, 202):
            print_error(f"Falha ao completar upload: {response.text}")
            return None
            
    except Exception as e:
        print_error(f"Erro ao completar upload: {e}")
        return None
    
    # 4. Aguardar merge completar
    max_wait = 30  # segundos
    wait_interval = 1  # segundo
    elapsed = 0
    
    print(f"  {Fore.WHITE}Aguardando processamento do merge...{Style.RESET_ALL}", end="", flush=True)
    
    while elapsed < max_wait:
        try:
            response = requests.get(
                f"{BASE_URL}/v1/files/{upload_id}/status",
                headers={
                    "Authorization": f"Bearer {token}"
                },
                timeout=10
            )
            
            if response.status_code == 200:
                status_data = response.json()
                file_status = status_data.get("status", "").upper()
                
                if file_status == "COMPLETED":
                    print(f" {Fore.GREEN}OK!{Style.RESET_ALL}")
                    return upload_id
                elif file_status == "FAILED":
                    print()
                    print_error("Merge do arquivo falhou")
                    return None
            
            print(".", end="", flush=True)
            time.sleep(wait_interval)
            elapsed += wait_interval
            
        except Exception as e:
            print()
            print_error(f"Erro ao verificar status: {e}")
            return None
    
    print()
    print_error("Timeout aguardando merge do arquivo")
    return None


def send_file_message(token: str, conversation_id: int, file_path: str, upload_id: str) -> bool:
    """
    Envia uma mensagem com arquivo.
    
    Args:
        token: Access token
        conversation_id: ID da conversa
        file_path: Caminho do arquivo
        upload_id: ID do upload
        
    Returns:
        bool: True se enviado com sucesso
    """
    try:
        message_id = str(uuid.uuid4())
        
        response = requests.post(
            f"{BASE_URL}/v1/messages",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "message_id": message_id,
                "conversation_id": conversation_id,
                "payload": {
                    "type": "file",
                    "file_id": upload_id
                },
                "channels": ["all"]
            },
            timeout=10
        )
        
        if response.status_code != 202:
            print_error(f"Status: {response.status_code} - {response.text}")
        
        return response.status_code == 202
        
    except Exception as e:
        print_error(f"Erro ao enviar mensagem: {e}")
        return False


def check_api_health() -> bool:
    """Verifica se a API está rodando."""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        return response.status_code == 200
    except:
        return False


def run_demo():
    """Executa a demonstração do chat."""
    
    print_header("Chat4All - Demonstração de Chat em Tempo Real")
    
    # Verifica se a API está rodando
    print_step(0, "Verificando conexão com a API...")
    if not check_api_health():
        print_error(f"API não está acessível em {BASE_URL}")
        print_error("Certifique-se que o Docker está rodando: docker-compose up -d")
        return
    print_success("API está rodando!")
    
    # Passo 1: Autenticar ambos os usuários
    print_step(1, "Autenticando usuários...")
    
    token1, user1_id = authenticate(USER1)
    if token1:
        USER1["id"] = user1_id
        print_success(f"user1 autenticado com sucesso (ID: {user1_id})")
    else:
        return
        
    token2, user2_id = authenticate(USER2)
    if token2:
        USER2["id"] = user2_id
        print_success(f"user2 autenticado com sucesso (ID: {user2_id})")
    else:
        return
    
    # Passo 2: Criar conversa privada
    print_step(2, "Criando conversa privada entre user1 e user2...")
    
    conversation_id = create_conversation(token1, [USER1["id"], USER2["id"]])
    if conversation_id:
        print_success(f"Conversa criada com ID: {conversation_id}")
    else:
        return
    
    # Passo 3: Simular troca de mensagens
    print_step(3, "Simulando troca de mensagens...")
    print()
    
    # Diálogo de exemplo
    messages = [
        (USER1, token1, "Olá! Como você está?"),
        (USER2, token2, "Oi! Estou bem, obrigado! E você?"),
        (USER1, token1, "Também estou bem! Vamos testar o sistema de chat."),
        (USER2, token2, "Ótima ideia! Este sistema parece funcionar bem."),
        (USER1, token1, "Sim! A comunicação em tempo real está funcionando perfeitamente."),
        (USER2, token2, "Incrível! 🎉"),
    ]
    
    for user, token, content in messages:
        color = Fore.CYAN if user == USER1 else Fore.MAGENTA
        
        if send_message(token, conversation_id, content):
            print_message(user["username"], content, color)
        else:
            print_error(f"Falha ao enviar mensagem de {user['username']}")
        
        time.sleep(0.5)  # Pequeno delay para simular conversa real
    
    print()
    
    # Passo 4: Demonstrar upload de arquivo
    print_step(4, "Demonstrando upload de arquivo...")
    
    # Cria arquivo de teste (500KB para ter chunks)
    test_file = create_test_file(size_kb=500)
    filename = os.path.basename(test_file)
    file_size = os.path.getsize(test_file)
    
    print(f"  {Fore.WHITE}Arquivo de teste: {filename} ({file_size:,} bytes){Style.RESET_ALL}")
    
    # Faz upload
    upload_id = upload_file(token1, conversation_id, test_file)
    
    if upload_id:
        print_success(f"Upload concluído! ID: {upload_id}")
        
        # Envia mensagem com o arquivo
        if send_file_message(token1, conversation_id, test_file, upload_id):
            print_success(f"{USER1['username']} enviou um arquivo: {filename}")
        else:
            print_error("Falha ao enviar mensagem com arquivo")
    else:
        print_error("Falha no upload do arquivo")
    
    # Limpa arquivo temporário
    try:
        os.remove(test_file)
    except:
        pass
    
    print()
    
    # Passo 5: Verificar mensagens no histórico
    print_step(5, "Verificando histórico de mensagens...")
    
    time.sleep(1)  # Aguarda processamento
    
    stored_messages = get_messages(token1, conversation_id)
    
    if stored_messages:
        print_success(f"{len(stored_messages)} mensagens armazenadas no histórico")
    else:
        print_error("Nenhuma mensagem encontrada no histórico")
    
    # Resumo
    print_header("Demonstração Concluída!")
    
    file_sent = 1 if upload_id else 0
    
    print(f"""
{Fore.GREEN}Resumo:{Style.RESET_ALL}
  • Conversa ID: {conversation_id}
  • Mensagens de texto enviadas: {len(messages)}
  • Arquivos enviados: {file_sent}
  • Mensagens no histórico: {len(stored_messages)}

{Fore.YELLOW}Próximos passos:{Style.RESET_ALL}
  1. Use o cliente interativo: python chat_client.py -u user1 -p password123
  2. Abra outro terminal: python chat_client.py -u user2 -p password123
  3. Entre na conversa: /entrar {conversation_id}
  4. Envie mensagens: digite qualquer texto
  5. Envie arquivos: /arquivo <caminho_do_arquivo>
""")


if __name__ == "__main__":
    try:
        run_demo()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Demonstração interrompida.{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}Erro: {e}{Style.RESET_ALL}")
