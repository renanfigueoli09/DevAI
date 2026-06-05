import os
"""
Orchestrator — pipeline completo de geração de projetos.

Single-stack:
  scaffold CLI → extract domain → manifest → generate → write → git

Fullstack (backend + frontend):
  shared setup → backend pipeline → extract API contract → frontend pipeline → git
"""

import json
import re
import subprocess
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.prompt import Confirm
from rich.table import Table

from config import MODEL_CODE, MODEL_ANALYST, VERBOSE
from tools.llm_client import OllamaClient
from tools.scanner import scan_project
from tools.scaffold import scaffold_project
from tools.gitignore import write_gitignore, write_env_example
from tools.file_writer import write_files, save_project_context, load_project_context
from tools.manifests import get_manifest, FileSpec
from tools.generator import generate_files
from tools.domain_extractor import extract_domain
from tools.task_classifier import classify
from tools.validator import validate, print_result as print_validation
from tools.self_healer import heal as auto_heal
from tools.setup_runner import run_post_generation_pipeline, delivery_report
from tools.knowledge_base import extract_infra_context, get_global_kb, InfraContext
from tools.infra_generator import generate_infra
from tools.api_contract import extract_api_contract
from tools.fullstack import (
    resolve_combo, COMBOS,
    write_shared_files,
)
from prompts import ANALYST_SYSTEM, analyst_prompt, ASK_SYSTEM, ask_prompt

console = Console()


# ─── helpers ──────────────────────────────────────────────────────────────────

def _run(cmd: list[str], cwd: Path = None, silent: bool = True) -> bool:
    try:
        r = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                           capture_output=silent, text=True)
        return r.returncode == 0
    except FileNotFoundError:
        return False


def _save_debug(path: Path, content: str):
    d = path / ".devai"
    d.mkdir(exist_ok=True)
    (d / "last_response.txt").write_text(content, encoding="utf-8")


def _show_manifest(specs: list[FileSpec], title: str = "Arquivos a gerar"):
    t = Table(title=f"📋 {title}", border_style="dim", show_lines=False)
    t.add_column("#", style="dim", width=4)
    t.add_column("Arquivo", style="cyan")
    t.add_column("Tipo", style="dim", width=14)
    for i, s in enumerate(specs, 1):
        t.add_row(str(i), s.path, s.file_type)
    console.print(t)
    console.print(f"[dim]Total: {len(specs)} arquivo(s)[/dim]\n")


def _filter_existing(specs: list[FileSpec], base: Path) -> list[FileSpec]:
    new = [s for s in specs if not (base / s.path).exists()]
    skipped = len(specs) - len(new)
    if skipped:
        console.print(f"[dim]  ↳ {skipped} arquivo(s) do scaffold já existem — pulando[/dim]")
    return new


def _parse_json(text: str) -> Optional[dict]:
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text.strip())
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
def _detect_infra_scope(description: str, ctx) -> list[str]:
    """
    Detecta quais componentes de infra gerar baseado no pedido e no que já existe.
    Retorna lista de componentes, ou None para gerar tudo.
    """
    text = description.lower()
    scope = []

    # Componentes explicitamente pedidos
    if any(w in text for w in ["dockerfile", "docker file", "image"]):
        scope.append("docker")
    if any(w in text for w in ["nginx", "proxy", "reverse proxy"]):
        scope.append("nginx")
    if any(w in text for w in ["github action", "ci/cd", "pipeline", "workflow", "ci"]):
        scope.append("cicd")
    if any(w in text for w in ["makefile", "make"]):
        scope.append("make")

    # "docker-compose" ou "compose" ou "docker" genérico → tudo docker
    if any(w in text for w in ["docker-compose", "compose", "docker stack", "containerizar", "dockerizar"]):
        if "docker" not in scope:
            scope.append("docker")

    # "infraestrutura completa" ou "infra" → tudo
    if any(w in text for w in ["infraestrutura completa", "infra completa", "tudo", "complete infra", "full infra"]):
        return None  # gera tudo

    # Se só pediu "docker" sem especificar, gera dockerfile + compose
    if not scope:
        scope.append("docker")

    return scope


class Orchestrator:
    def __init__(self):
        self.llm = OllamaClient()

    # ══════════════════════════════════════════════════════════════════════
    # CRIAR PROJETO SINGLE-STACK
    # ══════════════════════════════════════════════════════════════════════

    def create_new_project(self, stack: str, name: str, description: str):
        console.print(Rule(f"[bold cyan]Novo projeto — {stack} / {name}[/bold cyan]"))
        console.print(f"[dim]{description}[/dim]\n")
        self.llm.ensure_model(MODEL_CODE)

        output_path = Path(os.getcwd()).resolve() / name

        # 1. Scaffold CLI
        console.print(Rule("[bold]🔨 Scaffold do framework[/bold]"))
        scaffold_ok = scaffold_project(stack=stack, name=name,
                                       output_dir=output_path, description=description)
        output_path.mkdir(parents=True, exist_ok=True)

        # 2. Git + gitignore + env
        write_gitignore(stack, output_path)
        write_env_example(stack, output_path, name)
        if not (output_path / ".git").exists():
            _run(["git", "init"], cwd=output_path)
        console.print("[green]✓ .gitignore, .env.example, git init[/green]")

        # 3. Domain
        console.print(Rule("[bold]🤖 Análise de domínio[/bold]"))
        domain = extract_domain(description, self.llm)
        entities = domain.get("entities", [])
        has_auth = domain.get("has_auth", False)

        # 4. Manifest + filtro
        console.print(Rule("[bold]📋 Manifest de arquivos[/bold]"))
        specs = get_manifest(stack, name, entities, has_auth)
        if scaffold_ok:
            specs = _filter_existing(specs, output_path)
        _show_manifest(specs)

        if not Confirm.ask("[cyan]Iniciar geração?[/cyan]", default=True):
            return

        # 5. Geração
        console.print(Rule("[bold]💻 Gerando código[/bold]"))
        files = generate_files(specs=specs, stack=stack, name=name,
                               description=description, domain=domain,
                               llm=self.llm, output_path=output_path)

        # 6. Escreve os arquivos
        if files:
            write_files(files, base_path=output_path, confirm=False, preview=False)
            save_project_context(output_path, {
                "summary": {"name": name, "stack": stack},
                "analysis": domain, "context_string": "",
            })

        # 7. Pipeline de verificação pós-geração
        setup = run_post_generation_pipeline(
            project_path=output_path,
            stack=stack,
            name=name,
            files_written=len(files or []),
            llm=self.llm,
            run_health=False,   # não exige DB para entregar
            generated_files=files or [],
        )

        # 8. Commit inicial (só se validação passou)
        if setup.validation_passed or Confirm.ask(
            "\n[cyan]Fazer commit mesmo com erros pendentes?[/cyan]", default=False
        ):
            _run(["git", "add", "-A"], cwd=output_path)
            _run(["git", "commit", "-m", f"feat: scaffold {stack} — {name}"],
                 cwd=output_path, silent=False)

        # 9. Relatório final
        delivery_report(setup, output_path)

    # ══════════════════════════════════════════════════════════════════════
    # CRIAR PROJETO FULLSTACK
    # ══════════════════════════════════════════════════════════════════════

    def create_fullstack_project(self, combo: str, name: str, description: str):
        combo_key, cfg = resolve_combo(combo), COMBOS.get(combo)
        if not cfg:
            console.print(f"[red]✗ Combo '{combo}' não suportado[/red]")
            return

        backend_stack  = cfg["backend"]
        frontend_stack = cfg["frontend"]
        port_back      = cfg["port_back"]
        port_front     = cfg["port_front"]
        front_manifest = f"{frontend_stack}-client"  # ex: nextjs-client

        console.print(Rule(f"[bold cyan]Fullstack — {combo} / {name}[/bold cyan]"))
        console.print(f"[dim]{description}[/dim]")
        console.print(f"  Backend:  [bold]{backend_stack}[/bold] (:{port_back})")
        console.print(f"  Frontend: [bold]{frontend_stack}[/bold] (:{port_front})\n")

        self.llm.ensure_model(MODEL_CODE)

        root = Path(os.getcwd()).resolve() / name
        backend_path  = root / "backend"
        frontend_path = root / "frontend"

        root.mkdir(parents=True, exist_ok=True)

        # ── FASE 0: arquivos raiz compartilhados ──────────────────────────
        console.print(Rule("[bold]📁 Fase 0 — Estrutura raiz[/bold]"))
        write_shared_files(name, description, cfg, root)

        if not (root / ".git").exists():
            _run(["git", "init"], cwd=root)
        console.print("[green]✓ git init na raiz[/green]")

        # ── FASE 1: domínio (1 chamada LLM, compartilhado) ────────────────
        console.print(Rule("[bold]🤖 Fase 1 — Análise de domínio[/bold]"))
        domain = extract_domain(description, self.llm)
        entities = domain.get("entities", [])
        has_auth = domain.get("has_auth", False)
        console.print(f"  [dim]Compartilhado entre backend e frontend[/dim]")

        # ── FASE 2: BACKEND ───────────────────────────────────────────────
        console.print(Rule(f"[bold yellow]⚙  Fase 2 — Backend ({backend_stack})[/bold yellow]"))

        # Scaffold
        scaffold_ok = scaffold_project(
            stack=backend_stack, name="backend",
            output_dir=backend_path, description=description,
        )
        backend_path.mkdir(parents=True, exist_ok=True)
        write_gitignore(backend_stack, backend_path)
        write_env_example(backend_stack, backend_path, name)

        # Manifest backend
        back_specs = get_manifest(backend_stack, name, entities, has_auth)
        if scaffold_ok:
            back_specs = _filter_existing(back_specs, backend_path)
        _show_manifest(back_specs, f"Backend — {backend_stack}")

        # Gera backend
        back_domain = {**domain, "api_port": port_back, "role": "backend"}
        back_files = generate_files(
            specs=back_specs,
            stack=backend_stack,
            name=name,
            description=f"[BACKEND] {description}",
            domain=back_domain,
            llm=self.llm,
            output_path=backend_path,
        )
        if back_files:
            write_files(back_files, base_path=backend_path, confirm=False, preview=False)

        # ── FASE 3: extrai contrato de API ────────────────────────────────
        console.print(Rule("[bold]🔗 Fase 3 — Contrato de API[/bold]"))
        api_contract = extract_api_contract(
            backend_files=back_files or [],
            stack=backend_stack,
            entities=entities,
            has_auth=has_auth,
            api_port=port_back,
            llm=self.llm,
        )

        # ── FASE 4: FRONTEND ──────────────────────────────────────────────
        console.print(Rule(f"[bold cyan]🖥  Fase 4 — Frontend ({frontend_stack})[/bold cyan]"))

        # Scaffold frontend
        scaffold_front_ok = scaffold_project(
            stack=frontend_stack, name="frontend",
            output_dir=frontend_path, description=description,
        )
        frontend_path.mkdir(parents=True, exist_ok=True)
        write_gitignore(frontend_stack, frontend_path)

        # .env do frontend com a URL da API
        _write_frontend_env(frontend_stack, frontend_path, name, port_back, port_front)

        # Manifest frontend (variante -client que consome API REST)
        front_specs = get_manifest(
            front_manifest, name, entities, has_auth, api_port=port_back,
        )
        if scaffold_front_ok:
            front_specs = _filter_existing(front_specs, frontend_path)
        _show_manifest(front_specs, f"Frontend — {frontend_stack}")

        # Descrição enriquecida com contrato de API
        front_desc = (
            f"[FRONTEND consuming REST API]\n"
            f"Description: {description}\n\n"
            f"=== BACKEND API CONTRACT (use these exactly) ===\n"
            f"{api_contract.get('summary', '')}"
        )

        front_domain = {
            **domain,
            "api_port": port_back,
            "frontend_port": port_front,
            "role": "frontend",
            "api_contract": api_contract.get("summary", ""),
        }

        front_files = generate_files(
            specs=front_specs,
            stack=front_manifest,           # usa o manifest correto
            name=name,
            description=front_desc,
            domain=front_domain,
            llm=self.llm,
            output_path=frontend_path,
        )
        if front_files:
            write_files(front_files, base_path=frontend_path, confirm=False, preview=False)

        # ── FASE 5: instala dependências extras do frontend ───────────────
        self._install_frontend_deps(frontend_stack, frontend_path)

        # ── FASE 6: salva contexto e commit ──────────────────────────────
        save_project_context(root, {
            "summary": {"name": name, "stack": combo, "type": "fullstack"},
            "analysis": {**domain, "api_contract": api_contract},
            "backend_stack": backend_stack,
            "frontend_stack": frontend_stack,
            "context_string": api_contract.get("summary", ""),
        })

        if Confirm.ask("\n[cyan]Commit inicial?[/cyan]", default=True):
            _run(["git", "add", "-A"], cwd=root)
            _run(["git", "commit", "-m", f"feat: fullstack scaffold — {combo} — {name}"],
                 cwd=root, silent=False)

        self._print_done_fullstack(name, combo, port_back, port_front)

    # ══════════════════════════════════════════════════════════════════════
    # ESTUDAR PROJETO
    # ══════════════════════════════════════════════════════════════════════

    def study_project(self, project_path: Path):
        console.print(Rule("[bold cyan]Estudando projeto...[/bold cyan]"))
        self.llm.ensure_model(MODEL_ANALYST)

        summary = scan_project(project_path)
        ctx = summary.to_context_string()

        analysis_resp = self.llm.chat(
            model=MODEL_ANALYST,
            messages=[{"role": "user", "content": analyst_prompt(ctx)}],
            system=ANALYST_SYSTEM, stream=True,
        )

        analysis = _parse_json(analysis_resp) or {"raw": analysis_resp}

        # Extrai contexto de infra (análise estática, sem LLM)
        infra_ctx = extract_infra_context(project_path)
        infra_summary = infra_ctx.to_prompt_context()
        console.print(f"\n[dim]Infra detectada:[/dim]\n{infra_summary}")

        # Atualiza knowledge base global com o que aprendemos
        kb = get_global_kb()
        kb.set_fact(f"project_{summary.name}_stack", summary.stack, ttl_hours=720)
        kb.set_fact(f"project_{summary.name}_db", infra_ctx.database, ttl_hours=720)

        save_project_context(project_path, {
            "summary": {
                "name": summary.name, "stack": summary.stack,
                "total_files": summary.total_files,
                "languages": summary.languages,
                "key_files": summary.key_files,
            },
            "analysis": analysis,
            "infra": {
                "stack": infra_ctx.stack,
                "app_port": infra_ctx.app_port,
                "database": infra_ctx.database,
                "db_port": infra_ctx.db_port,
                "db_name": infra_ctx.db_name,
                "orm": infra_ctx.orm,
                "cache": infra_ctx.cache,
                "queue": infra_ctx.queue,
                "runtime_version": infra_ctx.runtime_version,
                "existing_modules": infra_ctx.existing_modules,
                "has_dockerfile": infra_ctx.has_dockerfile,
                "has_compose": infra_ctx.has_compose,
                "has_cicd": infra_ctx.has_cicd,
                "env_vars": infra_ctx.env_vars[:30],
            },
            "context_string": ctx[:8000],
        })

        console.print(Rule("[bold green]✅ Projeto estudado[/bold green]"))
        if isinstance(analysis, dict) and "raw" not in analysis:
            self._print_analysis(analysis)
        console.print(f"\n[dim]Contexto salvo em {project_path}/.devai/context.json[/dim]")
        console.print('[cyan]Próximo:[/cyan] devfeat "sua feature"')

    # ══════════════════════════════════════════════════════════════════════
    # ADICIONAR FEATURE
    # ══════════════════════════════════════════════════════════════════════

    def add_feature(self, project_path: Path, description: str):
        """
        Pipeline de feature — classifica o pedido e roteia para o handler correto.
        Tipos: infra | db | code | config | docs | security | research
        """
        console.print(Rule("[bold cyan]Nova feature[/bold cyan]"))
        console.print(f"[dim]{description}[/dim]\n")
        self.llm.ensure_model(MODEL_CODE)

        # ── 1. Carrega contexto do projeto ────────────────────────────────
        ctx_data = load_project_context(project_path)
        if ctx_data:
            console.print("[dim]✓ Contexto carregado do cache[/dim]")
            stack     = ctx_data.get("summary", {}).get("stack") or "desconhecida"
            proj_type = ctx_data.get("summary", {}).get("type", "single")
            analysis  = ctx_data.get("analysis", {})
        else:
            console.print("[yellow]Projeto não estudado. Escaneando agora...[/yellow]")
            summary = scan_project(project_path)
            stack     = summary.stack or "desconhecida"
            proj_type = "single"
            analysis  = {}
            save_project_context(project_path, {
                "summary": {"name": summary.name, "stack": stack},
                "analysis": {}, "context_string": summary.to_context_string()[:8000],
            })

        console.print(f"  Stack: [bold]{stack}[/bold]")

        # ── 2. Classifica o pedido ────────────────────────────────────────
        task = classify(description, llm=self.llm, model=MODEL_CODE)

        # ── 3. Roteamento por tipo de tarefa ──────────────────────────────
        # Detecta pedido de reparo ANTES de tudo
        fix_words = [
            "consertar","concertar","corrigir","corrige","arruma","arrumar",
            "fix","repair","build falhou","erros de build",
            "não compila","nao compila","corrige os erros",
            "arruma os erros","conserta os erros",
        ]
        is_fix_request = any(w in description.lower() for w in fix_words)
        if is_fix_request:
            console.print("[bold cyan]🔧 Modo reparo detectado[/bold cyan]")
            from tools.project_fixer import fix_project
            fix_project(project_path, llm=self.llm, model=MODEL_CODE)
            return

        if task.task_type == "infra":
            self._handle_infra(project_path, description, task.sub_type, stack, ctx_data)
            return

        if task.task_type == "research":
            self.ask(project_path, description)
            return

        if task.task_type in ("db", "config", "security", "docs"):
            # Trata como code mas com contexto adicional
            console.print(f"[dim]→ Tratando como feature de {task.task_type}[/dim]")

        # ── 4. Feature fullstack ──────────────────────────────────────────
        if proj_type == "fullstack" or "+" in stack:
            self._add_feature_fullstack(project_path, description, stack, ctx_data or {})
            return

        # ── 5. Feature single-stack (código) ──────────────────────────────
        domain    = extract_domain(description, self.llm)
        entities  = domain.get("entities", [])
        has_auth  = domain.get("has_auth", False)

        specs     = get_manifest(stack, project_path.name, entities, has_auth)
        new_specs = _filter_existing(specs, project_path)

        if not new_specs:
            console.print("[yellow]Todos os arquivos já existem. Use devask para orientações.[/yellow]")
            return

        _show_manifest(new_specs, "Nova feature")
        if not Confirm.ask("[cyan]Gerar?[/cyan]", default=True):
            return

        extra_ctx = analysis.get("recommendations_for_new_features", description)
        files = generate_files(
            specs=new_specs, stack=stack, name=project_path.name,
            description=f"{description}\n\nEXISTING PATTERNS:\n{extra_ctx}",
            domain=domain, llm=self.llm, output_path=project_path,
        )
        if files:
            write_files(files, base_path=project_path, confirm=True, preview=True)
            # Valida e auto-corrige
            from tools.validator   import validate, print_result as _pv
            from tools.self_healer import heal as _heal
            console.print(Rule("[bold]🔍 Validando[/bold]"))
            val = validate(stack, project_path)
            _pv(val)
            if not val.passed and val.fixable_errors:
                _heal(val, project_path, self.llm, stack)

    def _handle_infra(self, project_path: Path, description: str,
                      sub_type: str, stack: str, ctx_data: dict):
        """
        Geração autônoma de infraestrutura.
        Não usa LLM para inventar configs — usa templates + dados reais do projeto + web.
        """
        console.print(Rule("[bold yellow]🐳 Geração de Infraestrutura[/bold yellow]"))

        # Carrega infra context do cache (study) se disponível, senão extrai
        cached_infra = (ctx_data or {}).get("infra", {})
        if cached_infra and cached_infra.get("database"):
            console.print("[dim]✓ Contexto de infra carregado do cache (.devai/context.json)[/dim]")
            from tools.knowledge_base import InfraContext
            ctx = InfraContext(
                stack=cached_infra.get("stack", stack.split("+")[0]),
                app_name=project_path.name,
                app_port=cached_infra.get("app_port", 3000),
                database=cached_infra.get("database", "postgres"),
                db_port=cached_infra.get("db_port", 5432),
                db_name=cached_infra.get("db_name", project_path.name.replace("-","_")),
                orm=cached_infra.get("orm", ""),
                cache=cached_infra.get("cache", ""),
                cache_port=6379,
                queue=cached_infra.get("queue", ""),
                runtime_version=cached_infra.get("runtime_version", ""),
                existing_modules=cached_infra.get("existing_modules", []),
                has_dockerfile=cached_infra.get("has_dockerfile", False),
                has_compose=cached_infra.get("has_compose", False),
                has_nginx=cached_infra.get("has_nginx", False),
                has_cicd=cached_infra.get("has_cicd", False),
                env_vars=cached_infra.get("env_vars", []),
            )
        else:
            console.print("[dim]→ Analisando projeto para extrair contexto de infra...[/dim]")
            ctx = extract_infra_context(project_path)

        # Override stack do contexto salvo se disponível
        if stack and stack != "desconhecida" and not ctx.stack:
            ctx.stack = stack.split("+")[0]  # pega só o backend em fullstack

        console.print(ctx.to_prompt_context())

        # Detecta o que gerar baseado na descrição e no que já existe
        what = _detect_infra_scope(description, ctx)
        console.print(f"\n[dim]Escopo detectado: {', '.join(what) if what else 'completo'}[/dim]")

        # Avisa sobre o que já existe
        if ctx.has_dockerfile and "docker" in (what or []):
            console.print("[yellow]⚠ Dockerfile já existe — será sobrescrito[/yellow]")
        if ctx.has_compose and "docker" in (what or []):
            console.print("[yellow]⚠ docker-compose já existe — será sobrescrito[/yellow]")

        if not Confirm.ask("\n[cyan]Gerar infraestrutura?[/cyan]", default=True):
            return

        # Gera (com pesquisa web autônoma interna)
        files = generate_infra(ctx, project_path, what if what else None)

        if not files:
            console.print("[red]✗ Nenhum arquivo de infra gerado.[/red]")
            return

        # Escreve
        write_files(files, base_path=project_path, confirm=False, preview=False)

        # Torna entrypoint executável
        ep = project_path / "scripts" / "entrypoint.sh"
        if ep.exists():
            ep.chmod(0o755)

        console.print(Panel(
            "[bold green]✅ Infraestrutura gerada![/bold green]\n\n"
            "[cyan]Subir só a infra (dev):[/cyan]\n"
            f"  make docker-dev\n\n"
            "[cyan]Subir stack completa:[/cyan]\n"
            f"  make docker-up\n\n"
            "[cyan]Ver logs:[/cyan]\n"
            f"  make logs",
            border_style="green",
        ))

    def _add_feature_fullstack(self, root: Path, description: str, stack: str, ctx_data: dict):
        """Feature em projeto fullstack — pergunta onde adicionar."""
        from rich.prompt import Prompt
        side = Prompt.ask(
            "Adicionar em qual lado?",
            choices=["backend", "frontend", "ambos"],
            default="ambos",
        )

        backend_stack  = ctx_data.get("backend_stack",  stack.split("+")[0] if "+" in stack else stack)
        frontend_stack = ctx_data.get("frontend_stack", "nextjs")
        api_contract   = ctx_data.get("analysis", {}).get("api_contract", {})

        domain = extract_domain(description, self.llm)
        entities = domain.get("entities", [])
        has_auth = domain.get("has_auth", False)

        if side in ("backend", "ambos"):
            back_path = root / "backend"
            if back_path.exists():
                specs = get_manifest(backend_stack, root.name, entities, has_auth)
                new_specs = _filter_existing(specs, back_path)
                if new_specs:
                    _show_manifest(new_specs, f"Backend — {backend_stack}")
                    if Confirm.ask("[cyan]Gerar backend?[/cyan]", default=True):
                        files = generate_files(
                            specs=new_specs, stack=backend_stack, name=root.name,
                            description=f"[BACKEND FEATURE] {description}",
                            domain=domain, llm=self.llm, output_path=back_path,
                        )
                        if files:
                            write_files(files, base_path=back_path, confirm=True, preview=True)
                            # Atualiza contrato
                            from tools.api_contract import extract_api_contract
                            cfg = ctx_data.get("summary", {})
                            api_contract = extract_api_contract(
                                files, backend_stack, entities, has_auth,
                                cfg.get("port_back", 3001), self.llm
                            )

        if side in ("frontend", "ambos"):
            front_path = root / "frontend"
            if front_path.exists():
                front_manifest = f"{frontend_stack}-client"
                specs = get_manifest(front_manifest, root.name, entities, has_auth)
                new_specs = _filter_existing(specs, front_path)
                if new_specs:
                    _show_manifest(new_specs, f"Frontend — {frontend_stack}")
                    if Confirm.ask("[cyan]Gerar frontend?[/cyan]", default=True):
                        front_ctx = api_contract.get("summary", "") if isinstance(api_contract, dict) else str(api_contract)
                        files = generate_files(
                            specs=new_specs, stack=front_manifest, name=root.name,
                            description=f"[FRONTEND FEATURE] {description}\n\nAPI CONTRACT:\n{front_ctx}",
                            domain={**domain, "api_contract": front_ctx},
                            llm=self.llm, output_path=front_path,
                        )
                        if files:
                            write_files(files, base_path=front_path, confirm=True, preview=True)

    # ══════════════════════════════════════════════════════════════════════
    # PERGUNTAR
    # ══════════════════════════════════════════════════════════════════════

    def ask(self, project_path: Path, question: str):
        console.print(Rule("[bold cyan]DevAI Ask[/bold cyan]"))
        self.llm.ensure_model(MODEL_ANALYST)

        ctx_data = load_project_context(project_path)
        if ctx_data:
            ctx = ctx_data.get("context_string", "")
        else:
            console.print("[yellow]Escaneando projeto...[/yellow]")
            ctx = scan_project(project_path).to_context_string()

        console.print(f"\n[bold]❓ {question}[/bold]\n")
        console.print(Rule("[dim]Resposta[/dim]"))
        self.llm.chat(
            model=MODEL_ANALYST,
            messages=[{"role": "user", "content": ask_prompt(question, ctx)}],
            system=ASK_SYSTEM, stream=True,
        )

    # ══════════════════════════════════════════════════════════════════════
    # HELPERS
    # ══════════════════════════════════════════════════════════════════════

    def _install_frontend_deps(self, frontend_stack: str, path: Path):
        """Instala pacotes extras necessários para o frontend fullstack."""
        if not path.exists():
            return

        if frontend_stack == "nextjs":
            extra = ["axios", "zustand", "@tanstack/react-query", "react-hook-form", "@hookform/resolvers", "zod"]
            pkg_json = path / "package.json"
            if pkg_json.exists():
                console.print("[dim]→ Instalando dependências extras do Next.js...[/dim]")
                _run(["npm", "install", "--save"] + extra, cwd=path, silent=False)

        elif frontend_stack == "angular":
            pkg_json = path / "package.json"
            if pkg_json.exists():
                console.print("[dim]→ Instalando dependências extras do Angular...[/dim]")
                _run(["npm", "install", "--save", "axios"], cwd=path, silent=False)

    def _print_analysis(self, a: dict):
        t = Table(border_style="dim", show_header=False, padding=(0, 1))
        t.add_column("", style="cyan", width=22)
        t.add_column("")
        for k, v in [
            ("Stack", a.get("stack")),
            ("Arquitetura", a.get("architecture_style")),
            ("Padrões", ", ".join(a.get("patterns_found", [])[:5])),
            ("Módulos", ", ".join(a.get("existing_modules", [])[:8])),
        ]:
            if v:
                t.add_row(k, str(v))
        console.print(t)

    def _print_done_single(self, name: str, stack: str):
        hints = {
            "nestjs":      f"cd {name} && npm run start:dev",
            "nextjs":      f"cd {name} && npm run dev",
            "angular":     f"cd {name} && ng serve",
            "spring-boot": f"cd {name} && ./mvnw spring-boot:run",
            "python":      f"cd {name} && source .venv/bin/activate && uvicorn src.main:app --reload",
            "dotnet":      f"cd {name}/{name}.Api && dotnet run",
        }
        console.print(Panel(
            f"[bold green]✅ {name} pronto![/bold green]\n\n"
            f"[cyan]Rodar:[/cyan]  {hints.get(stack, f'cd {name}')}\n\n"
            f"[cyan]Próximos passos:[/cyan]\n"
            f"  cd {name} && devstudy\n"
            f"  devfeat \"autenticação OAuth2\"\n"
            f"  devask  \"como estruturar pagamentos?\"",
            border_style="green",
        ))

    def _print_done_fullstack(self, name: str, combo: str, port_back: int, port_front: int):
        console.print(Panel(
            f"[bold green]✅ {name} — fullstack pronto![/bold green]\n\n"
            f"[cyan]Subir infra (PostgreSQL + Redis):[/cyan]\n"
            f"  cd {name} && make docker-up-dev\n\n"
            f"[cyan]Rodar:[/cyan]\n"
            f"  make dev-back    # backend  → http://localhost:{port_back}\n"
            f"  make dev-front   # frontend → http://localhost:{port_front}\n\n"
            f"[cyan]Swagger:[/cyan]  http://localhost:{port_back}/api\n\n"
            f"[cyan]Feature nova:[/cyan]\n"
            f"  cd {name}\n"
            f"  devstudy\n"
            f"  devfeat \"módulo de pagamento com Stripe\"\n"
            f"  devask  \"como funciona o fluxo de autenticação?\"",
            border_style="green",
        ))


def _write_frontend_env(frontend: str, path: Path, name: str, port_back: int, port_front: int):
    if frontend == "nextjs":
        env = path / ".env.local"
        env.write_text(
            f"NEXT_PUBLIC_API_URL=http://localhost:{port_back}/api/v1\n"
            f"NEXTAUTH_URL=http://localhost:{port_front}\n"
            f"NEXTAUTH_SECRET=change-me-{name}\n"
        )
        env_ex = path / ".env.example"
        env_ex.write_text(
            f"NEXT_PUBLIC_API_URL=http://localhost:{port_back}/api/v1\n"
            f"NEXTAUTH_URL=http://localhost:{port_front}\n"
            f"NEXTAUTH_SECRET=change-me\n"
        )
    elif frontend == "angular":
        env_file = path / "src" / "environments"
        env_file.mkdir(parents=True, exist_ok=True)
        (env_file / "environment.ts").write_text(
            f"export const environment = {{\n"
            f"  production: false,\n"
            f"  apiUrl: 'http://localhost:{port_back}/api/v1',\n"
            f"}};\n"
        )
        (env_file / "environment.prod.ts").write_text(
            f"export const environment = {{\n"
            f"  production: true,\n"
            f"  apiUrl: '/api/v1',\n"
            f"}};\n"
        )
