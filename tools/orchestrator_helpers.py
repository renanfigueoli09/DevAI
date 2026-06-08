"""
Orchestrator Helpers — funções de step para o Planner.

Cada função recebe `ctx` (contexto compartilhado do plano) e retorna um resultado.
O contexto é mutado para passar dados entre steps.

ctx contém:
  intent        → Intent (stacks, nome, descrição, extras)
  project_path  → Path raiz do projeto
  research_ctx  → string de conhecimento pesquisado
  llm, model    → cliente LLM
  domain        → dict de entidades/auth (preenchido pelo step_domain)
  back_files    → arquivos gerados do backend
  front_files   → arquivos gerados do frontend
  api_contract  → contrato da API extraído do backend
"""

import os
import subprocess
from pathlib import Path
from rich.console import Console
from rich.rule import Rule

console = Console()


def _run(cmd: list, cwd: Path, silent: bool = True) -> bool:
    try:
        r = subprocess.run(cmd, cwd=str(cwd), capture_output=silent, text=True)
        return r.returncode == 0
    except FileNotFoundError:
        return False


# ─── Steps ────────────────────────────────────────────────────────────────────

def step_shared_files(ctx: dict, **_):
    """Cria diretório raiz, .gitignore, .env.example, git init."""
    intent       = ctx["intent"]
    project_path = ctx["project_path"]
    llm          = ctx["llm"]

    is_fullstack = intent.is_fullstack
    stack        = intent.backend_stack or intent.frontend_stack

    project_path.mkdir(parents=True, exist_ok=True)

    from tools.gitignore import write_gitignore, write_env_example
    from tools.db_strategy import detect_database
    from tools.domain_extractor import _has_auth_requested
    write_gitignore(stack, project_path)
    _db_type = detect_database(intent.description)
    _has_auth = _has_auth_requested(intent.description)
    _desc = intent.description.lower()
    _extra = []
    if any(k in _desc for k in ["redis-sentinel","sentinel","redis sentinel"]):
        _extra.append("redis-sentinel")
    elif any(k in _desc for k in ["redis","cache","bull"]):
        _extra.append("redis")
    if any(k in _desc for k in ["kafka","rabbitmq","amqp"]):
        _extra.append("kafka")
    if any(k in _desc for k in ["elasticsearch","elastic"]):
        _extra.append("elasticsearch")
    write_env_example(stack, project_path, intent.project_name,
                      db_type=_db_type, has_auth=_has_auth, extra_services=_extra)

    if not (project_path / ".git").exists():
        _run(["git", "init"], project_path)

    if is_fullstack:
        from tools.fullstack import write_shared_files, COMBOS
        cfg = COMBOS.get(intent.combo, COMBOS.get(
            f"{intent.backend_stack}+{intent.frontend_stack}", {}
        ))
        if cfg:
            write_shared_files(intent.project_name, intent.description, cfg, project_path)

    return {"path": str(project_path)}


def step_scaffold_backend(ctx: dict, **_):
    """Scaffold do backend com CLI do framework."""
    intent       = ctx["intent"]
    project_path = ctx["project_path"]
    stack        = intent.backend_stack

    if intent.is_fullstack:
        target = project_path / "backend"
    else:
        target = project_path

    from tools.scaffold import scaffold_project
    ok = scaffold_project(stack=stack, name=target.name,
                          output_dir=target, description=intent.description)
    target.mkdir(parents=True, exist_ok=True)

    from tools.gitignore import write_gitignore, write_env_example
    from tools.db_strategy import detect_database
    from tools.domain_extractor import _has_auth_requested
    write_gitignore(stack, target)
    _db_type = detect_database(intent.description)
    _has_auth = _has_auth_requested(intent.description)
    write_env_example(stack, target, intent.project_name,
                      db_type=_db_type, has_auth=_has_auth)

    ctx["backend_path"] = target
    return {"ok": ok, "path": str(target)}


def step_scaffold_frontend(ctx: dict, **_):
    """Scaffold do frontend com CLI do framework."""
    intent       = ctx["intent"]
    project_path = ctx["project_path"]
    stack        = intent.frontend_stack
    target       = project_path / "frontend"

    from tools.scaffold import scaffold_project
    ok = scaffold_project(stack=stack, name="frontend",
                          output_dir=target, description=intent.description)
    target.mkdir(parents=True, exist_ok=True)

    from tools.gitignore import write_gitignore
    write_gitignore(stack, target)

    # .env do frontend
    from tools.fullstack import COMBOS
    cfg = COMBOS.get(intent.combo, {})
    port_back = cfg.get("port_back", 3001)
    port_front = cfg.get("port_front", 3000)
    _write_frontend_env(stack, target, intent.project_name, port_back, port_front)

    ctx["frontend_path"] = target
    return {"ok": ok, "path": str(target)}


def step_domain(ctx: dict, **_):
    """Extrai entidades de domínio da descrição."""
    intent       = ctx["intent"]
    llm          = ctx["llm"]
    research_ctx = ctx.get("research_ctx", "")

    from tools.domain_extractor import extract_domain, _has_auth_requested
    from tools.db_strategy import detect_database

    # ── REGRA: detecção determinística SEMPRE na descrição original ──────────
    original_desc = intent.description

    # Detecta banco e auth na descrição — sem contaminação do research_ctx
    db_type  = detect_database(original_desc)
    has_auth = _has_auth_requested(original_desc)

    # ── Clarificação interativa — pergunta o que não ficou claro ─────────────
    try:
        from tools.clarifier import clarify_if_needed
        stack = intent.backend_stack or intent.frontend_stack or "nestjs"
        clarification = clarify_if_needed(original_desc, stack, interactive=True)

        # Respostas do usuário têm prioridade sobre detecção automática
        if clarification.db_type:
            db_type = clarification.db_type
        if clarification.has_auth is not None:
            has_auth = clarification.has_auth
        if clarification.extra_services:
            ctx["extra_services"] = clarification.extra_services
        if clarification.asked_anything:
            console.print(f"  [green]✓[/green] Confirmado: {db_type} | auth={has_auth} | extras={clarification.extra_services}")
    except Exception as _ce:
        console.print(f"  [dim]⚠ Clarifier: {_ce}[/dim]")

    # Extrai entidades e domínio com a descrição LIMPA (sem research_ctx)
    domain = extract_domain(original_desc, llm)

    # Força os valores determinísticos/confirmados pelo usuário
    domain["db_type"]  = db_type
    domain["has_auth"] = has_auth

    ctx["domain"] = domain
    console.print(f"  Banco: {db_type} | Auth: {has_auth} | Idioma: {domain.get('language','portuguese')}")
    return domain


def step_generate_backend(ctx: dict, **_):
    """Gera todos os arquivos de domínio do backend."""
    intent       = ctx["intent"]
    domain       = ctx.get("domain", {})
    research_ctx = ctx.get("research_ctx", "")
    llm          = ctx["llm"]

    path = ctx.get("backend_path", ctx["project_path"])
    stack = intent.backend_stack
    entities = domain.get("entities", [])
    has_auth = domain.get("has_auth", False)

    from tools.manifests import get_manifest
    from tools.generator import generate_files
    from tools.file_writer import write_files
    from tools.db_strategy import detect_database

    # Detecta db_type — descrição tem prioridade sobre LLM domain (evita default postgres)
    db_type = detect_database(intent.description) or domain.get("db_type") or "postgres"
    # Garante que o domain também tem o db_type correto para uso posterior
    domain["db_type"] = db_type

    specs = get_manifest(stack, intent.project_name, entities, has_auth, db_type=db_type)

    # Filtra o que o scaffold já criou
    specs = [s for s in specs if not (path / s.path).exists()]

    if not specs:
        console.print("  [dim]Todos os arquivos já existem[/dim]")
        ctx["back_files"] = []
        return []

    # Enriquece descrição com conhecimento pesquisado e padrões aprendidos
    from tools.file_trainer import get_relevant_templates
    from tools.vector_store import search_relevant

    # Detecta tópicos de código relevantes (NÃO injeta docker/devops no código)
    _code_topics = ["nestjs", "spring", "python", "dotnet", "mongodb",
                    "typeorm", "mongoose", "auth", "typescript", "common-errors"]
    _infra_topics = ["docker", "devops", "github-actions", "docker-advanced",
                     "docker-patterns", "ci", "nginx", "kubernetes"]

    learned = get_relevant_templates(intent.description)
    ts_ctx  = search_relevant(
        intent.description, limit=4,
        exclude_topics=_infra_topics,   # nunca injeta Docker no código
    )
    combined = [p for p in [research_ctx[:500], learned[:350], ts_ctx[:350]] if p]
    if combined:
        chars = sum(len(p) for p in combined)
        console.print(f"  [dim]✓ Treinamento de código: {chars} chars (infra excluída)[/dim]")
    desc = intent.description
    if combined:
        desc = f"{intent.description}\n\n{'\n\n'.join(combined)}"

    files = generate_files(
        specs=specs, stack=stack,
        name=intent.project_name,
        description=desc,
        domain=domain,
        llm=llm, output_path=path,
    )
    # Se gerou poucos arquivos ou nenhum, auto-estuda e tenta de novo
    if not files or len(files) < 2:
        console.print(f"  [yellow]→ Poucos arquivos gerados — estudando {stack}+{db_type}...[/yellow]")
        try:
            from scripts.study import study_topic, SEARCH_CURRICULUM
            study_key = f"{stack}_{db_type}".replace("-","_")
            searches  = SEARCH_CURRICULUM.get(study_key, [])[:3]
            if searches:
                from tools.llm_client import OllamaClient
                from config import MODEL_CODE
                _llm = OllamaClient()
                study_topic(study_key, searches, _llm, MODEL_CODE, intensive=True)
                console.print(f"  [green]✓[/green] Estudado: {study_key}")
                # Tenta gerar novamente
                files = generate_files(specs, stack, intent.project_name,
                                       desc, domain, llm, path)
        except Exception as _se:
            console.print(f"  [dim]⚠ Auto-study: {_se}[/dim]")

    if files:
        write_files(files, base_path=path, confirm=False, preview=False)

        # Remove diretórios inválidos criados por alucinação do LLM
        from tools.code_fixer import (
            integrate_module_into_app, ensure_db_in_app_module, cleanup_invalid_dirs
        )
        removed = cleanup_invalid_dirs(path)
        if removed:
            console.print(f"  [yellow]⚠ Removidos {len(removed)} diretório(s) inválido(s): {', '.join(removed)}[/yellow]")

        # Garante conexão do banco no app.module.ts (determinístico)
        app_module = path / "src" / "app.module.ts"
        db_type = domain.get("db_type", "postgres")
        db_name = intent.project_name.replace("-", "_")
        if ensure_db_in_app_module(app_module, db_type, db_name):
            console.print(f"  [green]✓[/green] Conexão {db_type} adicionada ao AppModule")

        # Integra cada módulo no app.module.ts (SEMPRE, não só em features)
        app_module = path / "src" / "app.module.ts"
        for entity in entities:
            el = entity.lower()
            module_name = f"{entity}Module"

            # Detecta o path correto do módulo (pode estar em subdiretório)
            module_files = [
                f for f in (path / "src").rglob(f"{el}.module.ts")
                if not any(x in str(f) for x in ["node_modules", "dist"])
            ]
            if module_files:
                # Calcula path relativo ao src/
                rel = module_files[0].relative_to(path / "src")
                import_path = "./" + str(rel).replace("\\", "/").replace(".ts", "")
            else:
                import_path = f"./{el}/{el}.module"

            new_content = integrate_module_into_app(app_module, module_name, import_path)
            if new_content:
                app_module.write_text(new_content, encoding="utf-8")
                console.print(f"  [green]✓[/green] {module_name} → AppModule")

        # Auth: só integra se foi pedido
        if has_auth:
            new_content = integrate_module_into_app(
                app_module, "AuthModule", "./auth/auth.module"
            )
            if new_content:
                app_module.write_text(new_content, encoding="utf-8")
                console.print("  [green]✓[/green] AuthModule → AppModule")

    ctx["back_files"] = files or []
    return files or []


def step_api_contract(ctx: dict, **_):
    """Extrai o contrato de API do backend gerado."""
    intent   = ctx["intent"]
    back_files = ctx.get("back_files", [])
    llm      = ctx["llm"]

    from tools.fullstack import COMBOS
    cfg = COMBOS.get(intent.combo, {})
    port_back = cfg.get("port_back", 3001)

    from tools.api_contract import extract_api_contract
    domain = ctx.get("domain", {})
    contract = extract_api_contract(
        backend_files=back_files,
        stack=intent.backend_stack,
        entities=domain.get("entities", []),
        has_auth=domain.get("has_auth", False),
        api_port=port_back,
        llm=llm,
    )
    ctx["api_contract"] = contract
    return contract


def step_generate_frontend(ctx: dict, **_):
    """Gera todos os arquivos do frontend com contexto da API."""
    intent       = ctx["intent"]
    domain       = ctx.get("domain", {})
    api_contract = ctx.get("api_contract", {})
    research_ctx = ctx.get("research_ctx", "")
    llm          = ctx["llm"]

    path  = ctx.get("frontend_path", ctx["project_path"] / "frontend")
    stack = intent.frontend_stack
    front_manifest = f"{stack}-client"

    from tools.fullstack import COMBOS
    cfg = COMBOS.get(intent.combo, {})
    port_back = cfg.get("port_back", 3001)

    from tools.manifests import get_manifest
    from tools.generator import generate_files
    from tools.file_writer import write_files

    specs = get_manifest(front_manifest, intent.project_name,
                         domain.get("entities", []), domain.get("has_auth", False),
                         api_port=port_back)
    specs = [s for s in specs if not (path / s.path).exists()]

    contract_summary = api_contract.get("summary", "") if isinstance(api_contract, dict) else ""

    desc = (
        f"{intent.description}\n\n"
        f"=== BACKEND API CONTRACT ===\n{contract_summary}\n\n"
        f"{research_ctx[:800]}"
    )

    files = generate_files(
        specs=specs, stack=front_manifest,
        name=intent.project_name,
        description=desc,
        domain={**domain, "api_contract": contract_summary, "role": "frontend"},
        llm=llm, output_path=path,
    )
    if files:
        write_files(files, base_path=path, confirm=False, preview=False)

    ctx["front_files"] = files or []

    # Instala dependências extras
    _install_frontend_extra_deps(stack, path)
    return files or []


def step_infra(ctx: dict, what=None, **_):
    """Gera infraestrutura completa com pesquisa de versões."""
    intent       = ctx["intent"]
    domain       = ctx.get("domain", {})          # ← fix NameError
    research_ctx = ctx.get("research_ctx", "")

    # Detecta o projeto (backend ou raiz)
    if intent.is_fullstack:
        infra_path = ctx["project_path"]
        check_path = ctx.get("backend_path", infra_path / "backend")
    else:
        infra_path = ctx.get("backend_path", ctx["project_path"])
        check_path = infra_path

    from tools.knowledge_base import extract_infra_context
    from tools.infra_generator import generate_infra
    from tools.file_writer import write_files
    from tools.db_strategy import detect_database, get_strategy

    infra_ctx = extract_infra_context(check_path)

    # Invalida cache se o banco do contexto salvo difere do banco pedido na descrição
    _desc_db = detect_database(intent.description)
    if _desc_db and infra_ctx.database and infra_ctx.database != _desc_db:
        console.print(
            f"  [yellow]⚠ Cache tem banco '{infra_ctx.database}', "
            f"descrição pede '{_desc_db}' — ignorando cache de banco[/yellow]"
        )
        infra_ctx.database = _desc_db

    # ── OVERRIDE com dados do domínio (mais confiável que file scan) ──────────
    # O db_type da descrição tem prioridade sobre o detectado no package.json
    db_type_from_domain = domain.get("db_type") or detect_database(intent.description)
    if db_type_from_domain:
        strategy = get_strategy(db_type_from_domain)
        infra_ctx.database = db_type_from_domain
        infra_ctx.orm      = strategy.orm
        if strategy.docker_port:
            infra_ctx.db_port = strategy.docker_port
        # Clear stale SQL vars when using NoSQL — env_vars may be list or dict
        if strategy.is_nosql:
            stale_sql_vars = {"DB_HOST","DB_PORT","DB_NAME","DB_USER","DB_PASS",
                              "POSTGRES_DB","POSTGRES_USER","POSTGRES_PASSWORD"}
            ev = infra_ctx.env_vars
            if isinstance(ev, dict):
                infra_ctx.env_vars = {k: v for k, v in ev.items() if k not in stale_sql_vars}
            elif isinstance(ev, list):
                # list of {"name": k, "value": v} format
                infra_ctx.env_vars = [e for e in ev if isinstance(e, dict)
                                      and e.get("name") not in stale_sql_vars]
            else:
                infra_ctx.env_vars = {}
        console.print(
            f"  [dim]→ Banco: [bold]{db_type_from_domain}[/bold] "
            f"(porta: {infra_ctx.db_port} | ORM: {strategy.orm})[/dim]"
        )

    if not infra_ctx.stack:
        infra_ctx.stack = intent.backend_stack or ""
    infra_ctx.app_name = intent.project_name

    # Cache/Redis pedido na descrição?
    if any(w in intent.description.lower() for w in ["redis","cache","session store"]):
        infra_ctx.cache = "redis"

    # RabbitMQ/Kafka pedido?
    if any(w in intent.description.lower() for w in ["rabbitmq","rabbit","amqp"]):
        infra_ctx.queue = "rabbitmq"
        infra_ctx.queue_port = 5672
    elif any(w in intent.description.lower() for w in ["kafka"]):
        infra_ctx.queue = "kafka"
        infra_ctx.queue_port = 9092

    # Para fullstack, ajusta as portas
    if intent.is_fullstack:
        from tools.fullstack import COMBOS
        cfg = COMBOS.get(intent.combo, {})
        if cfg:
            infra_ctx.app_port = cfg.get("port_back", infra_ctx.app_port)

    files = generate_infra(infra_ctx, infra_path, what)
    if files:
        # Torna entrypoint executável
        for f in files:
            if "entrypoint" in f.get("path", "") or f.get("path", "").endswith(".sh"):
                fp = infra_path / f["path"]
                if fp.exists():
                    fp.chmod(0o755)

        write_files(files, base_path=infra_path, confirm=False, preview=False)

    return files or []


def step_cicd(ctx: dict, **_):
    """Gera GitHub Actions CI/CD workflow."""
    intent   = ctx["intent"]
    domain   = ctx.get("domain", {})
    infra_path = ctx.get("backend_path", ctx["project_path"])

    from tools.knowledge_base import extract_infra_context
    from tools.infra_generator import _gen_github_ci
    from tools.file_writer import write_files

    infra_ctx = extract_infra_context(infra_path)
    if not infra_ctx.stack:
        infra_ctx.stack = intent.backend_stack or ""
    infra_ctx.app_name = intent.project_name

    ci_content = _gen_github_ci(infra_ctx)
    files = [{"path": ".github/workflows/ci.yml", "content": ci_content}]
    write_files(files, base_path=ctx["project_path"], confirm=False, preview=False)
    return files


def step_validate_and_fix(ctx: dict, side: str = "backend", **_):
    """Valida e auto-corrige erros de compilação."""
    intent = ctx["intent"]
    llm    = ctx["llm"]
    domain = ctx.get("domain", {})

    if side == "backend":
        path  = ctx.get("backend_path", ctx["project_path"])
        stack = intent.backend_stack
        files = ctx.get("back_files", [])
        # Install database-specific packages
        _install_db_packages(stack, domain, path)
    elif side == "frontend":
        path  = ctx.get("frontend_path", ctx["project_path"] / "frontend")
        stack = intent.frontend_stack
        files = ctx.get("front_files", [])
    else:
        path  = ctx["project_path"]
        stack = intent.backend_stack or intent.frontend_stack
        files = ctx.get("back_files", []) + ctx.get("front_files", [])

    if not stack:
        return {"skipped": True}

    from tools.setup_runner import setup_env, install_deps
    from tools.validator import validate, print_result
    from tools.self_healer import heal

    # Setup
    setup_env(path, stack, intent.project_name)
    ok, msg = install_deps(path, stack)
    if not ok:
        console.print(f"  [yellow]⚠ deps: {msg[:100]}[/yellow]")

    # Valida
    result = validate(stack, path)
    print_result(result)

    # Corrige
    if not result.passed:
        result = heal(result, path, llm, stack, files)

    return {"passed": result.passed, "errors": result.error_count}


def step_save_context(ctx: dict, **_):
    """Salva contexto completo para uso futuro."""
    intent       = ctx["intent"]
    project_path = ctx["project_path"]
    domain       = ctx.get("domain", {})
    api_contract = ctx.get("api_contract", {})

    from tools.file_writer import save_project_context
    from tools.knowledge_base import extract_infra_context

    back_path = ctx.get("backend_path", project_path)
    infra_ctx = extract_infra_context(back_path)

    save_project_context(project_path, {
        "summary": {
            "name": intent.project_name,
            "stack": intent.combo if intent.is_fullstack else intent.backend_stack,
            "type": "fullstack" if intent.is_fullstack else "single",
        },
        "analysis": domain,
        "infra": {
            "stack": infra_ctx.stack,
            "app_port": infra_ctx.app_port,
            "database": infra_ctx.database,
            "cache": infra_ctx.cache,
            "existing_modules": infra_ctx.existing_modules,
            "has_dockerfile": True,
            "has_compose": True,
            "has_cicd": True,
        },
        "backend_stack": intent.backend_stack,
        "frontend_stack": intent.frontend_stack,
        "api_contract": api_contract.get("summary", "") if isinstance(api_contract, dict) else "",
        "context_string": domain.get("description_summary", intent.description)[:2000],
    })
    return {"saved": True}


def step_git_commit(ctx: dict, **_):
    """Commit inicial — desabilitado (usuário decide quando commitar)."""
    return {"committed": False}


def step_generate_feature(ctx: dict, **_):
    """
    Gera arquivos de uma feature em projeto existente.
    Estuda o projeto, entende os padrões, gera arquivos que se integram.
    """
    intent       = ctx["intent"]
    domain       = ctx.get("domain", {})
    research_ctx = ctx.get("research_ctx", "")
    llm          = ctx["llm"]
    project_path = ctx["project_path"]

    # 1. Carrega contexto do projeto estudado
    from tools.file_writer import load_project_context
    from tools.knowledge_base import extract_infra_context
    from tools.scanner import scan_project

    ctx_data = load_project_context(project_path)
    if ctx_data:
        stack = ctx_data.get("summary", {}).get("stack") or ""
        existing_analysis = ctx_data.get("analysis", {})
        existing_ctx = ctx_data.get("context_string", "")
    else:
        console.print("  [yellow]Projeto não estudado — escaneando agora...[/yellow]")
        summary = scan_project(project_path)
        stack = summary.stack or ""
        existing_analysis = {}
        existing_ctx = summary.to_context_string()[:4000]

    if not stack:
        stack = intent.backend_stack or "nestjs"

    # 2. Gera apenas os arquivos do novo módulo/feature
    from tools.manifests import get_manifest
    from tools.generator import generate_files
    from tools.file_writer import write_files, save_project_context
    from tools.code_fixer import fix_all, integrate_module_into_app

    entities = domain.get("entities", [])
    has_auth = domain.get("has_auth", False)

    if not entities:
        console.print("  [yellow]Nenhuma entidade detectada na descrição[/yellow]")
        return []

    specs = get_manifest(stack, project_path.name, entities, has_auth)
    # Filtra o que já existe (não sobrescreve código existente)
    new_specs = [s for s in specs if not (project_path / s.path).exists()]

    if not new_specs:
        console.print("  [dim]Todos os arquivos já existem — verifique manualmente[/dim]")
        return []

    console.print(f"  Gerando {len(new_specs)} arquivo(s) para: {', '.join(entities)}")

    # 3. Contexto: projeto existente + treinamento (search/train)
    patterns = existing_analysis.get("recommendations_for_new_features", "")
    naming   = existing_analysis.get("naming_conventions", {})

    from tools.file_trainer import get_relevant_templates
    from tools.vector_store import search_relevant
    _infra_topics = ["docker", "devops", "github-actions", "nginx"]
    learned = get_relevant_templates(intent.description)
    ts_ctx  = search_relevant(
        intent.description, limit=3,
        exclude_topics=_infra_topics,
    )
    training_ctx = "\n\n".join(p for p in [learned[:350], ts_ctx[:300]] if p)
    if training_ctx:
        console.print(f"  [dim]✓ Treinamento consultado ({len(training_ctx)} chars)[/dim]")
    else:
        # Training vazio → pesquisa automaticamente e salva
        console.print("  [dim]→ Training insuficiente — pesquisando...[/dim]")
        try:
            from tools.research_agent import research_and_answer
            from config import MODEL_CODE as _MC
            web_r = research_and_answer(
                f"NestJS {intent.description[:60]} implementation example 2025",
                llm=llm, model=_MC, save=True,
            )
            if web_r:
                training_ctx = web_r[:500]
                console.print("  [green]✓[/green] Pesquisado e salvo no training")
        except Exception:
            pass

    desc = (
        f"Feature: {intent.description}\n\n"
        f"=== EXISTING PROJECT PATTERNS ===\n"
        f"{existing_ctx[:1200]}\n\n"
        f"Naming: {naming} | Patterns: {patterns}\n\n"
        f"=== TRAINING (devai search/train) ===\n"
        f"{training_ctx}\n\n"
        f"{research_ctx[:400]}"
    )

    files = generate_files(
        specs=new_specs, stack=stack,
        name=project_path.name, description=desc,
        domain=domain, llm=llm, output_path=project_path,
    )

    # Aplica edições determinísticas em arquivos existentes (swagger, cors, helmet, etc.)
    from tools.feature_editors import detect_and_apply_feature_edits
    applied = detect_and_apply_feature_edits(
        intent.description, project_path,
        app_name=intent.project_name, llm=llm, model=MODEL_CODE,
    )
    if applied:
        console.print(f"  [green]✓[/green] Features aplicadas: {', '.join(applied)}")

    if files:
        # 4. Integra o módulo no app.module.ts
        app_module = project_path / "src" / "app.module.ts"
        for entity in entities:
            el = entity.lower()
            module_name = f"{entity}Module"
            import_path = f"./{el}/{el}.module"
            new_content = integrate_module_into_app(app_module, module_name, import_path)
            if new_content:
                app_module.write_text(new_content, encoding="utf-8")
                console.print(f"  [green]✓[/green] {module_name} adicionado ao AppModule")

        # 5. Mostra diff antes de escrever
        write_files(files, base_path=project_path, confirm=True, preview=True)

        # 6. Atualiza contexto salvo
        if ctx_data:
            existing_mods = ctx_data.get("infra", {}).get("existing_modules", [])
            ctx_data["infra"] = ctx_data.get("infra", {})
            ctx_data["infra"]["existing_modules"] = list(set(existing_mods + [e.lower() for e in entities]))
            save_project_context(project_path, ctx_data)

    ctx["back_files"] = files or []
    return files or []


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _write_frontend_env(stack: str, path: Path, name: str, port_back: int, port_front: int):
    if stack == "nextjs":
        env = path / ".env.local"
        if not env.exists():
            env.write_text(
                f"NEXT_PUBLIC_API_URL=http://localhost:{port_back}/api/v1\n"
                f"NEXTAUTH_URL=http://localhost:{port_front}\n"
                f"NEXTAUTH_SECRET=devai-{name}-secret\n"
            )
    elif stack == "angular":
        env_dir = path / "src" / "environments"
        env_dir.mkdir(parents=True, exist_ok=True)
        (env_dir / "environment.ts").write_text(
            f"export const environment = {{\n"
            f"  production: false,\n"
            f"  apiUrl: 'http://localhost:{port_back}/api/v1',\n"
            f"}};\n"
        )


def _install_db_packages(stack: str, domain: dict, project_path: Path):
    """Instala pacotes específicos do banco de dados detectado."""
    import subprocess, shutil
    from tools.db_strategy import get_strategy, detect_database
    if not shutil.which("npm"):
        return

    # db_type vem do domain (detectado da descrição) OU do description direto
    db_type = domain.get("db_type") or "postgres"
    strategy = get_strategy(db_type)

    console.print(f"  [dim]→ Banco detectado: [bold]{db_type}[/bold] | ORM: {strategy.orm}[/dim]")

    if stack in ("nestjs", "nextjs"):
        pkgs = strategy.npm_packages + strategy.npm_dev_pkgs
        to_install = [p for p in pkgs if not (project_path / "node_modules" / p).exists()]
        if to_install:
            console.print(f"  [dim]→ Instalando {len(to_install)} pacote(s) do banco: {', '.join(to_install[:4])}[/dim]")
            r = subprocess.run(
                ["npm", "install", "--save", "--legacy-peer-deps", "--no-fund", "--no-audit"] + to_install,
                cwd=str(project_path), capture_output=True, text=True, timeout=300,
            )
            if r.returncode != 0:
                console.print(f"  [yellow]⚠ npm install parcial: {r.stderr[:150]}[/yellow]")
            else:
                console.print(f"  [green]✓ Pacotes {db_type} instalados[/green]")

    elif stack == "python":
        venv_pip = project_path / ".venv" / "bin" / "pip"
        pip = str(venv_pip) if venv_pip.exists() else shutil.which("pip3")
        if pip and strategy.pip_packages:
            subprocess.run(
                [pip, "install", "-q"] + strategy.pip_packages,
                cwd=str(project_path), capture_output=True, timeout=300,
            )

    elif stack == "spring-boot":
        if strategy.maven_deps:
            console.print(f"  [dim]Adicione ao pom.xml:[/dim]")
            for dep in strategy.maven_deps:
                parts = dep.split(":")
                if len(parts) >= 2:
                    console.print(f"  [dim]  {parts[0]}:{parts[1]}[/dim]")


def _install_frontend_extra_deps(stack: str, path: Path):
    import shutil
    if stack == "nextjs" and shutil.which("npm") and (path / "package.json").exists():
        extra = ["axios", "zustand", "@tanstack/react-query",
                 "react-hook-form", "@hookform/resolvers", "zod"]
        subprocess.run(
            ["npm", "install", "--save", "--prefer-offline"] + extra,
            cwd=str(path), capture_output=True, timeout=120,
        )
