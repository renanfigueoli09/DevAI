#!/usr/bin/env python3
"""
DevAI — Agente Autônomo de Desenvolvimento Local

MODO AUTÔNOMO (linguagem natural):
  devai "cria projeto fullstack com nest e next para um e-commerce"
  devai "cria uma api de pedidos em spring boot com auth jwt"
  devai "adiciona docker e ci/cd no projeto atual"
  devai "quero autenticação oauth2 com google neste projeto"
  devai "cria módulo de pagamentos com stripe"

MODO EXPLÍCITO (quando você sabe exatamente o que quer):
  devai new nestjs minha-api "descrição"
  devai new nestjs+nextjs loja "e-commerce com produtos e carrinho"
  devai feature "módulo de relatórios com exportação PDF"
  devai study
  devai ask "como funciona o fluxo de auth?"

PESQUISA E CONHECIMENTO:
  devai search "NestJS JWT best practices 2025"
  devai versions nestjs
  devai knowledge           ← mostra o que o agente já sabe
  devai knowledge --clear   ← limpa o knowledge base
"""

import sys
import os
import argparse
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Capture the working directory at startup BEFORE any subprocess changes it
_STARTUP_CWD = Path(os.getcwd()).resolve()

console = Console()


def print_banner():
    console.print(Panel(
        Text("⚡ DevAI — Agente Autônomo de Desenvolvimento", justify="center", style="bold cyan"),
        subtitle="[dim]Pesquisa · Planeja · Executa · Valida · Entrega[/dim]",
        border_style="cyan",
    ))


# ─── Modo autônomo ────────────────────────────────────────────────────────────

def run_autonomous(text: str, project_path: Path):
    """
    Ponto de entrada autônomo: entende o pedido, pesquisa, planeja, executa.
    """
    from tools.llm_client import OllamaClient
    from tools.intent_analyzer import analyze
    from tools.research_agent import research_for_task
    from tools.planner import Planner
    from config import MODEL_CODE

    llm = OllamaClient()
    llm.ensure_model(MODEL_CODE)

    # 1. Entende o pedido
    from rich.rule import Rule
    console.print(Rule("[bold]🧠 Analisando pedido[/bold]"))
    intent = analyze(text, project_path, llm, MODEL_CODE)

    # 2. Define caminhos
    if intent.action == "new":
        output_path = _STARTUP_CWD / intent.project_name
    else:
        output_path = project_path

    # 3. Pesquisa na web (autônomo)
    console.print(Rule("[bold]🔍 Pesquisando na web[/bold]"))
    stacks = intent.stacks or []
    research_ctx = research_for_task(
        task_description=intent.description,
        stacks=stacks,
        task_type=intent.action,
        llm=llm,
        model=MODEL_CODE,
    )

    # 4. Plano de execução
    planner = Planner(llm, MODEL_CODE)

    if intent.action == "new":
        plan = planner.build_new_project_plan(intent, output_path, research_ctx)
    elif intent.action in ("infra", "docker", "nginx", "cicd"):
        plan = planner.build_infra_plan(intent, output_path, research_ctx)
    elif intent.action == "fix":
        # Modo reparo — não gera arquivos, apenas conserta o que existe
        from tools.project_fixer import fix_project
        fix_project(output_path, llm=llm, model=MODEL_CODE)
        return
    elif intent.action in ("feature", "code", "db", "config", "security"):
        plan = planner.build_feature_plan(intent, output_path, research_ctx)
    elif intent.action == "ask":
        from orchestrator import Orchestrator
        Orchestrator().ask(output_path, text)
        return
    elif intent.action == "study":
        from orchestrator import Orchestrator
        Orchestrator().study_project(output_path)
        return
    elif intent.action == "search":
        from tools.research_agent import research_and_answer
        answer = research_and_answer(text, llm, MODEL_CODE)
        console.print(answer)
        return
    else:
        plan = planner.build_feature_plan(intent, output_path, research_ctx)

    # 5. Executa o plano
    planner.execute(plan)


# ─── Comandos explícitos ──────────────────────────────────────────────────────

SINGLE_STACKS = ["nestjs", "nextjs", "angular", "spring-boot", "python", "dotnet"]
FULLSTACK_ALIASES = {
    "nest+next":    "nestjs+nextjs",
    "nest+angular": "nestjs+angular",
    "spring+next":  "spring-boot+nextjs",
    "spring+ng":    "spring-boot+angular",
    "fastapi+next": "python+nextjs",
    "fastapi+ng":   "python+angular",
    "dotnet+next":  "dotnet+nextjs",
    "dotnet+ng":    "dotnet+angular",
}
FULLSTACK_STACKS = [
    "nestjs+nextjs", "nestjs+angular",
    "spring-boot+nextjs", "spring-boot+angular",
    "python+nextjs", "python+angular",
    "dotnet+nextjs", "dotnet+angular",
]

def resolve_stack(s: str) -> str:
    return FULLSTACK_ALIASES.get(s, s)

def is_fullstack(s: str) -> bool:
    return "+" in s


def cmd_new(args):
    stack = resolve_stack(args.stack)
    desc  = " ".join(args.description)
    # Rota para o modo autônomo com intent forçado
    text = f"criar projeto {stack} {args.name} {desc}"
    from tools.llm_client import OllamaClient
    from tools.intent_analyzer import Intent, analyze
    from tools.research_agent import research_for_task
    from tools.planner import Planner
    from config import MODEL_CODE

    llm = OllamaClient()
    llm.ensure_model(MODEL_CODE)

    # Intent explícito (mais rápido que análise)
    if is_fullstack(stack):
        back, front = stack.split("+")
        intent = Intent(
            action="new", project_name=args.name, description=desc,
            backend_stack=back, frontend_stack=front,
            needs_docker=True, needs_cicd=True, needs_nginx=True,
            needs_auth="auth" in desc.lower() or "jwt" in desc.lower(),
        )
    else:
        intent = Intent(
            action="new", project_name=args.name, description=desc,
            backend_stack=stack if stack in ("nestjs","spring-boot","python","dotnet") else "",
            frontend_stack=stack if stack in ("nextjs","angular") else "",
            needs_docker=True, needs_cicd=True,
            needs_auth="auth" in desc.lower() or "jwt" in desc.lower(),
        )

    output_path = _STARTUP_CWD / args.name
    stacks = [s for s in [intent.backend_stack, intent.frontend_stack] if s]

    console.print("[dim]🔍 Pesquisando...[/dim]")
    research_ctx = research_for_task(desc, stacks, "new", llm, MODEL_CODE)

    planner = Planner(llm, MODEL_CODE)
    plan = planner.build_new_project_plan(intent, output_path, research_ctx)
    planner.execute(plan)


def cmd_feature(args):
    from orchestrator import Orchestrator
    project_path = Path(args.path or str(_STARTUP_CWD))
    Orchestrator().add_feature(project_path, " ".join(args.description))


def cmd_study(args):
    from orchestrator import Orchestrator
    Orchestrator().study_project(Path(args.path or str(_STARTUP_CWD)))


def cmd_ask(args):
    from orchestrator import Orchestrator
    Orchestrator().ask(Path(args.path or str(_STARTUP_CWD)), " ".join(args.question))


def cmd_search(args):
    from tools.llm_client import OllamaClient
    from tools.research_agent import research_and_answer
    from config import MODEL_CODE
    query = " ".join(args.query)
    console.print(f"\n[cyan]🔍 Pesquisando:[/cyan] {query}\n")
    llm = OllamaClient()
    save = not args.no_save
    result = research_and_answer(query, llm, MODEL_CODE, save=save)
    console.print(result)
    if save:
        console.print(f"\n[dim]✓ Salvo no knowledge base — disponível para gerações futuras[/dim]")


def cmd_versions(args):
    from tools.web_research import fetch_stack_versions, cache_info
    from rich.table import Table
    if args.clear_cache:
        from tools.web_research import clear_cache
        clear_cache()
        return
    stacks = [args.stack] if args.stack else SINGLE_STACKS
    for stack in stacks:
        console.print(f"\n[bold cyan]{stack}[/bold cyan]")
        vers = fetch_stack_versions(stack)
        if vers:
            t = Table(border_style="dim", show_header=False, padding=(0,1))
            t.add_column("Pacote", style="cyan")
            t.add_column("Versao", style="green")
            for pkg, ver in vers.items():
                t.add_row(pkg, ver)
            console.print(t)
        else:
            console.print("  [dim]sem dados (verifique conexão)[/dim]")


def cmd_knowledge(args):
    from rich.table import Table
    from tools.vector_store import list_all, clear_all, export_markdown

    if args.clear:
        clear_all()
        console.print("[green]✓ Training store limpo[/green]")
        return

    if args.export:
        export_dir = export_markdown()
        console.print(f"\n[dim]Para commitar: cd {Path(os.environ.get('DEVAI_DIR', '.')).resolve()} && git add training/ && git commit -m 'training: update'[/dim]")
        return

    from tools.vector_store import stats as ts_stats, backfill_embeddings

    # Gera embeddings faltantes em background
    backfill_embeddings()

    s = ts_stats()
    items = list_all()
    if not items:
        console.print("[dim]Training store vazio.[/dim]")
        console.print("[dim]  devai search \"nestjs mongodb 2025\"[/dim]")
        console.print("[dim]  devai train --project /path/to/reference/[/dim]")
        return

    # Status da busca semântica
    try:
        from tools.embeddings import model_available
        sem = "[green]✓ semântica ativa[/green]" if model_available() else "[yellow]○ keyword only (instale: ollama pull nomic-embed-text)[/yellow]"
    except Exception:
        sem = "[dim]desconhecido[/dim]"

    console.print(f"\n[bold cyan]🧠 Training Store[/bold cyan]")
    console.print(f"   {s['total']} itens | {s['with_embedding']} com embedding | busca {sem}")

    t = Table(border_style="dim", show_lines=False, show_header=True)
    t.add_column("Tópico",   style="cyan",  width=14)
    t.add_column("Key",      style="white", max_width=36)
    t.add_column("Fonte",    style="dim",   width=14)
    t.add_column("Emb",      style="green", width=4)
    t.add_column("Idade",    style="dim",   width=7)
    for item in items[:30]:
        t.add_row(
            item["topic"], item["key"][:34],
            item["source"][:12],
            "✓" if item.get("has_embedding") else "○",
            f"{item['age_hours']}h",
        )
    console.print(t)
    if s["total"] > 30:
        console.print(f"  [dim]... e mais {s['total']-30} itens[/dim]")
    console.print(f"\n[dim]Commitar: git add training/ && git commit -m 'training: update knowledge'[/dim]")


def cmd_train(args):
    """Treina o agente com arquivos ou projeto de referência."""
    from tools.llm_client import OllamaClient
    from tools.file_trainer import train_file, train_directory, train_project
    from config import MODEL_CODE
    import os

    llm = OllamaClient()
    llm.ensure_model(MODEL_CODE)

    if args.project:
        path = Path(args.project)
        if not path.exists():
            console.print(f"[red]✗ Caminho não encontrado: {path}[/red]")
            return
        train_project(path, llm, MODEL_CODE)

    elif args.dir:
        path = Path(args.dir)
        if not path.exists():
            console.print(f"[red]✗ Diretório não encontrado: {path}[/red]")
            return
        pattern = args.pattern or "*.ts"
        train_directory(path, llm, MODEL_CODE, recursive=args.recursive, pattern=pattern)

    elif args.files:
        for f in args.files:
            path = Path(f)
            train_file(path, llm, MODEL_CODE, label=args.label)

    else:
        console.print("[yellow]Use --file, --dir ou --project para especificar o que treinar[/yellow]")
        console.print("  devai train src/configs/redis.sentinels.config.ts")
        console.print("  devai train --dir src/configs/")
        console.print("  devai train --project /path/to/reference-project/")


def cmd_fix(args):
    """Repara projeto: build → instala deps → corrige erros → roda → corrige runtime → finaliza."""
    from tools.llm_client import OllamaClient
    from tools.project_fixer import fix_project, run_verify_fix_loop
    from tools.project_fixer import _detect_stack
    from config import MODEL_CODE
    import os
    project_path = Path(args.path or str(_STARTUP_CWD))
    console.print(f"[bold cyan]🔧 devai fix[/bold cyan] — {project_path}")
    llm = OllamaClient()
    llm.ensure_model(MODEL_CODE)

    if args.run:
        # Modo completo: build + run + verify
        from tools.project_fixer import _detect_stack
        stack = _detect_stack(project_path)
        ports = {"nestjs":3000,"nextjs":3000,"angular":4200,"spring-boot":8080,"python":8000,"dotnet":5000}
        port = ports.get(stack, 3000)
        run_verify_fix_loop(project_path, stack, port, llm=llm, model=MODEL_CODE, max_rounds=args.rounds)
    else:
        fix_project(project_path, llm=llm, model=MODEL_CODE, max_rounds=args.rounds)


def cmd_list(args):
    console.print("\n[bold cyan]Single-stack[/bold cyan]")
    for s in SINGLE_STACKS:
        console.print(f"  devai new [cyan]{s}[/cyan] <nome> \"descrição\"")
    console.print("\n[bold cyan]Fullstack[/bold cyan]")
    for s in FULLSTACK_STACKS:
        console.print(f"  devai new [cyan]{s}[/cyan] <nome> \"descrição\"")
    console.print("\n[bold cyan]Aliases[/bold cyan]")
    for a, t in FULLSTACK_ALIASES.items():
        console.print(f"  [dim]{a}[/dim] → {t}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print_banner()

    # Modo autônomo: devai "texto livre"
    if len(sys.argv) == 2 and not sys.argv[1].startswith("-"):
        arg = sys.argv[1]
        # Se não é um subcomando, trata como pedido autônomo
        known_cmds = {"new","feature","study","ask","search","versions","knowledge","list","version","fix"}
        if arg not in known_cmds:
            run_autonomous(arg, _STARTUP_CWD)
            return

    parser = argparse.ArgumentParser(
        prog="devai",
        description="Agente autônomo de desenvolvimento",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    # devai new
    p_new = sub.add_parser("new", help="Cria projeto")
    p_new.add_argument("stack", help="Stack ou combo (ex: nestjs, nestjs+nextjs)")
    p_new.add_argument("name", help="Nome do projeto")
    p_new.add_argument("description", nargs="+", help="Descrição")
    p_new.set_defaults(func=cmd_new)

    # devai feature
    p_feat = sub.add_parser("feature", help="Adiciona feature ao projeto")
    p_feat.add_argument("description", nargs="+")
    p_feat.add_argument("--path")
    p_feat.set_defaults(func=cmd_feature)

    # devai study
    p_study = sub.add_parser("study", help="Estuda o projeto atual")
    p_study.add_argument("--path")
    p_study.set_defaults(func=cmd_study)

    # devai ask
    p_ask = sub.add_parser("ask", help="Pergunta sobre o projeto")
    p_ask.add_argument("question", nargs="+")
    p_ask.add_argument("--path")
    p_ask.set_defaults(func=cmd_ask)

    # devai search
    p_search = sub.add_parser("search", help="Pesquisa na web")
    p_search.add_argument("query", nargs="+")
    p_search.add_argument("--no-save", action="store_true", help="Não salva no knowledge base")
    p_search.set_defaults(func=cmd_search)

    # devai versions
    p_ver = sub.add_parser("versions", help="Versões dos pacotes")
    p_ver.add_argument("stack", nargs="?")
    p_ver.add_argument("--clear-cache", action="store_true")
    p_ver.set_defaults(func=cmd_versions)

    # devai knowledge
    p_kb = sub.add_parser("knowledge", help="Gerencia o training store")
    p_kb.add_argument("--clear",  action="store_true", help="Limpa todo o store")
    p_kb.add_argument("--export", action="store_true", help="Exporta para markdown (commitável)")
    p_kb.set_defaults(func=cmd_knowledge)

    # devai train
    p_train = sub.add_parser("train", help="Treina o agente com arquivos de referência")
    p_train.add_argument("files", nargs="*", help="Arquivos para treinar")
    p_train.add_argument("--dir",       help="Diretório de arquivos")
    p_train.add_argument("--project",   help="Projeto completo de referência")
    p_train.add_argument("--pattern",   default="*.ts", help="Padrão de arquivo (default: *.ts)")
    p_train.add_argument("--recursive", action="store_true", help="Recursivo")
    p_train.add_argument("--label",     help="Label para o conhecimento salvo")
    p_train.set_defaults(func=cmd_train)

    # devai fix
    p_fix = sub.add_parser("fix", help="Repara erros de build no projeto atual (roda até funcionar)")
    p_fix.add_argument("--path", help="Caminho do projeto (padrão: diretório atual)")
    p_fix.add_argument("--rounds", type=int, default=5, help="Máximo de rodadas de reparo (padrão: 5)")
    p_fix.add_argument("--run", action="store_true", help="Após build passar, tenta iniciar o app e verifica runtime")
    p_fix.set_defaults(func=cmd_fix)

    # devai list
    p_list = sub.add_parser("list", help="Lista stacks disponíveis")
    p_list.set_defaults(func=cmd_list)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return
    args.func(args)


def cmd_profile(args):
    """Mostra e gerencia o perfil de preferências do usuário."""
    from tools.user_profile import show_profile, save_profile, load_profile
    
    if hasattr(args, 'set') and args.set:
        profile = load_profile()
        for item in args.set:
            if '=' in item:
                k, v = item.split('=', 1)
                k = k.strip(); v = v.strip()
                if k in ('stack','default_stack'):
                    profile['preferences']['default_stack'] = v
                elif k in ('db','default_db'):
                    profile['preferences']['default_db'] = v
                elif k == 'language':
                    profile['preferences']['code_language'] = v
                elif k == 'minimal':
                    profile['preferences']['minimal'] = v.lower() in ('true','1','sim','yes')
        save_profile(profile)
        console.print("[green]✓ Preferências salvas[/green]")
    
    show_profile()


if __name__ == "__main__":
    main()
