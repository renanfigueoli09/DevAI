"""
Self Healer — corrige erros automaticamente, priorizando instalação de dependências.

Ordem de correção:
  1. Dependências faltantes (npm install / pip install) — sem LLM
  2. Erros de compilação corrigíveis por LLM (type errors, syntax errors)
  3. Re-validação após cada etapa
  4. Máximo MAX_ROUNDS tentativas LLM

Erros NÃO auto-corrigíveis (listados para o usuário):
  - Lógica de negócio incorreta
  - Pacotes Java Maven sem pom.xml configurado
  - Problemas de configuração de ambiente
"""

import re
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.rule import Rule
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from tools.validator import ValidationResult, ValidationError, validate, print_result
from tools.dependency_fixer import fix_dependencies, print_dep_report
from config import MODEL_CODE

console = Console()

MAX_ROUNDS = 3    # rodadas de correção LLM
MAX_FILES  = 8    # max arquivos por rodada (contexto 7B)


def heal(
    result: ValidationResult,
    project_path: Path,
    llm,
    stack: str,
    generated_files: list[dict] = None,
) -> ValidationResult:
    """
    Pipeline completo de correção.
    Retorna ValidationResult final.
    """
    if result.passed:
        return result

    console.print(f"\n[bold cyan]🔧 Auto-correção — {result.error_count} erro(s)[/bold cyan]")

    # ── ETAPA 1: Dependências faltantes ────────────────────────────────────────
    has_dep_errors = any(
        "TS2307" in e.message or "TS7016" in e.message
        or "No module named" in e.message
        or "cannot import name" in e.message
        or "does not exist" in e.message
        for e in result.errors
    )

    # Sempre escaneia imports dos arquivos gerados (pega deps antes de compilar)
    if stack in ("nestjs", "nextjs", "angular", "python") or has_dep_errors:
        console.print(Rule("[dim]Etapa 1 — Dependências[/dim]"))
        installed, not_inst = fix_dependencies(result, project_path, stack, generated_files)
        print_dep_report(installed, not_inst)

        if installed:
            # Re-valida após instalar
            console.print("\n[dim]→ Re-validando após instalação...[/dim]")
            result = validate(stack, project_path)
            print_result(result)
            if result.passed:
                console.print("[bold green]✅ Erros resolvidos com instalação de dependências![/bold green]")
                return result

    # ── ETAPA 2: Erros corrigíveis por LLM ─────────────────────────────────────
    fixable = result.fixable_errors
    if not fixable:
        _report_unfixable(result)
        return result

    console.print(Rule("[dim]Etapa 2 — Correção de código[/dim]"))
    console.print(f"  [cyan]{len(fixable)} erro(s) de código para corrigir[/cyan]")

    for round_num in range(1, MAX_ROUNDS + 1):
        console.print(f"\n[dim]  Rodada {round_num}/{MAX_ROUNDS}[/dim]")

        # Agrupa erros por arquivo (prioriza arquivos com mais erros)
        by_file: dict[str, list[ValidationError]] = {}
        for err in fixable[:20]:
            by_file.setdefault(err.file, []).append(err)

        # Ordena: arquivos com mais erros primeiro
        sorted_files = sorted(by_file.items(), key=lambda x: len(x[1]), reverse=True)
        fixed_count  = 0

        with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                      console=console, transient=True) as p:
            task = p.add_task("Corrigindo...", total=len(sorted_files[:MAX_FILES]))

            for rel_path, errors in sorted_files[:MAX_FILES]:
                p.update(task, description=f"[cyan]{Path(rel_path).name}[/cyan]")
                abs_path = _resolve_path(rel_path, project_path)
                if not abs_path or not abs_path.exists():
                    p.advance(task)
                    continue

                original = abs_path.read_text(encoding="utf-8", errors="ignore")
                fixed    = _fix_file_with_llm(original, rel_path, errors, stack, llm)

                if fixed and fixed.strip() != original.strip() and len(fixed.strip()) > 20:
                    abs_path.write_text(fixed, encoding="utf-8")
                    fixed_count += 1
                    p.update(task, description=f"[green]✓ {Path(rel_path).name}[/green]")
                else:
                    p.update(task, description=f"[dim]~ {Path(rel_path).name}[/dim]")

                p.advance(task)

        if fixed_count == 0:
            console.print("  [yellow]Nenhum arquivo corrigido — interrompendo.[/yellow]")
            break

        # Re-valida
        console.print(f"  [dim]→ Re-validando ({fixed_count} arquivo(s) corrigido(s))...[/dim]")
        result = validate(stack, project_path)
        print_result(result)

        if result.passed:
            console.print(f"[bold green]✅ Todos os erros corrigidos na rodada {round_num}![/bold green]")
            return result

        fixable = result.fixable_errors
        if not fixable:
            break

    # ── ETAPA 3: Relatório de erros restantes ─────────────────────────────────
    if not result.passed:
        _report_unfixable(result)
        _save_log(result, project_path)

    return result


def _fix_file_with_llm(
    content: str,
    filepath: str,
    errors: list[ValidationError],
    stack: str,
    llm,
) -> Optional[str]:
    """Envia arquivo + erros ao LLM e retorna o arquivo corrigido."""

    # Filtra erros não-LLM (deps) antes de mandar ao modelo
    code_errors = [e for e in errors if "TS2307" not in e.message and "TS7016" not in e.message]
    if not code_errors:
        return None

    error_list = "\n".join(
        f"  Line {e.line}: {e.message}"
        for e in code_errors[:6]
    )

    # Limita o arquivo para caber no contexto do 7B (~3500 tokens de code)
    content_for_llm = content[:3500]
    truncated = len(content) > 3500

    prompt = f"""You are fixing compile errors in a {stack} project.

File: {filepath}

Errors:
{error_list}

File content:
```
{content_for_llm}{"\\n// ... (file truncated)" if truncated else ""}
```

Instructions:
- Fix ONLY the errors listed above
- Keep all existing business logic unchanged
- Do NOT remove or change unrelated code
- Do NOT add placeholder comments like "// TODO"
- For missing properties: add them with correct types
- For wrong types: use the correct type
- For missing imports: add the correct import statement
- Return the COMPLETE corrected file as plain text (no JSON, no markdown fences)"""

    system = (
        "You fix compile errors in source code. "
        "Return ONLY the corrected file content as plain text. "
        "No JSON wrapper, no ```code``` fences, no explanation text before or after."
    )

    try:
        response = llm.chat(
            model=MODEL_CODE,
            messages=[{"role": "user", "content": prompt}],
            system=system,
            stream=False,
        )
        # Remove fences se o modelo as adicionou mesmo assim
        response = re.sub(r"^```\w*\n?", "", response.strip(), flags=re.MULTILINE)
        response = re.sub(r"\n?```\s*$", "", response.strip())
        return response if len(response.strip()) > 20 else None
    except Exception as e:
        console.print(f"  [dim red]LLM error: {e}[/dim red]")
        return None


def _resolve_path(rel_path: str, project_path: Path) -> Optional[Path]:
    """Resolve caminho relativo/absoluto para Path dentro do projeto."""
    if rel_path.startswith("/"):
        p = Path(rel_path)
        return p if p.exists() else None

    for candidate in [project_path / rel_path, project_path / "src" / rel_path]:
        if candidate.exists():
            return candidate

    # Busca pelo nome do arquivo na árvore
    filename = Path(rel_path).name
    matches = list(project_path.rglob(filename))
    return matches[0] if matches else None


def _report_unfixable(result: ValidationResult):
    """Exibe tabela com erros que precisam de atenção manual."""
    unfixable = [e for e in result.errors if not e.fixable]
    code_errors = [e for e in result.errors if e.fixable]

    if not unfixable and not code_errors:
        return

    console.print("\n[bold yellow]⚠ Erros que requerem atenção manual:[/bold yellow]")

    t = Table(border_style="yellow dim", show_header=True, show_lines=False)
    t.add_column("Arquivo",  style="cyan",   max_width=40)
    t.add_column("Linha",    style="dim",    width=6)
    t.add_column("Erro",     style="white",  max_width=60)
    t.add_column("Tipo",     style="yellow", width=12)

    all_remaining = result.errors[:15]
    for e in all_remaining:
        fname = Path(e.file).name if e.file else "—"
        etype = "dep" if ("TS2307" in e.message or "No module" in e.message) else "código"
        t.add_row(fname, str(e.line) if e.line else "—", e.message[:60], etype)

    console.print(t)
    console.print(f"\n  [dim]Veja .devai/validation.log para detalhes completos[/dim]")


def _save_log(result: ValidationResult, project_path: Path):
    """Salva log detalhado para debug."""
    log_dir = project_path / ".devai"
    log_dir.mkdir(exist_ok=True)
    lines = [
        f"Stack: {result.stack}",
        f"Passed: {result.passed}",
        f"Errors: {result.error_count}",
        f"Warnings: {result.warning_count}",
        "",
        "=== ERRORS ===",
        *[f"  {e.file}:{e.line} [{e.severity}] {e.message}" for e in result.errors],
        "",
        "=== RAW COMPILER OUTPUT ===",
        result.raw_output,
    ]
    (log_dir / "validation.log").write_text("\n".join(lines), encoding="utf-8")
