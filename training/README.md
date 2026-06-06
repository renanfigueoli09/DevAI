# DevAI Training Store

Conhecimento aprendido pelo agente. Commite este diretório — compartilha com o time.

## Estrutura

```
training/
  vectors/knowledge.lance/     ← LanceDB (Arrow + HNSW — busca vetorial)
  patterns/*.json              ← JSON por tópico (legível, editável)
  index.json                   ← índice de todos os itens
  study_journal.json           ← histórico: quando estudou, score, prioridade
  discovered_topics.json       ← tópicos auto-descobertos pelo agente
  validation_report.md         ← último resultado da validação
  study.log                    ← log do treinamento (não commitar)
  validation.log               ← log da validação (não commitar)
```

## .gitignore recomendado

```gitignore
training/export/*.md    # gerado por devai knowledge --export, redundante
training/study.log
training/validation.log
```

## Como treinar

```bash
# Estuda o que ainda não foi feito
./scripts/study.sh

# Por área
./scripts/study.sh --group nestjs
./scripts/study.sh --group methodology   # SOLID, Clean Arch, Security, Testing
./scripts/study.sh --group all           # Tudo

# Intensivo overnight + auto-commita + push
./scripts/study.sh --group all --intensive --loop

# Treino + validação em paralelo (sem conflito de git)
./scripts/train_and_validate.sh

# Valida e corrige fracos
python scripts/validate.py --fix --rounds 5

# Status do que foi estudado
./scripts/study.sh --status
```

## Commitar

```bash
git add training/ README.md
git commit -m "🧠 training: update"
git push
# O loop faz isso automaticamente a cada ciclo
```

## Cobertura

| Área | Tópicos |
|---|---|
| NestJS | Core, MongoDB, PostgreSQL, MySQL, Redis, Elasticsearch × Kafka, RabbitMQ, gRPC, GraphQL, WebSocket, Auth |
| Spring Boot | Core, MongoDB, PostgreSQL, MySQL, Redis × Kafka, RabbitMQ, gRPC, Auth |
| FastAPI | Core, MongoDB, PostgreSQL, Redis, Kafka, Auth |
| ASP.NET Core | Core, MongoDB, PostgreSQL, Redis, Kafka, SignalR, Auth |
| Next.js | Core, MongoDB, PostgreSQL, Auth |
| Databases | MongoDB, PostgreSQL, Redis, Elasticsearch, Cassandra (avançado) |
| Microservices | Kafka, RabbitMQ, gRPC, GraphQL, WebSocket, CQRS, Saga, Circuit Breaker |
| Docker | Todas as combinações + Kubernetes + CI/CD |
| Methodology | SOLID, Clean Architecture, API Design, Security, Testing, Performance, Anti-patterns |
| CI/CD | GitHub Actions, GitLab CI, Azure DevOps, Bitbucket, CircleCI, Jenkins |
| NLP | Entidades PT/EN, detecção de stack/banco, separação instrução×entidade |
| Erros | TS2307, TS2339, findOneBy, PartialType, módulo ausente |
