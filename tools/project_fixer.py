"""
Project Fixer — repara projetos existentes até o build passar.

Modos de uso:
  devai fix                → roda no diretório atual
  devai fix --path /proj   → roda em path específico

Pipeline por rodada:
  1. Roda o build real (npm run build / tsc / mvn compile / etc)
  2. Parseia TODOS os erros
  3. Instala pacotes faltantes (TS2307, ModuleNotFoundError)
  4. Corrige paths de import errados (busca o arquivo real no disco)
  5. Usa LLM para erros de código (type errors, syntax errors)
  6. Re-roda o build
  7. Repete até 0 erros ou MAX_ROUNDS

Nunca cria arquivos novos — só modifica o que existe.
"""

import re
import subprocess
import shutil
import json
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.rule import Rule
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

MAX_ROUNDS = 5


# ─── Build runner ─────────────────────────────────────────────────────────────

def _detect_stack(project_path: Path) -> str:
    if (project_path / "nest-cli.json").exists():       return "nestjs"
    if (project_path / "next.config.js").exists() or \
       (project_path / "next.config.ts").exists():      return "nextjs"
    if (project_path / "angular.json").exists():        return "angular"
    if (project_path / "pom.xml").exists() or \
       (project_path / "build.gradle").exists():        return "spring-boot"
    if (project_path / "requirements.txt").exists() or \
       (project_path / "pyproject.toml").exists():      return "python"
    for _ in project_path.glob("*.csproj"):             return "dotnet"
    return "unknown"


def _build_command(stack: str, project_path: Path) -> list[str]:
    """Retorna o comando de build/typecheck para a stack."""
    cmds = {
        # nest build uses tsconfig.build.json which matches what actually runs in production
        "nestjs":      ["npx", "nest", "build", "--tsc"],
        "nextjs":      ["npx", "tsc", "--noEmit", "--skipLibCheck"],
        "angular":     ["npx", "tsc", "--noEmit", "--skipLibCheck"],
        "spring-boot": ([str(project_path / "mvnw"), "compile", "-q"]
                        if (project_path / "mvnw").exists()
                        else ["mvn", "compile", "-q"]),
        "python":      [],  # handled separately
        "dotnet":      ["dotnet", "build", "--configuration", "Debug",
                        "--verbosity", "minimal"],
    }
    return cmds.get(stack, [])


def run_build(stack: str, project_path: Path) -> tuple[int, str]:
    """Executa o build e retorna (exit_code, output)."""
    cmd = _build_command(stack, project_path)
    if not cmd:
        if stack == "python":
            return _run_python_check(project_path)
        return 0, "no build command"

    try:
        r = subprocess.run(
            cmd, cwd=str(project_path),
            capture_output=True, text=True, timeout=180,
            env={**__import__("os").environ, "CI": "true", "NO_COLOR": "1"},
        )
        raw = r.stdout + r.stderr
        # Strip ANSI escape codes (nest build outputs colored text that breaks the parser)
        clean = re.sub(r"\x1b\[[0-9;]*[mKHJABCDEFGHfsSuIJ]", "", raw)
        clean = re.sub(r"\033\[[0-9;]*[mKHJABCDEFGHfsSuIJ]", "", clean)
        return r.returncode, clean[:12000]
    except subprocess.TimeoutExpired:
        return 1, "Build timeout"
    except FileNotFoundError as e:
        return 1, f"Command not found: {e}"


def _run_python_check(project_path: Path) -> tuple[int, str]:
    python = shutil.which("python3") or shutil.which("python")
    venv_py = project_path / ".venv" / "bin" / "python"
    if venv_py.exists():
        python = str(venv_py)
    if not python:
        return 0, "python not found"
    errors = []
    for f in project_path.rglob("*.py"):
        if any(p in str(f) for p in [".venv", "__pycache__", ".git"]):
            continue
        r = subprocess.run([python, "-m", "py_compile", str(f)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            errors.append(f"{f}: {r.stderr}")
    output = "\n".join(errors)
    return (1 if errors else 0), output


# ─── Error parser ─────────────────────────────────────────────────────────────

def parse_errors(output: str, stack: str) -> list[dict]:
    """
    Parseia output de build em lista de erros estruturados.
    Cada erro: {file, line, col, code, message, type}
    type: 'missing_module' | 'wrong_path' | 'code_error'
    """
    errors = []

    if stack in ("nestjs", "nextjs", "angular"):
        # Handles TWO formats:
        # 1. tsc: src/file.ts:10:28 - error TS2307: message
        # 2. nest build: src/file.ts(10,28): error TS2307: message
        patterns = [
            # tsc format: src/file.ts:10:28 - error TS2307:
            re.compile(r"([\w./\\-]+\.tsx?):(\d+):(\d+)\s*-\s*(error|warning)\s+(TS\d+):\s*(.+)"),
            # nest build format: src/file.ts(10,28): error TS2307:
            re.compile(r"([\w./\\-]+\.tsx?)\((\d+),(\d+)\):\s*(error|warning)\s+(TS\d+):\s*(.+)"),
        ]
        seen_msgs = set()
        for pattern in patterns:
            for m in pattern.finditer(output):
                filepath, line, col, sev, code, msg = m.groups()
                if sev == "warning":
                    continue
                key = (filepath.strip(), int(line), code)
                if key in seen_msgs:
                    continue
                seen_msgs.add(key)
                etype = _classify_ts_error(code, msg)
                module_name = _extract_module_name(code, msg)
                errors.append({
                    "file": filepath.strip(), "line": int(line), "col": int(col),
                    "code": code, "message": msg.strip(), "type": etype,
                    "module": module_name,
                })

    elif stack == "spring-boot":
        pattern = re.compile(r"\[ERROR\]\s+(.+?\.java):\[(\d+),(\d+)\]\s+(.+)")
        for m in pattern.finditer(output):
            filepath, line, col, msg = m.groups()
            errors.append({
                "file": filepath, "line": int(line), "col": int(col),
                "code": "JAVA", "message": msg.strip(),
                "type": "code_error", "module": None,
            })

    elif stack == "python":
        pattern = re.compile(r'File "(.+?)", line (\d+)')
        for m in pattern.finditer(output):
            filepath, line = m.groups()
            idx = m.end()
            msg = output[idx:idx+300].split("\n")[1].strip() if "\n" in output[idx:idx+50] else "syntax error"
            errors.append({
                "file": filepath, "line": int(line), "col": 0,
                "code": "PY", "message": msg,
                "type": "code_error", "module": None,
            })
        # ModuleNotFoundError
        for m in re.finditer(r"No module named '(.+?)'", output):
            errors.append({
                "file": "", "line": 0, "col": 0,
                "code": "PY_MODULE", "message": f"No module named '{m.group(1)}'",
                "type": "missing_module", "module": m.group(1).split(".")[0],
            })

    elif stack == "dotnet":
        pattern = re.compile(r"(.+?\.cs)\((\d+),(\d+)\):\s*(error|warning)\s+(CS\d+):\s*(.+)")
        for m in pattern.finditer(output):
            filepath, line, col, sev, code, msg = m.groups()
            if sev == "warning":
                continue
            errors.append({
                "file": filepath, "line": int(line), "col": int(col),
                "code": code, "message": msg.strip(),
                "type": "code_error", "module": None,
            })

    return errors


def _classify_ts_error(code: str, msg: str) -> str:
    if code in ("TS2307", "TS7016"):
        return "missing_module"
    if code == "TS2305" and ("has no exported member" in msg):
        return "wrong_path"
    if code == "TS2304" and "Cannot find name" in msg:
        return "code_error"
    if "Cannot find module" in msg:
        return "missing_module"
    return "code_error"


def _extract_module_name(code: str, msg: str) -> Optional[str]:
    m = re.search(r"Cannot find module '(.+?)'", msg)
    if m:
        return m.group(1)
    m = re.search(r"module '(.+?)' or", msg)
    if m:
        return m.group(1)
    return None


# ─── Import path fixer (deterministic, sem LLM) ──────────────────────────────

def _create_missing_module(entity: str, project_path: Path, db_type: str = "mongodb") -> bool:
    """
    Cria um module.ts mínimo para uma entidade quando o arquivo não existe.
    Chamado quando o fixer detecta TS2307 para um module que não foi gerado.
    """
    el = entity.lower()
    module_path = project_path / "src" / el / f"{el}.module.ts"
    if module_path.exists():
        return False

    module_path.parent.mkdir(parents=True, exist_ok=True)

    # Detecta se é Mongoose ou TypeORM
    is_nosql = db_type == "mongodb" or (project_path / "node_modules" / "@nestjs" / "mongoose").exists()

    if is_nosql:
        # Mongoose module
        ep = entity[0].upper() + entity[1:]
        content = f"""import {{ Module }} from '@nestjs/common';
import {{ MongooseModule }} from '@nestjs/mongoose';
import {{ {ep}, {ep}Schema }} from './{el}.schema';
import {{ {ep}Service }} from './{el}.service';
import {{ {ep}Controller }} from './{el}.controller';

@Module({{
  imports: [MongooseModule.forFeature([{{ name: {ep}.name, schema: {ep}Schema }}])],
  providers: [{ep}Service],
  controllers: [{ep}Controller],
  exports: [{ep}Service],
}})
export class {ep}Module {{}}
"""
    else:
        # TypeORM module
        ep = entity[0].upper() + entity[1:]
        content = f"""import {{ Module }} from '@nestjs/common';
import {{ TypeOrmModule }} from '@nestjs/typeorm';
import {{ {ep} }} from './{el}.entity';
import {{ {ep}Service }} from './{el}.service';
import {{ {ep}Controller }} from './{el}.controller';

@Module({{
  imports: [TypeOrmModule.forFeature([{ep}])],
  providers: [{ep}Service],
  controllers: [{ep}Controller],
  exports: [{ep}Service],
}})
export class {ep}Module {{}}
"""

    module_path.write_text(content, encoding="utf-8")
    console.print(f"  [green]✓[/green] Criado: {module_path.relative_to(project_path)}")
    return True


def fix_wrong_import_paths(project_path: Path, errors: list[dict]) -> list[str]:
    """
    Detecta imports com paths errados e os corrige buscando o arquivo real no disco.
    Trata casos especiais:
      - ../users/users.module → ../user/user.module (plural vs singular)
      - user.entity em projeto MongoDB → user.schema
    """
    fixed_files = []

    # Primeiro: re-aplica todos os fixes determinísticos
    from tools.code_fixer import apply_fixes_to_project
    n = apply_fixes_to_project(project_path)
    if n > 0:
        console.print(f"  [dim]→ {n} arquivo(s) com fixes determinísticos[/dim]")

    # Agrupa erros por arquivo (só erros de path relativo)
    # First pass: handle missing modules
    for e in errors:
        mod = e.get("module", "")
        if e.get("type") == "missing_module" and mod.startswith("."):
            # Special case: jwt.guard missing = auth not requested, just remove the import
            if "jwt.guard" in mod or "jwt-auth.guard" in mod or "auth.guard" in mod:
                # Find and remove the import from the file
                fpath = _resolve_path(e.get("file",""), project_path)
                if fpath and fpath.exists():
                    fc = fpath.read_text(encoding="utf-8", errors="ignore")
                    import re as _re
                    fc = _re.sub(r"import \{[^}]*JwtAuthGuard[^}]*\} from '[^']*';?\n?", "", fc)
                    fc = _re.sub(r"@UseGuards\(JwtAuthGuard\)\n?\s*", "", fc)
                    fpath.write_text(fc, encoding="utf-8")
                    console.print(f"  [green]✓[/green] Removido JwtAuthGuard de {fpath.name} (auth não pedida)")
                continue  # don't try to create jwt.guard file

        if e.get("type") == "missing_module" and ".module" in mod and mod.startswith("."):
            # Extract entity name from path like './book/book.module'
            parts = mod.strip("./").split("/")
            entity = parts[0] if parts else ""
            if entity:
                # Detect db type from package.json
                pkg_json = project_path / "package.json"
                db_type = "mongodb"
                if pkg_json.exists():
                    try:
                        import json as _json
                        pkg = _json.loads(pkg_json.read_text())
                        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                        if "@nestjs/typeorm" in deps:
                            db_type = "postgres"
                    except Exception:
                        pass
                _create_missing_module(entity, project_path, db_type)

    by_file: dict[str, list[dict]] = {}
    for e in errors:
        mod = e.get("module", "")
        if e.get("type") == "missing_module" and mod.startswith("."):
            by_file.setdefault(e["file"], []).append(e)

    for rel_path, errs in by_file.items():
        abs_path = _resolve_path(rel_path, project_path)
        if not abs_path or not abs_path.exists():
            continue

        text = abs_path.read_text(encoding="utf-8", errors="ignore")
        modified = False

        # Regex para capturar imports com paths relativos
        pat = re.compile(r"""from\s+(['"])(\.[\w./\-]+)""")
        for m in pat.finditer(text):
            quote       = m.group(1)
            import_path = m.group(2)
            current_dir = abs_path.parent

            # Se já resolve, ok
            candidate = (current_dir / import_path).resolve()
            if any((Path(str(candidate) + ext)).exists()
                   for ext in [".ts", "/index.ts", ""]):
                continue

            # Nome base do módulo pedido
            basename = Path(import_path).name   # ex: "users.module"
            stem     = import_path.split("/")[-1]  # última parte do path

            # Variações a tentar
            variants = [stem]
            if stem.startswith("users."):
                variants.append(stem.replace("users.", "user.", 1))
            if stem.endswith(".entity"):
                variants.append(stem.replace(".entity", ".schema"))
            if "user.entity" in stem:
                variants.append(stem.replace("user.entity", "user.schema"))

            best = None
            for variant in variants:
                found = [
                    f for f in project_path.rglob(f"{variant}.ts")
                    if not any(p in str(f) for p in ["node_modules", "dist", ".git"])
                ]
                if found:
                    best = found[0]
                    break

            if best:
                try:
                    rel = best.relative_to(abs_path.parent)
                    correct = "./" + str(rel).replace("\\", "/").replace(".ts", "")
                    if correct != import_path:
                        text = text.replace(
                            f"{quote}{import_path}{quote}",
                            f"{quote}{correct}{quote}"
                        )
                        modified = True
                        console.print(f"  [dim]  {import_path} → {correct}[/dim]")
                except ValueError:
                    pass

        if modified:
            abs_path.write_text(text, encoding="utf-8")
            fixed_files.append(str(rel_path))

    return fixed_files




# ─── Package installer ────────────────────────────────────────────────────────

def install_missing_packages(errors: list[dict], project_path: Path, stack: str) -> list[str]:
    """Instala todos os pacotes faltantes detectados nos erros."""
    missing_modules = {e["module"] for e in errors
                       if e.get("type") == "missing_module" and e.get("module")
                       and not e["module"].startswith(".")}

    if not missing_modules:
        return []

    console.print(f"\n  [cyan]📦 Módulos faltantes: {', '.join(sorted(missing_modules)[:8])}[/cyan]")

    if stack in ("nestjs", "nextjs", "angular"):
        from tools.dependency_fixer import fix_npm_deps
        from tools.validator import ValidationResult
        mock_result = ValidationResult(stack=stack, passed=False)
        # Cria erros mock para o fix_dependencies
        from tools.dependency_fixer import extract_missing_from_errors
        from dataclasses import dataclass

        @dataclass
        class MockError:
            message: str
            file: str = ""
            line: int = 0

        mock_errors = [MockError(message=f"TS2307: Cannot find module '{m}'")
                       for m in missing_modules]
        return fix_npm_deps(missing_modules, project_path)

    elif stack == "python":
        from tools.dependency_fixer import fix_pip_deps
        return fix_pip_deps(missing_modules, project_path)

    return []


def ensure_node_modules(project_path: Path, stack: str) -> bool:
    """Garante que node_modules existe e está completo."""
    if stack not in ("nestjs", "nextjs", "angular"):
        return True
    if not shutil.which("npm"):
        return False

    pkg_json = project_path / "package.json"
    if not pkg_json.exists():
        return False

    # Verifica se node_modules está incompleto verificando pacotes críticos
    critical_packages = {
        "nestjs": ["@nestjs/core", "@nestjs/common", "typeorm", "class-validator"],
        "nextjs": ["next", "react"],
        "angular": ["@angular/core"],
    }
    critical = critical_packages.get(stack, [])
    missing_critical = [p for p in critical
                        if not (project_path / "node_modules" / p).exists()]

    if missing_critical or not (project_path / "node_modules").exists():
        console.print(f"  [dim]→ Reinstalando dependências (node_modules incompleto)...[/dim]")
        r = subprocess.run(
            ["npm", "install", "--prefer-offline", "--legacy-peer-deps"],
            cwd=str(project_path), capture_output=True, text=True, timeout=300,
        )
        if r.returncode != 0:
            console.print(f"  [yellow]⚠ npm install: {r.stderr[:200]}[/yellow]")
            return False
        console.print("  [green]✓ node_modules reinstalado[/green]")

    return True


# ─── LLM code fixer ──────────────────────────────────────────────────────────

def fix_code_errors_with_llm(
    errors: list[dict],
    project_path: Path,
    stack: str,
    llm,
    model: str,
) -> list[str]:
    """
    Usa o LLM para corrigir erros de código (não de dependências).
    Agrupa por arquivo, envia o contexto do erro + conteúdo, recebe o fix.
    Retorna lista de arquivos corrigidos.
    """
    code_errors = [e for e in errors if e.get("type") == "code_error"]
    if not code_errors:
        return []

    # Agrupa por arquivo
    by_file: dict[str, list[dict]] = {}
    for e in code_errors[:15]:  # max 15 erros
        fpath = e.get("file", "")
        if fpath:
            by_file.setdefault(fpath, []).append(e)

    fixed = []
    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  console=console, transient=True) as p:
        task = p.add_task("Corrigindo...", total=len(by_file))

        for rel_path, file_errors in by_file.items():
            p.update(task, description=f"Corrigindo {Path(rel_path).name}...")
            abs_path = _resolve_path(rel_path, project_path)
            if not abs_path or not abs_path.exists():
                p.advance(task)
                continue

            original = abs_path.read_text(encoding="utf-8", errors="ignore")
            error_list = "\n".join(
                f"  Line {e['line']}: [{e['code']}] {e['message']}"
                for e in file_errors[:6]
            )

            # Consulta training com múltiplas queries para cada erro
            training_hint = ""
            try:
                from tools.vector_store import search_multi
                queries = []
                for e in file_errors[:3]:
                    code = e.get("code","")
                    msg  = e.get("message","")[:60]
                    queries.append(f"{stack} {code} {msg} fix")
                    queries.append(f"{stack} {code} solution TypeScript")
                result = search_multi(queries[:4], limit_per_query=2,
                                     exclude_topics=["docker","devops","cicd"])
                if result and len(result) > 50:
                    training_hint = f"\nTRAINING (how to fix these errors):\n{result[:400]}\n"
            except Exception:
                pass

            prompt = (
                f"Fix these TypeScript/compilation errors in this {stack} file.\n\n"
                f"File: {rel_path}\n\n"
                f"Errors:\n{error_list}\n"
                f"{training_hint}\n"
                f"File content:\n```\n{original[:3500]}\n```\n\n"
                f"Rules:\n"
                f"- Fix ONLY the listed errors\n"
                f"- Keep all existing logic unchanged\n"
                f"- For TS1272: use 'import type {{IFaceName}}' for interfaces in constructor params\n"
                f"- For TS2554: check constructor signature and fix the call\n"
                f"- For TS2339: add the missing property or fix the method name\n"
                f"- For TS2345: fix the type cast or conversion\n"
                f"- Return ONLY the corrected file as plain text (no JSON, no markdown fences)"
            )

            try:
                result = llm.chat(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    system=(
                        "You fix compilation errors in source files. "
                        "Return ONLY the corrected file content as plain text. "
                        "No JSON, no ```, no explanations."
                    ),
                    stream=False,
                )
                result = re.sub(r"^```\w*\n?", "", result.strip(), flags=re.MULTILINE)
                result = re.sub(r"\n?```$", "", result.strip())

                if result.strip() and len(result.strip()) > 30:
                    abs_path.write_text(result, encoding="utf-8")
                    fixed.append(rel_path)
                    p.update(task, description=f"[green]✓[/green] {Path(rel_path).name}")
                else:
                    p.update(task, description=f"[dim]~ {Path(rel_path).name} (sem fix)[/dim]")
            except Exception as e:
                console.print(f"  [dim red]LLM error: {e}[/dim red]")

            p.advance(task)

    return fixed


# ─── Relatório ────────────────────────────────────────────────────────────────

def print_error_summary(errors: list[dict], round_num: int):
    """Exibe tabela de erros atual."""
    t = Table(
        title=f"Erros — Rodada {round_num} ({len(errors)} total)",
        border_style="yellow dim", show_lines=False,
    )
    t.add_column("Arquivo", style="cyan", max_width=40)
    t.add_column("L", style="dim", width=5)
    t.add_column("Código", style="dim", width=8)
    t.add_column("Mensagem", max_width=60)
    t.add_column("Tipo", style="yellow", width=14)

    for e in errors[:20]:
        fname = Path(e.get("file","")).name
        t.add_row(fname, str(e.get("line","")), e.get("code",""),
                  e.get("message","")[:60], e.get("type",""))

    if len(errors) > 20:
        t.add_row(f"... e mais {len(errors)-20}", "", "", "", "")

    console.print(t)


# ─── Pipeline principal ───────────────────────────────────────────────────────

def fix_project(
    project_path: Path,
    llm=None,
    model: str = "qwen2.5-coder:7b",
    max_rounds: int = MAX_ROUNDS,
) -> bool:
    """
    Roda o pipeline completo de reparo até o build passar.
    Retorna True se o build passou.
    """
    stack = _detect_stack(project_path)
    console.print(f"\n[bold cyan]🔧 Reparando projeto[/bold cyan] — Stack: [bold]{stack}[/bold]")
    console.print(f"  Path: {project_path}\n")

    if stack == "unknown":
        console.print("[red]✗ Stack não detectada. Verifique o diretório.[/red]")
        return False

    # Garante node_modules está completo ANTES de qualquer coisa
    console.print("[dim]→ Verificando node_modules...[/dim]")
    ensure_node_modules(project_path, stack)

    # Instala pacotes base do NestJS
    if stack == "nestjs":
        from tools.code_fixer import preinstall_nestjs_deps, apply_fixes_to_project
        console.print("[dim]→ Garantindo pacotes NestJS base...[/dim]")
        preinstall_nestjs_deps(project_path)

    # STEP 0: Aplica todos os fixes determinísticos em TODOS os arquivos
    # (imports errados, PartialType, TypeORM overloads, etc) ANTES de compilar
    console.print("[dim]→ Aplicando correções automáticas nos arquivos...[/dim]")
    from tools.code_fixer import apply_fixes_to_project
    n_fixed = apply_fixes_to_project(project_path)
    if n_fixed:
        console.print(f"  [green]✓[/green] {n_fixed} arquivo(s) corrigido(s) automaticamente")

    prev_error_count = None

    for round_num in range(1, max_rounds + 1):
        console.print(Rule(f"[bold]Rodada {round_num}/{max_rounds}[/bold]"))

        # 1. Roda o build
        console.print("[dim]→ Compilando...[/dim]")
        rc, output = run_build(stack, project_path)

        if rc == 0:
            console.print(Panel(
                f"[bold green]✅ Build passou na rodada {round_num}![/bold green]\n\n"
                f"Stack: {stack}\n"
                f"O projeto está pronto para rodar.",
                border_style="green",
            ))
            return True

        # 2. Parseia erros
        errors = parse_errors(output, stack)
        if not errors:
            console.print("[yellow]Build falhou — erros não parseáveis. Output:[/yellow]")
            # Show only lines with 'error' or 'Error'
            error_lines = [l for l in output.splitlines() if "error" in l.lower() and l.strip()]
            shown = error_lines[:20] if error_lines else output.splitlines()[-30:]
            console.print("\n".join(shown[:25]))
            # Try to fix files with spaces in names (common LLM mistake)
            fixed_spaces = _fix_files_with_spaces(project_path)
            if fixed_spaces:
                console.print(f"[green]✓ {fixed_spaces} arquivo(s) com espaços no nome corrigido(s)[/green]")
                continue
            break

        print_error_summary(errors, round_num)

        # Detecta se não está progredindo
        if prev_error_count is not None and len(errors) >= prev_error_count:
            console.print("[yellow]⚠ Número de erros não diminuiu — tentando abordagem diferente[/yellow]")
            if round_num >= 3:
                break
        prev_error_count = len(errors)

        # 3. Instala pacotes faltantes
        missing_mod_errors = [e for e in errors if e.get("type") == "missing_module"]
        if missing_mod_errors:
            console.print(f"\n[bold]Passo 1 — Instalar {len(missing_mod_errors)} pacote(s) faltante(s)[/bold]")
            installed = install_missing_packages(missing_mod_errors, project_path, stack)
            if installed:
                console.print(f"  [green]✓ Instalado(s): {', '.join(installed[:5])}[/green]")
                continue  # re-run build first after installing

        # 4. Corrige paths de import errados (determinístico)
        path_errors = [e for e in errors if e.get("type") in ("missing_module", "wrong_path")
                       and e.get("module","").startswith(".")]
        if path_errors:
            console.print(f"\n[bold]Passo 2 — Corrigir paths de import[/bold]")
            fixed_paths = fix_wrong_import_paths(project_path, errors)
            if fixed_paths:
                console.print(f"  [green]✓ {len(fixed_paths)} arquivo(s) com paths corrigidos[/green]")

        # 5. Fix com LLM para erros de código
        code_errors = [e for e in errors if e.get("type") == "code_error"]
        if code_errors and llm:
            console.print(f"\n[bold]Passo 3 — Corrigir {len(code_errors)} erro(s) de código[/bold]")
            fixed_code = fix_code_errors_with_llm(errors, project_path, stack, llm, model)
            if fixed_code:
                console.print(f"  [green]✓ {len(fixed_code)} arquivo(s) corrigido(s)[/green]")
            else:
                console.print("  [yellow]Sem arquivos corrigidos pelo LLM[/yellow]")

        if not missing_mod_errors and not code_errors and not path_errors:
            console.print("[yellow]Erros não identificados — interrompendo[/yellow]")
            break

    # Build ainda falhou
    console.print(Rule("[red]Build não passou após todas as rodadas[/red]"))
    _, final_output = run_build(stack, project_path)
    final_errors = parse_errors(final_output, stack)

    if final_errors:
        _save_repair_log(final_errors, final_output, project_path)
        console.print(Panel(
            f"[yellow]⚠ Restam {len(final_errors)} erro(s)[/yellow]\n\n"
            f"Log salvo em: [dim].devai/repair.log[/dim]\n\n"
            f"Erros mais comuns:\n" +
            "\n".join(f"  • {e['code']}: {e['message'][:60]}" for e in final_errors[:5]),
            border_style="yellow",
        ))

    return False


def run_verify_fix_loop(
    project_path: Path,
    stack: str,
    port: int,
    llm=None,
    model: str = "qwen2.5-coder:7b",
    max_rounds: int = MAX_ROUNDS,
) -> bool:
    """
    Pipeline completo: build → fix → run → fix runtime errors → run again.
    Só finaliza quando o app sobe corretamente ou esgota as tentativas.
    """
    from tools.run_verifier import try_run, extract_runtime_errors, check_db_and_warn

    console.print(Rule("[bold cyan]🚀 Run → Verify → Fix Loop[/bold cyan]"))

    # Fase 1: Garante que o build passa
    build_ok = fix_project(project_path, llm=llm, model=model, max_rounds=max_rounds)
    if not build_ok:
        console.print("[yellow]⚠ Build ainda com erros — verificação de runtime pulada[/yellow]")
        return False

    # Fase 2: Verifica DB
    db_ok = check_db_and_warn(project_path)

    if not db_ok:
        console.print(Panel(
            "[bold green]✅ Build passou![/bold green]\n\n"
            "[yellow]⚠ Banco de dados não está rodando localmente.[/yellow]\n"
            "Para verificar o runtime:\n"
            "  make docker-dev   ← sobe DB + Redis\n"
            "  devai fix --run   ← re-verifica com runtime\n\n"
            "O projeto está pronto para rodar quando o banco estiver disponível.",
            border_style="green",
        ))
        return True  # Build passou, isso já é sucesso parcial

    # Fase 3: Build de produção (para stack node)
    if stack == "nestjs":
        console.print("[dim]→ Rodando npm run build...[/dim]")
        rc, out = _run_npm_build(project_path)
        if rc != 0:
            console.print(f"[yellow]⚠ npm build falhou:\n{out[-500:]}[/yellow]")
            if llm:
                errors = parse_errors(out, stack)
                fix_code_errors_with_llm(errors, project_path, stack, llm, model)
                _run_npm_build(project_path)

    # Fase 4: Tenta iniciar
    for attempt in range(1, 4):
        console.print(f"\n[bold]Tentativa de runtime {attempt}/3[/bold]")
        success, output = try_run(project_path, stack, port)

        if success:
            console.print(Panel(
                f"[bold green]✅ Aplicação rodando na porta {port}![/bold green]\n\n"
                f"URL: http://localhost:{port}\n"
                f"Swagger: http://localhost:{port}/api",
                border_style="green",
            ))
            return True

        # Extrai e corrige erros de runtime
        runtime_errors = extract_runtime_errors(output, stack)
        if not runtime_errors:
            console.print("[yellow]App não subiu mas sem erros identificados[/yellow]")
            console.print(f"[dim]{output[-500:]}[/dim]")
            break

        console.print(f"  [yellow]{len(runtime_errors)} erro(s) de runtime[/yellow]")
        for e in runtime_errors[:3]:
            console.print(f"  [dim]  • {e['message'][:80]}[/dim]")

        if llm:
            fix_code_errors_with_llm(runtime_errors, project_path, stack, llm, model)
            # Re-build após fix
            if stack == "nestjs":
                _run_npm_build(project_path)
        else:
            break

    return False


def _run_npm_build(project_path: Path) -> tuple[int, str]:
    """Roda npm run build."""
    import subprocess, os
    try:
        r = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(project_path), capture_output=True, text=True, timeout=180,
            env={**os.environ, "CI": "false"},
        )
        return r.returncode, r.stdout + r.stderr
    except Exception as e:
        return 1, str(e)


def _resolve_path(rel_path: str, project_path: Path) -> Optional[Path]:
    if rel_path.startswith("/"):
        p = Path(rel_path)
        return p if p.exists() else None
    for c in [project_path / rel_path, project_path / "src" / rel_path]:
        if c.exists():
            return c
    filename = Path(rel_path).name
    matches = list(project_path.rglob(filename))
    return matches[0] if matches else None


def _fix_files_with_spaces(project_path: Path) -> int:
    """
    Renomeia arquivos/diretórios com espaços no nome para usar kebab-case.
    Ex: 'banco mongodb.dto.ts' → 'banco-mongodb.dto.ts'
    Também corrige imports que referenciam os nomes antigos.
    """
    import shutil as sh
    renamed = 0

    # Encontra todos os .ts com espaços no nome
    for ts_file in list(project_path.rglob("*.ts")):
        if " " not in ts_file.name:
            continue
        # Pula node_modules e dist
        if any(p in str(ts_file) for p in ["node_modules", "dist", ".git"]):
            continue

        new_name = ts_file.name.replace(" ", "-").lower()
        new_path = ts_file.parent / new_name
        try:
            ts_file.rename(new_path)
            renamed += 1
            console.print(f"  [dim]Renomeado: {ts_file.name} → {new_name}[/dim]")
        except Exception:
            pass

    # Renomeia diretórios com espaços (de baixo para cima)
    dirs_with_spaces = sorted(
        [d for d in project_path.rglob("*")
         if d.is_dir() and " " in d.name
         and not any(p in str(d) for p in ["node_modules", ".git"])],
        key=lambda p: len(str(p)), reverse=True  # mais profundo primeiro
    )
    for d in dirs_with_spaces:
        new_name = d.name.replace(" ", "-").lower()
        new_path = d.parent / new_name
        try:
            d.rename(new_path)
            renamed += 1
            console.print(f"  [dim]Diretório renomeado: {d.name} → {new_name}[/dim]")
        except Exception:
            pass

    # Corrige imports nos arquivos que referenciam os nomes antigos
    if renamed > 0:
        _fix_imports_after_rename(project_path)

    return renamed


def _fix_imports_after_rename(project_path: Path) -> None:
    """Corrige imports que referenciam arquivos com espaços (agora renomeados)."""
    for ts_file in project_path.rglob("*.ts"):
        if any(p in str(ts_file) for p in ["node_modules", "dist", ".git"]):
            continue
        try:
            original = ts_file.read_text(encoding="utf-8", errors="ignore")
            # Fix imports with spaces: from './banco mongodb' → from './banco-mongodb'
            fixed = re.sub(
                r"from\s+'([^']*\s+[^']*)'",
                lambda m: f"from '{m.group(1).replace(' ', '-').lower()}'",
                original
            )
            fixed = re.sub(
                r'from\s+"([^"]*\s+[^"]*)"',
                lambda m: f'from "{m.group(1).replace(" ", "-").lower()}"',
                fixed
            )
            if fixed != original:
                ts_file.write_text(fixed, encoding="utf-8")
        except Exception:
            pass


def _save_repair_log(errors: list[dict], output: str, project_path: Path):
    log_dir = project_path / ".devai"
    log_dir.mkdir(exist_ok=True)
    lines = [
        f"Erros restantes: {len(errors)}",
        "",
        "=== ERROS ===",
        *[f"  {e.get('file','')}:{e.get('line','')} [{e.get('code','')}] {e.get('message','')}"
          for e in errors],
        "",
        "=== OUTPUT COMPLETO ===",
        output,
    ]
    (log_dir / "repair.log").write_text("\n".join(lines), encoding="utf-8")
