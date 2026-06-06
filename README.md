# ⚡ DevAI — Agente Autônomo de Desenvolvimento Local

Agente de código multi-stack usando LLM local via Ollama.
100% offline · aprende com o uso · entende português informal.

> Training store: **612 itens** | **16433 embeddings** | storage: `lancedb+json`
> *Atualizado: 2026-06-06 14:39*

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
