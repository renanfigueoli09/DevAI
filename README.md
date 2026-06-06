# ⚡ DevAI — Agente Autônomo de Desenvolvimento Local

Agente de código multi-stack usando LLM local via Ollama.
100% offline · aprende com o uso · entende português informal.

> Training store: **848 itens** | **825 embeddings** | storage: `lancedb+json`
> *Atualizado: 2026-06-06 01:11*

---

## Pré-requisitos

```bash
ollama pull qwen2.5-coder:7b    # modelo de código
ollama pull nomic-embed-text     # embeddings (busca semântica)
```

| Stack | Requisito |
|---|---|
| NestJS / Next.js | Node.js 18+ |
| Spring Boot | Java 21+ |
| ASP.NET Core | .NET SDK 8+ |
| FastAPI / Django | Python 3.10+ (já no venv) |

## Instalação

```bash
git clone <repo> ~/git/devai && cd ~/git/devai
chmod +x install.sh scripts/study.sh scripts/self_improve.py
./install.sh
source ~/.zshrc
```

---

## Comandos

### `devai new` / `devnew` — Criar projeto

```bash
devnew <stack> <nome> "<descrição em português ou inglês>"

# Exemplos:
devnew nestjs livros-api "CRUD de livros com MongoDB e docker"
devnew nestjs loja       "API de pedidos com PostgreSQL, JWT e Redis"
devnew nestjs chat       "Chat em tempo real com WebSocket, Kafka, MongoDB"
devnew spring-boot users "Microsserviço de usuários com MongoDB e JWT"
devnew python books-api  "API FastAPI de livros com MongoDB"
devnew dotnet catalog    "API ASP.NET Core com MongoDB"
devnew nextjs loja       "E-commerce Next.js 15 com MongoDB e NextAuth"
```

A IA entende português informal:
- `"tem o mongoDb"` → usa MongoDB
- `"s[oó] o necessário"` → sem extras
- `"código em inglês"` → identificadores em English

---

### `devai feature` / `devfeat` — Adicionar feature

```bash
devfeat "<descrição>"

devfeat "configure o docker-compose com app e MongoDB"
devfeat "configure o swagger"
devfeat "adicione auth JWT com refresh token"
devfeat "configure Kafka producer e consumer para pedidos"
devfeat "configure Redis Sentinel para alta disponibilidade"
devfeat "adicione rate limiting por IP"
devfeat "configure WebSocket gateway para notificações"
devfeat "adicione upload de arquivos para S3"
```

---

### `devai fix` / `devfix` — Corrigir erros de build

```bash
devfix
devai fix --rounds 15   # mais tentativas
devai fix --run         # roda após corrigir
```

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
```

---

### `devai search` / `devsearch` — Pesquisar e salvar no training

```bash
devsearch "nestjs mongoose schema required optional 2025"
devsearch "docker-compose mongodb healthcheck 2025"
devsearch "assunto específico" --no-save
```

---

### `devai train` / `devtrain` — Treinar com referências

```bash
devtrain src/app.module.ts
devtrain --dir src/configs/
devtrain --project /path/to/referencia/
```

---

### `devai knowledge` — Training store

```bash
devai knowledge           # lista + status embeddings
devai knowledge --export  # exporta para Markdown
devai knowledge --clear   # limpa tudo
```

---

### `devai profile` — Perfil e preferências do usuário

```bash
devai profile             # mostra preferências salvas
devai profile --set stack=nestjs db=mongodb  # define defaults
```

---
---

## Treinamento Autônomo

```bash
chmod +x scripts/study.sh  # já feito pelo install.sh

# Estuda o que ainda não foi feito (inteligente — não repete)
./scripts/study.sh

# Por grupo
./scripts/study.sh --group nestjs          # NestJS completo
./scripts/study.sh --group methodology     # SOLID, Clean Arch, API Design, Security
./scripts/study.sh --group all             # Tudo

# Intensivo + loop overnight
./scripts/study.sh --group all --intensive --loop --validate

# Ver o que já foi estudado
./scripts/study.sh --status

# Auto-gera exemplos e aprende com os resultados
python scripts/self_improve.py --loop

# Valida e corrige fracos
python scripts/validate.py --fix --rounds 5
```

| Grupo | O que estuda | Tempo aprox. |
|---|---|---|
| `databases` | 4 tópico(s) | ~25min |
| `dotnet` | 1 tópico(s) | ~15min |
| `frontend` | 3 tópico(s) | ~15min |
| `infra` | 7 tópico(s) | ~15min |
| `microservices` | 9 tópico(s) | ~25min |
| `nestjs` | 1 tópico(s) | ~35min |
| `python` | 2 tópico(s) | ~20min |
| `quick` | 5 tópico(s) | ~15min |
| `spring` | 1 tópico(s) | ~20min |
| **`all`** | **0 tópicos / ~0 pesquisas** | **~2-4h** |


**Loop inteligente** — usa `training/study_journal.json` para não repetir o que já foi estudado.
Descobre novos tópicos autonomamente a cada ciclo.


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
