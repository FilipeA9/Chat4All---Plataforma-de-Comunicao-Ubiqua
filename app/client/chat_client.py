#!/usr/bin/env python3
"""
Chat4All Command Line Client

Este cliente permite simular um chat em tempo real consumindo a API do Chat4All.
Suporta autenticação, criação de conversas, envio de mensagens e recebimento 
em tempo real via WebSocket.

Uso:
    python chat_client.py --user <username> --password <password>
    
Exemplo:
    # Terminal 1 - Usuário 1
    python chat_client.py --user user1 --password password123
    
    # Terminal 2 - Usuário 2
    python chat_client.py --user user2 --password password123
"""

import argparse
import asyncio
import json
import sys
import threading
import uuid
import base64
import os
import math
import hashlib
import mimetypes
from datetime import datetime
from typing import Optional

import requests
import websockets
from colorama import init, Fore, Style, Back

# Inicializa colorama para suporte a cores no Windows
init(autoreset=True)


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


class Chat4AllClient:
    """Cliente de linha de comando para o Chat4All."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.user_id: Optional[int] = None
        self.username: Optional[str] = None
        self.current_conversation_id: Optional[int] = None
        self.running = True
        self.ws_connection = None
        
    def print_header(self):
        """Imprime o cabeçalho do cliente."""
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"{Fore.CYAN}      Chat4All - Cliente de Chat em Tempo Real")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}\n")
        
    def print_success(self, message: str):
        """Imprime mensagem de sucesso."""
        print(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")
        
    def print_error(self, message: str):
        """Imprime mensagem de erro."""
        print(f"{Fore.RED}✗ {message}{Style.RESET_ALL}")
        
    def print_info(self, message: str):
        """Imprime mensagem informativa."""
        print(f"{Fore.YELLOW}ℹ {message}{Style.RESET_ALL}")
        
    def print_message(self, sender: str, content: str, timestamp: str, is_me: bool = False):
        """Imprime uma mensagem de chat."""
        time_str = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).strftime("%H:%M:%S")
        
        if is_me:
            print(f"{Fore.BLUE}[{time_str}] {Fore.CYAN}Você: {Style.RESET_ALL}{content}")
        else:
            print(f"{Fore.BLUE}[{time_str}] {Fore.MAGENTA}{sender}: {Style.RESET_ALL}{content}")
    
    def authenticate(self, username: str, password: str) -> bool:
        """
        Autentica o usuário na API.
        
        Args:
            username: Nome do usuário
            password: Senha do usuário
            
        Returns:
            bool: True se autenticado com sucesso
        """
        self.print_info(f"Autenticando como '{username}'...")
        
        try:
            response = requests.post(
                f"{self.base_url}/auth/token",
                json={
                    "grant_type": "password",
                    "username": username,
                    "password": password
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                self.access_token = data["access_token"]
                self.refresh_token = data["refresh_token"]
                self.username = username
                
                # Extrai user_id do JWT
                payload = decode_jwt_payload(self.access_token)
                self.user_id = payload.get("user_id")
                
                self.print_success(f"Autenticado com sucesso como '{username}' (ID: {self.user_id})!")
                return True
            else:
                self.print_error(f"Falha na autenticação: {response.json().get('detail', 'Erro desconhecido')}")
                return False
                
        except requests.exceptions.ConnectionError:
            self.print_error("Não foi possível conectar à API. Verifique se o servidor está rodando.")
            return False
        except Exception as e:
            self.print_error(f"Erro durante autenticação: {e}")
            return False
    
    def _get_headers(self) -> dict:
        """Retorna headers de autenticação."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
            
    def list_conversations(self) -> list:
        """
        Lista as conversas do usuário.
        
        Returns:
            list: Lista de conversas
        """
        try:
            response = requests.get(
                f"{self.base_url}/v1/conversations",
                headers=self._get_headers(),
                params={"limit": 20, "offset": 0},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("items", [])
            else:
                self.print_error(f"Erro ao listar conversas: {response.status_code}")
                return []
                
        except Exception as e:
            self.print_error(f"Erro ao listar conversas: {e}")
            return []
    
    def create_conversation(self, member_ids: list, name: str = None) -> Optional[int]:
        """
        Cria uma nova conversa.
        
        Args:
            member_ids: Lista de IDs dos membros
            name: Nome da conversa (opcional para privada)
            
        Returns:
            int: ID da conversa criada ou None
        """
        try:
            payload = {
                "type": "private" if len(member_ids) == 2 else "group",
                "member_ids": member_ids
            }
            
            if name:
                payload["name"] = name
                
            response = requests.post(
                f"{self.base_url}/v1/conversations",
                headers=self._get_headers(),
                json=payload,
                timeout=10
            )
            
            if response.status_code == 201:
                data = response.json()
                self.print_success(f"Conversa criada com ID: {data['id']}")
                return data["id"]
            else:
                self.print_error(f"Erro ao criar conversa: {response.json().get('detail', 'Erro')}")
                return None
                
        except Exception as e:
            self.print_error(f"Erro ao criar conversa: {e}")
            return None
    
    def send_message(self, conversation_id: int, content: str) -> bool:
        """
        Envia uma mensagem para uma conversa.
        
        Args:
            conversation_id: ID da conversa
            content: Conteúdo da mensagem
            
        Returns:
            bool: True se enviada com sucesso
        """
        try:
            message_id = str(uuid.uuid4())
            
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self._get_headers(),
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
            
            if response.status_code == 202:
                return True
            else:
                detail = response.json().get('detail', 'Erro desconhecido')
                self.print_error(f"Erro ao enviar mensagem: {detail}")
                return False
                
        except Exception as e:
            self.print_error(f"Erro ao enviar mensagem: {e}")
            return False
    
    def upload_file(self, conversation_id: int, file_path: str) -> Optional[str]:
        """
        Faz upload de um arquivo em chunks.
        
        Args:
            conversation_id: ID da conversa
            file_path: Caminho do arquivo
            
        Returns:
            str: Upload ID se sucesso, None se falhou
        """
        if not os.path.exists(file_path):
            self.print_error(f"Arquivo não encontrado: {file_path}")
            return None
        
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
        
        self.print_info(f"Enviando arquivo: {filename} ({file_size:,} bytes)")
        
        # 1. Iniciar upload
        try:
            response = requests.post(
                f"{self.base_url}/v1/files/initiate",
                headers=self._get_headers(),
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
                self.print_error(f"Falha ao iniciar upload: {response.text}")
                return None
            
            upload_data = response.json()
            upload_id = upload_data["upload_id"]
            
        except Exception as e:
            self.print_error(f"Erro ao iniciar upload: {e}")
            return None
        
        # 2. Enviar chunks (dados binários via application/octet-stream)
        self.print_info(f"Enviando {total_chunks} chunk(s)...")
        
        with open(file_path, "rb") as f:
            for chunk_num in range(1, total_chunks + 1):
                chunk_data = f.read(chunk_size)
                
                # Calcula hash do chunk
                chunk_hash = hashlib.sha256(chunk_data).hexdigest()
                
                try:
                    response = requests.post(
                        f"{self.base_url}/v1/files/{upload_id}/chunks",
                        params={
                            "chunk_number": chunk_num,
                            "checksum_sha256": chunk_hash
                        },
                        headers={
                            "Authorization": f"Bearer {self.token}",
                            "Content-Type": "application/octet-stream"
                        },
                        data=chunk_data,  # Dados binários diretamente
                        timeout=60
                    )
                    
                    if response.status_code != 200:
                        self.print_error(f"Falha ao enviar chunk {chunk_num}: {response.text}")
                        return None
                    
                    progress = (chunk_num / total_chunks) * 100
                    print(f"\r  Progresso: {progress:.1f}% ({chunk_num}/{total_chunks})", end="", flush=True)
                    
                except Exception as e:
                    self.print_error(f"Erro ao enviar chunk {chunk_num}: {e}")
                    return None
        
        print()  # Nova linha após progresso
        
        # 3. Completar upload (sem body JSON)
        try:
            response = requests.post(
                f"{self.base_url}/v1/files/{upload_id}/complete",
                headers={
                    "Authorization": f"Bearer {self.token}"
                },
                timeout=30
            )
            
            if response.status_code in (200, 202):
                self.print_success(f"Upload concluído! ID: {upload_id}")
                return upload_id
            else:
                self.print_error(f"Falha ao completar upload: {response.text}")
                return None
                
        except Exception as e:
            self.print_error(f"Erro ao completar upload: {e}")
            return None
    
    def send_file_message(self, conversation_id: int, file_path: str) -> bool:
        """
        Envia um arquivo como mensagem.
        
        Args:
            conversation_id: ID da conversa
            file_path: Caminho do arquivo
            
        Returns:
            bool: True se enviado com sucesso
        """
        # Faz upload do arquivo
        upload_id = self.upload_file(conversation_id, file_path)
        if not upload_id:
            return False
        
        # Envia mensagem com o arquivo (apenas type e file_id)
        try:
            message_id = str(uuid.uuid4())
            filename = os.path.basename(file_path)
            
            response = requests.post(
                f"{self.base_url}/v1/messages",
                headers=self._get_headers(),
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
            
            if response.status_code == 202:
                self.print_success(f"Arquivo enviado: {filename}")
                return True
            else:
                self.print_error(f"Erro ao enviar mensagem: {response.text}")
                return False
                
        except Exception as e:
            self.print_error(f"Erro ao enviar mensagem com arquivo: {e}")
            return False
    
    def get_messages(self, conversation_id: int, limit: int = 20) -> list:
        """
        Obtém mensagens de uma conversa.
        
        Args:
            conversation_id: ID da conversa
            limit: Número máximo de mensagens
            
        Returns:
            list: Lista de mensagens
        """
        try:
            response = requests.get(
                f"{self.base_url}/v1/conversations/{conversation_id}/messages",
                headers=self._get_headers(),
                params={"limit": limit, "offset": 0},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("messages", [])
            else:
                return []
                
        except Exception as e:
            self.print_error(f"Erro ao obter mensagens: {e}")
            return []
    
    async def connect_websocket(self):
        """Conecta ao WebSocket para receber mensagens em tempo real."""
        ws_uri = f"{self.ws_url}/ws?token={self.access_token}"
        
        try:
            async with websockets.connect(ws_uri) as websocket:
                self.ws_connection = websocket
                self.print_success("Conectado ao WebSocket para mensagens em tempo real!")
                
                # Se temos uma conversa ativa, se inscreve nela
                if self.current_conversation_id:
                    await self._subscribe_conversation(websocket, self.current_conversation_id)
                
                # Loop de recebimento de mensagens
                while self.running:
                    try:
                        message = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=1.0
                        )
                        await self._handle_ws_message(message)
                    except asyncio.TimeoutError:
                        continue
                    except websockets.exceptions.ConnectionClosed:
                        self.print_info("Conexão WebSocket fechada")
                        break
                        
        except Exception as e:
            self.print_error(f"Erro no WebSocket: {e}")
    
    async def _subscribe_conversation(self, websocket, conversation_id: int):
        """Inscreve-se em uma conversa no WebSocket."""
        await websocket.send(json.dumps({
            "action": "subscribe",
            "conversation_id": conversation_id
        }))
        
    async def _handle_ws_message(self, message: str):
        """Processa mensagem recebida via WebSocket."""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")
            
            if msg_type == "connected":
                self.user_id = data.get("user_id")
                self.print_info(f"Conectado como user_id: {self.user_id}")
                
            elif msg_type == "subscribed":
                self.print_info(f"Inscrito na conversa {data.get('conversation_id')}")
                
            elif msg_type == "message.created":
                payload = data.get("payload", {})
                sender = data.get("sender_username", "Desconhecido")
                content = payload.get("content", "[mensagem sem conteúdo]")
                timestamp = data.get("timestamp", datetime.utcnow().isoformat())
                
                # Não exibe mensagens enviadas por mim (já exibidas localmente)
                if data.get("sender_id") != self.user_id:
                    print()  # Nova linha para separar do prompt
                    self.print_message(sender, content, timestamp, is_me=False)
                    print(f"\n{Fore.GREEN}>>> {Style.RESET_ALL}", end="", flush=True)
                    
            elif msg_type == "ping":
                # Responde ao ping
                if self.ws_connection:
                    await self.ws_connection.send(json.dumps({"action": "pong"}))
                    
            elif msg_type == "error":
                self.print_error(f"Erro do servidor: {data.get('error', 'Desconhecido')}")
                
        except json.JSONDecodeError:
            pass
    
    def print_help(self):
        """Imprime comandos disponíveis."""
        print(f"\n{Fore.CYAN}Comandos disponíveis:{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}/conversas{Style.RESET_ALL}           - Lista suas conversas")
        print(f"  {Fore.YELLOW}/nova <user_id>{Style.RESET_ALL}      - Cria conversa privada com outro usuário")
        print(f"  {Fore.YELLOW}/entrar <conv_id>{Style.RESET_ALL}    - Entra em uma conversa existente")
        print(f"  {Fore.YELLOW}/historico{Style.RESET_ALL}           - Mostra histórico de mensagens")
        print(f"  {Fore.YELLOW}/arquivo <caminho>{Style.RESET_ALL}   - Envia um arquivo")
        print(f"  {Fore.YELLOW}/usuarios{Style.RESET_ALL}            - Lista usuários disponíveis")
        print(f"  {Fore.YELLOW}/ajuda{Style.RESET_ALL}               - Mostra esta ajuda")
        print(f"  {Fore.YELLOW}/sair{Style.RESET_ALL}                - Encerra o cliente")
        print(f"\n  {Fore.WHITE}Digite qualquer texto para enviar uma mensagem{Style.RESET_ALL}\n")
    
    def list_users(self):
        """Lista informações sobre usuários."""
        print(f"\n{Fore.CYAN}Informações de usuários:{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}Seu ID:{Style.RESET_ALL} {self.user_id}")
        print(f"  {Fore.YELLOW}Seu username:{Style.RESET_ALL} {self.username}")
        print(f"\n{Fore.CYAN}Usuários disponíveis para login:{Style.RESET_ALL}")
        print(f"  user1 (senha: password123)")
        print(f"  user2 (senha: password123)")
        print(f"  user3 (senha: password123)")
        print(f"\n  {Fore.WHITE}Para criar uma conversa com outro usuário,")
        print(f"  peça o ID dele (mostrado ao logar) e use /nova <user_id>{Style.RESET_ALL}\n")
    
    def display_conversations(self):
        """Exibe lista de conversas formatada."""
        conversations = self.list_conversations()
        
        if not conversations:
            self.print_info("Você ainda não tem conversas. Use /nova <user_id> para criar uma.")
            return
            
        print(f"\n{Fore.CYAN}Suas conversas:{Style.RESET_ALL}")
        for conv in conversations:
            conv_id = conv.get("conversation_id")
            conv_name = conv.get("conversation_name") or f"Conversa {conv_id}"
            conv_type = conv.get("conversation_type", "private")
            last_msg = conv.get("last_message_content", "Sem mensagens")
            unread = conv.get("unread_count", 0)
            
            unread_badge = f" {Fore.RED}({unread} não lidas){Style.RESET_ALL}" if unread > 0 else ""
            
            print(f"  {Fore.YELLOW}[{conv_id}]{Style.RESET_ALL} {conv_name} ({conv_type}){unread_badge}")
            if last_msg:
                print(f"      └─ {Fore.WHITE}{last_msg[:50]}{'...' if len(last_msg) > 50 else ''}{Style.RESET_ALL}")
        
        print(f"\n  {Fore.WHITE}Use /entrar <id> para entrar em uma conversa{Style.RESET_ALL}\n")
    
    def display_history(self):
        """Exibe histórico de mensagens da conversa atual."""
        if not self.current_conversation_id:
            self.print_info("Entre em uma conversa primeiro com /entrar <id>")
            return
            
        messages = self.get_messages(self.current_conversation_id, limit=20)
        
        if not messages:
            self.print_info("Nenhuma mensagem nesta conversa ainda.")
            return
            
        print(f"\n{Fore.CYAN}Histórico da conversa:{Style.RESET_ALL}")
        
        # Inverte para mostrar do mais antigo para o mais recente
        for msg in reversed(messages):
            sender = msg.get("sender_username", "Desconhecido")
            payload = msg.get("payload", {})
            content = payload.get("content", "[arquivo]") if payload.get("type") == "text" else "[arquivo]"
            timestamp = msg.get("created_at", datetime.utcnow().isoformat())
            is_me = msg.get("sender_username") == self.username
            
            self.print_message(sender, content, timestamp, is_me=is_me)
        
        print()
    
    async def subscribe_current_conversation(self):
        """Inscreve-se na conversa atual via WebSocket."""
        if self.ws_connection and self.current_conversation_id:
            try:
                await self._subscribe_conversation(self.ws_connection, self.current_conversation_id)
            except Exception as e:
                self.print_error(f"Erro ao se inscrever na conversa: {e}")
    
    async def run_input_loop(self):
        """Loop principal de entrada do usuário."""
        self.print_help()
        
        while self.running:
            try:
                # Usa asyncio para input não-bloqueante
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: input(f"{Fore.GREEN}>>> {Style.RESET_ALL}")
                )
                
                user_input = user_input.strip()
                
                if not user_input:
                    continue
                
                # Processa comandos
                if user_input.startswith("/"):
                    await self._process_command(user_input)
                else:
                    # Envia mensagem
                    if not self.current_conversation_id:
                        self.print_info("Entre em uma conversa primeiro com /entrar <id> ou /nova <user_id>")
                        continue
                    
                    if self.send_message(self.current_conversation_id, user_input):
                        timestamp = datetime.utcnow().isoformat()
                        self.print_message(self.username, user_input, timestamp, is_me=True)
                        
            except EOFError:
                self.running = False
                break
            except KeyboardInterrupt:
                self.running = False
                break
    
    async def _process_command(self, command: str):
        """Processa comandos do usuário."""
        parts = command.split()
        cmd = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        if cmd == "/sair":
            self.print_info("Encerrando...")
            self.running = False
            
        elif cmd == "/ajuda":
            self.print_help()
            
        elif cmd == "/conversas":
            self.display_conversations()
            
        elif cmd == "/usuarios":
            self.list_users()
            
        elif cmd == "/historico":
            self.display_history()
            
        elif cmd == "/arquivo":
            if not args:
                self.print_error("Uso: /arquivo <caminho_do_arquivo>")
                return
                
            if not self.current_conversation_id:
                self.print_info("Entre em uma conversa primeiro com /entrar <id>")
                return
                
            file_path = " ".join(args)  # Suporta caminhos com espaços
            if self.send_file_message(self.current_conversation_id, file_path):
                timestamp = datetime.utcnow().isoformat()
                filename = os.path.basename(file_path)
                self.print_message(self.username, f"[Arquivo: {filename}]", timestamp, is_me=True)
                
        elif cmd == "/nova":
            if not args:
                self.print_error("Uso: /nova <user_id>")
                self.print_info("Para encontrar o ID de outro usuário, peça para ele executar o cliente")
                return
                
            try:
                other_user_id = int(args[0])
                
                if other_user_id == self.user_id:
                    self.print_error("Você não pode criar uma conversa consigo mesmo!")
                    return
                    
                conv_id = self.create_conversation([self.user_id, other_user_id])
                if conv_id:
                    self.current_conversation_id = conv_id
                    self.print_success(f"Conversa criada! Agora você está na conversa {conv_id}")
                    await self.subscribe_current_conversation()
                    
            except ValueError:
                self.print_error("ID do usuário deve ser um número")
                
        elif cmd == "/entrar":
            if not args:
                self.print_error("Uso: /entrar <conversation_id>")
                return
                
            try:
                conv_id = int(args[0])
                self.current_conversation_id = conv_id
                self.print_success(f"Você entrou na conversa {conv_id}")
                await self.subscribe_current_conversation()
                self.display_history()
                
            except ValueError:
                self.print_error("ID da conversa deve ser um número")
                
        else:
            self.print_error(f"Comando desconhecido: {cmd}. Use /ajuda para ver comandos.")
    
    async def run(self, username: str, password: str):
        """
        Executa o cliente de chat.
        
        Args:
            username: Nome do usuário
            password: Senha do usuário
        """
        self.print_header()
        
        # Autentica
        if not self.authenticate(username, password):
            return
        
        # Inicia tarefas assíncronas
        ws_task = asyncio.create_task(self.connect_websocket())
        input_task = asyncio.create_task(self.run_input_loop())
        
        try:
            # Aguarda ambas as tarefas
            await asyncio.gather(ws_task, input_task, return_exceptions=True)
        except asyncio.CancelledError:
            pass
        finally:
            self.running = False
            self.print_info("Cliente encerrado.")


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description="Chat4All - Cliente de Chat em Tempo Real",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos de uso:
  python chat_client.py --user user1 --password password123
  python chat_client.py -u user2 -p password123 --url http://localhost:8000
  
Usuários disponíveis (seed):
  user1, user2, user3 (senha: password123)
        """
    )
    
    parser.add_argument(
        "-u", "--user",
        required=True,
        help="Nome do usuário para login"
    )
    
    parser.add_argument(
        "-p", "--password",
        required=True,
        help="Senha do usuário"
    )
    
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="URL base da API (default: http://localhost:8000)"
    )
    
    args = parser.parse_args()
    
    # Cria e executa o cliente
    client = Chat4AllClient(base_url=args.url)
    
    try:
        asyncio.run(client.run(args.user, args.password))
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Encerrando...{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
