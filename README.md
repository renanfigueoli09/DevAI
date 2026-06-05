# ⚡ DevAI — Agente Autônomo de Desenvolvimento Local

Agente de código multi-stack que cria, evolui e corrige projetos usando LLM local via Ollama.
100% offline · roda na sua GPU · aprende continuamente via vector store semântico (LanceDB).

---

## Pré-requisitos

| Ferramenta | Versão | Uso |
|---|---|---|
| Python | 3.10+ | runtime do agente |
| [Ollama](https://ollama.com) | latest | LLM local |
| GPU | 8GB VRAM+ (recomendado) | modelos 7B+ |
| Node.js | 18+ | NestJS / Next.js |
| Java | 21+ | Spring Boot |
| .NET SDK | 8+ | ASP.NET Core |

```bash
# Modelo de código
ollama pull qwen2.5-coder:7b     # recomendado
ollama pull deepseek-coder:6.7b  # alternativa leve

# Embeddings (busca semântica no training store — obrigatório)
ollama pull nomic-embed-text
```

---

## Instalação

```bash
git clone <repo> ~/git/devai && cd ~/git/devai
chmod +x install.sh scripts/study.sh
./install.sh
source ~/.zshrc  # ou ~/.bashrc
```

---

## Comandos

### `devai new` / `devnew` — Criar projeto

```bash
devai new <stack> <nome> "<descrição>"
```

**NestJS:**
```bash
devnew nestjs livros-api "CRUD de livros com MongoDB e docker"
devnew nestjs loja       "API de pedidos com PostgreSQL, JWT e Redis"
devnew nestjs chat       "Chat em tempo real com WebSocket, Kafka, MongoDB"
devnew nestjs catalog    "API GraphQL de catálogo com MongoDB"
devnew nestjs books-svc  "Microsserviço gRPC de livros com MongoDB"
```

**Spring Boot:**
```bash
devnew spring-boot users-svc  "Microsserviço de usuários com MongoDB, JWT e Kafka"
devnew spring-boot inventory  "API de estoque com PostgreSQL e Spring Security"
```

**Python FastAPI:**
```bash
devnew python books-api  "API FastAPI de livros com MongoDB"
devnew python orders-api "API FastAPI de pedidos com PostgreSQL e JWT"
```

**ASP.NET Core:**
```bash
devnew dotnet catalog-api "API de catálogo com ASP.NET Core 9 e MongoDB"
```

**Frontend / Fullstack:**
```bash
devnew nextjs loja "E-commerce Next.js 15 com MongoDB e NextAuth"
devnew nestjs+nextjs plataforma "Plataforma fullstack NestJS + Next.js"
```

**Stacks:** `nestjs` · `spring-boot` · `python` · `dotnet` · `nextjs` · `angular` · `react` · `nestjs+nextjs` · `nestjs+angular`

---

### `devai feature` / `devfeat` — Adicionar feature

```bash
cd ~/meu-projeto && devfeat "<descrição>"
```

```bash
devfeat "configure docker-compose com app e MongoDB"
devfeat "adicione auth JWT com refresh token e roles"
devfeat "adicione Kafka producer e consumer para pedidos"
devfeat "configure Redis Sentinel para alta disponibilidade"
devfeat "adicione WebSocket gateway para notificações em tempo real"
devfeat "adicione GraphQL com subscriptions"
devfeat "configure gRPC para comunicação com microsserviços"
devfeat "adicione upload de arquivos para S3/MinIO"
devfeat "configure rate limiting por IP com Redis"
devfeat "adicione módulo de relatórios com Elasticsearch"
devfeat "configure Circuit Breaker para chamadas externas"
devfeat "configure nginx como reverse proxy"
```

---

### `devai fix` / `devfix` — Reparar erros de build

```bash
devfix
devai fix --rounds 15   # até 15 tentativas
devai fix --run         # roda após corrigir
```

Corrige automaticamente:
- `PartialType` de `@nestjs/common` → `@nestjs/mapped-types`
- `findById` → `findOne` / `findByIdAndDelete`
- `users.module` → `user.module` (singular)
- `user.entity` → `user.schema` (projetos MongoDB)
- Paths de import errados → busca arquivo real no disco
- Diretórios inválidos criados por alucinação → removidos
- Espaços em nomes de arquivo → kebab-case

---

### `devai study` / `devstudy` — Estudar projeto existente

```bash
cd ~/meu-projeto && devstudy
devai study --path /caminho/do/projeto
```

---

### `devai ask` / `devask` — Perguntar sobre o projeto

```bash
devask "como funciona o módulo de autenticação?"
devask "como adicionar um novo endpoint seguindo o padrão?"
```

---

### `devai search` / `devsearch` — Pesquisar e salvar no training

```bash
devsearch "nestjs mongoose schema required optional 2025"
devsearch "docker-compose mongodb healthcheck 2025"
devsearch "fastapi postgresql sqlalchemy async 2025"
devsearch "spring boot kafka consumer error handler 2025"
devsearch "tema específico" --no-save  # só pesquisa, sem salvar
```

---

### `devai train` / `devtrain` — Treinar com arquivos de referência

```bash
devtrain src/configs/redis.sentinels.config.ts
devtrain --dir src/configs/
devtrain --dir src/modules/ --recursive
devtrain --project /path/to/projeto-referencia/
devtrain src/app.module.ts --label "app-module-mongodb"
```

---

### `devai knowledge` — Gerenciar o vector store

```bash
devai knowledge           # lista itens e status dos embeddings
devai knowledge --export  # exporta para Markdown
devai knowledge --clear   # limpa tudo
```

---

### `scripts/study.sh` — Treinamento autônomo ultra-detalhado

```bash
chmod +x scripts/study.sh  # (feito automaticamente pelo install.sh)

# Rápido (~15min) — NestJS+MongoDB + Docker + erros
./scripts/study.sh

# Por stack — cobre TODOS os bancos + microserviços + auth + infra para a stack
./scripts/study.sh --group nestjs          # NestJS completo
./scripts/study.sh --group spring          # Spring Boot completo
./scripts/study.sh --group python          # FastAPI + Django
./scripts/study.sh --group dotnet          # ASP.NET Core
./scripts/study.sh --group frontend        # Next.js + React + Angular

# Por tema transversal
./scripts/study.sh --group databases       # Todos os bancos (MongoDB, PostgreSQL, Redis, ES, Cassandra)
./scripts/study.sh --group microservices   # Kafka, RabbitMQ, gRPC, GraphQL, WebSocket, Patterns
./scripts/study.sh --group infra           # Docker, Kubernetes, GitHub Actions

# TUDO — ultra-completo (~2-4h)
./scripts/study.sh --group all

# Overnight com loop + auto-commit + descoberta autônoma
nohup ./scripts/study.sh --group all --loop > training/study.log 2>&1 &
tail -f training/study.log

# Intervalo menor entre ciclos (padrão: 30min)
./scripts/study.sh --group all --loop --interval 900   # 15min
```

**Cobertura do estudo:**

| Grupo | O que estuda (stack × banco × microserviço) |
|---|---|
| `nestjs` | NestJS × MongoDB/PostgreSQL/MySQL/Redis/Elasticsearch × Kafka/RabbitMQ/gRPC/GraphQL/WebSocket/TCP × JWT/OAuth2/RBAC |
| `spring` | Spring Boot × MongoDB/PostgreSQL/MySQL/Redis × Kafka/RabbitMQ/gRPC/GraphQL × JWT/Spring Security |
| `python` | FastAPI × MongoDB/PostgreSQL/MySQL/Redis × Kafka/RabbitMQ × JWT/OAuth2 · Django × MongoDB/PostgreSQL |
| `dotnet` | ASP.NET Core × MongoDB/PostgreSQL/MySQL/Redis × Kafka/RabbitMQ/SignalR × JWT/Identity |
| `frontend` | Next.js × MongoDB/PostgreSQL × NextAuth · React · Angular |
| `databases` | MongoDB/PostgreSQL/Redis/Elasticsearch/Cassandra (avançado) |
| `microservices` | Kafka/RabbitMQ/gRPC/GraphQL/WebSocket × todas as stacks + CQRS/Saga/Circuit Breaker/Event Sourcing |
| `infra` | Docker × todas as combinações + Kubernetes + GitHub Actions |
| **`all`** | **Tudo acima (~60 tópicos × ~350 pesquisas)** |

**O estudo descobre e mapeia novos tópicos automaticamente:**
- A cada ciclo, pede ao LLM sugestões de tópicos não cobertos
- Salva os novos tópicos em `training/discovered_topics.json`
- Estuda imediatamente e persiste para próximos ciclos
- O mapa de tópicos cresce continuamente

---

## Como o Training é Usado na Geração

Quando você executa `devai new` ou `devai feature`:

```
Você: devnew nestjs livros-api "CRUD de Livros com MongoDB"
              ↓
1. Domain Extraction (determinístico):
   Entidade: Book (de "Livros")
   db_type: mongodb
   has_auth: false
   infra: docker

2. Vector Search (nomic-embed-text):
   Query: "nestjs mongodb schema Book entity"
   Top matches:
     pattern:nestjs+mongodb:schema (score: 0.91) ← schema com ! e ?
     pattern:nestjs+mongodb:service (score: 0.87) ← service CRUD
     nlp:entities-pt-en-complete (score: 0.79)

3. Geração de cada arquivo:
   Para book.schema.ts → injeta pattern:nestjs+mongodb:schema como referência
   LLM instrução: "Adapt this working pattern for entity Book with fields: title, author, price"

4. Pós-processamento determinístico:
   ensure_db_in_app_module() → MongooseModule.forRoot() no AppModule
   integrate_module_into_app() → BookModule no @Module imports
   cleanup_invalid_dirs() → remove pastas docker/container/image
   apply_fixes_to_project() → PartialType, findById→findOne, etc.

5. Resultado: projeto compilável com padrões corretos
```

---

## Vector Store (LanceDB — não é SQL)

```
training/
  vectors/knowledge.lance/     ← LanceDB: Arrow files + índice vetorial HNSW
  patterns/                    ← JSON por tópico (legível, editável, commitável)
  index.json                   ← índice rápido de todos os itens
  discovered_topics.json       ← tópicos descobertos autonomamente
  export/                      ← Markdown gerado por devai knowledge --export
  study.log                    ← log do último treinamento
```

**Busca semântica:** embedding da query → cosine similarity → top-K mais relevantes

**Fallback:** se `nomic-embed-text` não disponível, busca por palavras-chave nos JSONs

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
├── main.py                      ← CLI: new/feature/fix/search/train/knowledge/ask/study
├── orchestrator.py              ← Pipeline de geração
├── install.sh                   ← Setup venv + deps + aliases + chmod
├── requirements.txt             ← lancedb, pyarrow, ddgs, rich, requests, ...
├── scripts/
│   ├── study.sh                 ← Launcher: --group all --loop --interval
│   └── study.py                 ← Currículo v4: stack×banco×microserviço×infra
├── training/
│   ├── vectors/knowledge.lance/ ← LanceDB (Arrow + HNSW index)
│   ├── patterns/*.json          ← Padrões de código por tópico (commitável)
│   ├── index.json               ← Índice de todos os itens
│   ├── discovered_topics.json   ← Tópicos auto-descobertos (persistente)
│   ├── export/                  ← Markdown por tópico
│   └── study.log
└── tools/
    ├── domain_extractor.py      ← NLP 2 fases: entidade × instrução
    ├── db_strategy.py           ← Stack × banco → ORM, pacotes, docker
    ├── manifests.py             ← Arquivos a gerar por stack/banco
    ├── generator.py             ← Geração com vector search obrigatório
    ├── infra_generator.py       ← docker-compose dinâmico
    ├── code_fixer.py            ← Fixes TypeScript determinísticos
    ├── project_fixer.py         ← Loop: compila → parseia → corrige
    ├── orchestrator_helpers.py  ← Steps do pipeline
    ├── vector_store.py          ← LanceDB + JSON storage
    ├── embeddings.py            ← nomic-embed-text via Ollama
    ├── research_agent.py        ← Pesquisa web + salva no vector store
    ├── file_trainer.py          ← Treina com arquivos/projetos
    ├── knowledge_templates.py   ← Templates: Docker, Mongoose, configs
    ├── llm_client.py            ← Cliente Ollama + retry + streaming
    └── scanner.py               ← Escaneia projetos existentes
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

# Projeto com pastas inválidas (dockerhub, container, image)
devfix   # cleanup automático + rebuild

# Erros de build persistem
devai fix --rounds 15
devsearch "nestjs TS2307 cannot find module fix 2025"
devfix

# Training store corrompido
devai knowledge --clear
./scripts/study.sh --group all

# Ver tópicos descobertos automaticamente
cat training/discovered_topics.json
```

---

## Validação do Treinamento

Após estudar, valide o conhecimento do agente:

```bash
# Validação completa
python scripts/validate.py

# Valida E retreina os tópicos com baixa pontuação
python scripts/validate.py --fix

# Validar só tópicos específicos
python scripts/validate.py --topic nestjs-mongodb nlp

# Via study.sh (valida ao final do estudo)
./scripts/study.sh --group all --validate

# Loop com validação a cada 3 ciclos
./scripts/study.sh --group all --loop --validate
```

**O que a validação testa:**

| Tópico | Exemplos de perguntas |
|---|---|
| `nestjs-mongodb` | Schema com `!` e `?`, InjectModel, MongooseModule, findOneBy vs findById |
| `nestjs-auth` | JwtStrategy, PartialType de `@nestjs/mapped-types` |
| `nlp` | "livros" → `Book`, docker não cria pasta em `src/`, "usuários" ≠ auth |
| `docker` | healthcheck MongoDB, não adicionar Redis sem pedir |
| `spring-boot-mongodb` | `@Document` vs `@Entity` |
| `python-fastapi` | Motor async connection |

**Saída:**
```
Overall: 83% [████████████████░░░░]
  17/20.5 pontos
  5/6 tópicos bem treinados

✅ nestjs-mongodb: 91%
✅ nestjs-auth: 88%
✅ nlp: 85%
⚠️ docker: 65% → ./scripts/study.sh --topics docker
❌ spring-boot-mongodb: 48% → ./scripts/study.sh --topics spring-boot-mongodb
```

**Relatório commitável:**
```bash
cat training/validation_report.md    # relatório detalhado
git add training/ && git commit -m "training: validation $(date +%Y-%m-%d)"
```

---

## Modo Intensivo

Para treinamento profundo (quando tem tempo e/ou GPU boa):

```bash
# Intensivo: 6 resultados por query + exemplos de código (4-8h)
./scripts/study.sh --group all --intensive

# Intensivo + validação ao final
./scripts/study.sh --group all --intensive --validate

# Overnight intensivo com loop e auto-commit
nohup ./scripts/study.sh --group all --intensive --loop > training/study.log 2>&1 &
tail -f training/study.log
```

**Diferença:**

| Modo | Resultados/query | Exemplos de código | Tempo |
|---|---|---|---|
| Normal (`--group all`) | 4 | não | ~1-2h |
| Intensivo (`--intensive`) | 6 + follow-up | sim | ~4-8h |
| Intensivo em loop | ilimitado | sim | dias/semanas |

---

## Como o treinamento realmente funciona

O DevAI usa **RAG** (Retrieval-Augmented Generation) — não fine-tuning do modelo.

| Aspecto | O que acontece |
|---|---|
| O LLM muda com o treino? | **Não.** Os pesos do `qwen2.5-coder:7b` são fixos |
| O que melhora? | O **contexto injetado** no prompt — padrões e exemplos relevantes |
| Limite do contexto? | ~2000 chars de training por geração (janela de contexto) |
| Melhora raciocínio? | Não diretamente — melhora acesso a padrões concretos |

**Para maximizar o benefício:**
```bash
# 1. Estuda padrões e metodologia
./scripts/study.sh --group all --intensive

# 2. Auto-geração de exemplos validados (o agente aprende com o que funciona)
python scripts/self_improve.py --loop

# 3. Valida e corrige fracos (retreinamento forçado dos pontos críticos)
python scripts/validate.py --fix --rounds 5

# 4. Sempre que criar um projeto bom, treina com ele
devai train --project ~/meu-projeto-bem-feito/
```

**O que o treino SÍ melhora:**
- Padrões de código concretos (schema Mongoose, service TypeORM, etc.)
- APIs de bibliotecas específicas
- Anti-patterns (o que não fazer e por quê)
- Configurações de infra (docker-compose correto)
- Nomenclatura PT→EN para entidades

**O que o treino NÃO melhora (limitação do RAG):**
- Raciocínio arquitetural complexo
- Julgamentos de trade-off não exemplificados
- Criatividade além dos padrões treinados

**Grupos de estudo por área:**
```bash
./scripts/study.sh --group methodology    # SOLID, Clean Architecture, API design
./scripts/study.sh --group security-patterns  # OWASP, JWT, validação
./scripts/study.sh --group testing-patterns   # TDD, Jest, pytest
./scripts/study.sh --group performance-patterns  # caching, N+1, paginação
./scripts/study.sh --group anti-patterns    # o que evitar e por quê
```
