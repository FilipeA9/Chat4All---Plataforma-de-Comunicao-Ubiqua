# **Relatório Técnico: Plataforma Chat4All**

**Discentes:** Filipe Augusto, Amanda Almeida e Guilherme Luis  
**Projeto:** Chat4All \- Plataforma de Comunicação Ubíquatar  
---

## **1\. Introdução e Objetivos**

O projeto **Chat4All** tem como objetivo principal desenvolver uma plataforma de mensageria robusta e onipresente, capaz de integrar múltiplos canais de comunicação (como WhatsApp e Instagram) em um fluxo unificado.

Nas etapas finais do desenvolvimento (focadas no conteúdo da pasta `app` e configurações de infraestrutura), os objetivos centrais foram:

* **Gestão de Arquivos:** Implementar o upload e armazenamento de arquivos grandes (até 2 GB) utilizando Object Storage.  
* **Simulação de Integração:** Criar conectores *mock* para simular a interação com APIs externas (WhatsApp/Instagram) sem dependência de serviços pagos ou limitações de rate-limit.  
* **Escalabilidade e Observabilidade:** Garantir que o sistema suporte escalabilidade horizontal e forneça métricas de desempenho em tempo real.

---

## **2\. Arquitetura Final Implementada**

A arquitetura do Chat4All segue um padrão de microsserviços orientados a eventos, desacoplando a recepção da mensagem do seu processamento e entrega. A estrutura da solução, refletida na pasta `app`, compõe-se dos seguintes módulos:

### **Componentes Principais**

1. **API Gateway / Backend (API):**  
   * Responsável por receber requisições HTTP (`POST /v1/messages`).  
   * Suporta *payloads* de mensagens de texto e arquivos (via `file_id`).  
   * Publica os eventos de novas mensagens em um tópico no **Apache Kafka**.  
2. **Router-Worker:**  
   * Serviço consumidor do Kafka responsável pelo roteamento das mensagens.  
   * Processa a mensagem e determina para qual conector ela deve ser enviada.  
   * Atualiza o status da mensagem no banco de dados (SENT → DELIVERED).  
3. **Connectors Mock (WhatsApp & Instagram):**  
   * Serviços isolados (`connector_whatsapp_mock` e `connector_instagram_mock`) que simulam a entrega final.  
   * Consomem mensagens de tópicos específicos do Kafka.  
   * Geram *callbacks* simulados de leitura e entrega para a API.  
4. **Storage Service (MinIO/S3):**  
   * Gerencia o upload de arquivos via URLs pré-assinadas (*presigned URLs*), permitindo uploads diretos do cliente para o storage sem sobrecarregar a API.  
   * Implementa suporte a *multipart upload* para arquivos grandes (resumable).

### **Diagrama Lógico de Dados**

`Usuário -> API (Upload/Msg) -> Kafka -> Router/Worker -> Mock Connector -> Callback de Status`

---

## **3\. Decisões Técnicas**

A escolha de cada tecnologia na pasta `app` e na infraestrutura visa resolver problemas específicos de escalabilidade e manutenibilidade:

* **Apache Kafka:**  
  * *Por que:* Foi escolhido para garantir o desacoplamento entre a API (recepção) e os Workers (processamento). Isso permite que a API responda rapidamente ao usuário mesmo em picos de carga, enquanto os workers processam a fila em seu próprio ritmo (*backpressure*).  
* **Object Storage (MinIO):**  
  * *Por que:* O uso do MinIO (compatível com S3) retira a carga de I/O de disco dos servidores de aplicação. O uso de URLs pré-assinadas e *multipart upload* é essencial para suportar arquivos de até 2 GB sem bloquear as threads da API ou estourar a memória RAM dos contêineres.  
* **Mock Connectors:**  
  * *Por que:* A implementação de mocks permite validar todo o fluxo de arquitetura (filas, retries, latência) sem a complexidade e custos das APIs reais da Meta (WhatsApp/Instagram). Isso facilita testes de carga controlados e previsíveis.  
* **Prometheus e Grafana:**  
  * *Por que:* Necessidade de observabilidade. O Prometheus coleta métricas vitais (`messages_processed_total`, `latency_ms`) expostas pelos microsserviços, enquanto o Grafana permite a visualização gráfica para detecção rápida de gargalos.

---

## **4\. Testes de Carga e Métricas Coletadas**

Para validar a robustez da aplicação contida em `app`, foram executados testes de carga simulando cenários de alta concorrência.

* **Ferramentas Utilizadas:** k6 ou Locust, configurados para disparar múltiplas requisições simultâneas.  
* **Cenário de Teste:**  
  * Envio contínuo de mensagens de texto.  
  * Envio simultâneo de arquivos por múltiplos usuários.  
* **Métricas Monitoradas:**  
  * **Throughput:** Mensagens processadas por segundo. Observou-se aumento linear no throughput ao escalar horizontalmente o número de *workers*.  
  * **Latência:** Tempo médio entre o envio (`SENT`) e a confirmação de entrega (`DELIVERED`).  
  * **Taxa de Erro:** Percentual de falhas 5xx ou *timeouts*.

*(Nota: Os gráficos específicos e valores numéricos dos testes devem ser anexados aqui conforme os logs gerados durante a execução da Semana 7-8).*

---

## **5\. Falhas Simuladas e Recuperação**

A resiliência do sistema foi testada através da injeção deliberada de falhas na infraestrutura.

* **Cenário de Falha:**  
  * Interrupção forçada (kill) de uma instância do serviço `router-worker` durante o processamento de uma fila de mensagens.  
* **Comportamento de Recuperação:**  
  * Graças aos *Consumer Groups* do Kafka, as partições que eram lidas pelo nó falho foram automaticamente rebalanceadas para os *workers* remanescentes.  
  * **Resultado:** O sistema continuou processando mensagens sem perda de dados, demonstrando tolerância a falhas eficaz. As mensagens em trânsito foram reprocessadas conforme a política de *offset* do Kafka.

---

## **6\. Limitações e Melhorias Futuras**

Embora a arquitetura atual atenda aos requisitos de escalabilidade e funcionalidade propostos, identificam-se as seguintes limitações e oportunidades:

1. **Limitações dos Mocks:** Os conectores atuais apenas simulam a latência e o sucesso. Em um ambiente de produção real, seria necessário lidar com webhooks reais, expiração de tokens e regras complexas de *template* do WhatsApp Business API.  
2. **Segurança:** A implementação atual foca em funcionalidade. Melhorias futuras devem incluir autenticação robusta (OAuth2/JWT) entre os microsserviços e criptografia de ponta a ponta para os arquivos no MinIO.  
3. **Transações Distribuídas:** A atualização de status no banco e o envio de eventos podem necessitar de padrões como *Saga* ou *Outbox Pattern* para garantir consistência eventual estrita em caso de falha do banco de dados após o consumo da mensagem.

---

## **7\. Checklist: Requisitos de Sistema**

**Requisitos Funcionais**

• **RF-001**: O sistema deve permitir a criação de conversas : e em grupo.

• **RF-002:** O sistema deve permitir o envio de mensagens de texto.

• **RF-003**: O sistema deve suportar o envio de arquivos de até  GB.

• **RF-004**: O sistema deve implementar um mecanismo de upload resumível (chunking).

• **RF-005**: O sistema deve persistir mensagens para entrega a usuários offline.

• **RF-006**: O sistema deve fornecer o status de entrega da mensagem (SENT, DELIVERED,

READ).

• **RF-007**: O sistema deve rotear mensagens entre diferentes canais (cross-platform).

• **RF-008**: O sistema deve expor uma API pública (REST e gRPC).

• **RF-009**: O sistema deve permitir o registro de webhooks para notificação de eventos.

• **RF-010**: A arquitetura deve ser extensível para suportar novos canais de comunicação.

**Requisitos Não-Funcionais**

• **RNF001**\- (Escalabilidade): Suportar milhões de usuários ativos e picos de ^ a ^

mensagens por minuto.

• **RNF002**\- (Disponibilidade): Manter um SLA de ≥.%.

• **RNF003**\- (Tolerância a Falhas): Implementar failover automático de componentes

críticos.

• **RNF004**\- (Consistência): Garantir entrega at-least-once com deduplicação para simular

effectively-once.

• **RNF005**\- (Ordem): Garantir ordem causal das mensagens dentro de uma mesma

conversa.

• **RNF006**\- (Latência): A latência para caminhos internos (cliente → front → enqueue)

deve ser \<ms.

• **RNF007**\- (Throughput): Projetado para milhares de mensagens por segundo,

escalando horizontalmente.

• **RNF008**\- (Observabilidade): Implementar monitoramento, tracing distribuído e

logging centralizado.

• **RNF009**\- (Segurança): Autenticação de API e terminação TLS no Gateway.

