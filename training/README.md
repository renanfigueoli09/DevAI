# DevAI Training Store

Conhecimento aprendido pelo agente. **Commite este diretório** — quanto mais treinado, mais inteligente.

## Estrutura

```
training/
  vectors/knowledge.lance/   ← LanceDB (Arrow + HNSW — busca vetorial nativa)
  patterns/                  ← JSON por tópico (legível, editável)
  index.json                 ← índice de todos os itens
  discovered_topics.json     ← tópicos auto-descobertos (cresce a cada ciclo)
  export/                    ← Markdown gerado por devai knowledge --export
  study.log                  ← log do último treinamento
```

## Como treinar

```bash
chmod +x scripts/study.sh  # garante permissão

# Rápido (~15min)
./scripts/study.sh

# Por stack (cobre TODOS os bancos + microserviços + auth + infra)
./scripts/study.sh --group nestjs        # NestJS × MongoDB/PostgreSQL/Redis/Kafka/gRPC/GraphQL...
./scripts/study.sh --group spring        # Spring Boot completo
./scripts/study.sh --group python        # FastAPI + Django
./scripts/study.sh --group dotnet        # ASP.NET Core
./scripts/study.sh --group microservices # Kafka/RabbitMQ/gRPC/GraphQL × todas as stacks
./scripts/study.sh --group databases     # MongoDB/PostgreSQL/Redis/Elasticsearch/Cassandra
./scripts/study.sh --group infra         # Docker/Kubernetes/GitHub Actions
./scripts/study.sh --group all           # TUDO (~2-4h)

# Overnight com descoberta autônoma de novos tópicos
./scripts/study.sh --group all --loop
```

## Como commitar

```bash
cd ~/git/devai
git add training/
git commit -m "training: $(date +%Y-%m-%d) after full study"
git push   # time inteiro recebe o treinamento
```

## Cobertura (stack × banco × microserviço)

| Stack | Bancos cobertos | Microserviços cobertos |
|---|---|---|
| NestJS | MongoDB, PostgreSQL, MySQL, Redis, Elasticsearch, Cassandra | Kafka, RabbitMQ, gRPC, GraphQL, WebSocket, TCP |
| Spring Boot | MongoDB, PostgreSQL, MySQL, Redis, Elasticsearch | Kafka, RabbitMQ, gRPC, GraphQL |
| FastAPI | MongoDB, PostgreSQL, MySQL, Redis | Kafka, RabbitMQ |
| ASP.NET Core | MongoDB, PostgreSQL, MySQL, Redis | Kafka, RabbitMQ, SignalR |
| Next.js | MongoDB, PostgreSQL | NextAuth |
| Docker | MongoDB, PostgreSQL, Redis Sentinel, Kafka, Nginx | todos |
| Microservices | CQRS, Saga, Event Sourcing, Circuit Breaker, API Gateway | todos |

## Descoberta autônoma

O estudo sugere e salva novos tópicos não cobertos a cada ciclo.
Verificar: `cat training/discovered_topics.json`

## Instalar embeddings

```bash
ollama pull nomic-embed-text
devai knowledge   # verifica: "busca ✓ semântica ativa (LanceDB)"
```
