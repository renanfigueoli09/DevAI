"""
Dependency Fixer — detecta e instala pacotes faltantes automaticamente.

Fluxo:
  1. Escaneia imports nos arquivos gerados
  2. Detecta quais não estão em package.json / requirements.txt / pom.xml
  3. Instala os faltantes via npm / pip / mvn
  4. Atualiza os arquivos de dependência
  5. Também parseia erros de compilação para extrair pacotes faltantes

Cobre NestJS, Next.js, Angular, Python, Spring Boot, .NET.
"""

import re
import json
import subprocess
import shutil
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table

console = Console()

# ─── Mapa de imports → pacotes npm ────────────────────────────────────────────

NPM_IMPORT_MAP: dict[str, list[str]] = {
    # NestJS core
    "@nestjs/swagger":               ["@nestjs/swagger"],
    "@nestjs/jwt":                   ["@nestjs/jwt"],
    "@nestjs/passport":              ["@nestjs/passport", "passport"],
    "@nestjs/config":                ["@nestjs/config"],
    "@nestjs/typeorm":               ["@nestjs/typeorm", "typeorm"],
    "@nestjs/mongoose":              ["@nestjs/mongoose", "mongoose"],
    "@nestjs/cache-manager":         ["@nestjs/cache-manager", "cache-manager"],
    "@nestjs/schedule":              ["@nestjs/schedule"],
    "@nestjs/event-emitter":         ["@nestjs/event-emitter"],
    "@nestjs/serve-static":          ["@nestjs/serve-static"],
    "@nestjs/websockets":            ["@nestjs/websockets"],
    "@nestjs/platform-socket.io":    ["@nestjs/platform-socket.io", "socket.io"],
    "@nestjs/microservices":         ["@nestjs/microservices"],
    "@nestjs/throttler":             ["@nestjs/throttler"],
    "@nestjs/terminus":              ["@nestjs/terminus"],
    "@nestjs/bull":                  ["@nestjs/bull", "bull"],
    "@nestjs/bullmq":                ["@nestjs/bullmq", "bullmq"],
    "@nestjs/axios":                 ["@nestjs/axios", "axios"],
    "@nestjs/mapped-types":          ["@nestjs/mapped-types"],
    # Passport strategies
    "passport-jwt":                  ["passport-jwt", "@types/passport-jwt"],
    "passport-local":                ["passport-local", "@types/passport-local"],
    "passport-google-oauth20":       ["passport-google-oauth20", "@types/passport-google-oauth20"],
    "passport":                      ["passport", "@types/passport"],
    # Validation
    "class-validator":               ["class-validator"],
    "class-transformer":             ["class-transformer"],
    "joi":                           ["joi"],
    "zod":                           ["zod"],
    # ORM / DB
    "typeorm":                       ["typeorm"],
    "prisma":                        ["prisma"],
    "@prisma/client":                ["@prisma/client"],
    "mongoose":                      ["mongoose"],
    "sequelize":                     ["sequelize"],
    "pg":                            ["pg", "@types/pg"],
    "mysql2":                        ["mysql2"],
    # Auth / Crypto
    "bcrypt":                        ["bcrypt", "@types/bcrypt"],
    "bcryptjs":                      ["bcryptjs", "@types/bcryptjs"],
    "jsonwebtoken":                  ["jsonwebtoken", "@types/jsonwebtoken"],
    "crypto-js":                     ["crypto-js", "@types/crypto-js"],
    # HTTP
    "axios":                         ["axios"],
    "node-fetch":                    ["node-fetch"],
    "got":                           ["got"],
    # Cache / Queue
    "ioredis":                       ["ioredis"],
    "redis":                         ["redis"],
    "bull":                          ["bull", "@types/bull"],
    "bullmq":                        ["bullmq"],
    "amqplib":                       ["amqplib", "@types/amqplib"],
    # Email / Files / Utils
    "nodemailer":                    ["nodemailer", "@types/nodemailer"],
    "multer":                        ["multer", "@types/multer"],
    "sharp":                         ["sharp"],
    "uuid":                          ["uuid", "@types/uuid"],
    "slugify":                       ["slugify"],
    "dayjs":                         ["dayjs"],
    "date-fns":                      ["date-fns"],
    "lodash":                        ["lodash", "@types/lodash"],
    "helmet":                        ["helmet"],
    "compression":                   ["compression", "@types/compression"],
    "cookie-parser":                 ["cookie-parser", "@types/cookie-parser"],
    "express":                       ["express", "@types/express"],
    "morgan":                        ["morgan", "@types/morgan"],
    # Docs / Reports
    "swagger-ui-express":            ["swagger-ui-express"],
    "exceljs":                       ["exceljs"],
    "pdfkit":                        ["pdfkit", "@types/pdfkit"],
    "pdfmake":                       ["pdfmake"],
    "handlebars":                    ["handlebars"],
    # Payments / Cloud
    "stripe":                        ["stripe"],
    "aws-sdk":                       ["aws-sdk"],
    "@aws-sdk/client-s3":            ["@aws-sdk/client-s3"],
    "@aws-sdk/lib-storage":          ["@aws-sdk/lib-storage"],
    # Next.js / React
    "next-auth":                     ["next-auth"],
    "zustand":                       ["zustand"],
    "@tanstack/react-query":         ["@tanstack/react-query"],
    "react-hook-form":               ["react-hook-form"],
    "@hookform/resolvers":           ["@hookform/resolvers"],
    "tailwind-merge":                ["tailwind-merge"],
    "clsx":                          ["clsx"],
    "framer-motion":                 ["framer-motion"],
    "lucide-react":                  ["lucide-react"],
    # Angular extras
    "@ngrx/store":                   ["@ngrx/store"],
    "@ngrx/effects":                 ["@ngrx/effects"],
    "@ngrx/signals":                 ["@ngrx/signals"],
    # built-ins — nunca instalar
    "path":      [], "fs":       [], "os":       [], "crypto":   [],
    "http":      [], "https":    [], "events":   [], "stream":   [],
    "buffer":    [], "util":     [], "url":      [], "net":      [],
    "child_process": [],
}

# ─── Mapa de imports Python → pacotes pip ─────────────────────────────────────

PIP_IMPORT_MAP: dict[str, str] = {
    "jose":          "python-jose[cryptography]",
    "passlib":       "passlib[bcrypt]",
    "jwt":           "PyJWT",
    "redis":         "redis",
    "celery":        "celery[redis]",
    "boto3":         "boto3",
    "stripe":        "stripe",
    "pillow":        "Pillow",
    "PIL":           "Pillow",
    "aiofiles":      "aiofiles",
    "httpx":         "httpx",
    "anyio":         "anyio",
    "tenacity":      "tenacity",
    "sendgrid":      "sendgrid",
    "jinja2":        "jinja2",
    "Jinja2":        "Jinja2",
    "openpyxl":      "openpyxl",
    "reportlab":     "reportlab",
    "python_multipart": "python-multipart",
    "multipart":     "python-multipart",
    "dotenv":        "python-dotenv",
    "decouple":      "python-decouple",
    "loguru":        "loguru",
    "structlog":     "structlog",
    "aiosmtplib":    "aiosmtplib",
    "emails":        "emails",
    "beanie":        "beanie",
    "motor":         "motor",
    "tortoise":      "tortoise-orm",
    "aiocache":      "aiocache",
}

# ─── Scanner de imports ────────────────────────────────────────────────────────

def scan_imports_ts(file_content: str) -> set[str]:
    """Extrai módulos importados de código TypeScript/JavaScript."""
    imports = set()
    patterns = [
        r"from\s+['\"](@?[\w/.-]+)['\"]",
        r"require\s*\(\s*['\"](@?[\w/.-]+)['\"]\s*\)",
        r"import\s+['\"](@?[\w/.-]+)['\"]",
    ]
    for pat in patterns:
        for m in re.finditer(pat, file_content):
            mod = m.group(1)
            # Normaliza: pega só o escopo+pacote (não o sub-path)
            # Ex: @nestjs/common/decorators → @nestjs/common
            if mod.startswith("@"):
                parts = mod.split("/")
                imports.add("/".join(parts[:2]))
            else:
                imports.add(mod.split("/")[0])
    return imports


def scan_imports_python(file_content: str) -> set[str]:
    """Extrai módulos importados de código Python."""
    imports = set()
    patterns = [
        r"^from\s+([\w]+)",
        r"^import\s+([\w]+)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, file_content, re.MULTILINE):
            imports.add(m.group(1))
    return imports


def _get_installed_npm(project_path: Path) -> set[str]:
    """Retorna pacotes já declarados em package.json."""
    pkg = project_path / "package.json"
    if not pkg.exists():
        return set()
    try:
        data = json.loads(pkg.read_text())
        return set(data.get("dependencies", {}).keys()) | set(data.get("devDependencies", {}).keys())
    except Exception:
        return set()


def _get_installed_pip(project_path: Path) -> set[str]:
    """Retorna pacotes já declarados em requirements.txt."""
    req = project_path / "requirements.txt"
    if not req.exists():
        return set()
    pkgs = set()
    for line in req.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            name = re.split(r"[>=<!=\[;]", line)[0].strip().lower()
            pkgs.add(name)
    return pkgs


# ─── Extrai pacotes faltantes de erros de compilação ─────────────────────────

def extract_missing_from_errors(errors, stack: str) -> set[str]:
    """
    Parseia erros de compilação e extrai nomes de módulos/pacotes faltantes.
    """
    missing = set()
    for err in errors:
        msg = err.message

        # TypeScript: TS2307 - Cannot find module 'X' or its corresponding type declarations
        m = re.search(r"TS2307.*Cannot find module '(.+?)'", msg)
        if m:
            missing.add(m.group(1).strip("'\""))
            continue

        # TypeScript: TS7016 - Could not find a declaration file for module 'X'
        m = re.search(r"TS7016.*module '(.+?)'", msg)
        if m:
            missing.add(m.group(1).strip("'\""))
            continue

        # Python: ModuleNotFoundError: No module named 'X'
        m = re.search(r"No module named '(.+?)'", msg)
        if m:
            missing.add(m.group(1).split(".")[0])
            continue

        # Python: ImportError: cannot import name 'X' from 'Y'
        m = re.search(r"cannot import name '.+?' from '(.+?)'", msg)
        if m:
            missing.add(m.group(1).split(".")[0])
            continue

        # Maven: package X does not exist
        m = re.search(r"package (.+?) does not exist", msg)
        if m:
            missing.add(m.group(1))
            continue

        # .NET: CS0246 - The type or namespace name 'X' could not be found
        m = re.search(r"CS0246.*The type or namespace name '(.+?)'", msg)
        if m:
            missing.add(m.group(1))

    return missing


# ─── Instaladores ─────────────────────────────────────────────────────────────

def _run_install(cmd: list[str], cwd: Path, label: str) -> tuple[bool, str]:
    console.print(f"  [dim]$ {' '.join(cmd)}[/dim]")
    try:
        r = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=300,
            env={**__import__("os").environ, "CI": "false"},
        )
        out = (r.stdout + r.stderr)[:2000]
        ok  = r.returncode == 0
        if ok:
            console.print(f"  [green]✓ {label}[/green]")
        else:
            console.print(f"  [yellow]⚠ {label}: {out[:200]}[/yellow]")
        return ok, out
    except subprocess.TimeoutExpired:
        console.print(f"  [red]✗ Timeout ao instalar {label}[/red]")
        return False, "timeout"
    except FileNotFoundError as e:
        console.print(f"  [red]✗ {e}[/red]")
        return False, str(e)


def fix_npm_deps(missing_modules: set[str], project_path: Path) -> list[str]:
    """Instala pacotes npm faltantes. Retorna lista de pacotes instalados."""
    if not shutil.which("npm"):
        console.print("  [yellow]npm não encontrado — não é possível instalar dependências[/yellow]")
        return []

    installed_in_pkg = _get_installed_npm(project_path)
    to_install = []
    to_install_dev = []

    for mod in missing_modules:
        pkgs = NPM_IMPORT_MAP.get(mod)
        if pkgs is None:
            # Módulo desconhecido — tenta instalar direto
            if mod not in installed_in_pkg and not mod.startswith("."):
                to_install.append(mod)
        elif pkgs:  # lista não vazia
            for pkg in pkgs:
                clean = pkg.lstrip("@").split("/")[0] if not pkg.startswith("@") else pkg
                if pkg not in installed_in_pkg:
                    if "@types/" in pkg:
                        to_install_dev.append(pkg)
                    else:
                        to_install.append(pkg)

    installed = []
    if to_install:
        ok, _ = _run_install(
            ["npm", "install", "--save", "--prefer-offline"] + to_install,
            project_path, f"npm install {' '.join(to_install[:3])}{'...' if len(to_install)>3 else ''}",
        )
        if ok:
            installed.extend(to_install)

    if to_install_dev:
        ok, _ = _run_install(
            ["npm", "install", "--save-dev", "--prefer-offline"] + to_install_dev,
            project_path, f"npm install -D {' '.join(to_install_dev[:3])}",
        )
        if ok:
            installed.extend(to_install_dev)

    return installed


def fix_pip_deps(missing_modules: set[str], project_path: Path) -> list[str]:
    """Instala pacotes pip faltantes."""
    venv_pip = project_path / ".venv" / "bin" / "pip"
    pip = str(venv_pip) if venv_pip.exists() else shutil.which("pip3") or shutil.which("pip")
    if not pip:
        console.print("  [yellow]pip não encontrado[/yellow]")
        return []

    installed_req = _get_installed_pip(project_path)
    to_install = []

    for mod in missing_modules:
        pkg = PIP_IMPORT_MAP.get(mod, mod)
        pkg_name = re.split(r"[>=<\[;]", pkg)[0].lower()
        if pkg_name not in installed_req:
            to_install.append(pkg)

    if not to_install:
        return []

    installed = []
    for pkg in to_install:
        ok, out = _run_install([pip, "install", "-q", pkg], project_path, f"pip install {pkg}")
        if ok:
            installed.append(pkg)
            # Adiciona ao requirements.txt
            req_file = project_path / "requirements.txt"
            if req_file.exists():
                content = req_file.read_text()
                pkg_name = re.split(r"[\[;]", pkg)[0]
                if pkg_name.lower() not in content.lower():
                    req_file.write_text(content.rstrip() + f"\n{pkg}\n")

    return installed


def fix_maven_deps(missing_modules: set[str], project_path: Path) -> list[str]:
    """Adiciona dependências ao pom.xml e roda mvn install."""
    # Maven é muito complexo para fazer dinamicamente
    # Verifica se é uma dependência conhecida do Spring Boot e informa
    SPRING_DEPS: dict[str, str] = {
        "springdoc": "org.springdoc:springdoc-openapi-starter-webmvc-ui:2.3.0",
        "mapstruct": "org.mapstruct:mapstruct:1.5.5.Final",
        "lombok":    "org.projectlombok:lombok",
        "jjwt":      "io.jsonwebtoken:jjwt-api:0.12.3",
        "validation":"jakarta.validation:jakarta.validation-api",
    }
    hints = []
    for mod in missing_modules:
        for key, dep in SPRING_DEPS.items():
            if key in mod.lower():
                hints.append(dep)

    if hints:
        console.print("  [yellow]Adicione ao pom.xml:[/yellow]")
        for h in hints:
            parts = h.split(":")
            console.print(
                f"  [dim]<dependency>\n"
                f"    <groupId>{parts[0]}</groupId>\n"
                f"    <artifactId>{parts[1]}</artifactId>\n"
                f"    {('<version>' + parts[2] + '</version>') if len(parts) > 2 else ''}\n"
                f"  </dependency>[/dim]"
            )
    return []


# ─── Ponto de entrada principal ───────────────────────────────────────────────

def fix_dependencies(
    validation_result,
    project_path: Path,
    stack: str,
    generated_files: list[dict] = None,
) -> tuple[list[str], set[str]]:
    """
    Detecta e instala dependências faltantes.

    Estratégia dupla:
      A) Parseia erros de compilação (TS2307, ModuleNotFoundError, etc.)
      B) Escaneia imports dos arquivos gerados vs. package.json/requirements.txt

    Retorna (pacotes_instalados, módulos_faltantes_não_instalados).
    """
    # Coleta módulos faltantes de múltiplas fontes
    missing_from_errors = extract_missing_from_errors(
        validation_result.errors + [e for e in validation_result.errors],
        stack,
    )

    missing_from_scan: set[str] = set()
    if generated_files:
        if stack in ("nestjs", "nextjs", "angular"):
            installed = _get_installed_npm(project_path)
            for f in generated_files:
                content = f.get("content", "")
                ext = Path(f.get("path", "")).suffix
                if ext in (".ts", ".tsx", ".js", ".jsx"):
                    for imp in scan_imports_ts(content):
                        pkgs = NPM_IMPORT_MAP.get(imp)
                        if pkgs is None:
                            # Desconhecido
                            if imp not in installed and not imp.startswith("."):
                                missing_from_scan.add(imp)
                        elif pkgs and not any(p in installed for p in pkgs):
                            missing_from_scan.add(imp)

        elif stack == "python":
            installed = _get_installed_pip(project_path)
            for f in generated_files:
                content = f.get("content", "")
                if f.get("path", "").endswith(".py"):
                    for imp in scan_imports_python(content):
                        if imp in PIP_IMPORT_MAP and PIP_IMPORT_MAP[imp].split("[")[0].lower() not in installed:
                            missing_from_scan.add(imp)

    all_missing = missing_from_errors | missing_from_scan

    if not all_missing:
        return [], set()

    console.print(f"\n  [cyan]📦 Dependências faltantes detectadas: {', '.join(sorted(all_missing)[:8])}[/cyan]")

    installed: list[str] = []
    not_installed: set[str] = set()

    if stack in ("nestjs", "nextjs", "angular"):
        installed = fix_npm_deps(all_missing, project_path)
        not_installed = all_missing - {
            m for m in all_missing
            if any(p in (NPM_IMPORT_MAP.get(m) or [m]) for p in installed)
        }

    elif stack == "python":
        installed = fix_pip_deps(all_missing, project_path)
        not_installed = all_missing - set(installed)

    elif stack == "spring-boot":
        fix_maven_deps(all_missing, project_path)
        not_installed = all_missing  # Maven requer intervenção manual

    return installed, not_installed


def print_dep_report(installed: list[str], not_installed: set[str]):
    """Exibe relatório de dependências."""
    if installed:
        console.print(f"  [green]✓ {len(installed)} pacote(s) instalado(s): {', '.join(installed[:5])}[/green]")
    if not_installed:
        console.print(f"  [yellow]⚠ {len(not_installed)} não instalado(s): {', '.join(sorted(not_installed)[:5])}[/yellow]")
