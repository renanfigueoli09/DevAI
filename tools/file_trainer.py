"""
File Trainer — treina o LLM com arquivos reais do projeto.

Comandos:
  devai train src/configs/redis.sentinels.config.ts    # arquivo único
  devai train --dir src/configs/                        # diretório
  devai train --project /path/to/reference/             # projeto completo
  devai knowledge --show redis                          # exibe o que foi aprendido

O conteúdo dos arquivos é sumarizado pelo LLM e salvo no knowledge base global
com a chave "file:{path}" ou "pattern:{nome}".

Uso nos prompts de geração:
  O generator lê o knowledge base e injeta os padrões aprendidos no contexto.
"""

import re
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.rule import Rule

console = Console()

# Extensões que valem como contexto de código
CODE_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".py", ".java", ".cs", ".go",
    ".yaml", ".yml", ".json", ".env", ".sh", ".conf",
    ".toml", ".prisma", ".graphql",
}

MAX_FILE_SIZE = 8_000  # chars máximos por arquivo para o LLM


def train_file(
    file_path: Path,
    llm,
    model: str,
    label: Optional[str] = None,
) -> Optional[str]:
    """
    Lê um arquivo e cria um sumário de padrões para o knowledge base.
    Retorna a key salva ou None se falhou.
    """
    from tools.research_agent import _store

    if not file_path.exists():
        console.print(f"  [red]✗ Arquivo não encontrado: {file_path}[/red]")
        return None

    if file_path.suffix not in CODE_EXTENSIONS and file_path.suffix:
        console.print(f"  [dim]Pulando {file_path.name} (extensão não suportada)[/dim]")
        return None

    content = file_path.read_text(encoding="utf-8", errors="ignore")
    if not content.strip():
        return None

    # Trunca para caber no contexto
    content_for_llm = content[:MAX_FILE_SIZE]
    truncated = len(content) > MAX_FILE_SIZE

    key = label or f"file:{file_path.name}"

    prompt = (
        f"Analyze this {file_path.suffix} file and extract reusable patterns.\n\n"
        f"File: {file_path.name}\n"
        f"Content:\n```\n{content_for_llm}\n"
        f"{'... (truncated)' if truncated else ''}\n```\n\n"
        "Extract:\n"
        "1. Main purpose / pattern name\n"
        "2. Key imports and dependencies\n"
        "3. Configuration patterns (if config file)\n"
        "4. Code patterns to reuse (class names, method signatures, decorators)\n"
        "5. Any important notes about usage\n\n"
        "Format as concise bullet points. Max 15 lines."
    )

    try:
        import threading
        result = [None]

        def _call():
            try:
                result[0] = llm.chat(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    system=(
                        "You analyze code files and extract reusable patterns. "
                        "Return bullet points only. No intro text."
                    ),
                    stream=False,
                )
            except Exception as e:
                result[0] = f"Error: {e}"

        t = threading.Thread(target=_call, daemon=True)
        t.start()
        t.join(timeout=30)

        summary = result[0] or ""
        if summary and not summary.startswith("Error"):
            full_content = f"=== {file_path.name} ===\n{summary}\n\nRaw:\n{content[:1500]}"
            # Salva no training_store (commitável)
            try:
                from tools.vector_store import save as ts_save, _infer_topic
                ts_save(key, full_content,
                        topic=_infer_topic(key, full_content),
                        source=f"file:{file_path.name}")
            except Exception:
                pass
            # Também no KB JSON (compat)
            from tools.research_agent import _store
            _store(key, full_content)
            console.print(f"  [green]✓[/green] Aprendido: [cyan]{key}[/cyan]")
            return key

    except Exception as e:
        console.print(f"  [yellow]⚠ {file_path.name}: {e}[/yellow]")

    return None


def train_directory(
    dir_path: Path,
    llm,
    model: str,
    recursive: bool = False,
    pattern: str = "*.ts",
) -> list[str]:
    """Treina com todos os arquivos de um diretório."""
    glob = dir_path.rglob(pattern) if recursive else dir_path.glob(pattern)
    files = [
        f for f in glob
        if f.is_file() and not any(
            p in str(f) for p in ["node_modules", ".git", "dist", "__pycache__", ".venv"]
        )
    ]

    if not files:
        console.print(f"  [yellow]Nenhum arquivo {pattern} em {dir_path}[/yellow]")
        return []

    console.print(f"\n[cyan]Treinando com {len(files)} arquivo(s) de {dir_path}[/cyan]")
    trained = []
    for f in files[:20]:  # max 20 arquivos por vez
        key = train_file(f, llm, model)
        if key:
            trained.append(key)

    return trained


def train_project(
    project_path: Path,
    llm,
    model: str,
) -> list[str]:
    """
    Treina com um projeto completo.
    Foca nos arquivos mais importantes: config, schemas, services principais.
    """
    console.print(Rule(f"[bold cyan]📚 Treinando com projeto: {project_path.name}[/bold cyan]"))

    # Arquivos prioritários para aprender padrões
    priority_patterns = [
        ("*.config.ts",     "configs/"),
        ("*.module.ts",     "src/"),
        ("docker-compose.yml", ""),
        ("Dockerfile",      ""),
        ("*.schema.ts",     "src/"),
        (".env.example",    ""),
    ]

    trained = []
    for pattern, subdir in priority_patterns:
        search_dir = project_path / subdir if subdir else project_path
        if not search_dir.exists():
            continue
        files = list(search_dir.rglob(pattern))[:5]
        for f in files:
            if any(p in str(f) for p in ["node_modules", "dist", ".git"]):
                continue
            key = train_file(f, llm, model, label=f"ref:{f.name}")
            if key:
                trained.append(key)

    # Sempre salva o docker-compose completo como referência
    dc = project_path / "docker-compose.yml"
    if dc.exists():
        from tools.research_agent import _store
        _store("ref:docker-compose", dc.read_text()[:6000])
        trained.append("ref:docker-compose")
        console.print("  [green]✓[/green] docker-compose salvo como referência")

    console.print(f"\n[green]✅ {len(trained)} padrão(ões) aprendido(s)[/green]")
    return trained


def get_relevant_templates(description: str) -> str:
    """
    Busca no training_store e knowledge base padrões relevantes.
    Retorna contexto para injetar nos prompts de geração.
    """
    relevant = []
    desc_lower = description.lower()

    # Busca no training_store (SQLite)
    try:
        from tools.vector_store import search_relevant
        ts_result = search_relevant(description, limit=4)
        if ts_result:
            relevant.append(ts_result)
    except Exception:
        pass

    from tools.research_agent import _load_kb
    kb = _load_kb()

    # Keywords para cada tipo de padrão
    keyword_map = {
        "redis": ["redis", "cache", "sentinel", "bull", "queue"],
        "kafka": ["kafka", "message", "producer", "consumer", "microservice", "event"],
        "websocket": ["websocket", "socket", "gateway", "real-time", "ws", "chat"],
        "mongodb": ["mongo", "mongodb", "mongoose", "schema"],
        "minio": ["s3", "minio", "upload", "file", "storage", "bucket"],
        "winston": ["log", "winston", "logger", "logging"],
        "bull": ["queue", "job", "processor", "background", "bull"],
        "jwt": ["auth", "jwt", "token", "passport"],
    }

    for topic, keywords in keyword_map.items():
        if any(kw in desc_lower for kw in keywords):
            # Busca no KB por entradas relacionadas
            for key in kb:
                if topic in key.lower() or any(kw in key.lower() for kw in keywords):
                    entry = kb[key]
                    if isinstance(entry, dict):
                        content = entry.get("content", "")[:500]
                    else:
                        content = str(entry)[:500]
                    if content:
                        relevant.append(f"[{key}]\n{content}")

    if not relevant:
        return ""

    return "=== LEARNED PATTERNS FROM REFERENCE PROJECT ===\n" + "\n\n".join(relevant[:4])
