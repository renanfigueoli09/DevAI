"""
DevAI Clarifier — pergunta ao usuário quando não tem certeza.

Quando a descrição é ambígua (banco não identificado, arquitetura não clara,
microserviços pedidos mas sem detalhe), pergunta antes de executar.

Regras:
  - Só pergunta quando realmente não tem certeza (evita perguntar o óbvio)
  - Máximo 1 tela de perguntas (agrupa tudo numa única interação)
  - Salva as respostas no user_profile para não perguntar de novo
  - Nunca pergunta se o usuário já especificou claramente
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

console = Console()


@dataclass
class ClarificationResult:
    db_type:        Optional[str] = None
    has_auth:       Optional[bool] = None
    extra_services: list[str] = field(default_factory=list)
    architecture:   Optional[str] = None   # rest | graphql | grpc | mixed
    has_tests:      Optional[bool] = None
    has_swagger:    Optional[bool] = None
    confirmed_stack: Optional[str] = None
    asked_anything: bool = False
    entities:       list[str] = field(default_factory=list)


# ── Confiança por tipo de decisão ─────────────────────────────────────────────

DB_KEYWORDS = {
    "mongodb":  ["mongodb","mongo","mongoose","nosql"],
    "postgres": ["postgres","postgresql","pg","relacional","sql","relational"],
    "mysql":    ["mysql","mariadb"],
    "sqlite":   ["sqlite"],
    "redis":    ["redis"],
    "cassandra":["cassandra"],
}

AUTH_KEYWORDS = [
    "auth","autenticação","autenticacao","login","jwt","token",
    "oauth","roles","permissions","permissões","usuários autenticados",
]

MICROSERVICE_KEYWORDS = [
    "kafka","rabbitmq","grpc","graphql","websocket","microserviço",
    "microsserviço","message broker","event driven","saga","cqrs",
]

ARCH_KEYWORDS = {
    "graphql": ["graphql","apollo"],
    "grpc":    ["grpc","protobuf","proto"],
    "rest":    ["rest","restful","api rest","crud"],
    "ws":      ["websocket","ws","realtime","tempo real"],
}


def _detect_confidence(description: str) -> dict:
    """
    Detecta o que foi explicitado e o que está ambíguo.
    Retorna dict com confidence (0.0-1.0) para cada decisão.
    """
    text = description.lower()
    conf = {}

    # Banco de dados
    db_matches = [(db, kws) for db, kws in DB_KEYWORDS.items()
                  if any(kw in text for kw in kws)]
    if len(db_matches) == 1:
        conf["db"] = (1.0, db_matches[0][0])
    elif len(db_matches) > 1:
        conf["db"] = (0.5, db_matches[0][0])  # ambíguo
    else:
        conf["db"] = (0.0, None)  # não mencionado

    # Auth
    if any(kw in text for kw in AUTH_KEYWORDS):
        conf["auth"] = (1.0, True)
    elif any(w in text for w in ["usuário","usuario","user","users"]):
        conf["auth"] = (0.4, False)  # tem usuários mas não pediu auth explicitamente
    else:
        conf["auth"] = (1.0, False)

    # Microserviços / serviços extras
    found_services = []
    if any(kw in text for kw in ["redis-sentinel","sentinel"]):
        found_services.append("redis-sentinel")
    elif "redis" in text or "cache" in text:
        found_services.append("redis")
    if "kafka" in text:
        found_services.append("kafka")
    if "rabbitmq" in text or "amqp" in text:
        found_services.append("rabbitmq")
    if "elasticsearch" in text or "elastic" in text:
        found_services.append("elasticsearch")
    conf["services"] = (1.0, found_services)

    # Arquitetura de API
    arch_matches = [(a, kws) for a, kws in ARCH_KEYWORDS.items()
                    if any(kw in text for kw in kws)]
    if arch_matches:
        conf["arch"] = (1.0, arch_matches[0][0])
    else:
        conf["arch"] = (0.0, "rest")  # default REST mas não foi explicitado

    # Swagger/documentação
    if any(w in text for w in ["swagger","openapi","documentação","docs"]):
        conf["swagger"] = (1.0, True)
    else:
        conf["swagger"] = (0.0, None)

    # Testes
    if any(w in text for w in ["test","testes","jest","pytest","junit","spec"]):
        conf["tests"] = (1.0, True)
    else:
        conf["tests"] = (0.0, None)

    return conf


def _should_ask(conf: dict, key: str, threshold: float = 0.6) -> bool:
    """Retorna True se a confiança for baixa demais para assumir."""
    c, _ = conf.get(key, (1.0, None))
    return c < threshold


# ── Perguntas interativas ──────────────────────────────────────────────────────

def _load_db_options() -> list[tuple[str, str, str, str]]:
    """
    Carrega bancos disponíveis dinamicamente:
    1. Todos do db_strategy.py (suportados nativamente)
    2. Bancos extras do training store (estudados mas não no strategy)
    3. Indica cobertura de treinamento para cada um
    Retorna: [(num, label, db_type, coverage_icon)]
    """
    options = []

    # Bancos nativos do db_strategy
    NATIVE_LABELS = {
        "postgres":  "PostgreSQL",
        "mysql":     "MySQL",
        "mongodb":   "MongoDB",
        "sqlite":    "SQLite",
        "mariadb":   "MariaDB",
        "cassandra": "Cassandra",
    }

    # Bancos extras conhecidos (não no strategy mas estudados)
    EXTRA_LABELS = {
        "dynamodb":   "DynamoDB",
        "firestore":  "Firestore",
        "supabase":   "Supabase (PostgreSQL)",
        "planetscale":"PlanetScale (MySQL)",
        "cockroachdb":"CockroachDB (PostgreSQL)",
        "redis":      "Redis (cache only)",
    }

    # Mede cobertura no training store
    def _coverage(db_key: str) -> str:
        try:
            from tools.vector_store import search_relevant
            result = search_relevant(f"nestjs {db_key} schema service CRUD", limit=2)
            if not result or len(result) < 100:
                result = search_relevant(f"spring {db_key} repository", limit=1)
            chars = len(result) if result else 0
            if chars > 800:  return "✅"   # bem treinado
            if chars > 200:  return "⚠️ "  # treinamento parcial
            return "📚"                     # pouco ou sem treinamento
        except Exception:
            return "❓"

    # Monta lista com nativos primeiro
    all_dbs = list(NATIVE_LABELS.items())

    # Adiciona extras que foram estudados no training
    try:
        from tools.vector_store import search_relevant
        for db_key, label in EXTRA_LABELS.items():
            result = search_relevant(f"{db_key} schema CRUD", limit=1)
            if result and len(result) > 100:
                all_dbs.append((db_key, label))
    except Exception:
        pass

    for i, (db_key, label) in enumerate(all_dbs, 1):
        cov = _coverage(db_key)
        options.append((str(i), label, db_key, cov))

    return options


def _ask_db(suggestion: str | None = None) -> str:
    """Pergunta qual banco de dados usar. Lista é dinâmica — lida do training store."""
    options = _load_db_options()

    console.print("\n  [cyan]Banco de dados não identificado — qual usar?[/cyan]")
    console.print("  [dim]✅ bem treinado  ⚠️  parcial  📚 pouco treinamento[/dim]\n")

    for num, label, db_key, cov in options:
        hint = " [dim](último usado)[/dim]" if db_key == suggestion else ""
        console.print(f"    {num}) {cov} {label}{hint}")

    valid = [n for n,_,_,_ in options]
    while True:
        choice = Prompt.ask(f"  Escolha [1-{len(options)}]", default="").strip()
        if choice in valid:
            db_type = next(v for n,_,v,_ in options if n == choice)
            # Se pouco treinado, auto-estuda antes de continuar
            cov_icon = next(c for n,_,v,c in options if n == choice)
            if "📚" in cov_icon:
                console.print(f"  [yellow]→ Pouco treinamento para {db_type} — estudando...[/yellow]")
                _auto_study_db(db_type)
            return db_type
        console.print(f"  [red]Digite um número entre 1 e {len(options)}[/red]")


def _auto_study_db(db_type: str) -> None:
    """Auto-estuda um banco antes de gerar código para ele."""
    try:
        from scripts.study import study_topic, SEARCH_CURRICULUM, load_discovered
        from tools.llm_client import OllamaClient
        from config import MODEL_CODE

        all_c = {**SEARCH_CURRICULUM, **load_discovered()}
        # Tenta chaves no formato nestjs_mongodb, spring_postgres, etc.
        keys_to_try = [
            f"nestjs_{db_type}", f"spring_{db_type}",
            f"fastapi_{db_type}", f"{db_type}_advanced",
        ]
        llm = OllamaClient()
        found = False
        for key in keys_to_try:
            if key in all_c:
                console.print(f"  [dim]📚 Estudando {key}...[/dim]")
                study_topic(key, all_c[key][:3], llm, MODEL_CODE, intensive=True)
                found = True
                break
        if not found:
            # Pesquisa direta na web
            from tools.web_research import web_search
            from tools.research_agent import _summarize
            from tools.vector_store import save
            q = f"NestJS {db_type} CRUD schema service module example 2025"
            results = web_search(q, max_results=4)
            if results:
                summary = _summarize(q, results, llm, MODEL_CODE)
                if summary:
                    save(f"auto:{db_type}", summary, topic=f"nestjs_{db_type}", source="auto_study")
                    console.print(f"  [green]✓[/green] {db_type} estudado e salvo no training")
    except Exception as e:
        console.print(f"  [dim]⚠ Auto-study: {e}[/dim]")

ARCH_OPTIONS = [
    ("1", "REST API (padrão)", "rest"),
    ("2", "GraphQL",           "graphql"),
    ("3", "gRPC",              "grpc"),
    ("4", "REST + WebSocket",  "rest+ws"),
]

SERVICE_OPTIONS = [
    ("redis",          "Cache Redis"),
    ("redis-sentinel", "Cache Redis Sentinel (HA)"),
    ("kafka",          "Kafka (message broker)"),
    ("rabbitmq",       "RabbitMQ (message broker)"),
    ("elasticsearch",  "Elasticsearch (busca)"),
]



def _ask_auth() -> bool:
    """Pergunta se precisa de autenticação. Sem default — usuário deve escolher."""
    console.print("\n  [cyan]Autenticação não identificada — precisa de JWT?[/cyan]")
    console.print("    1) Não (CRUD público, sem login)")
    console.print("    2) Sim (JWT + guards + login)")
    while True:
        choice = Prompt.ask("  Escolha [1/2]", default="").strip()
        if choice in ("1","2"):
            return choice == "2"
        console.print("  [red]Digite 1 ou 2[/red]")


def _ask_services(already: list[str]) -> list[str]:
    """Pergunta sobre serviços extras (Redis, Kafka, etc)."""
    console.print("\n  [cyan]Serviços adicionais?[/cyan] (pode escolher vários, separados por vírgula)")
    for key, label in SERVICE_OPTIONS:
        mark = "✓" if key in already else " "
        console.print(f"    [{mark}] {key} — {label}")
    console.print("    (enter para nenhum, ou ex: redis,kafka)")
    raw = Prompt.ask("  Serviços", default="").strip().lower()
    if not raw:
        return already
    chosen = [s.strip() for s in raw.split(",") if s.strip()]
    # Valida e resolve aliases
    valid = {k for k,_ in SERVICE_OPTIONS}
    return list({s for s in chosen if s in valid} | set(already))


def _ask_arch() -> str:
    """Pergunta sobre arquitetura da API."""
    console.print("\n  [cyan]Arquitetura da API?[/cyan]")
    for num, label, _ in ARCH_OPTIONS:
        console.print(f"    {num}) {label}")
    choice = Prompt.ask("  Escolha", choices=[n for n,_,_ in ARCH_OPTIONS], default="1")
    return next(v for n,_,v in ARCH_OPTIONS if n == choice)


def _ask_swagger() -> bool:
    console.print("\n  [cyan]Configurar Swagger/OpenAPI?[/cyan]")
    choice = Prompt.ask("  [1=Sim / 2=Não]", choices=["1","2"], default="1")
    return choice == "1"


# ── Ponto de entrada principal ─────────────────────────────────────────────────

def clarify_if_needed(
    description: str,
    stack: str,
    interactive: bool = True,
) -> ClarificationResult:
    """
    Analisa a descrição e pergunta ao usuário apenas o que for ambíguo.
    Se interactive=False, retorna defaults sem perguntar.
    """
    result = ClarificationResult()
    conf   = _detect_confidence(description)
    text   = description.lower()

    questions_needed = []

    # Banco — pergunta se não foi mencionado
    if _should_ask(conf, "db", threshold=0.7) and stack in ("nestjs","spring-boot","python","dotnet"):
        questions_needed.append("db")

    # Auth — pergunta só se tem "usuários" mas não pediu auth explicitamente
    db_conf, _ = conf.get("db", (1.0, None))
    auth_conf, auth_val = conf.get("auth", (1.0, False))
    if auth_conf < 0.6:
        questions_needed.append("auth")

    # Serviços — só pergunta se mencionou algo relacionado mas ambíguo
    # Ex: "preciso de cache" sem especificar Redis vs Memcached
    if "cache" in text and not any(
        kw in text for kw in ["redis","memcached","elasticache"]
    ):
        questions_needed.append("services")

    # Arquitetura — só pergunta se mencionou "graphql" ou "grpc" de forma vaga
    arch_conf, arch_val = conf.get("arch", (1.0, "rest"))
    # Não pergunta por padrão — REST é o default seguro

    # Se não tem nada ambíguo, retorna com os valores detectados (sem perguntar)
    if not questions_needed or not interactive:
        _, db_val  = conf.get("db", (0, None))
        _, srv_val = conf.get("services", (0, []))
        result.db_type        = db_val
        result.has_auth       = auth_val
        result.extra_services = srv_val or []
        result.architecture   = arch_val or "rest"
        return result

    # Carrega perfil apenas para SUGESTÃO no prompt (não para responder automaticamente)
    profile_db = None
    try:
        from tools.user_profile import load_profile
        p = load_profile()
        profile_db = p["preferences"].get("default_db") or None
    except Exception:
        pass

    # Mostra painel de clarificação
    console.print(Panel.fit(
        "[bold cyan]❓ Preciso de mais detalhes[/bold cyan]\n"
        "[dim]Algumas informações não ficaram claras na descrição.[/dim]",
        border_style="cyan",
    ))

    result.asked_anything = True

    if "db" in questions_needed:
        result.db_type = _ask_db(suggestion=profile_db)

    if "auth" in questions_needed:
        result.has_auth = _ask_auth()
    else:
        result.has_auth = auth_val

    if "services" in questions_needed:
        _, existing = conf.get("services", (1.0, []))
        result.extra_services = _ask_services(existing or [])
    else:
        _, srv = conf.get("services", (1.0, []))
        result.extra_services = srv or []

    # Sempre aplica o que foi detectado com certeza
    if result.db_type is None:
        _, db_val = conf.get("db", (0, None))
        result.db_type = db_val

    # Salva respostas no perfil para futuras sessões
    try:
        from tools.user_profile import load_profile, save_profile
        profile = load_profile()
        # Salva como "último usado" para SUGESTÃO — não como resposta automática
        if result.db_type:
            profile["preferences"]["last_used_db"] = result.db_type
        save_profile(profile)
    except Exception:
        pass

    console.print()
    return result
