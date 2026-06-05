"""
Research Agent — pesquisador autônomo que aprende antes de agir.

Para qualquer tarefa, o agente:
  1. Determina quais queries são necessárias
  2. Pesquisa na web (DuckDuckGo + registries)
  3. LLM sumariza os achados em fatos acionáveis
  4. Salva em ~/.devai/knowledge.json com TTL
  5. Retorna contexto compacto para os prompts de geração

O modelo 7B sabe muito menos que os fatos atuais da web.
Este módulo compensa essa limitação injetando conhecimento real.
"""

import json
import time
import re
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

KNOWLEDGE_FILE = Path.home() / ".devai" / "knowledge.json"
TTL_HOURS = 72   # re-pesquisa a cada 3 dias


# ─── Queries por tópico ────────────────────────────────────────────────────────
# Cada entrada: chave = tópico, valor = lista de queries para pesquisar

TOPIC_QUERIES: dict[str, list[str]] = {
    "nestjs": [
        "NestJS latest version 2025 create project CLI command",
        "NestJS TypeORM JWT passport best practices 2025",
        "NestJS Swagger OpenAPI setup 2025",
        "NestJS docker production dockerfile 2025",
    ],
    "nextjs": [
        "Next.js 14 15 create app latest command 2025",
        "Next.js App Router server components best practices 2025",
        "Next.js standalone docker build production 2025",
        "Next.js environment variables API URL configuration",
    ],
    "angular": [
        "Angular 17 18 latest version create project standalone 2025",
        "Angular signals NgRx store best practices 2025",
        "Angular docker nginx production build 2025",
    ],
    "spring-boot": [
        "Spring Boot 3 latest version create project initializr 2025",
        "Spring Boot JWT security configuration 2025",
        "Spring Boot PostgreSQL JPA best practices 2025",
        "Spring Boot docker layered jar dockerfile 2025",
    ],
    "python": [
        "FastAPI latest version 2025 project structure best practices",
        "FastAPI SQLAlchemy async PostgreSQL 2025",
        "FastAPI JWT authentication 2025",
        "FastAPI docker production uvicorn gunicorn 2025",
    ],
    "dotnet": [
        "dotnet 8 minimal API latest create project 2025",
        "dotnet 8 Entity Framework PostgreSQL best practices 2025",
        "dotnet 8 JWT authentication minimal API 2025",
        "dotnet 8 docker multi-stage build 2025",
    ],
    "docker": [
        "docker-compose 2025 best practices healthcheck depends_on",
        "docker compose v2 production nginx postgres redis configuration",
        "docker build multi-stage node alpine best practices 2025",
    ],
    "cicd": [
        "GitHub Actions CI/CD Node.js 2025 best practices cache",
        "GitHub Actions docker build push 2025",
        "GitHub Actions Java Maven test 2025",
        "GitHub Actions Python pytest 2025",
    ],
    "nginx": [
        "nginx reverse proxy nodejs next.js 2025 configuration",
        "nginx rate limiting security headers production 2025",
        "nginx upstream backend frontend configuration",
    ],
    "postgresql": [
        "PostgreSQL 16 docker configuration init scripts 2025",
        "PostgreSQL connection pooling PgBouncer 2025",
    ],
}

# ─── Knowledge store ──────────────────────────────────────────────────────────

def _load_kb() -> dict:
    try:
        if KNOWLEDGE_FILE.exists():
            return json.loads(KNOWLEDGE_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_kb(kb: dict):
    KNOWLEDGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    KNOWLEDGE_FILE.write_text(json.dumps(kb, indent=2, ensure_ascii=False))


def _is_fresh(entry: dict) -> bool:
    return time.time() - entry.get("ts", 0) < TTL_HOURS * 3600


def _store(topic: str, content: str):
    """Salva no training_store (SQLite commitável) E no cache JSON."""
    try:
        from tools.vector_store import save as ts_save, _infer_topic
        ts_save(topic, content, topic=_infer_topic(topic, content), source="web_research")
    except Exception:
        pass
    kb = _load_kb()
    kb[topic] = {"content": content, "ts": time.time()}
    _save_kb(kb)


def _retrieve(topic: str) -> Optional[str]:
    """Busca no training_store primeiro, depois no cache JSON."""
    try:
        from tools.vector_store import get as ts_get
        result = ts_get(topic)
        if result:
            return result
    except Exception:
        pass
    kb = _load_kb()
    entry = kb.get(topic)
    if entry and _is_fresh(entry):
        return entry["content"]
    return None


# ─── Summarizer ───────────────────────────────────────────────────────────────

def _summarize(topic: str, raw_results: list[dict], llm, model: str) -> str:
    """LLM sumariza os resultados de pesquisa em fatos acionáveis. Max 20s."""
    if not raw_results:
        return ""

    snippets = "\n".join(
        f"[{i+1}] {r.get('title','')}: {r.get('body','')[:250]}"
        for i, r in enumerate(raw_results[:4])
    )

    prompt = (
        f"Topic: {topic}\n\n"
        f"Search results:\n{snippets}\n\n"
        "Extract ONLY actionable facts for a developer:\n"
        "- CLI commands with exact flags\n"
        "- Latest versions\n"
        "- Key config options\n"
        "Format: brief bullet points (max 10 lines). Be concrete."
    )

    try:
        import threading
        result = [None]
        def _call():
            try:
                result[0] = llm.chat(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    system="Extract actionable developer facts as bullet points. No intro, no conclusions.",
                    stream=False,
                )
            except Exception:
                result[0] = None

        t = threading.Thread(target=_call, daemon=True)
        t.start()
        t.join(timeout=25)  # máximo 25s por pesquisa
        if result[0]:
            return result[0]
    except Exception:
        pass

    # Fallback: usa snippets brutos
    return "\n".join(f"• {r.get('body','')[:200]}" for r in raw_results[:3])


# ─── Core research function ────────────────────────────────────────────────────

def research_topic(topic: str, llm, model: str, force: bool = False) -> str:
    """
    Pesquisa um tópico. Usa cache se disponível.
    Máximo 2 queries por tópico para não travar.
    """
    if not force:
        cached = _retrieve(topic)
        if cached:
            return cached

    queries = TOPIC_QUERIES.get(topic, [f"{topic} best practices 2025"])

    try:
        from tools.web_research import web_search
    except ImportError:
        return ""

    all_results = []
    for q in queries[:2]:  # máximo 2 queries por tópico
        try:
            results = web_search(q, max_results=3)
            all_results.extend(results)
        except Exception:
            pass

    if not all_results:
        return ""

    summary = _summarize(topic, all_results, llm, model)
    if summary:
        _store(topic, summary)

    return summary


# ── Tópicos específicos detectáveis por palavra-chave ─────────────────────────
FEATURE_TOPIC_MAP: dict[str, tuple[str, str]] = {
    # keyword → (topic_key, search_query)
    "winston":    ("nestjs_winston",   "NestJS winston logger configuration 2025"),
    "pino":       ("nestjs_pino",      "NestJS pino logger configuration 2025"),
    "swagger":    ("nestjs_swagger",   "NestJS Swagger OpenAPI setup 2025 latest"),
    "mongodb":    ("nestjs_mongodb",   "NestJS MongoDB Mongoose setup 2025"),
    "mongo":      ("nestjs_mongodb",   "NestJS MongoDB Mongoose setup 2025"),
    "mongoose":   ("nestjs_mongodb",   "NestJS MongoDB Mongoose setup 2025"),
    "redis":      ("redis_cache",      "NestJS Redis cache configuration 2025"),
    "rabbitmq":   ("rabbitmq",         "NestJS RabbitMQ microservices configuration 2025"),
    "kafka":      ("kafka",            "NestJS Kafka microservices configuration 2025"),
    "jwt":        ("nestjs_jwt",       "NestJS JWT authentication guard strategy 2025"),
    "oauth":      ("nestjs_oauth",     "NestJS OAuth2 Google GitHub strategy 2025"),
    "typeorm":    ("nestjs_typeorm",   "NestJS TypeORM PostgreSQL configuration 2025"),
    "prisma":     ("nestjs_prisma",    "NestJS Prisma ORM setup 2025"),
    "graphql":    ("nestjs_graphql",   "NestJS GraphQL Code-first setup 2025"),
    "websocket":  ("nestjs_ws",        "NestJS WebSocket Gateway setup 2025"),
    "upload":     ("nestjs_upload",    "NestJS file upload multer S3 2025"),
    "email":      ("nestjs_email",     "NestJS nodemailer email service 2025"),
    "stripe":     ("stripe_nest",      "NestJS Stripe payment integration 2025"),
    "docker":     ("docker",           "docker-compose NestJS MongoDB production 2025"),
    "nginx":      ("nginx",            "nginx reverse proxy NestJS configuration 2025"),
    "rate limit": ("ratelimit",        "NestJS rate limiting throttler 2025"),
    "rate-limit": ("ratelimit",        "NestJS rate limiting throttler 2025"),
    "cache":      ("nestjs_cache",     "NestJS caching interceptor Redis 2025"),
    "s3":         ("aws_s3",           "NestJS AWS S3 file upload 2025"),
    "test":       ("nestjs_testing",   "NestJS unit integration testing Jest 2025"),
}


def research_for_task(
    task_description: str,
    stacks: list[str],
    task_type: str,
    llm,
    model: str,
) -> str:
    """
    Pesquisa tudo que é necessário para uma tarefa e retorna contexto consolidado.
    Chamado ANTES de qualquer geração de código.
    Extrai tópicos específicos da descrição (winston, swagger, mongodb, etc.)
    """
    topics_needed = set()
    custom_searches: dict[str, str] = {}  # topic_key → query

    # Stacks sempre pesquisadas
    for stack in stacks:
        normalized = stack.replace("-", "_").lower()
        if normalized in TOPIC_QUERIES:
            topics_needed.add(normalized)
        stack_map = {
            "spring_boot": "spring-boot",
            "nestjs": "nestjs", "nextjs": "nextjs",
            "angular": "angular", "python": "python",
            "dotnet": "dotnet",
        }
        for k, v in stack_map.items():
            if k in normalized:
                topics_needed.add(v)

    # ── Extrai tópicos específicos da DESCRIÇÃO ────────────────────────────────
    desc_lower = task_description.lower()
    for keyword, (topic_key, query) in FEATURE_TOPIC_MAP.items():
        if keyword in desc_lower:
            custom_searches[topic_key] = query

    # Tópicos por tipo de tarefa
    if task_type in ("infra", "docker"):
        topics_needed.update(["docker", "nginx"])
    if task_type == "cicd":
        topics_needed.add("cicd")
    if "nginx" in desc_lower:
        topics_needed.add("nginx")
    if any(w in desc_lower for w in ["postgres", "postgresql"]):
        topics_needed.add("postgresql")
    if "mongo" in desc_lower or "mongodb" in desc_lower:
        topics_needed.add("mongodb")
        custom_searches["nestjs_mongodb"] = "NestJS MongoDB Mongoose setup 2025"
    if "ci" in desc_lower or "github actions" in desc_lower:
        topics_needed.add("cicd")
    if "docker" in desc_lower:
        topics_needed.add("docker")

    # Sempre pesquisa docker para projetos fullstack
    if len(stacks) > 1:
        topics_needed.update(["docker", "nginx"])

    # Limita o total de pesquisas para não travar (max 6 tópicos)
    topics_needed = set(list(topics_needed)[:4])        # max 4 tópicos gerais
    custom_items  = list(custom_searches.items())[:4]   # max 4 específicos
    custom_searches = dict(custom_items)

    all_topics_count = len(topics_needed) + len(custom_searches)
    if all_topics_count == 0:
        return ""

    console.print(f"\n[dim]🔍 Pesquisando {all_topics_count} tópico(s): "
                  f"{', '.join(list(sorted(topics_needed))[:3] + list(custom_searches.keys())[:3])}[/dim]")

    results = {}
    total_searches = len(topics_needed) + len(custom_searches)
    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  console=console, transient=True) as p:
        task = p.add_task("Pesquisando...", total=total_searches)

        # Tópicos gerais
        for topic in sorted(topics_needed):
            p.update(task, description=f"[dim]Pesquisando {topic}...[/dim]")
            content_r = research_topic(topic, llm, model)
            if content_r:
                results[topic] = content_r
            p.advance(task)

        # Tópicos específicos da descrição (winston, swagger, mongodb, etc.)
        for topic_key, query in custom_searches.items():
            if topic_key in results:  # já pesquisado
                p.advance(task)
                continue
            p.update(task, description=f"[dim]Pesquisando {topic_key}...[/dim]")
            # Pesquisa direta com query específica
            cached = _retrieve(topic_key)
            if cached:
                results[topic_key] = cached
            else:
                from tools.web_research import web_search
                raw = web_search(query, max_results=4)
                if raw:
                    summary = _summarize(query, raw, llm, model)
                    if summary:
                        _store(topic_key, summary)
                        results[topic_key] = summary
            p.advance(task)

    if not results:
        return ""

    # Consolida em contexto compacto
    lines = ["=== KNOWLEDGE BASE (web-researched) ==="]
    for topic, content in results.items():
        lines.append(f"\n## {topic.upper()}")
        # Limita cada tópico para não explodir o contexto do 7B
        topic_lines = content.strip().splitlines()[:12]
        lines.extend(topic_lines)

    context = "\n".join(lines)
    console.print(f"  [green]✓[/green] Conhecimento carregado ({len(context)} chars)")
    return context


# ─── Comando de pesquisa standalone ───────────────────────────────────────────

def research_and_answer(question: str, llm, model: str, save: bool = True) -> str:
    """
    Pesquisa uma pergunta e retorna resposta sintetizada.
    save=True (padrão): salva no training_store (commitável) para gerações futuras.
    """
    try:
        from tools.web_research import web_search
        results = web_search(question, max_results=6)
        if not results:
            return "Nenhum resultado encontrado na web."
        summary = _summarize(question, results, llm, model)
        if summary and save:
            key = "search:" + re.sub(r"\W+", "_", question[:50].lower())
            _store(key, summary)
        return summary
    except Exception as e:
        return f"Erro na pesquisa: {e}"


def list_knowledge() -> dict:
    """Lista o que está no knowledge base."""
    kb = _load_kb()
    return {
        k: {
            "fresh": _is_fresh(v),
            "age_hours": int((time.time() - v.get("ts", 0)) / 3600),
            "size": len(v.get("content", "")),
        }
        for k, v in kb.items()
    }


def clear_knowledge(topic: str = None):
    """Limpa todo o knowledge base ou um tópico específico."""
    if topic:
        kb = _load_kb()
        kb.pop(topic, None)
        _save_kb(kb)
    else:
        _save_kb({})
