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

DB_OPTIONS = [
    ("1", "MongoDB",    "mongodb"),
    ("2", "PostgreSQL", "postgres"),
    ("3", "MySQL",      "mysql"),
    ("4", "SQLite",     "sqlite"),
    ("5", "Cassandra",  "cassandra"),
]

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


def _ask_db(suggestion: str | None = None) -> str:
    """Pergunta qual banco de dados usar. Nunca usa default silencioso."""
    console.print("\n  [cyan]Banco de dados não identificado — qual usar?[/cyan]")
    for num, label, val in DB_OPTIONS:
        hint = " [dim](último usado)[/dim]" if val == suggestion else ""
        console.print(f"    {num}) {label}{hint}")
    # Sem default — força o usuário a escolher
    valid = [n for n,_,_ in DB_OPTIONS]
    while True:
        choice = Prompt.ask("  Escolha [1-5]", default="").strip()
        if choice in valid:
            return next(v for n,_,v in DB_OPTIONS if n == choice)
        console.print("  [red]Digite um número entre 1 e 5[/red]")


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
