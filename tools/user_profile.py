"""
User Profile — memória das preferências e estilo de comunicação do usuário.

Aprende e lembra:
  - Como o usuário escreve (abreviações, termos informais PT)
  - Tecnologias que prefere
  - Padrões de projeto que usa sempre
  - Decisões que tomou no passado

Armazenado em: .devai/user_profile.json (por projeto) e ~/config/devai/profile.json (global)
"""

import json
import re
import time
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()

GLOBAL_PROFILE_DIR  = Path.home() / ".config" / "devai"
GLOBAL_PROFILE_FILE = GLOBAL_PROFILE_DIR / "profile.json"


DEFAULT_PROFILE = {
    "name":          "",
    "created_at":    0,
    "updated_at":    0,
    "preferences":   {
        "default_stack":    "",         # nestjs, spring, python, dotnet
        "default_db":       "",         # mongodb, postgres, mysql
        "code_language":    "english",  # english, portuguese
        "minimal":          True,       # evita extras não pedidos
        "confirm_writes":   True,
        "verbose":          1,
    },
    "communication": {
        "language": "pt-br",
        "style":    "informal",         # formal, informal
        "aliases":  {},                 # {"tals": "etc", "oq": "o que"}
    },
    "history": {
        "stacks_used":   [],
        "dbs_used":      [],
        "entities_seen": [],
        "commands_run":  0,
    },
    "tech_decisions": {},   # {"project-name": {"stack": "nestjs", "db": "mongodb"}}
}

# Vocabulário informal PT → significado
PT_INFORMAL_VOCAB = {
    # Abreviações comuns
    "oq":     "o que",
    "tals":   "etc, e outros",
    "tbm":    "também",
    "mto":    "muito",
    "pra":    "para",
    "pro":    "para o",
    "ia":     "inteligência artificial / agente",
    "n":      "não",
    "ñ":      "não",
    "q":      "que",
    "td":     "todo",
    "tdo":    "todo",
    "vc":     "você",
    "mt":     "muito",
    "vlw":    "valeu",
    "blz":    "beleza",

    # Termos técnicos informais
    "repo":   "repository / repositório",
    "app":    "aplicação",
    "api":    "API REST",
    "lib":    "biblioteca / library",
    "dep":    "dependência",
    "env":    "variável de ambiente",
    "prod":   "produção",
    "dev":    "desenvolvimento / developer",
    "config": "configuração",
    "auth":   "autenticação",
    "db":     "banco de dados",
    "crud":   "Create Read Update Delete",

    # Ações implícitas
    "configura":  "configure / setup",
    "arruma":     "fix / correct",
    "melhora":    "improve / enhance",
    "adiciona":   "add",
    "cria":       "create",
    "faz":        "create / implement",
    "testa":      "test",
    "atualiza":   "update",
}

# Padrões de intenção que o usuário usa
INTENT_PATTERNS = [
    # "configure o docker" → infra/docker
    (r"\b(configur[ae]|setup|faz[er]*)\s+.*(docker|compose)\b",            "infra/docker"),
    (r"\b(configur[ae]|setup)\s+.*(swagger|openapi)\b",                     "feature/swagger"),
    (r"\b(configur[ae]|setup)\s+.*(cors)\b",                               "feature/cors"),
    (r"\b(configur[ae]|adiciona)\s+.*(auth|jwt|login)\b",                  "feature/auth"),
    (r"\b(configur[ae]|adiciona)\s+.*(kafka)\b",                           "feature/kafka"),
    (r"\b(configur[ae]|adiciona)\s+.*(redis)\b",                           "feature/redis"),
    (r"\b(cria?|faz[er]*|gera?)\s+.*(crud|api|rest)\b",                    "new/api"),
    (r"\b(arruma?|corrige?|fix)\s+",                                        "fix"),
    (r"\b(melhora?|refatora?|otimiza?)\s+",                                 "improve"),
    (r"\b(testa?|valida?)\s+",                                              "test/validate"),

    # Tecnologia implícita
    (r"\bcom\s+(mongo|mongodb)\b",                                          "db/mongodb"),
    (r"\bcom\s+(postgres|postgresql|pg)\b",                                 "db/postgres"),
    (r"\bcom\s+(mysql|mariadb)\b",                                          "db/mysql"),
    (r"\btem\s+(mongo|mongodb)\b",                                          "db/mongodb"),
    (r"\btem\s+(postgres|postgresql)\b",                                    "db/postgres"),

    # Qualificadores importantes
    (r"\b(s[oó]|apenas|s[oó] o necess[aá]rio|minimal)\b",                  "qualifier/minimal"),
    (r"\bem\s+inglês\b",                                                    "qualifier/english"),
    (r"\bem\s+portugu[eê]s\b",                                              "qualifier/portuguese"),
    (r"\btodo o?\s+c[oó]digo\b",                                            "qualifier/all-code"),
]


def load_profile() -> dict:
    """Carrega perfil global do usuário."""
    if GLOBAL_PROFILE_FILE.exists():
        try:
            return {**DEFAULT_PROFILE, **json.loads(GLOBAL_PROFILE_FILE.read_text())}
        except Exception:
            pass
    return dict(DEFAULT_PROFILE)


def save_profile(profile: dict) -> None:
    """Salva perfil global."""
    GLOBAL_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    profile["updated_at"] = time.time()
    GLOBAL_PROFILE_FILE.write_text(json.dumps(profile, indent=2, ensure_ascii=False))


def learn_from_description(description: str) -> dict:
    """
    Aprende com a descrição do usuário.
    Detecta tecnologias, estilo e preferências implícitas.
    Retorna hints detectados.
    """
    profile = load_profile()
    hints   = {}
    desc    = description.lower()

    # Detecta tecnologias mencionadas
    if any(w in desc for w in ["nestjs","nest.js","typescript api"]):
        hints["stack"] = "nestjs"
        if "nestjs" not in profile["history"]["stacks_used"]:
            profile["history"]["stacks_used"].append("nestjs")

    if any(w in desc for w in ["spring","java api","spring boot"]):
        hints["stack"] = "spring"

    if any(w in desc for w in ["fastapi","python api","flask","django"]):
        hints["stack"] = "python"

    # Detecta banco de dados
    if any(w in desc for w in ["mongodb","mongo","nosql"]):
        hints["db"] = "mongodb"
        if "mongodb" not in profile["history"]["dbs_used"]:
            profile["history"]["dbs_used"].append("mongodb")

    if any(w in desc for w in ["postgres","postgresql","pg "]):
        hints["db"] = "postgres"

    # Detecta qualificadores
    if re.search(r"\bs[oó]\b|\bapenas\b|\bminimal\b|\bs[oó] o necess[aá]rio\b", desc):
        hints["minimal"] = True

    if re.search(r"\bem\s+inglês\b|\bingles\b|\bin english\b|\bcode.*english\b", desc):
        hints["code_language"] = "english"

    # Incrementa contador
    profile["history"]["commands_run"] = profile["history"].get("commands_run", 0) + 1

    save_profile(profile)
    return hints


def normalize_description(description: str) -> str:
    """
    Normaliza descrição do usuário:
    - Expande abreviações informais
    - Mantém a intenção original
    """
    text = description

    # Expande abreviações comuns
    replacements = {
        r"\boq\b":   "o que",
        r"\btbm\b":  "também",
        r"\btals\b": "etc",
        r"\bpra\b":  "para",
        r"\bpro\b":  "para o",
        r"\bn\b(?!\w)": "não",  # "n" sozinho = não
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text


def get_intent_hints(description: str) -> list[str]:
    """Detecta intenções a partir de padrões de escrita do usuário."""
    hints = []
    desc  = description.lower()
    for pattern, intent in INTENT_PATTERNS:
        if re.search(pattern, desc, re.IGNORECASE):
            hints.append(intent)
    return hints


def show_profile():
    """Mostra o perfil atual do usuário."""
    profile = load_profile()
    from rich.table import Table

    t = Table(title="👤 Perfil do Usuário", border_style="cyan")
    t.add_column("Campo",   style="cyan",  width=20)
    t.add_column("Valor",   style="white")

    prefs = profile["preferences"]
    hist  = profile["history"]

    t.add_row("Stack preferida",   prefs.get("default_stack","—") or "—")
    t.add_row("DB preferido",      prefs.get("default_db","—") or "—")
    t.add_row("Idioma do código",  prefs.get("code_language","english"))
    t.add_row("Modo minimal",      "✓" if prefs.get("minimal") else "✗")
    t.add_row("Stacks usadas",     ", ".join(hist.get("stacks_used",[])[:5]) or "—")
    t.add_row("DBs usados",        ", ".join(hist.get("dbs_used",[])[:5]) or "—")
    t.add_row("Comandos rodados",  str(hist.get("commands_run",0)))

    console.print(t)


def save_tech_decision(project_name: str, stack: str, db: str, extras: list = None):
    """Salva decisão tecnológica de um projeto para referência futura."""
    profile = load_profile()
    if "tech_decisions" not in profile:
        profile["tech_decisions"] = {}
    profile["tech_decisions"][project_name] = {
        "stack":   stack,
        "db":      db,
        "extras":  extras or [],
        "at":      time.strftime("%Y-%m-%d"),
    }
    save_profile(profile)
