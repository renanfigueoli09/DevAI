"""
DevAI Docs Updater — mantém o README e a documentação sempre atualizados.

Executa após qualquer mudança de comando ou feature.
Detecta novos comandos, flags e grupos de estudo automaticamente.

Uso:
  python scripts/update_docs.py          # atualiza README.md
  python scripts/update_docs.py --check  # verifica se está atualizado
"""

import argparse, json, re, sys, time
from pathlib import Path

DEVAI_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(DEVAI_DIR))

from rich.console import Console
console = Console()


def extract_commands_from_main() -> dict:
    """Lê main.py e extrai todos os comandos disponíveis."""
    main_py = DEVAI_DIR / "main.py"
    if not main_py.exists():
        return {}

    content = main_py.read_text()
    commands = {}

    # Detecta subcommands (argparse)
    for m in re.finditer(r'add_parser\(["\'](\w+)["\'].*?help=["\']([^"\']+)["\']', content):
        commands[m.group(1)] = m.group(2)

    # Detecta aliases
    aliases = {}
    for m in re.finditer(r'alias.*?["\'](\w+)["\'].*?["\']devai\s+(\w+)["\']', content):
        aliases[m.group(1)] = m.group(2)

    return {"commands": commands, "aliases": aliases}


def extract_study_groups() -> dict:
    """Lê study.py e extrai grupos e métricas."""
    study_py = DEVAI_DIR / "scripts" / "study.py"
    if not study_py.exists():
        return {}

    content = study_py.read_text()

    # Extract TOPIC_GROUPS
    groups = {}
    m = re.search(r'TOPIC_GROUPS\s*=\s*\{(.+?)\n\}', content, re.DOTALL)
    if m:
        for line in m.group(1).split("\n"):
            km = re.match(r'\s*["\'](\w[\w-]+)["\']:\s*\[(.+?)\]', line)
            if km:
                group = km.group(1)
                topics = re.findall(r'["\']([^"\']+)["\']', km.group(2))
                groups[group] = topics

    # Count total searches
    curriculum_m = re.search(r'SEARCH_CURRICULUM\s*=\s*\{(.+?)\n\}', content, re.DOTALL)
    total_searches = 0
    total_topics   = 0
    if curriculum_m:
        total_topics   = len(re.findall(r'^\s*["\'][\w+\-]+["\']:', curriculum_m.group(1), re.MULTILINE))
        total_searches = len(re.findall(r'"[^"]{10,}"', curriculum_m.group(1)))

    return {
        "groups":         groups,
        "total_topics":   total_topics,
        "total_searches": total_searches,
    }


def get_training_stats() -> dict:
    """Estatísticas atuais do training store."""
    try:
        from tools.vector_store import stats
        return stats()
    except Exception:
        return {}


def generate_commands_section() -> str:
    """Gera seção de comandos para o README."""
    return '''## Comandos

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

---'''


def generate_study_section(study_data: dict) -> str:
    """Gera seção de estudo para o README."""
    groups    = study_data.get("groups", {})
    n_topics  = study_data.get("total_topics", 0)
    n_queries = study_data.get("total_searches", 0)

    group_table = "| Grupo | O que estuda | Tempo aprox. |\n|---|---|---|\n"
    group_times = {
        "quick":        "~15min",
        "nestjs":       "~35min",
        "spring":       "~20min",
        "python":       "~20min",
        "dotnet":       "~15min",
        "frontend":     "~15min",
        "databases":    "~25min",
        "microservices":"~25min",
        "infra":        "~15min",
        "methodology":  "~30min",
        "all":          "~2-4h",
    }
    for group, topics in sorted(groups.items()):
        if group == "all":
            continue
        t = group_times.get(group, "~20min")
        desc = f"{len(topics)} tópico(s)"
        group_table += f"| `{group}` | {desc} | {t} |\n"
    group_table += f"| **`all`** | **{n_topics} tópicos / ~{n_queries} pesquisas** | **~2-4h** |\n"

    return f'''## Treinamento Autônomo

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

{group_table}

**Loop inteligente** — usa `training/study_journal.json` para não repetir o que já foi estudado.
Descobre novos tópicos autonomamente a cada ciclo.

'''


def update_readme() -> bool:
    """Atualiza o README.md com informações atuais."""
    readme = DEVAI_DIR / "README.md"
    study_data = extract_study_groups()
    ts_stats   = get_training_stats()

    # Read existing
    existing = readme.read_text(encoding="utf-8") if readme.exists() else ""

    # Build new header
    n_items = ts_stats.get("total", 0)
    n_emb   = ts_stats.get("with_embedding", 0)
    storage = ts_stats.get("storage", "lancedb+json")

    header = f'''# ⚡ DevAI — Agente Autônomo de Desenvolvimento Local

Agente de código multi-stack usando LLM local via Ollama.
100% offline · aprende com o uso · entende português informal.

> Training store: **{n_items} itens** | **{n_emb} embeddings** | storage: `{storage}`
> *Atualizado: {time.strftime("%Y-%m-%d %H:%M")}*

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

'''

    commands_section = generate_commands_section()
    study_section    = generate_study_section(study_data)

    # Keep the bottom sections (architecture, troubleshooting, etc.)
    # Split existing at first ## that we're replacing
    bottom = ""
    markers = ["## Vector Store", "## Como o treinamento", "## Aliases",
               "## Configuração", "## Estrutura", "## Troubleshooting"]
    for marker in markers:
        idx = existing.find(marker)
        if idx > 0:
            bottom = existing[idx:]
            break

    new_content = header + commands_section + "\n---\n\n" + study_section + "\n---\n\n" + bottom

    if new_content.strip() == existing.strip():
        return False  # no changes

    readme.write_text(new_content, encoding="utf-8")
    return True


def main():
    parser = argparse.ArgumentParser(description="DevAI Docs Updater")
    parser.add_argument("--check", action="store_true", help="Só verifica, não atualiza")
    args = parser.parse_args()

    console.print("[cyan]📄 Atualizando documentação...[/cyan]")

    changed = update_readme()

    if changed:
        console.print("[green]✓ README.md atualizado[/green]")
        console.print("[dim]git add README.md && git commit -m 'docs: auto-update'[/dim]")
    else:
        console.print("[dim]README.md já está atualizado[/dim]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
