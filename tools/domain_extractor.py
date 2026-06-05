"""
Domain Extractor — processa a descrição em 2 fases antes de extrair entidades.

FASE 1 — Pré-processamento determinístico (sem LLM):
  Separa o que o usuário pediu em categorias:
    entities_hint  → substantivos de domínio explícitos (User, Product, Order)
    infra_requests → docker, redis, kafka, nginx, ci/cd
    db_type        → banco de dados detectado
    has_auth       → autenticação explicitamente pedida
    language       → idioma do código
    clean_desc     → descrição limpa, sem instruções técnicas

FASE 2 — LLM só extrai entidades, recebe descrição já limpa
  Nunca extrai nomes de entidades de instruções como:
  "configure todo o docker", "todo código em inglês", "use mongoDb"
"""

import json
import re
from rich.console import Console
from config import MODEL_CODE
from tools.db_strategy import detect_database, get_strategy

console = Console()

# ── Termos que NÃO são entidades ──────────────────────────────────────────────
NOT_ENTITIES = {
    # Bancos
    "mongodb","mongo","postgres","postgresql","mysql","sqlite","mariadb",
    "redis","cassandra","dynamodb","firebase","supabase","banco","database","db",
    # ORMs
    "mongoose","typeorm","prisma","sequelize","knex","drizzle",
    # Frameworks
    "nestjs","nest","express","fastify","nextjs","next","angular","react",
    "vue","nuxt","spring","springboot","fastapi","django","flask","dotnet",
    "net","csharp",
    # Infra
    "docker","dockerfile","compose","dockercompose","kubernetes","k8s","nginx",
    "aws","gcp","azure","s3","minio","rabbitmq","kafka","bull","celery",
    "redis","sentinel",
    # Auth
    "jwt","oauth","passport","auth0","keycloak","token","bearer",
    # Libs/tools
    "winston","swagger","openapi","jest","mocha","eslint","prettier",
    "typescript","javascript","english","inglês","inglês",
    # Verbos/instruções (critical)
    "configure","config","configurar","configuração","setup","install",
    "create","criar","build","generate","gerar","implement","implementar",
    # Genéricos
    "api","app","application","system","service","module","feature",
    "crud","rest","http","endpoint","todo","all","code","código",
    "com","para","use","usar","com","toda","todo","todos","todas",
}

# ── Palavras que indicam auth explicitamente ──────────────────────────────────
AUTH_KEYWORDS = {
    "auth","autenticação","autenticar","authentication","login","logout",
    "signin","signup","jwt","token","bearer","oauth","oauth2","sso","saml",
    "roles","permissions","rbac","guards","session","sessão","password reset",
}

# ── Padrões de instrução a remover antes do LLM ───────────────────────────────
INSTRUCTION_PATTERNS = [
    r"configure\s+(?:todo\s+(?:o\s+)?)?(?:o\s+)?docker(?:-compose)?(?:\s+com\s+docker-compose)?",
    r"configure\s+(?:o\s+)?\w+",
    r"todo\s+(?:o\s+)?c[oó]digo\s+em\s+ingl[eê]s",
    r"all\s+code\s+in\s+english",
    r"(?:use|usa|usar|using)\s+(?:a?\s+)?(?:banco\s+de\s+dados|banco|database\s+)?(?:de\s+)?\w+",
    r"banco\s+de\s+dados\s+\w+",
    r"(?:com|with)\s+docker-compose",
    r"docker-compose",
    r"em\s+ingl[eê]s",
    r"in\s+english",
    r"todo\s+o\s+docker",
]

SYSTEM = """You are extracting ONLY the business domain entities from a software description.

Return ONLY this JSON (no markdown, no explanation):
{"entities": ["User", "Product"], "description_summary": "User CRUD API with MongoDB"}

STRICT RULES:
- entities: ONLY real business nouns explicitly named (User, Product, Order, Post, Comment, Category...)
- A business entity represents a data record that will be stored in the database
- NEVER include: database names, framework names, infrastructure, configuration words
- NEVER include: words from instructions like "configure", "setup", "docker", "english"
- NEVER include: words that are NOT proper nouns for data models
- If description says "CRUD de usuários" → entity is "User"
- If description says "configure docker" → that is NOT an entity, ignore it
- Max 6 entities, min 1
- Return ONLY the JSON"""


def _preprocess(description: str) -> dict:
    """
    FASE 1: Processa a descrição deterministicamente antes do LLM.
    Separa entidades óbvias, infra, banco, auth, idioma.
    Retorna descrição limpa para enviar ao LLM.
    """
    text = description.lower()

    # Detecta banco
    db_type = detect_database(description)

    # Detecta auth
    has_auth = any(kw in text for kw in AUTH_KEYWORDS)

    # Detecta idioma
    language = "english" if ("inglês" in text or "english" in text or "em inglês" in text) else "portuguese"

    # Detecta pedidos de infra (não são entidades)
    infra_hints = []
    if any(w in text for w in ["docker", "compose", "dockerfile"]):
        infra_hints.append("docker")
    if any(w in text for w in ["redis", "cache"]):
        infra_hints.append("redis")
    if any(w in text for w in ["kafka"]):
        infra_hints.append("kafka")

    # Limpa a descrição — remove instruções técnicas antes de enviar ao LLM
    clean = description
    for pattern in INSTRUCTION_PATTERNS:
        clean = re.sub(pattern, "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s{2,}", " ", clean).strip(" ,.")

    # Extrai entidades óbvias da descrição limpa (substantivos capitalizados ou comuns)
    obvious_map = {
        # Português → entidade singular PascalCase
        r"\busu[aá]rio[s]?\b":          "User",
        r"\bproduto[s]?\b":              "Product",
        r"\bpedido[s]?\b":               "Order",
        r"\blivro[s]?\b":                "Book",
        r"\bautor[es]*\b":               "Author",
        r"\bcliente[s]?\b":              "Customer",
        r"\bcategoria[s]?\b":            "Category",
        r"\bpagamento[s]?\b":            "Payment",
        r"\bfatura[s]?\b":               "Invoice",
        r"\btarefa[s]?\b":               "Task",
        r"\bnotifica[cç][aã]o[oe]?[s]?\b": "Notification",
        r"\b(?:cart|carrinho[s]?)\b":    "Cart",
        r"\bitem[s]?\b":                 "Item",
        r"\bcoment[aá]rio[s]?\b":        "Comment",
        r"\bpost[s]?\b":                 "Post",
        r"\bevento[s]?\b":               "Event",
        r"\bmensagem[ns]?\b":            "Message",
        r"\bperfil[s]?\b":               "Profile",
        r"\bassinatura[s]?\b":           "Subscription",
        r"\bcupom[ns]?\b":               "Coupon",
        r"\bestoque[s]?\b":              "Inventory",
        r"\bfuncion[aá]rio[s]?\b":       "Employee",
        r"\bdepartamento[s]?\b":         "Department",
        r"\bfornecedor[es]*\b":          "Supplier",
        r"\bcontrato[s]?\b":             "Contract",
        r"\brelatório[s]?\b":            "Report",
        r"\bagendamento[s]?\b":          "Appointment",
        r"\btransação[oe]?[s]?\b":       "Transaction",
        r"\bconta[s]?\b":                "Account",
        r"\barquivo[s]?\b":              "File",
        r"\bavalia[cç][aã]o[oe]?[s]?\b": "Review",
        # English
        r"\b(?:user|users)\b":           "User",
        r"\b(?:book|books)\b":           "Book",
        r"\b(?:product|products)\b":     "Product",
        r"\b(?:order|orders)\b":         "Order",
        r"\b(?:customer|customers)\b":   "Customer",
        r"\b(?:category|categories)\b":  "Category",
        r"\b(?:payment|payments)\b":     "Payment",
        r"\b(?:invoice|invoices)\b":     "Invoice",
        r"\b(?:task|tasks)\b":           "Task",
        r"\b(?:post|posts)\b":           "Post",
        r"\b(?:comment|comments)\b":     "Comment",
        r"\b(?:event|events)\b":         "Event",
        r"\b(?:message|messages)\b":     "Message",
        r"\b(?:file|files)\b":           "File",
        r"\b(?:review|reviews)\b":       "Review",
        r"\b(?:report|reports)\b":       "Report",
        r"\b(?:subscription|subscriptions)\b": "Subscription",
        r"\b(?:inventory|inventories)\b": "Inventory",
        r"\b(?:employee|employees)\b":   "Employee",
    }
    hints = []
    for pattern, entity in obvious_map.items():
        if re.search(pattern, text) and entity not in hints:
            hints.append(entity)

    return {
        "db_type": db_type,
        "has_auth": has_auth,
        "language": language,
        "infra_hints": infra_hints,
        "clean_description": clean,
        "entity_hints": hints,
    }


def _is_valid_entity(name: str) -> str | None:
    """Valida e normaliza um nome de entidade. Retorna None se inválido."""
    # Remove whitespace e chars especiais
    clean = re.sub(r"[^a-zA-Z]", "", name).strip()
    if len(clean) < 2 or len(clean) > 30:
        return None

    # PascalCase
    clean = clean[0].upper() + clean[1:]

    # Rejeita termos técnicos
    if clean.lower() in NOT_ENTITIES:
        return None

    # Rejeita se parece instrução (contém verbos comuns no início)
    if re.match(r"^(Configure|Setup|Create|Build|Use|Install|Generate)", clean):
        return None

    return clean


def _sanitize_entities(raw: list) -> list[str]:
    result = []
    for name in (raw or []):
        if not isinstance(name, str):
            continue
        valid = _is_valid_entity(name)
        if valid and valid not in result:
            result.append(valid)
    return result[:6]


def _has_auth_requested(description: str) -> bool:
    """Returns True ONLY if auth was explicitly requested."""
    text = description.lower()
    return any(kw in text for kw in AUTH_KEYWORDS)


def extract_domain(description: str, llm) -> dict:
    # Normaliza a descrição (expande abreviações informais do usuário)
    try:
        from tools.user_profile import normalize_description, learn_from_description
        description = normalize_description(description)
        learn_from_description(description)   # aprende preferências
    except Exception:
        pass

    """
    Extrai entidades e banco da descrição.
    FASE 1: pré-processa deterministicamente.
    FASE 2: LLM só recebe descrição limpa.
    """
    console.print("[dim]→ Processando descrição...[/dim]")

    # ── FASE 1: Pré-processamento sem LLM ────────────────────────────────────
    pre = _preprocess(description)
    db_type   = pre["db_type"]
    has_auth  = pre["has_auth"]
    language  = pre["language"]
    clean_desc = pre["clean_description"]
    entity_hints = pre["entity_hints"]
    strategy  = get_strategy(db_type)

    console.print(f"  [dim]Banco: {db_type} | Auth: {has_auth} | Idioma: {language}[/dim]")
    console.print(f"  [dim]Descrição limpa: {clean_desc[:80]}[/dim]")
    if entity_hints:
        console.print(f"  [dim]Entidades detectadas: {', '.join(entity_hints)}[/dim]")

    # ── FASE 2: LLM extrai entidades da descrição LIMPA ──────────────────────
    entities = []

    if clean_desc.strip():
        try:
            resp = llm.chat(
                model=MODEL_CODE,
                messages=[{"role": "user", "content":
                    f"Extract business entities from: {clean_desc}\n"
                    f"Hint - obvious entities already detected: {entity_hints}\n"
                    f"Return JSON only: {{\"entities\": [\"User\"], \"description_summary\": \"...\"}}"
                }],
                system=SYSTEM,
                stream=False,
            )
            parsed = _parse(resp)
            if parsed:
                entities = _sanitize_entities(parsed.get("entities", []))
        except Exception as e:
            console.print(f"  [dim]LLM error: {e}[/dim]")

    # ── Combina hints com resultado do LLM ────────────────────────────────────
    for hint in entity_hints:
        if hint not in entities:
            entities.append(hint)

    # Remove duplicatas e inválidos
    entities = _sanitize_entities(entities)

    # Fallback
    if not entities:
        console.print("[yellow]  ↻ Nenhuma entidade detectada — usando 'Item' como padrão[/yellow]")
        entities = ["Item"]

    domain = {
        "entities":            entities,
        "has_auth":            has_auth,
        "has_jwt":             has_auth,
        "db_type":             db_type,
        "orm":                 strategy.orm,
        "is_nosql":            strategy.is_nosql,
        "language":            language,
        "infra_hints":         pre["infra_hints"],
        "description_summary": clean_desc[:120],
    }

    console.print(f"  ✓ Entidades: [bold]{', '.join(entities)}[/bold]")
    console.print(f"  ✓ Banco: [bold]{db_type}[/bold] ({strategy.orm})")
    if has_auth:
        console.print("  ✓ Auth: sim")
    if pre["infra_hints"]:
        console.print(f"  ✓ Infra pedida: {', '.join(pre['infra_hints'])}")

    return domain


def _parse(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text.strip())
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return None
