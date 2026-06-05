"""
Execution Planner — cria e executa um plano de ações visível e auditável.

O usuário vê cada etapa antes e durante a execução.
Cada etapa tem: nome, descrição, função, contexto.
O conhecimento pesquisado é passado para TODAS as etapas.

Isso torna o sistema transparente: você sabe exatamente o que está sendo feito
e por quê, mesmo com um modelo 7B limitado.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Any
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.prompt import Confirm

console = Console()


@dataclass
class Step:
    num:      int
    phase:    str
    name:     str
    desc:     str
    fn:       Callable       # função a executar
    args:     dict = field(default_factory=dict)
    skip_if:  Optional[Callable] = None   # pula se retornar True
    status:   str = "pending"             # pending | running | done | skipped | failed
    result:   Any = None
    duration: float = 0.0


@dataclass
class Plan:
    title:   str
    steps:   list[Step]
    context: dict = field(default_factory=dict)   # contexto compartilhado entre steps


class Planner:
    def __init__(self, llm, model: str):
        self.llm   = llm
        self.model = model

    def build_new_project_plan(
        self,
        intent,           # Intent from intent_analyzer
        project_path: Path,
        research_ctx: str,
    ) -> Plan:
        """Constrói o plano completo para criar um projeto."""
        from tools.orchestrator_helpers import (
            step_scaffold_backend, step_scaffold_frontend,
            step_shared_files, step_domain, step_generate_backend,
            step_generate_frontend, step_api_contract,
            step_validate_and_fix, step_infra, step_cicd,
            step_git_commit, step_save_context,
        )

        ctx = {
            "intent": intent,
            "project_path": project_path,
            "research_ctx": research_ctx,
            "llm": self.llm,
            "model": self.model,
            "domain": None,
            "back_files": [],
            "front_files": [],
            "api_contract": {},
        }

        steps = []
        n = 1

        # ── Phase 1: Setup ────────────────────────────────────────────────
        steps.append(Step(n, "Setup", "Estrutura raiz",
            "Cria diretório, .gitignore, .env.example, git init",
            step_shared_files, skip_if=None))
        n += 1

        if intent.backend_stack:
            steps.append(Step(n, "Setup", f"Scaffold {intent.backend_stack}",
                f"Executa CLI do framework para criar a estrutura base em backend/",
                step_scaffold_backend))
            n += 1

        if intent.frontend_stack:
            steps.append(Step(n, "Setup", f"Scaffold {intent.frontend_stack}",
                f"Cria frontend/ com o CLI do framework",
                step_scaffold_frontend))
            n += 1

        # ── Phase 2: Domínio ──────────────────────────────────────────────
        steps.append(Step(n, "Domínio", "Extração de entidades",
            "LLM analisa a descrição e identifica entidades, módulos e auth",
            step_domain))
        n += 1

        # ── Phase 3: Geração de código ────────────────────────────────────
        if intent.backend_stack:
            steps.append(Step(n, "Código", f"Gerar backend ({intent.backend_stack})",
                "Gera todos os arquivos de domínio do backend (entidades, serviços, controllers, testes)",
                step_generate_backend))
            n += 1

        if intent.frontend_stack:
            steps.append(Step(n, "Código", "Extrair contrato de API",
                "Lê o backend gerado e mapeia endpoints, tipos e auth para o frontend",
                step_api_contract))
            n += 1

            steps.append(Step(n, "Código", f"Gerar frontend ({intent.frontend_stack})",
                "Gera componentes, API client, hooks e páginas conectados ao backend",
                step_generate_frontend))
            n += 1

        # ── Phase 4: Infraestrutura ───────────────────────────────────────
        steps.append(Step(n, "Infra", "Docker completo",
            "Dockerfile (multi-stage), docker-compose.yml, docker-compose.dev.yml, nginx, scripts/",
            step_infra, args={"what": None}))
        n += 1

        steps.append(Step(n, "Infra", "CI/CD GitHub Actions",
            "Workflow de CI: testa, builda, valida Docker em cada push",
            step_cicd))
        n += 1

        # ── Phase 5: Verificação ──────────────────────────────────────────
        if intent.backend_stack:
            steps.append(Step(n, "Verificação", f"Validar backend",
                "Compila, lint, auto-instala dependências, LLM corrige erros",
                step_validate_and_fix, args={"side": "backend"}))
            n += 1

        if intent.frontend_stack:
            steps.append(Step(n, "Verificação", f"Validar frontend",
                "Compila, lint, auto-instala dependências, LLM corrige erros",
                step_validate_and_fix, args={"side": "frontend"}))
            n += 1

        # ── Phase 6: Finalização ──────────────────────────────────────────
        steps.append(Step(n, "Finalização", "Salvar contexto",
            "Salva análise completa em .devai/context.json para uso futuro",
            step_save_context))
        n += 1

        steps.append(Step(n, "Finalização", "Commit inicial",
            'git add -A && git commit -m "feat: initial scaffold"',
            step_git_commit))

        return Plan(title=intent.description, steps=steps, context=ctx)

    def build_feature_plan(self, intent, project_path: Path, research_ctx: str) -> Plan:
        """Plano para adicionar uma feature a um projeto existente."""
        from tools.orchestrator_helpers import (
            step_domain, step_generate_feature, step_validate_and_fix,
        )

        ctx = {
            "intent": intent,
            "project_path": project_path,
            "research_ctx": research_ctx,
            "llm": self.llm,
            "model": self.model,
            "domain": None,
            "back_files": [],
        }

        steps = [
            Step(1, "Análise",    "Extrair domínio da feature", "", step_domain),
            Step(2, "Código",     "Gerar arquivos da feature",  "", step_generate_feature),
            Step(3, "Verificação","Validar e corrigir erros",   "", step_validate_and_fix, args={"side": "project"}),
        ]
        return Plan(title=intent.description, steps=steps, context=ctx)

    def build_infra_plan(self, intent, project_path: Path, research_ctx: str) -> Plan:
        """Plano para gerar infraestrutura de um projeto existente."""
        from tools.orchestrator_helpers import step_infra, step_cicd

        ctx = {
            "intent": intent,
            "project_path": project_path,
            "research_ctx": research_ctx,
            "llm": self.llm,
            "model": self.model,
        }

        steps = []
        n = 1

        what = []
        if intent.needs_docker or intent.action == "infra":
            steps.append(Step(n, "Infra", "Docker completo",
                "Dockerfile, docker-compose, nginx, scripts", step_infra, args={"what": None}))
            n += 1

        if intent.needs_cicd:
            steps.append(Step(n, "Infra", "CI/CD", "GitHub Actions workflow", step_cicd))
            n += 1

        if not steps:
            steps.append(Step(1, "Infra", "Infraestrutura completa",
                "Docker + CI/CD + nginx", step_infra, args={"what": None}))

        return Plan(title=intent.description, steps=steps, context=ctx)

    def print_plan(self, plan: Plan):
        """Exibe o plano para o usuário aprovar."""
        # Agrupa por fase
        phases: dict[str, list[Step]] = {}
        for s in plan.steps:
            phases.setdefault(s.phase, []).append(s)

        t = Table(
            title=f"📋 Plano: {plan.title[:60]}",
            border_style="cyan",
            show_lines=False,
            show_header=True,
        )
        t.add_column("#",      style="dim",   width=4)
        t.add_column("Fase",   style="yellow", width=14)
        t.add_column("Etapa",  style="cyan",   width=28)
        t.add_column("O que fará",  style="dim")

        for step in plan.steps:
            t.add_row(str(step.num), step.phase, step.name, step.desc[:60])

        console.print(t)
        console.print(f"  [dim]Total: {len(plan.steps)} etapas[/dim]\n")

    def execute(self, plan: Plan) -> dict:
        """
        Executa o plano etapa por etapa.
        Retorna o contexto final com todos os resultados.
        """
        self.print_plan(plan)

        if not Confirm.ask("[cyan]Executar este plano?[/cyan]", default=True):
            console.print("[dim]Cancelado.[/dim]")
            return plan.context

        start_total = time.time()
        done = 0
        failed = 0

        for step in plan.steps:
            # Verifica se deve pular
            if step.skip_if and step.skip_if(plan.context):
                step.status = "skipped"
                console.print(f"  [dim]⊘ {step.num}. {step.name} (pulado)[/dim]")
                continue

            console.print(Rule(f"[bold]{step.num}/{len(plan.steps)} — {step.phase}: {step.name}[/bold]"))

            t0 = time.time()
            step.status = "running"
            try:
                result = step.fn(plan.context, **step.args)
                step.result   = result
                step.status   = "done"
                step.duration = time.time() - t0
                done += 1
                console.print(f"  [green]✓[/green] {step.name} [dim]({step.duration:.1f}s)[/dim]")
            except Exception as e:
                step.status   = "failed"
                step.duration = time.time() - t0
                failed += 1
                console.print(f"  [red]✗ {step.name}: {e}[/red]")
                import traceback
                console.print(f"  [dim]{traceback.format_exc()[-500:]}[/dim]")
                # Pergunta se continua
                if not Confirm.ask("  [yellow]Continuar mesmo com erro?[/yellow]", default=True):
                    break

        total_time = time.time() - start_total
        self._print_summary(plan, done, failed, total_time)
        return plan.context

    def _print_summary(self, plan: Plan, done: int, failed: int, elapsed: float):
        status_color = "green" if failed == 0 else "yellow"
        status_icon  = "✅" if failed == 0 else "⚠"

        rows = "\n".join(
            f"  {'✓' if s.status=='done' else ('⊘' if s.status=='skipped' else '✗')} "
            f"{s.num}. {s.name} "
            f"[dim]({s.duration:.1f}s)[/dim]"
            for s in plan.steps
        )

        console.print(Panel(
            f"[bold {status_color}]{status_icon} Plano concluído[/bold {status_color}]\n\n"
            f"{rows}\n\n"
            f"[dim]{done} etapas concluídas · {failed} falha(s) · {elapsed:.0f}s total[/dim]",
            border_style=status_color,
        ))
