#!/usr/bin/env python3
"""
Chat4All - Teste de Upload de Arquivos

Este script testa o upload de arquivos em chunks para a API do Chat4All.
Ele simula o envio de um arquivo dividido em partes (chunks).

Uso:
    python test_file_upload.py
    python test_file_upload.py --file <caminho_do_arquivo>
"""

import requests
import argparse
import os
import math
import hashlib
import uuid
import base64
import json
import time
from datetime import datetime
from colorama import init, Fore, Style

# Inicializa colorama
init(autoreset=True)

# Configuração
BASE_URL = "http://localhost:8000"


def print_header(text: str):
    """Imprime cabeçalho formatado."""
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"{Fore.CYAN}  {text}")
    print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")


def print_step(step: int, text: str):
    """Imprime passo do teste."""
    print(f"{Fore.YELLOW}[Passo {step}]{Style.RESET_ALL} {text}")


def print_success(text: str):
    """Imprime mensagem de sucesso."""
    print(f"  {Fore.GREEN}✓ {text}{Style.RESET_ALL}")


def print_error(text: str):
    """Imprime mensagem de erro."""
    print(f"  {Fore.RED}✗ {text}{Style.RESET_ALL}")


def print_info(text: str):
    """Imprime mensagem informativa."""
    print(f"  {Fore.BLUE}ℹ {text}{Style.RESET_ALL}")


def decode_jwt_payload(token: str) -> dict:
    """Decodifica o payload de um token JWT."""
    try:
        payload_b64 = token.split('.')[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += '=' * padding
        payload_json = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_json)
    except Exception:
        return {}


def authenticate(username: str, password: str) -> tuple:
    """
    Autentica um usuário e retorna o access_token e user_id.
    """
    try:
        response = requests.post(
            f"{BASE_URL}/auth/token",
            json={
                "grant_type": "password",
                "username": username,
                "password": password
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data["access_token"]
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
    """Cria uma conversa privada."""
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


def calculate_sha256(data: bytes) -> str:
    """Calcula o hash SHA-256 de dados."""
    return hashlib.sha256(data).hexdigest()


def create_test_file(filename: str, size_mb: float = 1) -> bytes:
    """Cria um arquivo de teste com dados aleatórios."""
    size_bytes = int(size_mb * 1024 * 1024)
    # Cria dados que parecem um arquivo (texto repetido)
    content = f"Chat4All Test File - {datetime.now().isoformat()}\n"
    content += "=" * 80 + "\n"
    content += "Este é um arquivo de teste para verificar o upload de arquivos.\n" * 100
    
    # Repete até atingir o tamanho desejado
    while len(content.encode()) < size_bytes:
        content += f"Linha {len(content)}: " + "X" * 100 + "\n"
    
    return content[:size_bytes].encode()


def initiate_upload(token: str, conversation_id: int, filename: str, 
                   file_size: int, mime_type: str, chunk_size: int = 1048576) -> dict:
    """
    Inicia uma sessão de upload de arquivo.
    
    Args:
        token: Token de acesso
        conversation_id: ID da conversa
        filename: Nome do arquivo
        file_size: Tamanho do arquivo em bytes
        mime_type: Tipo MIME do arquivo
        chunk_size: Tamanho de cada chunk (default: 1MB)
        
    Returns:
        dict: Resposta da API com upload_id, total_chunks, etc.
    """
    try:
        response = requests.post(
            f"{BASE_URL}/v1/files/initiate",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "conversation_id": conversation_id,
                "filename": filename,
                "file_size": file_size,
                "mime_type": mime_type,
                "chunk_size": chunk_size
            },
            timeout=10
        )
        
        if response.status_code == 201:
            return response.json()
        else:
            print_error(f"Falha ao iniciar upload: {response.status_code}")
            print_error(f"Detalhes: {response.text}")
            return None
            
    except Exception as e:
        print_error(f"Erro: {e}")
        return None


def upload_chunk(token: str, upload_id: str, chunk_number: int, 
                chunk_data: bytes, checksum: str = None) -> dict:
    """
    Faz upload de um chunk do arquivo.
    
    Args:
        token: Token de acesso
        upload_id: ID do upload
        chunk_number: Número do chunk (1-based)
        chunk_data: Dados binários do chunk
        checksum: Checksum SHA-256 do chunk (opcional)
        
    Returns:
        dict: Resposta da API com progresso
    """
    try:
        params = {"chunk_number": chunk_number}
        if checksum:
            params["checksum_sha256"] = checksum
            
        response = requests.post(
            f"{BASE_URL}/v1/files/{upload_id}/chunks",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/octet-stream"
            },
            params=params,
            data=chunk_data,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print_error(f"Falha ao enviar chunk {chunk_number}: {response.status_code}")
            print_error(f"Detalhes: {response.text}")
            return None
            
    except Exception as e:
        print_error(f"Erro no chunk {chunk_number}: {e}")
        return None


def get_upload_status(token: str, upload_id: str) -> dict:
    """
    Obtém o status do upload.
    """
    try:
        response = requests.get(
            f"{BASE_URL}/v1/files/{upload_id}/status",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print_error(f"Falha ao obter status: {response.status_code}")
            return None
            
    except Exception as e:
        print_error(f"Erro: {e}")
        return None


def complete_upload(token: str, upload_id: str) -> dict:
    """
    Completa o upload e inicia o merge dos chunks.
    """
    try:
        response = requests.post(
            f"{BASE_URL}/v1/files/{upload_id}/complete",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        
        if response.status_code == 202:
            return response.json()
        else:
            print_error(f"Falha ao completar upload: {response.status_code}")
            print_error(f"Detalhes: {response.text}")
            return None
            
    except Exception as e:
        print_error(f"Erro: {e}")
        return None


def send_file_message(token: str, conversation_id: int, file_id: str) -> bool:
    """
    Envia uma mensagem com o arquivo.
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
                    "file_id": file_id
                },
                "channels": ["all"]
            },
            timeout=10
        )
        
        return response.status_code == 202
        
    except Exception as e:
        print_error(f"Erro: {e}")
        return False


def check_api_health() -> bool:
    """Verifica se a API está rodando."""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        return response.status_code == 200
    except:
        return False


def run_file_upload_test(file_path: str = None, file_size_mb: float = 0.5):
    """
    Executa o teste de upload de arquivo.
    
    Args:
        file_path: Caminho para um arquivo existente (opcional)
        file_size_mb: Tamanho do arquivo de teste em MB (se file_path não for fornecido)
    """
    
    print_header("Chat4All - Teste de Upload de Arquivos")
    
    # Passo 0: Verificar API
    print_step(0, "Verificando conexão com a API...")
    if not check_api_health():
        print_error(f"API não está acessível em {BASE_URL}")
        print_error("Certifique-se que o Docker está rodando: docker-compose up -d")
        return
    print_success("API está rodando!")
    
    # Passo 1: Autenticar usuários
    print_step(1, "Autenticando usuários...")
    
    token1, user1_id = authenticate("user1", "password123")
    if not token1:
        return
    print_success(f"user1 autenticado (ID: {user1_id})")
    
    token2, user2_id = authenticate("user2", "password123")
    if not token2:
        return
    print_success(f"user2 autenticado (ID: {user2_id})")
    
    # Passo 2: Criar ou usar conversa existente
    print_step(2, "Criando conversa...")
    
    conversation_id = create_conversation(token1, [user1_id, user2_id])
    if not conversation_id:
        return
    print_success(f"Conversa criada com ID: {conversation_id}")
    
    # Passo 3: Preparar arquivo
    print_step(3, "Preparando arquivo para upload...")
    
    if file_path and os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            file_data = f.read()
        filename = os.path.basename(file_path)
        # Determinar MIME type baseado na extensão
        ext = os.path.splitext(filename)[1].lower()
        mime_types = {
            '.txt': 'text/plain',
            '.pdf': 'application/pdf',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.mp4': 'video/mp4',
            '.zip': 'application/zip',
        }
        mime_type = mime_types.get(ext, 'application/octet-stream')
    else:
        file_data = create_test_file("test_file.txt", file_size_mb)
        filename = f"test_file_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        mime_type = "text/plain"
    
    file_size = len(file_data)
    file_checksum = calculate_sha256(file_data)
    
    print_success(f"Arquivo: {filename}")
    print_info(f"Tamanho: {file_size:,} bytes ({file_size/1024/1024:.2f} MB)")
    print_info(f"SHA-256: {file_checksum[:16]}...")
    
    # Passo 4: Iniciar upload
    print_step(4, "Iniciando sessão de upload...")
    
    # Usar chunks de 1MB (mínimo exigido pela API)
    chunk_size = 1024 * 1024  # 1MB (1048576 bytes)
    
    upload_info = initiate_upload(
        token=token1,
        conversation_id=conversation_id,
        filename=filename,
        file_size=file_size,
        mime_type=mime_type,
        chunk_size=chunk_size
    )
    
    if not upload_info:
        return
        
    upload_id = upload_info["upload_id"]
    total_chunks = upload_info["total_chunks"]
    
    print_success(f"Upload ID: {upload_id}")
    print_info(f"Total de chunks: {total_chunks}")
    print_info(f"Tamanho do chunk: {chunk_size:,} bytes")
    
    # Passo 5: Enviar chunks
    print_step(5, f"Enviando {total_chunks} chunk(s)...")
    
    for chunk_num in range(1, total_chunks + 1):
        start = (chunk_num - 1) * chunk_size
        end = min(start + chunk_size, file_size)
        chunk_data = file_data[start:end]
        chunk_checksum = calculate_sha256(chunk_data)
        
        result = upload_chunk(
            token=token1,
            upload_id=upload_id,
            chunk_number=chunk_num,
            chunk_data=chunk_data,
            checksum=chunk_checksum
        )
        
        if result:
            percentage = result.get("percentage", 0)
            print(f"\r  {Fore.GREEN}✓ Chunk {chunk_num}/{total_chunks} enviado ({percentage:.1f}%){Style.RESET_ALL}", end="")
        else:
            print()
            print_error(f"Falha ao enviar chunk {chunk_num}")
            return
    
    print()  # Nova linha após progresso
    print_success("Todos os chunks enviados com sucesso!")
    
    # Passo 6: Verificar status
    print_step(6, "Verificando status do upload...")
    
    status_info = get_upload_status(token1, upload_id)
    if status_info:
        print_success(f"Status: {status_info.get('status')}")
        print_info(f"Chunks enviados: {status_info.get('uploaded_chunks')}/{status_info.get('total_chunks')}")
        print_info(f"Progresso: {status_info.get('percentage')}%")
        
        missing = status_info.get('missing_chunks')
        if missing:
            print_error(f"Chunks faltando: {missing}")
            return
    
    # Passo 7: Completar upload
    print_step(7, "Completando upload...")
    
    complete_result = complete_upload(token1, upload_id)
    if complete_result:
        print_success(f"Status: {complete_result.get('status')}")
        print_info(f"Mensagem: {complete_result.get('message')}")
    else:
        print_error("Falha ao completar upload")
        return
    
    # Passo 8: Aguardar merge e verificar status final
    print_step(8, "Aguardando processamento do arquivo...")
    
    time.sleep(2)  # Aguarda processamento
    
    final_status = get_upload_status(token1, upload_id)
    if final_status:
        print_success(f"Status final: {final_status.get('status')}")
        if final_status.get('download_url'):
            print_info(f"URL de download disponível")
            print_info(f"File ID: {final_status.get('file_id')}")
    
    # Passo 9: Enviar mensagem com arquivo
    print_step(9, "Enviando mensagem com arquivo...")
    
    file_id = final_status.get('file_id') or upload_id
    
    if send_file_message(token1, conversation_id, str(file_id)):
        print_success("Mensagem com arquivo enviada com sucesso!")
    else:
        print_error("Falha ao enviar mensagem com arquivo")
    
    # Resumo
    print_header("Teste de Upload Concluído!")
    
    print(f"""
{Fore.GREEN}Resumo:{Style.RESET_ALL}
  • Arquivo: {filename}
  • Tamanho: {file_size:,} bytes
  • Upload ID: {upload_id}
  • Conversa ID: {conversation_id}
  • Chunks enviados: {total_chunks}
  • Status: {final_status.get('status') if final_status else 'desconhecido'}
""")


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description="Chat4All - Teste de Upload de Arquivos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  python test_file_upload.py                    # Cria arquivo de teste de 0.5MB
  python test_file_upload.py --size 2           # Cria arquivo de teste de 2MB
  python test_file_upload.py --file meu_doc.pdf # Envia arquivo existente
        """
    )
    
    parser.add_argument(
        "-f", "--file",
        help="Caminho para um arquivo existente para upload"
    )
    
    parser.add_argument(
        "-s", "--size",
        type=float,
        default=0.5,
        help="Tamanho do arquivo de teste em MB (default: 0.5)"
    )
    
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="URL base da API (default: http://localhost:8000)"
    )
    
    args = parser.parse_args()
    
    global BASE_URL
    BASE_URL = args.url
    
    try:
        run_file_upload_test(file_path=args.file, file_size_mb=args.size)
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Teste interrompido.{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}Erro: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
