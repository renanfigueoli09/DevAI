"""
File Writer — escreve arquivos gerados pelo agente.
Mostra diff e pede confirmação antes de qualquer escrita.
"""

import os
import json
import re
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.syntax import Syntax
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from config import CONFIRM_WRITES

console = Console()


def extract_files_from_response(response: str) -> list[dict]:
    """
    Extrai arquivos da resposta do LLM.
    Tenta múltiplas estratégias em ordem de confiabilidade.
    """
    files = []

    # ── Estratégia 1: JSON puro ou com fences ──────────────────────────────
    files = _try_parse_json(response)
    if files:
        return _filter_placeholder_files(files)

    # ── Estratégia 2: JSON embutido dentro de texto ────────────────────────
    # Pega o maior objeto JSON encontrado na resposta
    files = _try_extract_embedded_json(response)
    if files:
        return _filter_placeholder_files(files)

    # ── Estratégia 3: blocos de código markdown com FILE: comment ──────────
    pattern = re.compile(
        r"```(?:\w+)?\n(?:(?://|#|/\*)\s*FILE:\s*(.+?)\s*(?:\*/)?\n)([\s\S]+?)```",
        re.MULTILINE,
    )
    for match in pattern.finditer(response):
        files.append({"path": match.group(1).strip(), "content": match.group(2)})
    if files:
        return _filter_placeholder_files(files)

    # ── Estratégia 4: ### path\n```code``` ────────────────────────────────
    pattern2 = re.compile(r"###\s+`?([^\n`]+\.\w+)`?\n```(?:\w+)?\n([\s\S]+?)```", re.MULTILINE)
    for match in pattern2.finditer(response):
        files.append({"path": match.group(1).strip(), "content": match.group(2)})
    if files:
        return _filter_placeholder_files(files)

    # ── Estratégia 5: qualquer bloco de código com path na linha anterior ──
    pattern3 = re.compile(r"(?:^|\n)([a-zA-Z0-9_/.-]+\.[a-zA-Z]+)\n```(?:\w+)?\n([\s\S]+?)```", re.MULTILINE)
    for match in pattern3.finditer(response):
        path = match.group(1).strip()
        if "/" in path or path.count(".") >= 1:
            files.append({"path": path, "content": match.group(2)})
    if files:
        return _filter_placeholder_files(files)

    return []


def _try_parse_json(text: str) -> list[dict]:
    """Tenta parsear JSON da resposta, removendo markdown fences se presentes."""
    candidates = [text.strip()]

    # Remove fences ```json ... ``` ou ``` ... ```
    clean = re.sub(r"^```(?:json)?\s*\n?", "", text.strip(), flags=re.MULTILINE)
    clean = re.sub(r"\n?```\s*$", "", clean.strip())
    candidates.append(clean)

    for candidate in candidates:
        try:
            data = json.loads(candidate)
            return _extract_files_from_parsed(data)
        except (json.JSONDecodeError, ValueError):
            pass
    return []


def _try_extract_embedded_json(text: str) -> list[dict]:
    """Encontra o maior objeto JSON dentro de um texto misto."""
    # Encontra todas as posições de { e tenta parsear de cada uma
    for match in re.finditer(r'\{', text):
        start = match.start()
        # Tenta pegar até o final do texto
        for end in range(len(text), start, -1):
            if text[end-1] == '}':
                try:
                    data = json.loads(text[start:end])
                    result = _extract_files_from_parsed(data)
                    if result:
                        return result
                except (json.JSONDecodeError, ValueError):
                    continue
    return []


def _extract_files_from_parsed(data) -> list[dict]:
    """Extrai lista de files de um objeto JSON já parseado."""
    if isinstance(data, list):
        if all(isinstance(f, dict) and "path" in f for f in data):
            return data
    if isinstance(data, dict):
        # {"files": [...]}
        if "files" in data and isinstance(data["files"], list):
            return data["files"]
        # {"path": "...", "content": "..."} — arquivo único
        if "path" in data and "content" in data:
            return [data]
        # {"ModuleName": {"file.ts": "content"}} — formato de dicionário aninhado
        files = []
        for key, value in data.items():
            if isinstance(value, dict):
                for fname, fcontent in value.items():
                    if isinstance(fcontent, str) and fname.endswith(
                        (".ts", ".tsx", ".js", ".java", ".py", ".cs", ".kt", ".html", ".css", ".json", ".yaml", ".yml", ".md")
                    ):
                        # Constrói o path a partir do key (módulo) e fname
                        path = f"src/{key.lower().replace('module','')}/{fname}".replace("//", "/")
                        files.append({"path": path, "content": fcontent})
        if files:
            return files
    return []


def _filter_placeholder_files(files: list[dict]) -> list[dict]:
    """
    Remove arquivos que são apenas placeholders (sem código real).
    Detecta conteúdo como '// Cart exceptions implementation' sem código.
    """
    real_files = []
    placeholder_patterns = [
        r"^//\s+\w+ \w+ implementation\s*$",
        r"^#\s+\w+ \w+ implementation\s*$",
        r"^/\*\s+\w+ \w+ implementation\s*\*/\s*$",
        r"^// TODO",
        r"^// implementation here",
    ]
    import re as _re
    compiled = [_re.compile(p, _re.IGNORECASE) for p in placeholder_patterns]

    for f in files:
        content = f.get("content", "").strip()
        if not content:
            continue
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        if not lines:
            continue
        # Se tem apenas 1 linha e ela é um placeholder, ignora
        if len(lines) == 1 and any(p.match(lines[0]) for p in compiled):
            console.print(f"  [dim yellow]⚠ Pulando placeholder: {f.get('path')}[/dim yellow]")
            continue
        real_files.append(f)

    return real_files


def show_file_plan(files: list[dict], action: str = "criar"):
    """Exibe tabela com os arquivos que serão criados/alterados."""
    table = Table(title=f"📁 Arquivos para {action}", border_style="cyan", show_lines=True)
    table.add_column("Nº", style="dim", width=4)
    table.add_column("Arquivo", style="cyan")
    table.add_column("Linhas", justify="right", style="green")
    table.add_column("Tamanho", justify="right", style="dim")

    for i, f in enumerate(files, 1):
        content = f.get("content", "")
        lines = content.count("\n")
        size = f"{len(content)} bytes"
        table.add_row(str(i), f["path"], str(lines), size)

    console.print(table)


def preview_file(file: dict):
    """Exibe o conteúdo de um arquivo com syntax highlighting."""
    path = file["path"]
    content = file.get("content", "")
    ext = Path(path).suffix.lstrip(".")

    # Mapeamento de extensões para linguagem do rich
    lang_map = {
        "ts": "typescript", "tsx": "tsx", "js": "javascript",
        "jsx": "jsx", "py": "python", "java": "java", "kt": "kotlin",
        "cs": "csharp", "json": "json", "yaml": "yaml", "yml": "yaml",
        "xml": "xml", "md": "markdown", "gradle": "groovy",
        "toml": "toml", "html": "html", "css": "css", "scss": "scss",
    }
    lang = lang_map.get(ext, "text")

    console.print(Panel(
        Syntax(content, lang, theme="monokai", line_numbers=True, word_wrap=True),
        title=f"[bold cyan]{path}[/bold cyan]",
        border_style="dim",
    ))


def write_files(
    files: list[dict],
    base_path: Path,
    confirm: bool = CONFIRM_WRITES,
    preview: bool = True,
) -> list[str]:
    """
    Escreve os arquivos no disco.
    Retorna lista dos caminhos escritos.
    """
    if not files:
        console.print("[yellow]⚠ Nenhum arquivo para escrever.[/yellow]")
        return []

    show_file_plan(files)

    if preview:
        show_preview = Confirm.ask("\n[cyan]Deseja visualizar os arquivos antes de salvar?[/cyan]", default=False)
        if show_preview:
            for f in files:
                preview_file(f)
                if len(files) > 1:
                    if not Confirm.ask("Próximo arquivo?", default=True):
                        break

    if confirm:
        if not Confirm.ask(
            f"\n[bold yellow]✍ Salvar {len(files)} arquivo(s) em [cyan]{base_path}[/cyan]?[/bold yellow]",
            default=True,
        ):
            console.print("[dim]Escrita cancelada.[/dim]")
            return []

    written = []
    for f in files:
        full_path = base_path / f["path"]
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Se arquivo existe, mostra diff simples
        if full_path.exists():
            existing = full_path.read_text(encoding="utf-8", errors="ignore")
            if existing == f["content"]:
                console.print(f"  [dim]= {f['path']} (sem alterações)[/dim]")
                continue
            console.print(f"  [yellow]~ {f['path']} (modificado)[/yellow]")
        else:
            console.print(f"  [green]+ {f['path']}[/green]")

        full_path.write_text(f["content"], encoding="utf-8")
        written.append(str(full_path))

    console.print(f"\n[bold green]✅ {len(written)} arquivo(s) salvo(s) em {base_path}[/bold green]")
    return written


def save_project_context(project_path: Path, context: dict):
    """Salva o contexto analisado do projeto para reutilização."""
    devai_dir = project_path / ".devai"
    devai_dir.mkdir(exist_ok=True)
    ctx_file = devai_dir / "context.json"
    ctx_file.write_text(json.dumps(context, indent=2, ensure_ascii=False))
    console.print(f"[dim]💾 Contexto salvo em {ctx_file}[/dim]")


def load_project_context(project_path: Path) -> Optional[dict]:
    """Carrega contexto previamente salvo."""
    ctx_file = project_path / ".devai" / "context.json"
    if ctx_file.exists():
        try:
            return json.loads(ctx_file.read_text())
        except Exception:
            pass
    return None
