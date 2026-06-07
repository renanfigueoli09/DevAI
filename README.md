# ⚡ DevAI — Agente Autônomo de Desenvolvimento Local

Agente de código multi-stack usando LLM local via Ollama.
100% offline · aprende com o uso · entende português informal · training store semântico (LanceDB).

---

## Pré-requisitos

```bash
ollama pull qwen2.5-coder:7b    # modelo de código (recomendado)
ollama pull nomic-embed-text     # embeddings — busca semântica (obrigatório)
```

| Stack | Requisito adicional |
|---|---|
| NestJS / Next.js | Node.js 18+ |
| Spring Boot | Java 21+ |
| ASP.NET Core | .NET SDK 8+ |
| FastAPI / Django | Python 3.10+ (já no venv) |

## Instalação

```bash
git clone <repo> ~/git/devai && cd ~/git/devai
chmod +x install.sh scripts/study.sh scripts/self_improve.py scripts/train_and_validate.sh
./install.sh
source ~/.zshrc   # ou ~/.bashrc
```

---

## Comandos

### `devai new` / `devnew` — Criar projeto

```bash
devnew <stack> <nome> "<descrição>"

# NestJS
devnew nestjs livros-api   "CRUD de livros com MongoDB e docker"
devnew nestjs loja-api     "API de pedidos com PostgreSQL, JWT e Redis"
devnew nestjs chat-api     "Chat em tempo real com WebSocket, Kafka e MongoDB"
devnew nestjs catalog-api  "API GraphQL de catálogo com MongoDB"
devnew nestjs books-svc    "Microsserviço gRPC de livros com MongoDB"

# Spring Boot
devnew spring-boot users-svc  "Microsserviço de usuários com MongoDB, JWT e Kafka"
devnew spring-boot inventory  "API de estoque com PostgreSQL e Spring Security"

# Python FastAPI
devnew python books-api   "API FastAPI de livros com MongoDB"
devnew python orders-api  "API FastAPI de pedidos com PostgreSQL e JWT"

# ASP.NET Core
devnew dotnet catalog-api "API de catálogo com MongoDB e JWT"

# Frontend / Fullstack
devnew nextjs loja        "E-commerce Next.js 15 com MongoDB e NextAuth"
devnew nestjs+nextjs app  "Plataforma fullstack NestJS + Next.js"
```

**A IA entende português informal:**

| Você escreve | IA entende |
|---|---|
| `"tem o mongoDb"` | usar MongoDB |
| `"só o necessário"` | modo minimal, sem extras |
| `"código em inglês"` | identificadores em English |
| `"configura o docker"` | gerar docker-compose + Dockerfile |
| `"tals"` / `"tbm"` / `"oq"` | etc / também / o que |

**Stacks:** `nestjs` · `spring-boot` · `python` · `dotnet` · `nextjs` · `angular` · `react` · `nestjs+nextjs` · `nestjs+angular`

---

### `devai feature` / `devfeat` — Adicionar feature

```bash
cd ~/meu-projeto && devfeat "<descrição>"

devfeat "configure o docker-compose com app e MongoDB"
devfeat "configure o swagger"
devfeat "adicione auth JWT com refresh token e roles"
devfeat "configure Kafka producer e consumer para pedidos"
devfeat "configure Redis Sentinel para alta disponibilidade"
devfeat "adicione WebSocket gateway para notificações"
devfeat "configure rate limiting por IP"
devfeat "adicione upload de arquivos para S3"
devfeat "adicione GraphQL com subscriptions"
devfeat "configure gRPC para comunicação com microsserviços"
devfeat "configure nginx como reverse proxy"
```

Features que editam arquivos existentes automaticamente:
`swagger` · `cors` · `helmet` · `rate-limit` · `winston` · `global prefix`

---

### `devai fix` / `devfix` — Corrigir erros de build

```bash
devfix
devai fix --rounds 15   # mais tentativas
devai fix --run         # roda após corrigir
```

Correções determinísticas incluídas:
- `PartialType` de `@nestjs/common` → `@nestjs/mapped-types`
- `findOneBy` → `findById` (Mongoose)
- `users.module` → `user.module` (singular)
- Módulo ausente (`TS2307`) → cria o arquivo automaticamente
- Diretórios inválidos (`src/docker/`, `src/mongodb/`) → removidos

---

### `devai study` / `devstudy` — Estudar projeto existente

```bash
devstudy
devai study --path /caminho/do/projeto
```

---

### `devai ask` / `devask` — Perguntar sobre o projeto

```bash
devask "como funciona o módulo de auth?"
devask "como adicionar endpoint seguindo o padrão?"
devask "explique a estrutura de pastas"
```

---

### `devai search` / `devsearch` — Pesquisar e salvar no training

```bash
devsearch "nestjs mongoose schema required optional 2025"
devsearch "docker-compose mongodb healthcheck 2025"
devsearch "assunto específico" --no-save
```

---

### `devai train` / `devtrain` — Treinar com arquivos de referência

```bash
devtrain src/app.module.ts
devtrain --dir src/configs/
devtrain --project /path/to/projeto-referencia/
```

---

### `devai knowledge` — Gerenciar o training store

```bash
devai knowledge           # lista + status embeddings
devai knowledge --export  # exporta para Markdown
devai knowledge --clear   # limpa tudo
```

---

### `devai profile` — Perfil do usuário

```bash
devai profile                              # ver preferências salvas
devai profile --set stack=nestjs db=mongodb
devai profile --set minimal=true language=english
```

O perfil é salvo em `~/.config/devai/profile.json` e usado para defaults em todos os comandos.

---

## Treinamento Autônomo

### `scripts/study.sh` — Loop inteligente

```bash
chmod +x scripts/study.sh   # feito pelo install.sh

# Estuda só o que ainda não foi feito (não repete)
./scripts/study.sh

# Por grupo
./scripts/study.sh --group nestjs          # NestJS completo
./scripts/study.sh --group spring          # Spring Boot
./scripts/study.sh --group python          # FastAPI + Django
./scripts/study.sh --group dotnet          # ASP.NET Core
./scripts/study.sh --group databases       # MongoDB, PostgreSQL, Redis, Elasticsearch
./scripts/study.sh --group microservices   # Kafka, RabbitMQ, gRPC, GraphQL, WebSocket
./scripts/study.sh --group infra           # Docker, Kubernetes, GitHub Actions
./scripts/study.sh --group methodology     # SOLID, Clean Arch, API Design, Security, Testing
./scripts/study.sh --group cicd            # GitHub Actions, GitLab CI, Azure DevOps, Bitbucket, CircleCI
./scripts/study.sh --group all             # Tudo

# Intensivo (6 results/query + exemplos de código)
./scripts/study.sh --group all --intensive

# Loop overnight — auto-descobre novos tópicos + commita + push
./scripts/study.sh --group all --intensive --loop

# Ver o que já foi estudado e o que falta
./scripts/study.sh --status

# Forçar re-estudo mesmo de tópicos ok
./scripts/study.sh --group nestjs --force
```

**Grupos disponíveis:**

| Grupo | O que estuda |
|---|---|
| `quick` | NestJS + MongoDB + Docker + Erros comuns |
| `nestjs` | NestJS × todos os bancos × todos os microserviços |
| `spring` | Spring Boot × todos os bancos × Kafka/gRPC/GraphQL |
| `python` | FastAPI + Django × MongoDB/PostgreSQL/Redis |
| `dotnet` | ASP.NET Core × MongoDB/PostgreSQL/Redis/SignalR |
| `frontend` | Next.js + React + Angular |
| `databases` | MongoDB, PostgreSQL, Redis, Elasticsearch, Cassandra (avançado) |
| `microservices` | Kafka, RabbitMQ, gRPC, GraphQL, WebSocket, CQRS, Saga |
| `infra` | Docker, Kubernetes, Helm, GitHub Actions |
| `methodology` | SOLID, Clean Architecture, API Design, Security, TDD, Performance, Anti-patterns |
| `cicd` | GitHub Actions, GitLab CI, Azure DevOps, Bitbucket, CircleCI, Jenkins |
| **`all`** | **Tudo (~60 tópicos / ~350 pesquisas)** |

**Loop inteligente** — usa `training/study_journal.json`:
- Prioridade 100: nunca estudado
- Prioridade 80: score < 50% na validação
- Prioridade 40: estudado mas sem validação há >48h
- Prioridade 0: bom score e recente → **pula**

**Auto-descobre** novos tópicos a cada ciclo com 5 prompts rotativos diferentes.

**Auto-commita e faz push** após cada ciclo com emoji: `🧠 training: 2025-06-05 23:00`

---

### `scripts/validate.py` — Validação do treinamento

```bash
python scripts/validate.py              # valida tudo
python scripts/validate.py --fix        # valida + retreina fracos + re-valida
python scripts/validate.py --fix --rounds 5   # 5 rodadas de fix
python scripts/validate.py --topic nestjs-mongodb nlp
python scripts/validate.py --strict     # aprovação exige 90%
```

Tópicos validados: `nestjs-mongodb` · `nestjs-typeorm` · `nestjs-auth` · `nestjs-core` · `nlp` · `docker` · `spring-mongodb` · `fastapi` · `common-errors`

O `--fix` salva **respostas corretas exatas** no vector store (não só pesquisa web):
```
+ qa:mongoose-required-field-modifier → "! para required, ? para optional"
+ qa:livros-to-Book → "livros → Book (English singular)"
+ qa:mongodb-docker-only-no-redis → "only = somente o pedido"
```

Gera `training/validation_report.md` commitável.

---

### `scripts/train_and_validate.sh` — Treino + Validação em paralelo

```bash
chmod +x scripts/train_and_validate.sh

# Roda study em background + validate em foreground a cada 5min
./scripts/train_and_validate.sh

# Grupo específico
./scripts/train_and_validate.sh --group nestjs

# Validação mais frequente
VAL_INTERVAL=120 ./scripts/train_and_validate.sh   # a cada 2min
```

Sem conflito de git: só o `study.sh` commita. O `validate.py` nunca toca no git.
Lock guard automático: aguarda e remove `index.lock` de processos mortos.

---

### `scripts/self_improve.py` — Auto-melhoria

```bash
python scripts/self_improve.py          # gera exemplos e valida
python scripts/self_improve.py --loop  # contínuo
```

O agente gera código real, valida e salva:
- Se passou → salva como **exemplo de alta qualidade**
- Se falhou → salva como **anti-pattern** (o que não fazer)

---

## Vector Store (LanceDB — não é SQL)

```
training/
  vectors/knowledge.lance/     ← LanceDB (Arrow + HNSW index)
  patterns/                    ← JSON por tópico (legível, commitável)
  index.json                   ← índice de todos os itens
  study_journal.json           ← o que foi estudado + scores
  discovered_topics.json       ← tópicos auto-descobertos
  validation_report.md         ← último resultado de validação
  study.log                    ← log do treinamento
  validation.log               ← log das validações
```

**Commitar o treinamento:**
```bash
git add training/ README.md
git commit -m "🧠 training: update"
git push
# O loop faz isso automaticamente
```

**`.gitignore` recomendado:**
```gitignore
training/export/*.md   # gerado automaticamente, redundante
training/study.log
training/validation.log
```

---

## Aliases

| Alias | Comando |
|---|---|
| `devai` | agente principal |
| `devnew` | `devai new` |
| `devfeat` | `devai feature` |
| `devstudy` | `devai study` |
| `devask` | `devai ask` |
| `devfix` | `devai fix` |
| `devtrain` | `devai train` |
| `devsearch` | `devai search` |

---

## Configuração

```bash
# ~/.bashrc ou ~/.zshrc
export DEVAI_MODEL_CODE=qwen2.5-coder:7b
export DEVAI_OLLAMA_HOST=http://localhost:11434
export DEVAI_TEMPERATURE=0.2
export DEVAI_CONFIRM_WRITES=true
export DEVAI_VERBOSE=1
export DEVAI_DIR=/home/$USER/git/devai
```

---

## Estrutura do Projeto

```
devai/
├── main.py                        ← CLI: new/feature/fix/search/train/knowledge/ask/study/profile
├── orchestrator.py
├── install.sh
├── requirements.txt               ← inclui lancedb, pyarrow
├── scripts/
│   ├── study.sh                   ← Loop inteligente de treinamento
│   ├── study.py                   ← Currículo completo + diário de estudo
│   ├── validate.py                ← Validação rigorosa + fix com Q&A exato
│   ├── self_improve.py            ← Auto-melhoria via geração + validação
│   ├── update_docs.py             ← Auto-atualização do README
│   └── train_and_validate.sh     ← Treino + validação paralelos sem conflito git
├── training/
│   ├── vectors/knowledge.lance/   ← LanceDB
│   ├── patterns/*.json            ← padrões por tópico
│   ├── index.json
│   ├── study_journal.json         ← histórico + prioridades
│   ├── discovered_topics.json     ← tópicos auto-descobertos
│   └── validation_report.md
└── tools/
    ├── domain_extractor.py        ← NLP: entidade × instrução
    ├── db_strategy.py             ← Stack × banco → ORM, pacotes, docker
    ├── manifests.py               ← Arquivos a gerar por stack/banco
    ├── generator.py               ← Geração com training obrigatório
    ├── infra_generator.py         ← docker-compose dinâmico
    ├── code_fixer.py              ← Fixes TypeScript determinísticos
    ├── project_fixer.py           ← Loop: compila → parseia → corrige
    ├── feature_editors.py         ← Edita main.ts, app.module.ts para features
    ├── orchestrator_helpers.py    ← Steps do pipeline
    ├── vector_store.py            ← LanceDB + JSON storage
    ├── embeddings.py              ← nomic-embed-text via Ollama
    ├── user_profile.py            ← Memória de preferências do usuário
    ├── research_agent.py          ← Pesquisa web + salva
    ├── file_trainer.py            ← Treina com arquivos/projetos
    ├── knowledge_templates.py     ← Templates Docker, Mongoose, configs
    └── llm_client.py              ← Cliente Ollama + retry + streaming
```

---

## Troubleshooting

```bash
# Ollama não responde
ollama serve

# Modelo não encontrado
ollama list && ollama pull qwen2.5-coder:7b

# Embeddings sem funcionar
ollama pull nomic-embed-text
devai knowledge   # verifica: "✓ semântica ativa"

# LanceDB não instala
source .venv/bin/activate && pip install lancedb pyarrow

# Erro index.lock (git travado)
rm -f ~/git/devai/.git/index.lock
# O auto_commit agora faz isso automaticamente

# Projeto com pastas inválidas (src/docker/, src/mongodb/)
devfix   # cleanup automático + rebuild

# Validação não passa mesmo com --fix
python scripts/validate.py --fix --rounds 10 --strict

# Ver o que foi estudado
./scripts/study.sh --status
cat training/study_journal.json
cat training/discovered_topics.json
```
