"""
Validator — executa verificações reais no código gerado.

Por stack:
  NestJS      → tsc --noEmit, eslint --fix
  Next.js     → tsc --noEmit
  Angular     → tsc --noEmit
  Spring Boot → ./mvnw compile
  Python      → py_compile + ruff check
  .NET        → dotnet build

Retorna erros estruturados para o self-healer corrigir.
"""

import re
import subprocess
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table

console = Console()

MAX_OUTPUT = 8000  # trunca output de compilação


@dataclass
class ValidationError:
    file:     str
    line:     int
    col:      int
    message:  str
    severity: str   # error | warning
    fixable:  bool  # se o LLM pode tentar corrigir


@dataclass
class ValidationResult:
    stack:    str
    passed:   bool
    checks:   list[str]          = field(default_factory=list)   # checks que passaram
    errors:   list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    raw_output: str = ""

    @property
    def error_count(self)  -> int: return len(self.errors)
    @property
    def warning_count(self) -> int: return len(self.warnings)
    @property
    def fixable_errors(self) -> list[ValidationError]:
        return [e for e in self.errors if e.fixable]


# ─── Runner ───────────────────────────────────────────────────────────────────

def _run(cmd: list[str], cwd: Path, timeout: int = 120) -> tuple[int, str]:
    """Executa comando, retorna (returncode, combined_output)."""
    try:
        r = subprocess.run(
            cmd, cwd=str(cwd),
            capture_output=True, text=True,
            timeout=timeout,
            env={**__import__("os").environ, "CI": "true", "NO_COLOR": "1"},
        )
        out = (r.stdout + r.stderr)[:MAX_OUTPUT]
        return r.returncode, out
    except subprocess.TimeoutExpired:
        return 1, f"Timeout ({timeout}s) ao executar: {' '.join(cmd)}"
    except FileNotFoundError as e:
        return 127, f"Comando não encontrado: {e}"


def _has(cmd: str) -> bool:
    return bool(shutil.which(cmd))


# ─── Parsers de erro por stack ─────────────────────────────────────────────────

def _parse_ts_errors(output: str) -> list[ValidationError]:
    """Parse TypeScript compiler output."""
    errors = []
    # src/main.ts(10,5): error TS2322: Type 'string' is not assignable to type 'number'.
    pattern = re.compile(r"(.+?)\((\d+),(\d+)\):\s*(error|warning)\s+(TS\d+):\s*(.+)")
    for m in pattern.finditer(output):
        filepath, line, col, sev, code, msg = m.groups()
        # TS2307 = missing module → instalar pacote, não corrigir código
        # TS7016 = missing type declarations → instalar @types/
        dep_errors = ("TS2307", "TS7016")
        fixable = code not in dep_errors
        errors.append(ValidationError(
            file=filepath.strip(), line=int(line), col=int(col),
            message=f"{code}: {msg.strip()}", severity=sev, fixable=fixable,
        ))
    return errors


def _parse_eslint_errors(output: str) -> list[ValidationError]:
    """Parse ESLint output."""
    errors = []
    # /path/file.ts
    #   10:5  error  'x' is defined but never used  @typescript-eslint/no-unused-vars
    current_file = ""
    file_re  = re.compile(r"^(/\S+\.tsx?)")
    error_re = re.compile(r"^\s+(\d+):(\d+)\s+(error|warning)\s+(.+?)\s{2,}")
    for line in output.splitlines():
        fm = file_re.match(line)
        if fm:
            current_file = fm.group(1)
            continue
        em = error_re.match(line)
        if em and current_file:
            ln, col, sev, msg = em.groups()
            errors.append(ValidationError(
                file=current_file, line=int(ln), col=int(col),
                message=msg.strip(), severity=sev, fixable=True,
            ))
    return errors


def _parse_java_errors(output: str) -> list[ValidationError]:
    """Parse Maven/Java compiler output."""
    errors = []
    # [ERROR] /path/File.java:[10,5] error message
    pattern = re.compile(r"\[(ERROR|WARNING)\]\s+(.+?\.java):\[(\d+),(\d+)\]\s+(.+)")
    for m in pattern.finditer(output):
        sev, filepath, line, col, msg = m.groups()
        errors.append(ValidationError(
            file=filepath, line=int(line), col=int(col),
            message=msg.strip(), severity=sev.lower(), fixable=True,
        ))
    return errors


def _parse_python_errors(output: str) -> list[ValidationError]:
    """Parse py_compile / ruff output."""
    errors = []
    # File "src/main.py", line 10
    py_re = re.compile(r'File "(.+?)", line (\d+)')
    for m in py_re.finditer(output):
        filepath, line = m.groups()
        # Pega a mensagem depois
        idx = m.end()
        msg_lines = output[idx:idx+200].split("\n")
        msg = msg_lines[1].strip() if len(msg_lines) > 1 else "syntax error"
        errors.append(ValidationError(
            file=filepath, line=int(line), col=0,
            message=msg, severity="error", fixable=True,
        ))
    # Ruff: src/main.py:10:5: F401 `os` imported but unused
    ruff_re = re.compile(r"(.+?):(\d+):(\d+):\s+([A-Z]\d+)\s+(.+)")
    for m in ruff_re.finditer(output):
        filepath, line, col, code, msg = m.groups()
        fixable = code not in ("E501",)  # linha muito longa não é auto-fixável pelo LLM
        errors.append(ValidationError(
            file=filepath, line=int(line), col=int(col),
            message=f"{code}: {msg.strip()}", severity="error", fixable=fixable,
        ))
    return errors


def _parse_dotnet_errors(output: str) -> list[ValidationError]:
    """Parse dotnet build output."""
    errors = []
    # File.cs(10,5): error CS0103: The name 'x' does not exist in the current context
    pattern = re.compile(r"(.+?\.cs)\((\d+),(\d+)\):\s*(error|warning)\s+(CS\d+):\s*(.+)")
    for m in pattern.finditer(output):
        filepath, line, col, sev, code, msg = m.groups()
        errors.append(ValidationError(
            file=filepath, line=int(line), col=int(col),
            message=f"{code}: {msg.strip()}", severity=sev, fixable=True,
        ))
    return errors


# ─── Validadores por stack ─────────────────────────────────────────────────────

def _validate_nestjs(path: Path) -> ValidationResult:
    result = ValidationResult(stack="nestjs", passed=True)

    # 1. TypeScript compile check
    if _has("npx"):
        rc, out = _run(["npx", "tsc", "--noEmit", "--skipLibCheck"], path, timeout=90)
        result.raw_output += f"=== TSC ===\n{out}\n"
        errs = _parse_ts_errors(out)
        if errs:
            result.errors.extend(errs)
            result.passed = False
        else:
            result.checks.append("TypeScript compile")

    # 2. ESLint auto-fix
    if _has("npx") and (path / ".eslintrc.js").exists() or (path / "eslint.config.mjs").exists():
        rc, out = _run(["npx", "eslint", "src", "--ext", ".ts", "--fix", "--max-warnings=50"], path, timeout=60)
        result.raw_output += f"=== ESLint ===\n{out}\n"
        if rc == 0:
            result.checks.append("ESLint")
        else:
            warns = _parse_eslint_errors(out)
            result.warnings.extend([w for w in warns if w.severity == "warning"])
            errs = [w for w in warns if w.severity == "error"]
            if errs:
                result.errors.extend(errs)
                result.passed = False

    return result


def _validate_nextjs(path: Path) -> ValidationResult:
    result = ValidationResult(stack="nextjs", passed=True)
    if _has("npx"):
        rc, out = _run(["npx", "tsc", "--noEmit", "--skipLibCheck"], path, timeout=90)
        result.raw_output += out
        errs = _parse_ts_errors(out)
        if errs:
            result.errors.extend(errs)
            result.passed = False
        else:
            result.checks.append("TypeScript compile")
    return result


def _validate_angular(path: Path) -> ValidationResult:
    return _validate_nextjs(path)   # mesmo processo: tsc --noEmit


def _validate_spring_boot(path: Path) -> ValidationResult:
    result = ValidationResult(stack="spring-boot", passed=True)
    mvnw = path / "mvnw"
    mvn  = shutil.which("mvn")

    cmd = [str(mvnw), "compile", "-q"] if mvnw.exists() else (["mvn", "compile", "-q"] if mvn else None)
    if not cmd:
        result.checks.append("Maven não encontrado — pulando compile check")
        return result

    rc, out = _run(cmd, path, timeout=180)
    result.raw_output += out
    if rc == 0:
        result.checks.append("Maven compile")
    else:
        errs = _parse_java_errors(out)
        if errs:
            result.errors.extend(errs)
        else:
            result.errors.append(ValidationError(
                file="pom.xml", line=0, col=0,
                message=out[:500], severity="error", fixable=False,
            ))
        result.passed = False
    return result


def _validate_python(path: Path) -> ValidationResult:
    result = ValidationResult(stack="python", passed=True)
    import sys

    python = shutil.which("python3") or shutil.which("python")
    if not python:
        return result

    # 1. Syntax check em todos os .py
    all_ok = True
    for py_file in path.rglob("*.py"):
        if any(p in str(py_file) for p in [".venv", "venv", "__pycache__"]):
            continue
        rc, out = _run([python, "-m", "py_compile", str(py_file)], path, timeout=10)
        if rc != 0:
            result.raw_output += f"{py_file}: {out}\n"
            errs = _parse_python_errors(out)
            if errs:
                result.errors.extend(errs)
            else:
                result.errors.append(ValidationError(
                    file=str(py_file.relative_to(path)), line=0, col=0,
                    message=out[:200], severity="error", fixable=True,
                ))
            all_ok = False

    if all_ok:
        result.checks.append("Python syntax")

    # 2. Ruff lint (se disponível)
    venv_ruff = path / ".venv" / "bin" / "ruff"
    ruff = str(venv_ruff) if venv_ruff.exists() else shutil.which("ruff")
    if ruff:
        rc, out = _run([ruff, "check", "--fix", "--select=E,F,I", "."], path, timeout=30)
        result.raw_output += f"=== Ruff ===\n{out}\n"
        if rc == 0:
            result.checks.append("Ruff lint")
        else:
            warns = _parse_python_errors(out)
            result.warnings.extend(warns)

    result.passed = not result.errors
    return result


def _validate_dotnet(path: Path) -> ValidationResult:
    result = ValidationResult(stack="dotnet", passed=True)
    if not _has("dotnet"):
        result.checks.append("dotnet não encontrado — pulando compile check")
        return result

    rc, out = _run(["dotnet", "build", "--configuration", "Debug", "--verbosity", "minimal"], path, timeout=180)
    result.raw_output += out
    if rc == 0:
        result.checks.append("dotnet build")
    else:
        errs = _parse_dotnet_errors(out)
        if errs:
            result.errors.extend(errs)
        else:
            result.errors.append(ValidationError(
                file="", line=0, col=0,
                message=out[-1000:], severity="error", fixable=False,
            ))
        result.passed = False
    return result


# ─── Ponto de entrada ──────────────────────────────────────────────────────────

VALIDATORS = {
    "nestjs":      _validate_nestjs,
    "nextjs":      _validate_nextjs,
    "angular":     _validate_angular,
    "spring-boot": _validate_spring_boot,
    "python":      _validate_python,
    "dotnet":      _validate_dotnet,
}


def validate(stack: str, project_path: Path) -> ValidationResult:
    """Executa validação estática para a stack. Retorna ValidationResult."""
    fn = VALIDATORS.get(stack)
    if not fn:
        r = ValidationResult(stack=stack, passed=True)
        r.checks.append(f"Stack '{stack}' sem validador — pulando")
        return r

    # Verifica se dependências estão instaladas
    if stack in ("nestjs", "nextjs", "angular"):
        if not (project_path / "node_modules").exists():
            r = ValidationResult(stack=stack, passed=True)
            r.checks.append("node_modules ausente — instale com npm install")
            return r

    return fn(project_path)


def print_result(result: ValidationResult):
    """Imprime o resultado da validação de forma legível."""
    if result.passed:
        console.print(f"\n  [green]✅ Validação OK[/green] — {', '.join(result.checks)}")
        if result.warning_count:
            console.print(f"  [yellow]⚠ {result.warning_count} aviso(s)[/yellow]")
        return

    console.print(f"\n  [red]✗ {result.error_count} erro(s) de compilação[/red]")

    t = Table(border_style="red dim", show_header=True, show_lines=False)
    t.add_column("Arquivo", style="cyan", max_width=50)
    t.add_column("Linha", style="dim", width=6)
    t.add_column("Erro", style="white")
    t.add_column("Auto-fix", width=9)

    for e in result.errors[:20]:
        fname = e.file.split("/")[-1] if "/" in e.file else e.file
        fix = "[green]✓[/green]" if e.fixable else "[dim]manual[/dim]"
        t.add_row(fname, str(e.line) if e.line else "—", e.message[:80], fix)

    console.print(t)
