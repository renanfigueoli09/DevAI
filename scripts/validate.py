"""
DevAI Training Validator v2 — Dois modos de validação:

  Fase 1 — Knowledge Check: verifica se o vector store contém as respostas certas
            (sem LLM — testa a qualidade do training store diretamente)

  Fase 2 — Generation Check: gera código real e verifica se está correto
            (usa LLM com o contexto do training)

O --fix agora salva as respostas corretas E verifica que podem ser recuperadas
antes de passar para a próxima rodada.

Uso:
  python scripts/validate.py              # valida tudo
  python scripts/validate.py --fix        # valida + retreina + re-valida
  python scripts/validate.py --fix --rounds 5
  python scripts/validate.py --knowledge  # só fase 1 (rápido, sem LLM)
  python scripts/validate.py --generation # só fase 2 (geração real)
"""

import argparse, json, re, sys, time
from dataclasses import dataclass, field
from pathlib import Path

DEVAI_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(DEVAI_DIR))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.rule import Rule

console = Console()


# ─── Fase 1: Knowledge Check (sem LLM) ───────────────────────────────────────
# Verifica se o vector store contém padrões corretos pesquisando por keywords

KNOWLEDGE_CHECKS = [
    {
        "name":     "Mongoose: required=! optional=?",
        "queries":  ["mongoose required field !", "Prop required true field!"],
        "must_find": ["!", "required", "@Prop"],
        "must_not":  ["findOneBy", "TypeOrmModule"],
        "weight": 3,
    },
    {
        "name":     "findOneBy não existe no Mongoose",
        "queries":  ["findOneBy does not exist Mongoose findById"],
        "must_find": ["findById", "findOneBy"],
        "must_not":  [],
        "weight": 3,
    },
    {
        "name":     "MongooseModule.forFeature (não TypeOrmModule)",
        "queries":  ["MongooseModule forFeature Book schema module"],
        "must_find": ["MongooseModule.forFeature", "BookSchema"],
        "must_not":  ["TypeOrmModule.forFeature"],
        "weight": 3,
    },
    {
        "name":     "app.module MongoDB = MongooseModule.forRoot",
        "queries":  ["MongooseModule forRoot MONGODB_URI app module"],
        "must_find": ["MongooseModule.forRoot", "MONGODB_URI"],
        "must_not":  ["DB_HOST", "TypeOrmModule"],
        "weight": 3,
    },
    {
        "name":     "livros → Book (não Livros)",
        "queries":  ["livros entity Book português singular"],
        "must_find": ["Book", "livros"],
        "must_not":  [],
        "weight": 3,
    },
    {
        "name":     "docker config não cria src/docker/",
        "queries":  ["configure docker src folder never"],
        "must_find": ["docker-compose", "NEVER", "src/"],
        "must_not":  [],
        "weight": 3,
    },
    {
        "name":     "usuários ≠ auth (has_auth=false)",
        "queries":  ["usuários has_auth false auth login jwt"],
        "must_find": ["false", "usuários"],
        "must_not":  [],
        "weight": 3,
    },
    {
        "name":     "PartialType de @nestjs/mapped-types",
        "queries":  ["PartialType @nestjs/mapped-types not @nestjs/common"],
        "must_find": ["@nestjs/mapped-types", "PartialType"],
        "must_not":  ["@nestjs/common"],
        "weight": 3,
    },
    {
        "name":     "MongoDB healthcheck: mongosh ping",
        "queries":  ["MongoDB healthcheck mongosh adminCommand ping"],
        "must_find": ["mongosh", "ping"],
        "must_not":  ["pg_isready"],
        "weight": 2,
    },
    {
        "name":     "docker only = sem Redis/Kafka",
        "queries":  ["MongoDB only docker compose no Redis Kafka"],
        "must_find": ["only", "redis", "no"],
        "must_not":  [],
        "weight": 2,
    },
    {
        "name":     "TS2307 module not found → criar arquivo",
        "queries":  ["TS2307 module not found book.module create fix"],
        "must_find": ["BookModule", "@Module", "create"],
        "must_not":  [],
        "weight": 2,
    },
    {
        "name":     "Spring MongoDB: @Document não @Entity",
        "queries":  ["Spring Boot MongoDB @Document MongoRepository"],
        "must_find": ["@Document", "MongoRepository"],
        "must_not":  ["@Entity", "JpaRepository"],
        "weight": 2,
    },
    {
        "name":     "FastAPI: AsyncIOMotorClient (não pymongo)",
        "queries":  ["FastAPI MongoDB Motor AsyncIOMotorClient async"],
        "must_find": ["AsyncIOMotorClient", "motor"],
        "must_not":  ["MongoClient", "pymongo"],
        "weight": 2,
    },
]

# ─── Geração dinâmica de checks com base no training store ───────────────────

_DYNAMIC_CHECKS_CACHE = None
_DYNAMIC_CHECKS_FILE  = DEVAI_DIR / "training" / "dynamic_checks.json"


def _generate_checks_for_topic(topic: str, content_sample: str, llm=None, model: str = "") -> list[dict]:
    """
    Gera checks de validação DETERMINISTICAMENTE a partir do conteúdo do training.
    Extrai keywords específicos do código encontrado — não depende do LLM.
    """
    import re as _re

    checks = []
    text = content_sample.lower()
    topic_label = topic.replace("_", " ").replace("+", " + ")

    # Extract code-specific keywords from training content
    pat_dec = r'@[A-Za-z][A-Za-z]+'
    pat_cls = r'class ([A-Z][A-Za-z]+)'
    pat_mth = r'[.](?:findById|findOne|findAll|create|update|delete|save|insert|emit)[(]'
    decorators = list(dict.fromkeys(_re.findall(pat_dec, content_sample)))[:4]
    classes    = list(dict.fromkeys(_re.findall(pat_cls, content_sample)))[:3]
    methods    = list(dict.fromkeys(_re.findall(pat_mth, content_sample)))[:3]
    imports    = []

    # Build must_find from most specific keywords found
    must_find = []
    if decorators: must_find.extend(decorators[:2])
    if imports:    must_find.extend([i.split("/")[-1] for i in imports[:2]])
    if methods:    must_find.extend(list(dict.fromkeys(methods))[:2])

    # Only create check if we found meaningful keywords
    if len(must_find) >= 2:
        checks.append({
            "name":      f"{topic_label}: padrões de código",
            "queries":   [f"{topic} pattern code example", topic_label],
            "must_find": must_find[:4],
            "must_not":  [],
            "weight":    1,
            "dynamic":   True,
            "source_topic": topic,
        })

    # Second check: look for common wrong patterns for this topic type
    if "mongo" in topic or "mongoose" in topic:
        checks.append({
            "name": f"{topic_label}: não usa TypeORM",
            "queries": [f"{topic} schema service"],
            "must_find": [kw for kw in ["Mongoose", "mongo", "@Schema", "findById"] if kw.lower() in text][:3],
            "must_not": ["TypeOrmModule", "@Entity", "Repository<"],
            "weight": 1,
            "dynamic": True,
            "source_topic": topic,
        })
    elif "kafka" in topic:
        checks.append({
            "name": f"{topic_label}: producer consumer",
            "queries": [f"{topic} producer consumer example"],
            "must_find": [kw for kw in ["kafka", "producer", "consumer", "@EventPattern", "emit"] if kw.lower() in text][:3],
            "must_not": [],
            "weight": 1,
            "dynamic": True,
            "source_topic": topic,
        })
    elif "redis" in topic:
        checks.append({
            "name": f"{topic_label}: cache",
            "queries": [f"{topic} cache redis example"],
            "must_find": [kw for kw in ["redis", "cache", "CacheModule", "CACHE_MANAGER", "ioredis"] if kw.lower() in text][:3],
            "must_not": [],
            "weight": 1,
            "dynamic": True,
            "source_topic": topic,
        })

    return [c for c in checks if len(c.get("must_find", [])) >= 1]


def load_dynamic_checks(llm=None, model: str = "") -> list[dict]:
    """
    Carrega checks dinâmicos gerados a partir dos tópicos treinados.
    Regenera quando há novos tópicos estudados.
    """
    global _DYNAMIC_CHECKS_CACHE

    # Load from cache if recent AND not empty
    if _DYNAMIC_CHECKS_FILE.exists():
        try:
            cached = json.loads(_DYNAMIC_CHECKS_FILE.read_text())
            age_h  = (time.time() - cached.get("generated_at", 0)) / 3600
            cached_count = len(cached.get("checks", []))
            # Check if new topics were added since cache
            try:
                from scripts.study import load_journal
                journal = load_journal()
                studied_count = sum(1 for e in journal.values() if e.times_studied >= 2)
                cache_studied = cached.get("studied_count", 0)
                # Regenerate if: new topics added OR cache is old OR cache is empty
                if age_h < 12 and cached_count > 0 and studied_count == cache_studied:
                    _DYNAMIC_CHECKS_CACHE = cached["checks"]
                    return _DYNAMIC_CHECKS_CACHE
            except Exception:
                if age_h < 24 and cached_count > 0:
                    _DYNAMIC_CHECKS_CACHE = cached["checks"]
                    return _DYNAMIC_CHECKS_CACHE
        except Exception:
            pass

    # llm is optional now — generation is deterministic

    # Generate checks for well-studied topics not yet in KNOWLEDGE_CHECKS
    existing_topics = {c["name"].lower() for c in KNOWLEDGE_CHECKS}
    new_checks = []

    try:
        from tools.vector_store import search_relevant
        from scripts.study import load_journal, SEARCH_CURRICULUM

        journal = load_journal()
        # Topics studied well (times_studied >= 2) and not already validated
        candidate_topics = [
            t for t, e in sorted(journal.items(),
                                  key=lambda x: x[1].times_studied, reverse=True)
            if e.times_studied >= 2
            and not any(t.replace("_","").replace("+","") in ex for ex in existing_topics)
        ][:10]  # max 10 new topics to validate

        for topic in candidate_topics:
            # Get training content for this topic
            content_sample = search_relevant(
                f"{topic} pattern example code",
                limit=2, exclude_topics=["docker","devops"]
            )
            if not content_sample or len(content_sample) < 100:
                continue

            checks = _generate_checks_for_topic(topic, content_sample)
            for c in checks:
                c["dynamic"] = True
                c["source_topic"] = topic
            new_checks.extend(checks)

    except Exception as e:
        pass

    # Cache (always save, even if empty, with studied_count for invalidation)
    try:
        from scripts.study import load_journal
        journal = load_journal()
        studied_count = sum(1 for e in journal.values() if e.times_studied >= 2)
    except Exception:
        studied_count = 0

    _DYNAMIC_CHECKS_FILE.write_text(
        json.dumps({
            "generated_at": time.time(),
            "studied_count": studied_count,
            "checks": new_checks,
        }, indent=2, ensure_ascii=False)
    )
    if new_checks:
        console.print(f"  [green]✓[/green] {len(new_checks)} checks dinâmicos gerados e salvos")

    _DYNAMIC_CHECKS_CACHE = new_checks
    return new_checks


def _strip_negations(text: str) -> str:
    """Remove linhas que negam termos (NEVER, NOT, don't use, não use)."""
    import re
    lines = text.split("\n")
    # Remove lines where the term appears in a negation context
    cleaned = []
    for line in lines:
        ll = line.lower()
        is_negation = any(neg in ll for neg in [
            "never", "not ", "don't", "avoid", "instead", "wrong:",
            "não use", "não é", "errado", "proibido", "forbidden",
            "← typeorm", "← wrong", "(typeorm", "typeorm only",
        ])
        cleaned.append("" if is_negation else line)
    return "\n".join(cleaned)


def check_knowledge(check: dict) -> tuple[bool, float, str]:
    """Verifica se o vector store tem a informação correta.
    Ignora termos que aparecem em contexto de negação (NEVER, NOT, etc.)
    """
    from tools.vector_store import search_relevant

    all_content = ""
    for q in check["queries"]:
        result = search_relevant(q, limit=3)
        all_content += result.lower() + "\n"

    # For must_not: strip negation context before checking
    # "NEVER use TypeOrmModule" should NOT count as TypeOrmModule being present
    content_for_must_not = _strip_negations(all_content)

    found   = [kw for kw in check["must_find"] if kw.lower() in all_content]
    wrong   = [kw for kw in check["must_not"]  if kw.lower() in content_for_must_not]
    missing = [kw for kw in check["must_find"] if kw.lower() not in all_content]

    w = check["weight"]
    if not check["must_find"]:
        score = w if not wrong else 0.0
    else:
        ratio = len(found) / len(check["must_find"])
        penalty = 0.0 if wrong else 1.0
        score = w * ratio * penalty

    passed = len(missing) <= len(check["must_find"]) // 2 and not wrong
    detail = f"found={found[:3]} missing={missing[:3]} wrong={wrong[:2]}"
    return passed, score, detail


# ─── Fase 2: Generation Check (com LLM) ──────────────────────────────────────

GENERATION_CHECKS = [
    {
        "name":    "schema.ts Mongoose strict mode",
        "prompt":  "Generate ONLY the content of book.schema.ts for NestJS Mongoose. Required fields: title (string), price (number). Optional: description (string). Use @Schema, @Prop, HydratedDocument, SchemaFactory. TypeScript strict mode.",
        "must_contain": ["@Schema", "@Prop", "title!:", "price!:", "description?:", "HydratedDocument", "SchemaFactory"],
        "must_not":     ["title?:", "price?:", "findOneBy", "@Entity"],
        "weight": 4,
    },
    {
        "name":    "service.ts Mongoose CRUD",
        "prompt":  "Generate ONLY the content of book.service.ts for NestJS Mongoose. Use @InjectModel, Model<BookDocument>. Methods: findAll, findOne(id), create(dto), update(id,dto), remove(id). Use findById, findByIdAndUpdate, findByIdAndDelete. Throw NotFoundException.",
        "must_contain": ["@InjectModel", "Model<", "findById", "NotFoundException"],
        "must_not":     ["findOneBy", "@InjectRepository", "Repository<"],
        "weight": 4,
    },
    {
        "name":    "dto.ts PartialType correto",
        "prompt":  "Generate ONLY the content of book.dto.ts for NestJS. CreateBookDto with title (string required). UpdateBookDto extends PartialType from @nestjs/mapped-types.",
        "must_contain": ["@nestjs/mapped-types", "PartialType", "UpdateBookDto"],
        "must_not":     ["from '@nestjs/common'"],
        "weight": 3,
    },
    {
        "name":    "docker-compose MongoDB only",
        "prompt":  "Generate ONLY a docker-compose.yml for NestJS app with MongoDB ONLY. No Redis, no Kafka, no Nginx. MongoDB healthcheck with mongosh ping. App depends_on db with service_healthy.",
        "must_contain": ["mongo:7.0", "mongosh", "service_healthy", "MONGODB_URI"],
        "must_not":     ["redis", "kafka", "nginx", "zookeeper"],
        "weight": 3,
    },
]


def run_generation_check(check: dict, llm, model: str) -> tuple[bool, float, str]:
    """Gera código e verifica se está correto."""
    from tools.vector_store import search_relevant

    ctx = search_relevant(check["prompt"][:200], limit=3,
                          exclude_topics=["docker","devops"] if "docker" not in check["name"].lower() else [])

    prompt = f"Training reference:\n{ctx[:800]}\n\n{check['prompt']}\n\nReturn ONLY the file content."

    try:
        resp = llm.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            system="Generate production-ready code. Follow the training reference exactly. Return ONLY file content.",
            stream=False,
        )
        resp = re.sub(r"^```\w*\n?|\n?```$", "", resp.strip(), flags=re.MULTILINE)
    except Exception as e:
        return False, 0.0, f"LLM error: {e}"

    r = resp.lower()
    found   = [kw for kw in check["must_contain"] if kw.lower() in r]
    wrong   = [kw for kw in check["must_not"]     if kw.lower() in r]
    missing = [kw for kw in check["must_contain"] if kw.lower() not in r]

    w = check["weight"]
    ratio = len(found) / len(check["must_contain"]) if check["must_contain"] else 1
    score = w * ratio * (0.0 if wrong else 1.0)
    passed = not missing and not wrong
    detail = f"found={found[:3]} missing={missing[:3]} wrong={wrong[:2]}"
    return passed, score, detail


# ─── Padrões críticos para retreinamento ─────────────────────────────────────

CRITICAL_PATTERNS = [
    ("qa:mongoose-required-bang", "nestjs_mongodb",
     "@Prop({required:true}) → field!: string  (! = required, NON-NULL ASSERTION)\n"
     "@Prop() → field?: string  (? = optional)\n"
     "NEVER: @Prop({required:true}) field?: string  (WRONG)\n"
     "NEVER: @Prop({required:true}) field: string   (WRONG, needs !)\n"
     "RULE: required=! | optional=? | NO EXCEPTIONS"),

    ("qa:mongoose-no-findOneBy", "nestjs_mongodb",
     "findOneBy does NOT exist in Mongoose. findOneBy is TypeORM-only.\n"
     "Mongoose CORRECT: findById(id), findByIdAndUpdate(id,{$set:dto},{new:true}), findByIdAndDelete(id)\n"
     "WRONG: this.model.findOneBy({_id:id})  ← TypeORM only\n"
     "CORRECT: this.model.findById(id).exec()"),

    ("qa:mongoose-forFeature", "nestjs_mongodb",
     "NestJS Mongoose module uses MongooseModule.forFeature NEVER TypeOrmModule.\n"
     "@Module({ imports: [MongooseModule.forFeature([{name: Book.name, schema: BookSchema}])] })\n"
     "WRONG: TypeOrmModule.forFeature([Book])  ← TypeORM only"),

    ("qa:app-module-mongodb", "nestjs_mongodb",
     "app.module.ts MongoDB: MongooseModule.forRoot(process.env.MONGODB_URI || 'mongodb://localhost:27017/app')\n"
     "WRONG: TypeOrmModule with DB_HOST/DB_PORT/DB_NAME  ← PostgreSQL config\n"
     "MongoDB uses MONGODB_URI, NOT DB_HOST/DB_PORT"),

    ("qa:livros-book", "nlp",
     "RULE: Portuguese entity words → English singular PascalCase\n"
     "livros → Book (NOT Livros, NOT livros)\n"
     "usuários → User | produtos → Product | pedidos → Order\n"
     "class name: Book | file: book.schema.ts | folder: src/book/"),

    ("qa:docker-no-src", "nlp",
     "RULE: 'configure docker' → docker-compose.yml + Dockerfile at ROOT\n"
     "NEVER create src/docker/ or src/mongodb/ or src/configure/\n"
     "src/ contains ONLY business domain entities: src/book/, src/user/"),

    ("qa:usuarios-no-auth", "nlp",
     "has_auth=true ONLY when: auth, autenticação, login, jwt, token, oauth, roles, permissions\n"
     "'API de usuários com MongoDB' → has_auth=FALSE (User is just an entity)\n"
     "'API com login JWT' → has_auth=TRUE"),

    ("qa:partialtype-mapped-types", "nestjs",
     "PartialType: ALWAYS from '@nestjs/mapped-types'\n"
     "CORRECT: import { PartialType } from '@nestjs/mapped-types';\n"
     "WRONG:   import { PartialType } from '@nestjs/common';   ← does NOT exist\n"
     "WRONG:   import { PartialType } from '@nestjs/swagger';  ← avoid"),

    ("qa:docker-mongodb-only", "docker",
     "When user says 'MongoDB only' or 'only MongoDB': docker-compose has ONLY app + mongo:7.0\n"
     "NO redis:, NO kafka:, NO nginx: unless explicitly requested\n"
     "'only' means ONLY what is mentioned"),

    ("qa:mongodb-healthcheck", "docker",
     "MongoDB healthcheck: mongosh --eval db.adminCommand('ping')\n"
     "test: [CMD, mongosh, --eval, db.adminCommand('ping')]\n"
     "interval: 15s | timeout: 10s | retries: 5\n"
     "NEVER pg_isready (PostgreSQL) or redis-cli for MongoDB"),

    ("qa:ts2307-create-module", "common_errors",
     "TS2307 Cannot find module './book/book.module': CREATE src/book/book.module.ts\n"
     "@Module({\n  imports: [MongooseModule.forFeature([{name:Book.name,schema:BookSchema}])],\n"
     "  providers: [BookService], controllers: [BookController], exports: [BookService]\n"
     "}) export class BookModule {}"),

    ("qa:spring-document-not-entity", "spring_boot_mongodb",
     "Spring Boot MongoDB: use @Document NOT @Entity\n"
     "@Document(collection='books') class Book { @Id String id; @NotBlank String title; }\n"
     "Repository: extends MongoRepository<Book, String>\n"
     "WRONG: @Entity, JpaRepository  ← those are JPA/PostgreSQL"),

    ("qa:fastapi-motor-not-pymongo", "python_fastapi",
     "FastAPI MongoDB: use Motor (async) NOT pymongo (sync)\n"
     "CORRECT: from motor.motor_asyncio import AsyncIOMotorClient\n"
     "WRONG:   from pymongo import MongoClient\n"
     "Motor is async-compatible with FastAPI async routes"),
]


def force_train(topic: str, llm, model: str) -> int:
    """Força retreinamento com padrões críticos + verifica recuperação."""
    from tools.vector_store import save, search_relevant, backfill_embeddings

    saved = 0
    console.print(f"  [cyan]→ Salvando {len(CRITICAL_PATTERNS)} padrões críticos...[/cyan]")

    # Salva TODOS os padrões críticos (não só do topic específico)
    for key, t, content in CRITICAL_PATTERNS:
        save(key, content, topic=t, source="critical_pattern")
        saved += 1

    # Gera embeddings imediatamente
    console.print("  [dim]→ Gerando embeddings...[/dim]")
    n_emb = backfill_embeddings()
    if n_emb:
        console.print(f"  [green]✓[/green] {n_emb} embeddings")

    # Verifica recuperação dos padrões críticos
    test_cases = [
        ("mongoose required field !", ["!", "required"]),
        ("livros entity name Book", ["Book"]),
        ("PartialType mapped-types", ["mapped-types"]),
        ("MongoDB healthcheck mongosh", ["mongosh"]),
    ]
    all_ok = True
    for query, expected in test_cases:
        result = search_relevant(query, limit=2)
        found = all(e.lower() in result.lower() for e in expected)
        icon = "✓" if found else "✗"
        if not found:
            all_ok = False
        console.print(f"  [{icon}] [{('green' if found else 'red')}]{icon}[/] Retrieval: '{query[:35]}' → {'OK' if found else 'FALHOU'}")

    if not all_ok:
        console.print("  [yellow]⚠ Retrieval fraco — rodando backfill novamente[/yellow]")
        backfill_embeddings()

    # Pesquisa web para tópicos específicos fracos
    try:
        from scripts.study import study_topic, SEARCH_CURRICULUM, load_discovered
        all_c = {**SEARCH_CURRICULUM, **load_discovered()}
        tmap = {
            "nestjs-mongodb":  ["nestjs_mongodb"],
            "nlp":             ["nlp_patterns"],
            "docker":          ["docker_patterns"],
            "nestjs-auth":     ["nestjs_auth"],
            "common-errors":   ["common_errors"],
            "spring-mongodb":  ["spring_mongodb"],
            "fastapi":         ["fastapi_mongodb"],
        }
        for sk in tmap.get(topic, []):
            if sk in all_c:
                n = study_topic(sk, all_c[sk][:3], llm, model, intensive=True)
                saved += n
                if n: console.print(f"  [green]✓[/green] {n} pesquisas web ({sk})")
    except Exception as e:
        console.print(f"  [dim]⚠ Web: {e}[/dim]")

    return saved


# ─── Main ─────────────────────────────────────────────────────────────────────

def run_knowledge_phase(llm=None, model: str = "") -> tuple[float, float, list]:
    """Fase 1: testa o vector store diretamente + checks dinâmicos do training."""
    results = []
    total_score = 0.0
    max_score   = 0.0

    # Static + dynamic checks
    all_checks = list(KNOWLEDGE_CHECKS)
    try:
        dynamic = load_dynamic_checks(llm, model)
        if dynamic:
            console.print(f"  [dim]+ {len(dynamic)} checks dinâmicos do training[/dim]")
            all_checks.extend(dynamic)
    except Exception:
        pass

    for check in all_checks:
        passed, score, detail = check_knowledge(check)
        results.append({"name": check["name"], "passed": passed,
                        "score": score, "max": check["weight"], "detail": detail})
        total_score += score
        max_score   += check["weight"]

        icon  = "[green]✓[/green]" if passed else "[red]✗[/red]"
        color = "green" if passed else "red"
        console.print(f"  {icon} [{color}][{score:.1f}/{check['weight']}][/{color}] {check['name']}")
        if not passed:
            console.print(f"    [dim]{detail}[/dim]")

    return total_score, max_score, results


def run_generation_phase(llm, model: str) -> tuple[float, float, list]:
    """Fase 2: gera código e verifica."""
    results = []
    total_score = 0.0
    max_score   = 0.0

    for check in GENERATION_CHECKS:
        passed, score, detail = run_generation_check(check, llm, model)
        results.append({"name": check["name"], "passed": passed,
                        "score": score, "max": check["weight"], "detail": detail})
        total_score += score
        max_score   += check["weight"]

        icon  = "[green]✓[/green]" if passed else "[red]✗[/red]"
        color = "green" if passed else "red"
        console.print(f"  {icon} [{color}][{score:.1f}/{check['weight']}][/{color}] {check['name']}")
        if not passed:
            console.print(f"    [dim]{detail}[/dim]")

    return total_score, max_score, results


def write_report(k_score, k_max, g_score, g_max, k_results, g_results) -> None:
    import datetime
    total = k_score + g_score
    maxt  = k_max + g_max
    pct   = total / maxt * 100 if maxt else 0
    bar   = "█" * int(pct/5) + "░" * (20 - int(pct/5))

    lines = [
        f"# DevAI Validation Report",
        f"*{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        f"",
        f"## Score: {pct:.0f}% `[{bar}]`  ({total:.1f}/{maxt:.1f})",
        f"",
        f"### Knowledge Check (vector store): {k_score:.1f}/{k_max:.1f}",
        f"| Check | Score | OK |",
        f"|---|---|---|",
    ]
    for r in k_results:
        icon = "✅" if r["passed"] else "❌"
        lines.append(f"| {r['name']} | {r['score']:.1f}/{r['max']} | {icon} |")

    lines += [f"", f"### Generation Check (LLM): {g_score:.1f}/{g_max:.1f}",
              f"| Check | Score | OK |", f"|---|---|---|"]
    for r in g_results:
        icon = "✅" if r["passed"] else "❌"
        lines.append(f"| {r['name']} | {r['score']:.1f}/{r['max']} | {icon} |")

    weak = [r for r in k_results + g_results if not r["passed"]]
    if weak:
        lines += ["", "## ❌ Falhou", ""]
        for r in weak:
            lines.append(f"- **{r['name']}** — {r['detail']}")

    lines += ["", "## Fix", "```bash",
              "python scripts/validate.py --fix --rounds 10",
              "./scripts/train_and_validate.sh", "```"]

    (DEVAI_DIR / "training" / "validation_report.md").write_text(
        "\n".join(lines), encoding="utf-8")

    # JSON for shell coordination (train_and_validate.sh reads this)
    # Maps check NAME keywords → study curriculum keys (must match SEARCH_CURRICULUM)
    _KEYWORD_TO_STUDY = {
        "mongoose":           "nestjs_mongodb",
        "mongoosemodule":     "nestjs_mongodb",
        "injectmodel":        "nestjs_mongodb",
        "schema.ts":          "nestjs_mongodb",
        "service.ts":         "nestjs_mongodb",
        "app.module mongodb": "nestjs_mongodb",
        "findoneBy":          "nestjs_mongodb",
        "partialtype":        "nestjs_auth",
        "jwtauthguard":       "nestjs_auth",
        "docker":             "docker_patterns",
        "healthcheck":        "docker_patterns",
        "mongosh":            "docker_patterns",
        "redis/kafka":        "docker_patterns",
        "livros":             "nlp_patterns",
        "usuários":           "nlp_patterns",
        "has_auth":           "nlp_patterns",
        "src/docker":         "nlp_patterns",
        "@document":          "spring_mongodb",
        "spring":             "spring_mongodb",
        "asynciomotorclient": "fastapi_mongodb",
        "fastapi":            "fastapi_mongodb",
        "ts2307":             "common_errors",
        "module not found":   "common_errors",
    }

    def _resolve_study_key(name: str) -> str:
        nl = name.lower()
        for kw, key in _KEYWORD_TO_STUDY.items():
            if kw in nl:
                return key
        import re as _re
        return _re.sub(r"[^\w]", "_", nl)[:30].strip("_")

    import json as _json
    # k_results and g_results are dicts — use .get() not .attribute
    all_results = k_results + g_results
    total = k_score + g_score
    maxt  = k_max + g_max
    pct   = round(total / maxt * 100, 1) if maxt else 0

    # Group by topic to get pass_rate per topic
    topic_scores: dict = {}
    for r in all_results:
        name = r.get("name","unknown")
        topic = name  # use check name as topic identifier
        if topic not in topic_scores:
            topic_scores[topic] = {"score": 0, "max": 0, "passed": True}
        topic_scores[topic]["score"] += r.get("score", 0)
        topic_scores[topic]["max"]   += r.get("max", 1)
        if not r.get("passed", True):
            topic_scores[topic]["passed"] = False

    # Map known weak topics to study keys
    def _study_key(name: str) -> str:
        return _resolve_study_key(name)

    results_json = [
        {"topic": name,
         "study_key": _study_key(name),
         "pass_rate": round(v["score"] / v["max"], 3) if v["max"] else 0,
         "passed": v["passed"]}
        for name, v in topic_scores.items()
        if v["max"] > 0
    ]

    (DEVAI_DIR / "training" / "validation_report.json").write_text(
        _json.dumps({"score": pct, "results": results_json}, indent=2),
        encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="DevAI Validator v2")
    parser.add_argument("--fix",        action="store_true")
    parser.add_argument("--rounds",     type=int, default=3)
    parser.add_argument("--knowledge",  action="store_true", help="Só fase 1 (sem LLM)")
    parser.add_argument("--generation", action="store_true", help="Só fase 2 (com LLM)")
    parser.add_argument("--topic",      nargs="+")
    parser.add_argument("--loop",       action="store_true",
                        help="Loop até atingir score mínimo, depois estuda novos tópicos indefinidamente")
    parser.add_argument("--min-score",  type=int, default=70,
                        help="Score mínimo para passar para expansão (default: 70)")
    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]🧪 DevAI Validator v2[/bold cyan]\n"
        "[dim]Fase 1: Knowledge Check | Fase 2: Generation Check[/dim]",
        border_style="cyan",
    ))

    llm = model = None
    if not args.knowledge:
        try:
            from tools.llm_client import OllamaClient
            from config import MODEL_CODE
            llm = OllamaClient(); llm.ensure_model(MODEL_CODE)
            model = MODEL_CODE
            console.print(f"  [green]✓[/green] Modelo: {model}")
        except Exception as e:
            console.print(f"  [yellow]⚠ LLM não disponível: {e} — rodando só fase 1[/yellow]")
            args.knowledge = True

    best = 0.0
    for round_num in range(1, args.rounds + 1):
        if args.rounds > 1:
            console.print(Rule(f"[cyan]Rodada {round_num}/{args.rounds}[/cyan]"))

        k_score = k_max = g_score = g_max = 0
        k_results = g_results = []

        # Fase 1 — Knowledge Check
        if not args.generation:
            console.print(Rule("[cyan]Fase 1 — Knowledge Check (vector store)[/cyan]"))
            k_score, k_max, k_results = run_knowledge_phase()
            kpct = k_score / k_max * 100 if k_max else 0
            color = "green" if kpct >= 70 else "yellow" if kpct >= 40 else "red"
            console.print(f"  [{color}]Knowledge: {kpct:.0f}% ({k_score:.1f}/{k_max})[/{color}]")

        # Fase 2 — Generation Check
        if not args.knowledge and llm:
            console.print(Rule("[cyan]Fase 2 — Generation Check (LLM)[/cyan]"))
            g_score, g_max, g_results = run_generation_phase(llm, model)
            gpct = g_score / g_max * 100 if g_max else 0
            color = "green" if gpct >= 70 else "yellow" if gpct >= 40 else "red"
            console.print(f"  [{color}]Generation: {gpct:.0f}% ({g_score:.1f}/{g_max})[/{color}]")

        total = k_score + g_score
        maxt  = k_max + g_max
        overall = total / maxt * 100 if maxt else 0
        best = max(best, overall)
        bar = "█" * int(overall/5) + "░" * (20 - int(overall/5))
        color = "green" if overall >= 70 else "yellow" if overall >= 40 else "red"

        console.print(Panel.fit(
            f"[bold {color}]Score: {overall:.0f}% [{bar}][/bold {color}]\n"
            f"{total:.1f}/{maxt:.1f} | {'✅ PASSOU' if overall >= 70 else '❌ REPROVADO'}",
            border_style=color,
        ))

        write_report(k_score, k_max, g_score, g_max, k_results, g_results)
        console.print("[dim]→ training/validation_report.md atualizado[/dim]")

        # Fix se necessário
        weak = [r for r in k_results + g_results if not r["passed"]]
        if args.fix and weak and round_num < args.rounds:
            console.print(Rule(f"[yellow]Fix — {len(weak)} falhou[/yellow]"))
            for r in weak:
                console.print(f"  [dim]→ {r['name']}[/dim]")
            topic = args.topic[0] if args.topic else "nestjs-mongodb"
            n = force_train(topic, llm, model)
            console.print(f"  [green]✓[/green] {n} padrões salvos")
        elif not weak:
            console.print("[green]✅ Todos os checks passaram![/green]")
            break

    # Commit
    try:
        from tools.vector_store import auto_commit
        if auto_commit(f"🧠 training: validate {time.strftime('%Y-%m-%d %H:%M')}"):
            console.print("[dim]✓ Commitado[/dim]")
    except Exception:
        pass

    if args.rounds > 1:
        console.print(Panel.fit(f"[bold green]Melhor score: {best:.0f}%[/bold green]",
                                border_style="green"))

    # Modo loop: continua até atingir o score mínimo, depois expande
    if args.loop:
        min_score = args.min_score
        fix_attempt = 0
        max_fix = 50

        while best < min_score and fix_attempt < max_fix:
            fix_attempt += 1
            console.print(Rule(f"[yellow]Loop Fix {fix_attempt} — score {best:.0f}% < {min_score}%[/yellow]"))

            # Estuda os tópicos fracos
            weak = [r.get("study_key", r.get("topic","")) for r in
                    json.loads((DEVAI_DIR/"training"/"validation_report.json").read_text()).get("results",[])
                    if not r.get("passed", True) and r.get("study_key")]
            if weak:
                console.print(f"  [yellow]→ Estudando fracos: {', '.join(weak[:4])}[/yellow]")
                try:
                    from scripts.study import study_topic, SEARCH_CURRICULUM, load_discovered, load_llm
                    all_c = {**SEARCH_CURRICULUM, **load_discovered()}
                    _llm, _model = load_llm()
                    for wk in weak[:3]:
                        if wk in all_c:
                            study_topic(wk, all_c[wk][:3], _llm, _model, intensive=True)
                            console.print(f"  [green]✓[/green] {wk} estudado")
                except Exception as _e:
                    console.print(f"  [dim]⚠ Study: {_e}[/dim]")

            # Re-valida
            results2 = []
            k2 = k3 = g2 = g3 = 0.0
            kr2 = gr2 = []
            if not args.generation:
                console.print(Rule("[cyan]Knowledge Check[/cyan]"))
                k2, k3, kr2 = run_knowledge_phase()
            if not args.knowledge and llm:
                console.print(Rule("[cyan]Generation Check[/cyan]"))
                g2, g3, gr2 = run_generation_phase(llm, model)
            best2 = (k2+g2)/(k3+g3)*100 if (k3+g3) else 0
            best = max(best, best2)
            write_report(k2, k3, g2, g3, kr2, gr2)
            console.print(f"  Score: {best2:.0f}% (melhor: {best:.0f}%)")

            # Commit
            try:
                from tools.vector_store import auto_commit
                auto_commit(f"🧠 training: loop fix {fix_attempt} score={best2:.0f}%")
            except Exception: pass

            if best2 >= min_score:
                console.print(f"[green]✅ Score {best2:.0f}% ≥ {min_score}% — iniciando expansão![/green]")
                break

        # Fase de expansão: estuda novos tópicos indefinidamente
        if best >= min_score:
            expand = 1
            console.print(Rule("[bold cyan]Expansão contínua[/bold cyan]"))
            while True:
                _t = time.strftime('%H:%M')
                console.print(f"  [cyan]── Expansão {expand} — {_t} ──[/cyan]")
                try:
                    from scripts.study import main as study_main, TOPIC_GROUPS
                    import sys as _sys
                    old_argv = _sys.argv
                    _sys.argv = ["study.py","--group","all","--intensive"]
                    try: study_main()
                    except SystemExit: pass
                    _sys.argv = old_argv
                except Exception as _e:
                    console.print(f"  [dim]⚠ Expand: {_e}[/dim]")

                # Revalida a cada 3 ciclos
                if expand % 3 == 0:
                    console.print("  [dim]→ Re-validando...[/dim]")
                    k2, k3, kr2 = run_knowledge_phase()
                    score_now = k2/k3*100 if k3 else 0
                    console.print(f"  Knowledge: {score_now:.0f}%")
                    try:
                        from tools.vector_store import auto_commit
                        auto_commit(f"🧠 training: expand {expand}")
                    except Exception: pass

                expand += 1

    return 0 if best >= 70 else 1


if __name__ == "__main__":
    sys.exit(main())
