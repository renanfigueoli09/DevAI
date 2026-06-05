"""
Scaffold — executa os comandos CLI reais de cada framework.

NestJS      → nest new
Next.js     → create-next-app
Angular     → ng new
Spring Boot → Spring Initializr API (curl) ou spring CLI
Python      → estrutura manual + venv
.NET        → dotnet new webapi
"""

import os
import sys
import shutil
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from rich.console import Console
from rich.prompt import Confirm

console = Console()


# ─── Utilitários ──────────────────────────────────────────────────────────────

def _run(cmd: list[str], cwd: Path = None, env: dict = None) -> bool:
    """Executa um comando, exibindo output em tempo real. Retorna True se ok."""
    console.print(f"[dim]$ {' '.join(cmd)}[/dim]")
    merged_env = {**os.environ, **(env or {})}
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=merged_env,
            check=True,
        )
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        console.print(f"[red]✗ Comando falhou (exit {e.returncode})[/red]")
        return False
    except FileNotFoundError:
        console.print(f"[red]✗ Comando não encontrado: {cmd[0]}[/red]")
        return False


def _require(tool: str, install_hint: str) -> bool:
    """Verifica se uma ferramenta está instalada."""
    if shutil.which(tool):
        return True
    console.print(f"[red]✗ '{tool}' não encontrado.[/red]")
    console.print(f"[yellow]  Instale com: {install_hint}[/yellow]")
    return False


def _npx_available() -> bool:
    return bool(shutil.which("npx"))


def _node_version() -> str:
    try:
        r = subprocess.run(["node", "--version"], capture_output=True, text=True)
        return r.stdout.strip()
    except Exception:
        return ""


# ─── Scaffold por stack ───────────────────────────────────────────────────────

def scaffold_nestjs(name: str, output_dir: Path) -> bool:
    """nest new — usa versão mais recente do CLI via web_research"""
    console.print("\n[cyan]📦 Scaffolding NestJS...[/cyan]")

    node_ver = _node_version()
    if not node_ver:
        console.print("[red]✗ Node.js não encontrado. Instale em https://nodejs.org[/red]")
        return False
    console.print(f"  ✓ Node.js {node_ver}")

    # Busca versão mais recente do CLI
    try:
        from tools.web_research import fetch_scaffold_command
        info = fetch_scaffold_command("nestjs")
        cli_ver = info.get("cli_version", "latest")
        console.print(f"  [dim]→ @nestjs/cli@{cli_ver}[/dim]")
    except Exception:
        cli_ver = "latest"

    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)

    ok = _run(
        ["npx", "--yes", f"@nestjs/cli@{cli_ver}", "new", name,
         "--skip-git", "--package-manager", "npm", "--strict"],
        cwd=parent,
    )
    return ok


def scaffold_nextjs(name: str, output_dir: Path) -> bool:
    """create-next-app com App Router, TypeScript, Tailwind, src/"""
    console.print("\n[cyan]📦 Scaffolding Next.js...[/cyan]")

    if not _node_version():
        console.print("[red]✗ Node.js não encontrado.[/red]")
        return False

    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)

    try:
        from tools.web_research import fetch_scaffold_command
        info = fetch_scaffold_command("nextjs")
        cna_ver = info.get("cli_version", "latest")
        console.print(f"  [dim]→ create-next-app@{cna_ver}[/dim]")
    except Exception:
        cna_ver = "latest"

    ok = _run(
        ["npx", "--yes", f"create-next-app@{cna_ver}", name,
         "--typescript", "--tailwind", "--eslint",
         "--app", "--src-dir", "--import-alias", "@/*", "--no-git",
         ],
        cwd=parent,
    )
    return ok


def scaffold_angular(name: str, output_dir: Path) -> bool:
    """ng new com standalone components, SCSS, routing"""
    console.print("\n[cyan]📦 Scaffolding Angular...[/cyan]")

    if not _node_version():
        console.print("[red]✗ Node.js não encontrado.[/red]")
        return False

    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)

    try:
        from tools.web_research import fetch_scaffold_command
        info = fetch_scaffold_command("angular")
        ng_ver = info.get("cli_version", "latest")
        console.print(f"  [dim]→ @angular/cli@{ng_ver}[/dim]")
    except Exception:
        ng_ver = "latest"

    ok = _run(
        ["npx", "--yes", f"@angular/cli@{ng_ver}", "new", name,
         "--routing", "--style=scss", "--skip-git",
         "--skip-install", "--standalone", "--ssr=false",
         ],
        cwd=parent,
    )
    if ok:
        console.print("[dim]→ Instalando dependências Angular...[/dim]")
        _run(["npm", "install"], cwd=output_dir)
    return ok


def scaffold_spring_boot(name: str, output_dir: Path, description: str = "") -> bool:
    """
    Baixa projeto do Spring Initializr (start.spring.io).
    Não requer spring CLI instalado.
    """
    console.print("\n[cyan]📦 Scaffolding Spring Boot via Spring Initializr...[/cyan]")

    # Converte name para artifactId (kebab-case → camelCase para groupId)
    artifact_id = name.lower().replace("_", "-")
    group_id = "com.devai"
    package_name = f"{group_id}.{artifact_id.replace('-', '')}"

    params = urllib.parse.urlencode({
        "type": "maven-project",
        "language": "java",
        "bootVersion": "3.4.1",
        "baseDir": name,
        "groupId": group_id,
        "artifactId": artifact_id,
        "name": artifact_id,
        "description": description or f"{name} Spring Boot application",
        "packageName": package_name,
        "packaging": "jar",
        "javaVersion": "21",
        "dependencies": ",".join([
            "web",
            "data-jpa",
            "postgresql",
            "lombok",
            "validation",
            "actuator",
            "devtools",
        ]),
    })

    url = f"https://start.spring.io/starter.zip?{params}"
    zip_path = output_dir.parent / f"{name}.zip"

    console.print(f"  [dim]→ Baixando de start.spring.io...[/dim]")
    try:
        urllib.request.urlretrieve(url, zip_path)
    except Exception as e:
        console.print(f"[red]✗ Erro ao baixar do Spring Initializr: {e}[/red]")
        console.print("[yellow]  Verifique sua conexão ou use: https://start.spring.io[/yellow]")
        return False

    # Extrai o zip
    import zipfile
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(output_dir.parent)
    zip_path.unlink()

    console.print(f"  [green]✓ Spring Boot project extraído em {output_dir}[/green]")
    return output_dir.exists()


def scaffold_python(name: str, output_dir: Path) -> bool:
    """
    Cria estrutura FastAPI manualmente (não existe CLI oficial).
    Cria venv, instala dependências básicas.
    """
    console.print("\n[cyan]📦 Scaffolding Python/FastAPI...[/cyan]")

    # Verifica Python
    python = shutil.which("python3") or shutil.which("python")
    if not python:
        console.print("[red]✗ Python não encontrado.[/red]")
        return False

    output_dir.mkdir(parents=True, exist_ok=True)

    # Estrutura de diretórios
    dirs = [
        "src",
        f"src/{name.replace('-', '_')}",
        f"src/{name.replace('-', '_')}/routers",
        f"src/{name.replace('-', '_')}/services",
        f"src/{name.replace('-', '_')}/repositories",
        f"src/{name.replace('-', '_')}/models",
        f"src/{name.replace('-', '_')}/schemas",
        f"src/{name.replace('-', '_')}/core",
        f"src/{name.replace('-', '_')}/exceptions",
        "tests",
        "alembic",
        "alembic/versions",
    ]
    for d in dirs:
        (output_dir / d).mkdir(parents=True, exist_ok=True)
        (output_dir / d / "__init__.py").touch()

    # requirements.txt
    (output_dir / "requirements.txt").write_text(
        "fastapi>=0.115.0\n"
        "uvicorn[standard]>=0.32.0\n"
        "sqlalchemy>=2.0.0\n"
        "asyncpg>=0.30.0\n"
        "alembic>=1.14.0\n"
        "pydantic[email]>=2.10.0\n"
        "pydantic-settings>=2.7.0\n"
        "python-jose[cryptography]>=3.3.0\n"
        "passlib[bcrypt]>=1.7.4\n"
        "httpx>=0.28.0\n"
    )

    (output_dir / "requirements-dev.txt").write_text(
        "-r requirements.txt\n"
        "pytest>=8.0.0\n"
        "pytest-asyncio>=0.24.0\n"
        "pytest-cov>=6.0.0\n"
        "httpx>=0.28.0\n"
        "ruff>=0.9.0\n"
    )

    # pyproject.toml
    pkg = name.replace("-", "_")
    (output_dir / "pyproject.toml").write_text(f"""[project]
name = "{name}"
version = "0.1.0"
description = ""
requires-python = ">=3.12"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP"]
""")

    # main.py
    (output_dir / "src" / "main.py").write_text(f"""from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown


app = FastAPI(
    title="{name}",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {{"status": "ok"}}
""")

    # alembic.ini simplificado
    (output_dir / "alembic.ini").write_text(f"""[alembic]
script_location = alembic
sqlalchemy.url = postgresql+asyncpg://user:pass@localhost/{pkg}
""")

    # Cria venv
    console.print("  [dim]→ Criando ambiente virtual...[/dim]")
    venv_ok = _run([python, "-m", "venv", ".venv"], cwd=output_dir)

    if venv_ok:
        venv_pip = str(output_dir / ".venv" / "bin" / "pip")
        console.print("  [dim]→ Instalando dependências...[/dim]")
        _run([venv_pip, "install", "-q", "-r", "requirements.txt"], cwd=output_dir)
        _run([venv_pip, "install", "-q", "-r", "requirements-dev.txt"], cwd=output_dir)

    return True


def scaffold_dotnet(name: str, output_dir: Path) -> bool:
    """dotnet new webapi com minimal API"""
    console.print("\n[cyan]📦 Scaffolding .NET 8...[/cyan]")

    if not _require("dotnet", "https://dot.net/download"):
        return False

    # Verifica versão
    try:
        r = subprocess.run(["dotnet", "--version"], capture_output=True, text=True)
        console.print(f"  ✓ .NET {r.stdout.strip()}")
    except Exception:
        pass

    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)

    # Cria solução + projetos em Clean Architecture
    ok = _run(["dotnet", "new", "sln", "-n", name], cwd=parent)
    if not ok:
        return False

    sln_dir = parent / name
    sln_dir.mkdir(exist_ok=True)

    layers = {
        f"{name}.Api":            "webapi",
        f"{name}.Application":    "classlib",
        f"{name}.Domain":         "classlib",
        f"{name}.Infrastructure": "classlib",
    }

    for proj_name, template in layers.items():
        proj_dir = sln_dir / proj_name
        _run(["dotnet", "new", template, "-n", proj_name, "-o", str(proj_dir),
              "--no-restore"], cwd=sln_dir)
        _run(["dotnet", "sln", f"{name}.sln", "add", str(proj_dir / f"{proj_name}.csproj")],
             cwd=parent)

    # Referências entre projetos
    refs = [
        (f"{name}.Api",            f"{name}.Application"),
        (f"{name}.Application",    f"{name}.Domain"),
        (f"{name}.Infrastructure", f"{name}.Domain"),
        (f"{name}.Api",            f"{name}.Infrastructure"),
    ]
    for src, dep in refs:
        src_csproj = sln_dir / src / f"{src}.csproj"
        dep_csproj = sln_dir / dep / f"{dep}.csproj"
        _run(["dotnet", "add", str(src_csproj), "reference", str(dep_csproj)], cwd=sln_dir)

    # Pacotes essenciais na API
    api_csproj = str(sln_dir / f"{name}.Api" / f"{name}.Api.csproj")
    packages = [
        "Microsoft.EntityFrameworkCore.Design",
        "Npgsql.EntityFrameworkCore.PostgreSQL",
        "Swashbuckle.AspNetCore",
    ]
    for pkg in packages:
        _run(["dotnet", "add", api_csproj, "package", pkg, "--no-restore"], cwd=sln_dir)

    _run(["dotnet", "restore"], cwd=sln_dir)

    # Move para output_dir esperado
    if sln_dir != output_dir:
        shutil.copytree(str(sln_dir), str(output_dir), dirs_exist_ok=True)

    return True


# ─── Dispatcher ───────────────────────────────────────────────────────────────

SCAFFOLD_FN = {
    "nestjs":      scaffold_nestjs,
    "nextjs":      scaffold_nextjs,
    "angular":     scaffold_angular,
    "spring-boot": scaffold_spring_boot,
    "python":      scaffold_python,
    "dotnet":      scaffold_dotnet,
}


def scaffold_project(stack: str, name: str, output_dir: Path, description: str = "") -> bool:
    """
    Roda o scaffolding real da stack.
    Retorna True se bem-sucedido.
    """
    fn = SCAFFOLD_FN.get(stack.lower())
    if not fn:
        console.print(f"[yellow]⚠ Sem scaffolding automático para '{stack}'.[/yellow]")
        return False

    # Verifica se o diretório já existe
    if output_dir.exists():
        console.print(f"[yellow]⚠ Diretório já existe: {output_dir}[/yellow]")
        if not Confirm.ask("Continuar mesmo assim (pode sobrescrever arquivos)?", default=False):
            return False

    if stack == "spring-boot":
        ok = fn(name, output_dir, description)
    else:
        ok = fn(name, output_dir)

    if ok:
        console.print(f"\n[green]✓ Scaffold concluído em {output_dir}[/green]")
    else:
        console.print(f"\n[yellow]⚠ Scaffold falhou. O agente irá gerar os arquivos manualmente.[/yellow]")

    return ok
