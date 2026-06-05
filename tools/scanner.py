"""
Project Scanner — lê e indexa arquivos de um projeto existente.
Produz um resumo estruturado que alimenta os agentes.
"""

import os
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from config import IGNORE_DIRS, IGNORE_EXTENSIONS, MAX_CONTEXT_TOKENS

console = Console()

# Extensões de código que queremos ler
CODE_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".py", ".java", ".kt",
    ".cs", ".go", ".rs", ".cpp", ".c", ".h", ".hpp",
    ".json", ".yaml", ".yml", ".toml", ".xml", ".gradle",
    ".md", ".txt", ".env.example", ".properties",
}


@dataclass
class FileInfo:
    path: str          # relativo à raiz do projeto
    content: str
    language: str
    lines: int
    size_bytes: int


@dataclass
class ProjectSummary:
    root: str
    stack: Optional[str] = None
    name: str = ""
    total_files: int = 0
    total_lines: int = 0
    languages: dict = field(default_factory=dict)    # lang -> count
    key_files: list = field(default_factory=list)    # arquivos importantes
    structure: str = ""                               # árvore de dirs
    files: list = field(default_factory=list)        # FileInfo list
    dependencies: dict = field(default_factory=dict) # deps principais
    entry_points: list = field(default_factory=list)
    test_files: list = field(default_factory=list)

    def to_context_string(self, max_tokens: int = MAX_CONTEXT_TOKENS) -> str:
        """
        Serializa o projeto em texto otimizado para o LLM.
        Prioriza arquivos de configuração, entidades e interfaces.
        Trunca se necessário para caber no contexto.
        """
        lines = [
            f"# Projeto: {self.name}",
            f"Stack detectada: {self.stack or 'desconhecida'}",
            f"Linguagens: {', '.join(self.languages.keys())}",
            f"Total de arquivos: {self.total_files} | Linhas: {self.total_lines}",
            "",
            "## Estrutura de diretórios",
            self.structure,
            "",
            "## Dependências principais",
            json.dumps(self.dependencies, indent=2),
            "",
            "## Arquivos-chave (conteúdo)",
        ]

        budget = max_tokens - sum(len(l) // 4 for l in lines)

        for f in self.files:
            snippet = f"### {f['path']}\n```\n{f['content']}\n```\n"
            cost = len(snippet) // 4
            if budget - cost < 500:
                lines.append(f"### {f['path']} [truncado por limite de contexto]")
                break
            lines.append(snippet)
            budget -= cost

        return "\n".join(lines)


def detect_stack(root: Path) -> Optional[str]:
    """Detecta a stack pelo conteúdo do projeto."""
    checks = {
        "nestjs":      [root / "nest-cli.json", root / "src" / "main.ts"],
        "nextjs":      [root / "next.config.js", root / "next.config.ts", root / "next.config.mjs"],
        "angular":     [root / "angular.json"],
        "spring-boot": [root / "pom.xml", root / "build.gradle", root / "build.gradle.kts"],
        "python":      [root / "pyproject.toml", root / "requirements.txt", root / "setup.py"],
        "dotnet":      list(root.glob("*.csproj")) + list(root.glob("*.sln")),
    }
    for stack, paths in checks.items():
        if any(p.exists() for p in paths):
            return stack
    return None


def get_language(ext: str) -> str:
    MAP = {
        ".ts": "TypeScript", ".tsx": "TypeScript",
        ".js": "JavaScript", ".jsx": "JavaScript",
        ".py": "Python", ".java": "Java", ".kt": "Kotlin",
        ".cs": "C#", ".go": "Go", ".rs": "Rust",
        ".cpp": "C++", ".c": "C", ".h": "C/C++",
        ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
        ".xml": "XML", ".md": "Markdown", ".toml": "TOML",
    }
    return MAP.get(ext, "Other")


def is_key_file(path: Path) -> int:
    """Retorna prioridade do arquivo (maior = mais importante). 0 = ignorar."""
    name = path.name.lower()
    parts = str(path).lower()

    if any(x in name for x in ["package.json", "pom.xml", "pyproject.toml", "*.csproj", "build.gradle"]):
        return 100
    if any(x in parts for x in ["/entity/", "/entities/", "/model/", "/models/"]):
        return 90
    if any(x in parts for x in ["/interface/", "/interfaces/", "/contract/"]):
        return 85
    if any(x in parts for x in ["/dto/", "/dtos/"]):
        return 80
    if "main" in name or "app" in name or "bootstrap" in name:
        return 75
    if any(x in parts for x in ["/module/", "/modules/"]):
        return 70
    if any(x in parts for x in ["/service/", "/services/"]):
        return 65
    if any(x in parts for x in ["/controller/", "/controllers/", "/handler/"]):
        return 60
    if any(x in parts for x in ["/repository/", "/repositories/"]):
        return 55
    if "readme" in name:
        return 50
    if ".spec." in name or ".test." in name or "test_" in name:
        return 10  # testes são importantes mas lidos por último
    return 20


def build_tree(root: Path, prefix: str = "", max_depth: int = 4) -> str:
    lines = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: (p.is_file(), p.name))
    except PermissionError:
        return ""

    for i, entry in enumerate(entries):
        if entry.name in IGNORE_DIRS or entry.name.startswith("."):
            continue
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{entry.name}")
        if entry.is_dir() and max_depth > 0:
            ext_prefix = prefix + ("    " if is_last else "│   ")
            lines.append(build_tree(entry, ext_prefix, max_depth - 1))

    return "\n".join(filter(None, lines))


def read_dependencies(root: Path, stack: Optional[str]) -> dict:
    deps = {}
    try:
        if stack in ("nestjs", "nextjs", "angular"):
            pkg = root / "package.json"
            if pkg.exists():
                data = json.loads(pkg.read_text())
                deps = {
                    **data.get("dependencies", {}),
                    **{f"[dev] {k}": v for k, v in data.get("devDependencies", {}).items()},
                }
        elif stack == "spring-boot":
            pom = root / "pom.xml"
            if pom.exists():
                # Extrai apenas as dependências de forma simples
                content = pom.read_text()
                import re
                artifacts = re.findall(r"<artifactId>(.+?)</artifactId>", content)
                deps = {a: "" for a in artifacts[:30]}
        elif stack == "python":
            req = root / "requirements.txt"
            if req.exists():
                for line in req.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split("==")
                        deps[parts[0]] = parts[1] if len(parts) > 1 else "*"
            pyp = root / "pyproject.toml"
            if pyp.exists() and not deps:
                import re
                content = pyp.read_text()
                matches = re.findall(r'"([a-zA-Z0-9_-]+)[>=<~^!]*', content)
                deps = {m: "*" for m in matches[:30]}
        elif stack == "dotnet":
            for csproj in root.rglob("*.csproj"):
                import re
                content = csproj.read_text()
                pkgs = re.findall(r'PackageReference Include="(.+?)".*?Version="(.+?)"', content)
                deps.update({p: v for p, v in pkgs})
    except Exception:
        pass
    return deps


def scan_project(root: Path) -> ProjectSummary:
    """Escaneia o projeto e retorna um ProjectSummary."""
    root = root.resolve()
    console.print(f"\n[cyan]🔍 Escaneando projeto em [bold]{root}[/bold]...[/cyan]")

    summary = ProjectSummary(
        root=str(root),
        name=root.name,
        stack=detect_stack(root),
        structure=build_tree(root),
    )

    all_files: list[tuple[int, FileInfo]] = []
    languages = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Lendo arquivos...", total=None)

        for fpath in root.rglob("*"):
            if not fpath.is_file():
                continue
            # Ignora dirs proibidos
            if any(part in IGNORE_DIRS for part in fpath.parts):
                continue
            if fpath.suffix in IGNORE_EXTENSIONS:
                continue
            if fpath.suffix not in CODE_EXTENSIONS:
                continue

            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel = str(fpath.relative_to(root))
            lang = get_language(fpath.suffix)
            priority = is_key_file(fpath)

            fi = FileInfo(
                path=rel,
                content=content,
                language=lang,
                lines=content.count("\n"),
                size_bytes=len(content),
            )
            all_files.append((priority, fi))
            languages[lang] = languages.get(lang, 0) + 1
            summary.total_files += 1
            summary.total_lines += fi.lines

            if ".spec." in fpath.name or ".test." in fpath.name or fpath.name.startswith("test_"):
                summary.test_files.append(rel)

            progress.update(task, description=f"Lendo {rel[:60]}...")

    # Ordena por prioridade (mais importante primeiro)
    all_files.sort(key=lambda x: x[0], reverse=True)
    # Converte para dict ANTES de qualquer subscript
    files_as_dicts = [(p, asdict(fi)) for p, fi in all_files]
    summary.files     = [f for _, f in files_as_dicts]
    summary.key_files = [f["path"] for _, f in files_as_dicts[:20]]
    summary.languages = languages
    summary.dependencies = read_dependencies(root, summary.stack)

    console.print(
        f"[green]✓ Escaneado:[/green] {summary.total_files} arquivos · "
        f"{summary.total_lines} linhas · Stack: [bold]{summary.stack or '?'}[/bold]"
    )

    return summary
