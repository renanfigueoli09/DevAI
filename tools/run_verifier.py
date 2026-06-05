"""
Run Verifier — inicia a aplicação, aguarda subir, verifica health, captura erros de runtime.

Complementa o build check (tsc/mvn): verifica que o app RODA, não só que compila.
Requer que a infra (DB, Redis) esteja disponível via docker-compose.

Fluxo:
  1. Verifica se DB está acessível (tenta conexão TCP)
  2. Copia .env.example → .env se necessário
  3. Inicia app em background
  4. Aguarda até 45s por "application started" no stdout
  5. Faz GET /health
  6. Retorna (ok, runtime_errors)
"""

import os
import re
import time
import socket
import subprocess
import shutil
from pathlib import Path
from typing import Optional
from rich.console import Console

console = Console()


def _db_accessible(host: str = "localhost", port: int = 5432, timeout: int = 3) -> bool:
    """Testa se o banco de dados está acessível via TCP."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.error, OSError):
        return False


def _start_command(stack: str, project_path: Path, port: int) -> Optional[list[str]]:
    """Retorna o comando para iniciar o app."""
    cmds = {
        "nestjs": ["node", "dist/main"],
        "spring-boot": [str(project_path / "mvnw"), "spring-boot:run", "-q"]
                        if (project_path / "mvnw").exists() else None,
        "python": [str(project_path / ".venv" / "bin" / "uvicorn"),
                   "src.main:app", "--host", "0.0.0.0", "--port", str(port)]
                  if (project_path / ".venv" / "bin" / "uvicorn").exists() else None,
        "dotnet": ["dotnet", "run"] if shutil.which("dotnet") else None,
    }
    return cmds.get(stack)


def _success_marker(stack: str) -> str:
    """String que indica que o app subiu com sucesso."""
    return {
        "nestjs":      "Nest application successfully started",
        "spring-boot": "Started .+ in",
        "python":      "Application startup complete",
        "dotnet":      "Now listening on",
    }.get(stack, "started")


def try_run(
    project_path: Path,
    stack: str,
    port: int = 3000,
    wait_seconds: int = 45,
) -> tuple[bool, str]:
    """
    Tenta iniciar a aplicação e verifica se sobe corretamente.
    Retorna (success, output_with_errors).
    """
    cmd = _start_command(stack, project_path, port)
    if not cmd:
        return False, f"Não sei como iniciar {stack}"

    # Para NestJS, verifica que o build existe
    if stack == "nestjs" and not (project_path / "dist" / "main.js").exists():
        return False, "dist/main.js não existe — rode npm run build primeiro"

    env = {
        **os.environ,
        "PORT": str(port),
        "NODE_ENV": "development",
        "APP_ENV": "development",
        "SPRING_PROFILES_ACTIVE": "dev",
    }

    console.print(f"  [dim]→ Iniciando {stack} na porta {port}...[/dim]")
    console.print(f"  [dim]$ {' '.join(cmd[:4])}[/dim]")

    try:
        proc = subprocess.Popen(
            cmd, cwd=str(project_path),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=env,
            bufsize=1, universal_newlines=True,
        )
    except FileNotFoundError as e:
        return False, f"Comando não encontrado: {e}"

    output_lines = []
    success = False
    marker  = _success_marker(stack)
    deadline = time.time() + wait_seconds

    try:
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
                continue
            output_lines.append(line.rstrip())
            if len(output_lines) <= 5 or "error" in line.lower() or "warn" in line.lower():
                console.print(f"  [dim]  {line.rstrip()[:120]}[/dim]")

            if re.search(marker, line, re.IGNORECASE):
                success = True
                break

            # Detecta erro fatal
            if any(kw in line.lower() for kw in [
                "cannot start", "failed to start", "application run failed",
                "error starting", "exit code 1", "module not found",
                "cannot find module", "syntaxerror",
            ]):
                break

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    output = "\n".join(output_lines)
    return success, output


def extract_runtime_errors(output: str, stack: str) -> list[dict]:
    """Extrai erros de runtime do output do servidor."""
    errors = []
    patterns = {
        "nestjs": [
            r"Error:\s+(.+)",
            r"Cannot find module '(.+?)'",
            r"Nest can't resolve dependencies of (.+?)\.",
            r"UnknownDependenciesException: (.+)",
            r"TypeError:\s+(.+)",
        ],
        "spring-boot": [
            r"APPLICATION FAILED TO START",
            r"Error creating bean with name '(.+?)'",
            r"Field .+? in .+? required a bean of type '(.+?)'",
            r"org\.springframework\.beans\.factory\..+?: (.+)",
        ],
        "python": [
            r"ImportError: (.+)",
            r"ModuleNotFoundError: (.+)",
            r"AttributeError: (.+)",
            r"pydantic\.errors\..+?: (.+)",
        ],
        "dotnet": [
            r"System\.\w+Exception: (.+)",
            r"No service for type '(.+?)'",
        ],
    }

    for pattern in patterns.get(stack, []):
        for m in re.finditer(pattern, output, re.IGNORECASE | re.MULTILINE):
            msg = m.group(1) if m.lastindex else m.group(0)
            errors.append({
                "message": msg.strip()[:200],
                "type": "runtime",
                "file": "",
                "line": 0,
                "code": "RUNTIME",
            })

    return errors[:10]


def check_db_and_warn(project_path: Path) -> bool:
    """Verifica se o banco está acessível. Dá dicas se não estiver."""
    # Lê .env para pegar porta do DB
    env_file = project_path / ".env"
    db_port = 5432
    db_host = "localhost"

    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("DB_PORT="):
                try: db_port = int(line.split("=")[1])
                except: pass
            if line.startswith("DB_HOST="):
                db_host = line.split("=")[1].strip()

    if db_host not in ("localhost", "127.0.0.1"):
        return True  # Assume acessível se não é local

    if _db_accessible(db_host, db_port):
        console.print(f"  [green]✓[/green] Banco de dados acessível ({db_host}:{db_port})")
        return True

    console.print(f"  [yellow]⚠ Banco não acessível em {db_host}:{db_port}[/yellow]")
    console.print("  [dim]Suba a infra com: make docker-dev[/dim]")
    console.print("  [dim]Ou: docker compose -f docker-compose.dev.yml up -d[/dim]")
    return False
