"""
Intent Analyzer — entende pedidos em linguagem natural.

Exemplos de input:
  "cria projeto fullstack com back em nest e front em next"
  "quero um app de e-commerce com nestjs e nextjs"
  "adiciona docker e ci/cd no projeto atual"
  "cria uma api de produtos em spring boot"
  "dockeriza o projeto"
  "adiciona autenticação jwt"

Retorna Intent estruturado com tudo que o planner precisa.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from rich.console import Console

console = Console()

# ─── Stack detection ──────────────────────────────────────────────────────────

STACK_ALIASES: dict[str, str] = {
    "nest":       "nestjs",   "nestjs":      "nestjs",
    "next":       "nextjs",   "nextjs":      "nextjs",    "next.js": "nextjs",
    "angular":    "angular",  "ng":          "angular",
    "spring":     "spring-boot", "springboot": "spring-boot", "spring-boot": "spring-boot",
    "fastapi":    "python",   "python":      "python",    "flask": "python", "django": "python",
    "dotnet":     "dotnet",   ".net":        "dotnet",    "aspnet": "dotnet", "asp.net": "dotnet",
    "react":      "nextjs",   "vue":         "nextjs",    # React/Vue → sugere Next.js
    "node":       "nestjs",   "express":     "nestjs",
    "java":       "spring-boot", "kotlin":   "spring-boot",
}

BACKEND_STACKS  = {"nestjs", "spring-boot", "python", "dotnet"}
FRONTEND_STACKS = {"nextjs", "angular"}

INFRA_KEYWORDS = {
    "docker", "dockerfile", "compose", "docker-compose", "container",
    "nginx", "proxy", "ci", "cd", "ci/cd", "pipeline", "github actions",
    "kubernetes", "k8s", "infra", "infraestrutura", "deploy",
}

FEATURE_KEYWORDS = {
    "auth", "autenticação", "jwt", "login", "usuário", "user",
    "crud", "api", "endpoint", "módulo", "module",
    "pagamento", "payment", "stripe", "email", "notificação",
    "upload", "arquivo", "file", "relatório", "report",
    "websocket", "socket", "chat", "real-time",
    "cache", "redis", "queue", "fila", "rabbitmq", "kafka",
    "test", "teste", "spec",
}


@dataclass
class Intent:
    # Ação principal
    action: str = "new"           # new | feature | infra | study | ask | search

    # Projeto
    project_name: str = ""        # nome do projeto
    description:  str = ""        # descrição livre

    # Stacks detectadas
    backend_stack:  str = ""       # nestjs | spring-boot | python | dotnet
    frontend_stack: str = ""       # nextjs | angular | ""
    is_fullstack:   bool = False

    # Escopo extra
    needs_docker:  bool = False
    needs_cicd:    bool = False
    needs_nginx:   bool = False
    needs_auth:    bool = False
    needs_infra:   bool = False    # qualquer infra

    # Informações derivadas
    combo: str = ""                # ex: nestjs+nextjs
    stacks: list = field(default_factory=list)   # todas as stacks envolvidas

    def __post_init__(self):
        if self.backend_stack and self.frontend_stack:
            self.is_fullstack = True
            self.combo = f"{self.backend_stack}+{self.frontend_stack}"
            self.stacks = [self.backend_stack, self.frontend_stack]
        elif self.backend_stack:
            self.stacks = [self.backend_stack]
        elif self.frontend_stack:
            self.stacks = [self.frontend_stack]

        self.needs_infra = self.needs_docker or self.needs_cicd or self.needs_nginx

    def to_summary(self) -> str:
        parts = [f"Ação: {self.action}"]
        if self.project_name: parts.append(f"Projeto: {self.project_name}")
        if self.is_fullstack:  parts.append(f"Fullstack: {self.combo}")
        elif self.backend_stack: parts.append(f"Stack: {self.backend_stack}")
        infra = [k for k, v in [("Docker", self.needs_docker), ("CI/CD", self.needs_cicd), ("Nginx", self.needs_nginx), ("Auth", self.needs_auth)] if v]
        if infra: parts.append(f"Extras: {', '.join(infra)}")
        return " | ".join(parts)


# ─── Parser de linguagem natural ──────────────────────────────────────────────

def _detect_stacks(text: str) -> tuple[str, str]:
    """Detecta backend e frontend no texto."""
    text_lower = text.lower()
    found: list[str] = []

    # Palavras-chave ordenadas por especificidade
    for alias, canonical in STACK_ALIASES.items():
        if re.search(r"\b" + re.escape(alias) + r"\b", text_lower):
            if canonical not in found:
                found.append(canonical)

    backends  = [s for s in found if s in BACKEND_STACKS]
    frontends = [s for s in found if s in FRONTEND_STACKS]

    backend  = backends[0]  if backends  else ""
    frontend = frontends[0] if frontends else ""

    return backend, frontend


def _detect_action(text: str) -> str:
    text_lower = text.lower()
    # Palavras que indicam criação
    create_words = ["cria", "criar", "new", "novo", "nova", "gera", "iniciar", "start", "build", "make"]
    feature_words = ["adiciona", "adicionar", "add", "implementa", "implementar", "feature", "funcionalidade", "módulo"]
    study_words = ["estuda", "analisa", "analise", "estude", "index", "indexa", "scan"]
    ask_words = ["como", "o que", "por que", "explica", "explique", "qual", "quando", "onde"]
    search_words = ["pesquisa", "busca", "search", "find", "procura"]
    infra_words = ["dockeriza", "dockerize", "containeriza", "ci/cd", "deploy"]

    # Palavras de reparo/fix
    fix_words = [
        "consertar", "concertar", "corrigir", "corrige", "arruma", "arrumar",
        "fix", "repair", "resolve", "resolver erros", "fix errors",
        "tá quebrando", "ta quebrando", "build falhou", "erros de build",
        "tsc erro", "typescript erro", "não compila", "não roda",
        "corrige os erros", "arruma os erros", "conserta os erros",
    ]
    if any(w in text_lower for w in fix_words):
        return "fix"

    if any(w in text_lower for w in infra_words):
        return "infra"
    if any(w in text_lower for w in search_words):
        return "search"
    if any(w in text_lower for w in study_words):
        return "study"
    if any(w in text_lower for w in ask_words):
        return "ask"
    if any(w in text_lower for w in feature_words):
        return "feature"
    if any(w in text_lower for w in create_words):
        return "new"

    # Infra keywords como ação
    if any(w in text_lower for w in INFRA_KEYWORDS):
        return "infra"

    return "new"  # default


def _detect_project_name(text: str, backend: str, frontend: str) -> str:
    """Tenta extrair o nome do projeto do texto."""
    # Remove palavras de stacks do texto para isolar o nome
    stack_words = list(STACK_ALIASES.keys()) + ["back", "front", "backend", "frontend",
                  "com", "e", "e", "projeto", "project", "app", "api", "fullstack",
                  "cria", "criar", "new", "novo", "nova"]
    words = text.lower().split()
    candidates = [w for w in words if w not in stack_words and len(w) > 2
                  and not w.startswith("\"") and re.match(r"^[a-zA-Z0-9_-]+$", w)]

    if candidates:
        return candidates[0]

    # Fallback baseado nas stacks
    if backend and frontend:
        return f"{backend.replace('-','')}+{frontend}"
    if backend:
        return backend.replace("-", "_")
    return "meu-projeto"


def _detect_infra_needs(text: str) -> tuple[bool, bool, bool, bool]:
    """Retorna (docker, cicd, nginx, auth)."""
    t = text.lower()
    docker = any(w in t for w in ["docker", "container", "compose", "containeriza"])
    cicd   = any(w in t for w in ["ci/cd", "ci", "cd", "github actions", "pipeline", "workflow", "deploy"])
    nginx  = any(w in t for w in ["nginx", "proxy"])
    auth   = any(w in t for w in ["auth", "autenticação", "jwt", "login", "oauth"])
    return docker, cicd, nginx, auth


def analyze(
    text: str,
    project_path: Path = None,
    llm=None,
    model: str = None,
) -> Intent:
    """
    Analisa texto livre e retorna Intent estruturado.
    Usa LLM apenas quando a análise baseada em regras é ambígua.
    """
    backend, frontend = _detect_stacks(text)
    action = _detect_action(text)
    docker, cicd, nginx, auth = _detect_infra_needs(text)

    # Se ação é infra mas stacks não detectadas, tenta do projeto
    if action == "infra" and not backend and project_path:
        try:
            from tools.knowledge_base import extract_infra_context
            ctx = extract_infra_context(project_path)
            backend = ctx.stack or ""
        except Exception:
            pass

    name = _detect_project_name(text, backend, frontend)

    intent = Intent(
        action=action,
        project_name=name,
        description=text,
        backend_stack=backend,
        frontend_stack=frontend,
        needs_docker=docker or action == "infra",
        needs_cicd=cicd,
        needs_nginx=nginx,
        needs_auth=auth,
    )

    # Validação: fullstack precisa de backend
    if intent.is_fullstack and not intent.backend_stack:
        intent.backend_stack = "nestjs"  # default
        intent.stacks = [intent.backend_stack, intent.frontend_stack]

    # Se ambíguo e temos LLM, refina
    if llm and _is_ambiguous(intent, text):
        intent = _llm_refine(intent, text, llm, model)

    console.print(f"  [dim]Intent: {intent.to_summary()}[/dim]")
    return intent


def _is_ambiguous(intent: Intent, text: str) -> bool:
    """Retorna True se a intenção não ficou clara."""
    return not intent.backend_stack and not intent.frontend_stack and intent.action not in ("search", "ask", "study")


def _llm_refine(intent: Intent, text: str, llm, model: str) -> Intent:
    """Usa LLM para resolver ambiguidade."""
    stacks_str = "nestjs, nextjs, angular, spring-boot, python, dotnet"
    prompt = (
        f"User request: \"{text}\"\n\n"
        f"Available stacks: {stacks_str}\n\n"
        "Return JSON:\n"
        "{\"backend\": \"nestjs\", \"frontend\": \"nextjs or empty\", \"action\": \"new\", \"name\": \"project-name\"}"
    )
    try:
        resp = llm.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            system="Extract project intent. Return only raw JSON.",
            stream=False,
        )
        import json
        m = re.search(r"\{.*?\}", resp, re.DOTALL)
        if m:
            data = json.loads(m.group())
            if data.get("backend"):
                intent.backend_stack = STACK_ALIASES.get(data["backend"].lower(), data["backend"])
            if data.get("frontend"):
                intent.frontend_stack = STACK_ALIASES.get(data["frontend"].lower(), data["frontend"])
            if data.get("name"):
                intent.project_name = data["name"]
            if data.get("action"):
                intent.action = data["action"]
    except Exception:
        pass
    return intent
