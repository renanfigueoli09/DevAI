"""
Task Classifier — classifica qualquer pedido antes de agir.

Tipos de tarefa:
  infra    → docker, dockerfile, nginx, ci/cd, kubernetes, deploy, compose
  db       → migration, seed, schema, flyway, alembic, liquibase
  code     → feature, entity, crud, module, service, api, controller
  config   → env, settings, cors, middleware, logging, monitoring
  docs     → readme, swagger, openapi, documentation
  research → como, por que, explique, o que é, best practice
  security → auth, jwt, oauth, ssl, certs, rate limit, cors

Não usa LLM — baseado em palavras-chave com fallback para LLM em ambíguos.
"""

import re
from dataclasses import dataclass
from rich.console import Console

console = Console()


@dataclass
class TaskResult:
    task_type:  str          # infra | db | code | config | docs | research | security
    confidence: float        # 0.0 - 1.0
    keywords:   list[str]    # palavras que dispararam
    sub_type:   str = ""     # ex: infra→docker, infra→nginx, code→entity


# ── Regras por tipo ──────────────────────────────────────────────────────────

_RULES: list[tuple[str, str, list[str]]] = [
    # (task_type, sub_type, keywords)
    ("infra",    "docker",    ["docker", "dockerfile", "container", "docker-compose", "compose", "dockerizar"]),
    ("infra",    "nginx",     ["nginx", "proxy reverso", "reverse proxy", "load balancer", "upstream"]),
    ("infra",    "kubernetes",["kubernetes", "k8s", "helm", "pod", "deployment", "ingress", "kubectl"]),
    ("infra",    "cicd",      ["ci/cd", "github actions", "pipeline", "workflow", "deploy", "action", "jenkins", "gitlab-ci"]),
    ("infra",    "monitoring",["prometheus", "grafana", "jaeger", "tracing", "metrics", "monitoring"]),
    ("infra",    "infra",     ["infraestrutura", "infrastructure", "servidor", "server setup", "vps", "cloud"]),
    ("db",       "migration", ["migration", "migração", "flyway", "alembic", "liquibase", "schema change"]),
    ("db",       "seed",      ["seed", "fixture", "dados iniciais", "popular banco", "initial data"]),
    ("db",       "index",     ["índice", "index", "índices", "performance de banco", "query optimization"]),
    ("security", "auth",      ["oauth", "oauth2", "keycloak", "sso", "saml"]),
    ("security", "jwt",       ["jwt", "refresh token", "access token", "token rotation"]),
    ("security", "ssl",       ["ssl", "tls", "certificado", "https", "let's encrypt", "certbot"]),
    ("security", "ratelimit", ["rate limit", "rate limiting", "throttle", "throttling", "brute force"]),
    ("config",   "env",       ["variável de ambiente", "env var", "configuração", ".env", "secrets", "vault"]),
    ("config",   "logging",   ["log", "logging", "winston", "pino", "logback", "structured log"]),
    ("config",   "cors",      ["cors", "cross-origin", "allowed origins"]),
    ("docs",     "readme",    ["readme", "documentação", "documentation", "wiki"]),
    ("docs",     "swagger",   ["swagger", "openapi", "api doc", "api docs"]),
    ("research", "howto",     ["como ", "how to", "como faço", "qual a diferença", "o que é", "explain", "best practice"]),
    ("code",     "entity",    ["entidade", "entity", "model", "modelo", "tabela", "table"]),
    ("code",     "crud",      ["crud", "repositório", "repository", "service", "serviço"]),
    ("code",     "module",    ["módulo", "module", "feature", "funcionalidade"]),
    ("code",     "test",      ["teste", "test", "spec", "unit test", "e2e", "integration test"]),
    ("code",     "webhook",   ["webhook", "event", "listener", "subscriber"]),
]

_SCORES: dict[str, int] = {
    "infra":    10,
    "db":        8,
    "security":  8,
    "config":    6,
    "docs":      5,
    "research":  4,
    "code":      2,   # fallback
}


def classify(description: str, llm=None, model: str = None) -> TaskResult:
    """
    Classifica o pedido. Retorna TaskResult.
    Se confiança < 0.5 e llm disponível, confirma com LLM.
    """
    text = description.lower()

    scores: dict[str, list] = {}
    for task_type, sub_type, keywords in _RULES:
        for kw in keywords:
            if kw in text:
                key = (task_type, sub_type)
                if key not in scores:
                    scores[key] = []
                scores[key].append(kw)

    if not scores:
        result = TaskResult("code", 0.3, [], "general")
        console.print(f"  [dim]Tarefa: code (padrão)[/dim]")
        return result

    # Ranqueia por tipo + quantidade de matches
    best = max(
        scores.items(),
        key=lambda x: (_SCORES.get(x[0][0], 0), len(x[1]))
    )
    (task_type, sub_type), matched_kws = best
    confidence = min(0.95, 0.5 + len(matched_kws) * 0.15)

    result = TaskResult(task_type, confidence, matched_kws, sub_type)
    console.print(
        f"  [dim]Tarefa classificada: [bold]{task_type}[/bold]/{sub_type} "
        f"(confiança {confidence:.0%}, keywords: {', '.join(matched_kws[:3])})[/dim]"
    )

    # Se confiança baixa e temos LLM, confirma
    if confidence < 0.6 and llm:
        result = _llm_classify(description, result, llm, model)

    return result


def _llm_classify(description: str, hint: TaskResult, llm, model: str) -> TaskResult:
    types = "infra | db | code | config | docs | security | research"
    prompt = (
        f"Classify this software development request into ONE category.\n"
        f"Request: \"{description}\"\n"
        f"Categories: {types}\n"
        f"Return ONLY the category word, nothing else."
    )
    try:
        resp = llm.chat(
            model=model or "qwen2.5-coder:7b",
            messages=[{"role": "user", "content": prompt}],
            system="Return only one word from the given categories.",
            stream=False,
        ).strip().lower().split()[0]

        valid = {"infra", "db", "code", "config", "docs", "security", "research"}
        if resp in valid:
            console.print(f"  [dim]LLM confirmou: {resp}[/dim]")
            return TaskResult(resp, 0.8, hint.keywords, hint.sub_type)
    except Exception:
        pass
    return hint
