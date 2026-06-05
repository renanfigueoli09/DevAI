"""
Setup Runner — prepara e verifica o projeto após geração.

Etapas:
  1. setup_env()        → cria .env a partir de .env.example com defaults funcionais
  2. install_deps()     → npm install / pip install / mvn resolve / dotnet restore
  3. health_check()     → inicia o app em background e testa /health
  4. delivery_report()  → relatório final completo
"""

import os
import re
import time
import shutil
import secrets
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule

console = Console()


@dataclass
class SetupResult:
    env_ready:    bool = False
    deps_ok:      bool = False
    health_ok:    bool = False
    health_url:   str  = ""
    validation_passed: bool = False
    errors_fixed: int  = 0
    errors_remain: int = 0
    warnings:     int  = 0
    files_written: int = 0
    stack:         str = ""
    project_name:  str = ""
    messages:      list = field(default_factory=list)

    def add(self, msg: str):
        self.messages.append(msg)


# ─── 1. Setup de Ambiente ──────────────────────────────────────────────────────

def setup_env(project_path: Path, stack: str, name: str) -> bool:
    """
    Garante que .env existe com valores funcionais para desenvolvimento.
    Nunca sobrescreve .env existente.
    """
    env_file = project_path / ".env"
    if env_file.exists():
        console.print("  [dim]✓ .env já existe[/dim]")
        return True

    # Lê .env.example se existir
    example = project_path / ".env.example"
    if example.exists():
        content = example.read_text()
    else:
        content = ""

    # Preenche valores padrão por stack
    db_name = name.replace("-", "_").lower()
    jwt_secret = secrets.token_urlsafe(32)

    defaults = {
        # DB
        "DB_HOST":     "localhost",
        "DB_PORT":     "5432",
        "DB_NAME":     db_name,
        "DB_USER":     "postgres",
        "DB_PASS":     "postgres",
        "DB_PASSWORD": "postgres",
        # Auth
        "JWT_SECRET":       jwt_secret,
        "JWT_EXPIRES_IN":   "7d",
        "NEXTAUTH_SECRET":  jwt_secret,
        "SECRET_KEY":       jwt_secret,
        # App
        "NODE_ENV":                "development",
        "APP_ENV":                 "development",
        "SPRING_PROFILES_ACTIVE":  "dev",
        "ASPNETCORE_ENVIRONMENT":  "Development",
        # DB URLs completas
        "DATABASE_URL":            f"postgresql+asyncpg://postgres:postgres@localhost:5432/{db_name}",
        "SPRING_DATASOURCE_URL":   f"jdbc:postgresql://localhost:5432/{db_name}",
        "ConnectionStrings__Default": f"Host=localhost;Port=5432;Database={db_name};Username=postgres;Password=postgres",
    }

    # Se não há .env.example, cria do zero
    if not content:
        lines = [f"# {name} — gerado pelo DevAI", ""]
        for k, v in defaults.items():
            lines.append(f"{k}={v}")
        content = "\n".join(lines)
    else:
        # Substitui placeholders no .env.example
        new_lines = []
        for line in content.splitlines():
            if "=" in line and not line.startswith("#"):
                key, _, val = line.partition("=")
                key = key.strip()
                # Substitui se o valor está em branco ou é um placeholder
                if not val.strip() or val.strip() in ("change-me", "change_me", "your-secret", "secret", ""):
                    if key in defaults:
                        line = f"{key}={defaults[key]}"
            new_lines.append(line)
        content = "\n".join(new_lines)

    env_file.write_text(content)
    console.print(f"  [green]✓ .env criado[/green] com valores padrão de desenvolvimento")
    return True


# ─── 2. Instalação de Dependências ────────────────────────────────────────────

def install_deps(project_path: Path, stack: str) -> tuple[bool, str]:
    """
    Instala dependências do projeto.
    Retorna (success, message).
    """
    def run(cmd, timeout=300):
        console.print(f"  [dim]$ {' '.join(cmd)}[/dim]")
        try:
            r = subprocess.run(cmd, cwd=str(project_path),
                               capture_output=True, text=True, timeout=timeout)
            return r.returncode == 0, (r.stdout + r.stderr)[:3000]
        except subprocess.TimeoutExpired:
            return False, f"Timeout ({timeout}s)"
        except FileNotFoundError as e:
            return False, f"Não encontrado: {e}"

    if stack in ("nestjs", "nextjs", "angular"):
        if (project_path / "node_modules").exists():
            console.print("  [dim]✓ node_modules já existe[/dim]")
            return True, "already installed"
        if not shutil.which("npm"):
            return False, "npm não encontrado"
        ok, out = run(["npm", "install", "--prefer-offline", "--no-audit"])
        return ok, out

    elif stack == "spring-boot":
        mvnw = project_path / "mvnw"
        if mvnw.exists():
            ok, out = run([str(mvnw), "dependency:resolve", "-q"], timeout=300)
        elif shutil.which("mvn"):
            ok, out = run(["mvn", "dependency:resolve", "-q"], timeout=300)
        else:
            return True, "Maven não encontrado — pulando"
        return ok, out

    elif stack == "python":
        python = shutil.which("python3") or shutil.which("python")
        if not python:
            return False, "Python não encontrado"

        venv = project_path / ".venv"
        if not venv.exists():
            ok, out = run([python, "-m", "venv", ".venv"])
            if not ok:
                return False, out

        pip = str(venv / "bin" / "pip")
        req_files = ["requirements.txt", "requirements-dev.txt"]
        for req in req_files:
            if (project_path / req).exists():
                ok, out = run([pip, "install", "-q", "-r", req], timeout=300)
                if not ok:
                    return False, out
        return True, "ok"

    elif stack == "dotnet":
        if not shutil.which("dotnet"):
            return True, "dotnet não encontrado — pulando"
        ok, out = run(["dotnet", "restore", "--verbosity", "minimal"], timeout=300)
        return ok, out

    return True, "sem gerenciador de dependências configurado"


# ─── 3. Health Check ─────────────────────────────────────────────────────────

def health_check(project_path: Path, stack: str, port: int) -> tuple[bool, str]:
    """
    Inicia o app em background e testa o endpoint /health.
    Retorna (ok, url_or_error).
    """
    import requests

    start_cmd = _start_command(project_path, stack, port)
    if not start_cmd:
        return False, "Não foi possível determinar o comando de start"

    health_url = f"http://localhost:{port}/health"
    console.print(f"  [dim]→ Iniciando {stack} em modo teste (porta {port})...[/dim]")
    console.print(f"  [dim]$ {' '.join(start_cmd)}[/dim]")

    env = {**os.environ, "PORT": str(port), "NODE_ENV": "development",
           "APP_ENV": "development", "SPRING_PROFILES_ACTIVE": "dev"}

    try:
        proc = subprocess.Popen(
            start_cmd, cwd=str(project_path),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env=env,
        )
    except FileNotFoundError as e:
        return False, f"Comando não encontrado: {e}"

    # Aguarda até 45 segundos
    ok = False
    for i in range(45):
        time.sleep(1)
        try:
            r = requests.get(health_url, timeout=3)
            if r.status_code < 500:
                ok = True
                break
        except Exception:
            pass
        if i % 10 == 9:
            console.print(f"  [dim]... aguardando ({i+1}s)[/dim]")

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()

    if ok:
        return True, health_url
    return False, f"App não respondeu em {health_url} em 45s"


def _start_command(project_path: Path, stack: str, port: int) -> Optional[list[str]]:
    """Retorna o comando de start para health check."""
    cmds = {
        "nestjs": (
            ["node", "dist/main"] if (project_path / "dist" / "main.js").exists()
            else None
        ),
        "nextjs": (
            ["node", ".next/standalone/server.js"]
            if (project_path / ".next" / "standalone").exists()
            else None
        ),
        "spring-boot": (
            [str(project_path / "mvnw"), "spring-boot:run", "-q"]
            if (project_path / "mvnw").exists() else None
        ),
        "python": (
            [str(project_path / ".venv" / "bin" / "uvicorn"),
             "src.main:app", "--host", "0.0.0.0", "--port", str(port)]
            if (project_path / ".venv" / "bin" / "uvicorn").exists() else None
        ),
        "dotnet": (
            ["dotnet", "run", "--no-build"]
            if shutil.which("dotnet") else None
        ),
    }
    return cmds.get(stack)


# ─── 4. Relatório Final ────────────────────────────────────────────────────────

def delivery_report(
    result: SetupResult,
    project_path: Path,
    validation_result=None,
) -> bool:
    """
    Exibe relatório final e determina se o projeto pode ser "entregue".
    Retorna True se pronto para uso.
    """
    console.print(Rule("[bold]📊 Relatório de Entrega[/bold]"))

    checks = Table(border_style="dim", show_header=False, padding=(0, 1))
    checks.add_column("", width=3)
    checks.add_column("Verificação", style="cyan")
    checks.add_column("Status")

    def row(ok: bool, label: str, detail: str = ""):
        icon   = "[green]✓[/green]" if ok else "[red]✗[/red]"
        status = f"[green]{detail or 'ok'}[/green]" if ok else f"[red]{detail or 'falhou'}[/red]"
        checks.add_row(icon, label, status)

    row(result.env_ready,   ".env configurado",         "desenvolvimento")
    row(result.deps_ok,     "Dependências",              "instaladas")
    row(result.validation_passed, "Compile/Lint",
        f"{result.errors_fixed} erro(s) corrigido(s)" if result.errors_fixed else "sem erros")
    if result.errors_remain:
        row(False, "Erros não corrigidos",   f"{result.errors_remain} requerem atenção manual")
    row(result.files_written > 0, "Arquivos gerados",  str(result.files_written))

    console.print(checks)

    # Verifica se pronto
    ready = result.env_ready and result.deps_ok and result.validation_passed

    # Comandos para rodar
    hints = {
        "nestjs":      f"npm run start:dev",
        "nextjs":      f"npm run dev",
        "angular":     f"ng serve",
        "spring-boot": f"./mvnw spring-boot:run",
        "python":      f"source .venv/bin/activate && uvicorn src.main:app --reload",
        "dotnet":      f"dotnet run",
    }
    run_cmd = hints.get(result.stack, "veja o README")

    status_color = "green" if ready else "yellow"
    status_text  = "✅ PRONTO PARA USO" if ready else "⚠ REQUER ATENÇÃO MANUAL"

    msg = (
        f"[bold {status_color}]{status_text}[/bold {status_color}]\n\n"
        f"Projeto: [cyan]{result.project_name}[/cyan]\n"
        f"Stack:   [cyan]{result.stack}[/cyan]\n\n"
    )

    if not ready:
        if result.errors_remain:
            msg += f"[red]Erros pendentes: {result.errors_remain}[/red]\n"
            msg += "  Veja: [dim].devai/validation.log[/dim]\n\n"
        if not result.deps_ok:
            msg += "[yellow]Instale as dependências manualmente[/yellow]\n\n"

    msg += f"[cyan]Rodar:[/cyan]\n  cd {result.project_name} && {run_cmd}\n\n"

    if not result.health_ok:
        msg += "[dim]Nota: health check não executado (requer DB).[/dim]\n"
        msg += "[dim]Suba a infra com: make docker-dev[/dim]\n"

    msg += (
        f"\n[cyan]Próximos passos:[/cyan]\n"
        f"  devstudy                              ← indexa o projeto\n"
        f"  devfeat \"autenticação JWT\"             ← adiciona feature\n"
        f"  devfeat \"docker-compose completo\"      ← gera infra\n"
    )

    console.print(Panel(msg, border_style=status_color))
    return ready


# ─── Pipeline completo ────────────────────────────────────────────────────────

def run_post_generation_pipeline(
    project_path: Path,
    stack: str,
    name: str,
    files_written: int,
    llm=None,
    run_health: bool = False,
    port: int = 3000,
    generated_files: list = None,
) -> SetupResult:
    """
    Executa o pipeline completo pós-geração:
      env → pre-scan deps → validate → heal → report
    """
    from tools.validator   import validate, print_result
    from tools.self_healer import heal

    result = SetupResult(stack=stack, project_name=name, files_written=files_written)

    console.print(Rule("[bold]🔧 Pipeline de Verificação[/bold]"))

    # 1. Ambiente
    console.print("\n[bold]1. Configuração do ambiente[/bold]")
    result.env_ready = setup_env(project_path, stack, name)

    # 2. Dependências
    console.print("\n[bold]2. Instalação de dependências[/bold]")
    ok, msg = install_deps(project_path, stack)
    result.deps_ok = ok
    if not ok:
        console.print(f"  [yellow]⚠ {msg[:200]}[/yellow]")
    else:
        console.print(f"  [green]✓ Dependências OK[/green]")

    # 3. Pré-instalação de dependências (ANTES de qualquer compilação)
    console.print("\n[bold]3. Instalação de dependências[/bold]")

    # NestJS: instala todos os pacotes base conhecidos primeiro
    if stack == "nestjs":
        try:
            from tools.code_fixer import preinstall_nestjs_deps
            console.print("  [dim]→ Instalando pacotes NestJS base...[/dim]")
            preinstall_nestjs_deps(project_path)
            console.print("  [green]✓ Pacotes NestJS base instalados[/green]")
        except Exception as e:
            console.print(f"  [dim]⚠ {e}[/dim]")

    # Pré-scan geral de imports vs package.json
    try:
        from tools.dependency_fixer import fix_dependencies, print_dep_report
        from tools.validator import ValidationResult
        empty_result = ValidationResult(stack=stack, passed=True)
        installed, not_inst = fix_dependencies(empty_result, project_path, stack, generated_files)
        if installed:
            print_dep_report(installed, not_inst)
        else:
            console.print("  [dim]✓ Dependências verificadas[/dim]")
    except Exception as e:
        console.print(f"  [dim]⚠ Pre-scan: {e}[/dim]")

    # 4. Validação estática
    console.print("\n[bold]4. Validação estática (compile/lint)[/bold]")
    val = validate(stack, project_path)
    print_result(val)

    initial_errors = val.error_count

    # 5. Auto-correção se necessário
    if not val.passed and llm:
        console.print("\n[bold]5. Auto-correção de erros[/bold]")
        val = heal(val, project_path, llm, stack, generated_files)

    result.validation_passed = val.passed
    result.errors_fixed  = max(0, initial_errors - val.error_count)
    result.errors_remain = val.error_count
    result.warnings      = val.warning_count

    # 6. Health check (opcional — precisa de DB rodando)
    if run_health and result.deps_ok and result.validation_passed:
        console.print("\n[bold]5. Health check[/bold]")
        ok, url = health_check(project_path, stack, port)
        result.health_ok  = ok
        result.health_url = url
        status = f"[green]✓ {url}[/green]" if ok else f"[yellow]⚠ {url}[/yellow]"
        console.print(f"  {status}")
    else:
        console.print("\n[dim]6. Health check pulado (requer DB ativo)[/dim]")

    return result
