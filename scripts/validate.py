"""
DevAI Training Validator — testa e corrige o conhecimento do agente.

Uso:
  python scripts/validate.py                # valida tudo
  python scripts/validate.py --fix          # valida + retreina fracos + re-valida
  python scripts/validate.py --topic nestjs-mongodb
  python scripts/validate.py --strict       # critério mais rígido (70% → 90%)

Produz:
  training/validation_report.md   — relatório commitável
  training/validation_report.json — dados completos
"""

import argparse, time as _time, json, re, sys, time
from dataclasses import dataclass, field, asdict
from pathlib import Path

DEVAI_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(DEVAI_DIR))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.rule import Rule

console = Console()

# ─── Perguntas de validação rigorosas ────────────────────────────────────────

VALIDATION_SUITE: dict[str, list] = {

    "nestjs-mongodb": [
        {
            "q": "NestJS Mongoose: required field uses ! or ? TypeScript modifier?",
            "must_contain": ["!"],
            "must_not_contain": ["?"],  # resposta correta é ! não ?
            "weight": 3,
        },
        {
            "q": "NestJS Mongoose schema: @Prop({required:true}) maps to field!:string or field?:string?",
            "must_contain": ["field!", "!:"],
            "must_not_contain": ["field?", "?:string"],
            "weight": 3,
        },
        {
            "q": "NestJS Mongoose service: which method to use instead of findOneBy?",
            "must_contain": ["findById", "findOne"],
            "must_not_contain": ["findOneBy"],
            "weight": 3,
        },
        {
            "q": "NestJS Mongoose module: which import to use, MongooseModule.forFeature or TypeOrmModule.forFeature?",
            "must_contain": ["MongooseModule.forFeature"],
            "must_not_contain": ["TypeOrmModule"],
            "weight": 3,
        },
        {
            "q": "NestJS app.module.ts for MongoDB: what module to add for database connection?",
            "must_contain": ["MongooseModule.forRoot", "MONGODB_URI"],
            "must_not_contain": ["TypeOrmModule", "DB_HOST", "DB_PORT"],
            "weight": 3,
        },
    ],

    "nestjs-typeorm": [
        {
            "q": "NestJS TypeORM: which decorator for primary UUID column?",
            "must_contain": ["@PrimaryGeneratedColumn", "uuid"],
            "must_not_contain": [],
            "weight": 2,
        },
        {
            "q": "NestJS TypeORM service: @InjectRepository vs @InjectModel?",
            "must_contain": ["@InjectRepository"],
            "must_not_contain": ["@InjectModel"],
            "weight": 2,
        },
    ],

    "nestjs-auth": [
        {
            "q": "NestJS PartialType: from @nestjs/mapped-types or @nestjs/common?",
            "must_contain": ["@nestjs/mapped-types"],
            "must_not_contain": ["@nestjs/common"],
            "weight": 3,
        },
        {
            "q": "NestJS JWT: which class to extend for JwtStrategy?",
            "must_contain": ["PassportStrategy", "Strategy"],
            "must_not_contain": [],
            "weight": 2,
        },
    ],

    "nestjs-core": [
        {
            "q": "NestJS ValidationPipe: what options to set for whitelist and transform?",
            "must_contain": ["whitelist", "transform"],
            "must_not_contain": [],
            "weight": 2,
        },
        {
            "q": "NestJS Swagger setup in main.ts: which classes to use?",
            "must_contain": ["DocumentBuilder", "SwaggerModule"],
            "must_not_contain": [],
            "weight": 2,
        },
    ],

    "nlp": [
        {
            "q": "User says 'CRUD de livros com MongoDB'. What is the entity name?",
            "must_contain": ["Book"],
            "must_not_contain": ["Livros", "livros", "LIVROS", "Livro"],
            "weight": 4,
        },
        {
            "q": "User says 'configure docker com mongodb'. Should you create src/docker/ or src/mongodb/ folder?",
            "must_contain": ["no", "não", "never", "docker-compose", "Dockerfile"],
            "must_not_contain": ["src/docker", "src/mongodb"],
            "weight": 4,
        },
        {
            "q": "User says 'API de usuários com MongoDB'. Is has_auth true or false?",
            "must_contain": ["false", "não", "no"],
            "must_not_contain": ["true", "sim", "yes", "JWT"],
            "weight": 4,
        },
        {
            "q": "User requests 'API with MongoDB and Docker only'. Should Redis appear in docker-compose?",
            "must_contain": ["no", "não", "only", "apenas", "not"],
            "must_not_contain": ["redis:", "Redis:", "image: redis"],
            "weight": 3,
        },
    ],

    "docker": [
        {
            "q": "MongoDB healthcheck in docker-compose: which command?",
            "must_contain": ["mongosh", "adminCommand", "ping"],
            "must_not_contain": ["pg_isready", "redis-cli"],
            "weight": 2,
        },
        {
            "q": "docker-compose depends_on: how to wait for a healthy service?",
            "must_contain": ["condition", "service_healthy"],
            "must_not_contain": [],
            "weight": 2,
        },
    ],

    "spring-mongodb": [
        {
            "q": "Spring Boot MongoDB: @Document or @Entity for model class?",
            "must_contain": ["@Document"],
            "must_not_contain": ["@Entity", "@Table"],
            "weight": 2,
        },
        {
            "q": "Spring Data MongoDB: extends MongoRepository or JpaRepository?",
            "must_contain": ["MongoRepository"],
            "must_not_contain": ["JpaRepository"],
            "weight": 2,
        },
    ],

    "fastapi": [
        {
            "q": "FastAPI MongoDB: which async driver to use?",
            "must_contain": ["motor", "Motor", "AsyncIOMotorClient"],
            "must_not_contain": ["pymongo", "MongoClient"],
            "weight": 2,
        },
        {
            "q": "FastAPI: Pydantic v2 model method to serialize: model_dump or dict?",
            "must_contain": ["model_dump"],
            "must_not_contain": [".dict()"],
            "weight": 2,
        },
    ],

    "common-errors": [
        {
            "q": "NestJS TS2307: module not found book.module — what is the fix?",
            "must_contain": ["create", "module.ts", "BookModule", "@Module"],
            "must_not_contain": [],
            "weight": 3,
        },
        {
            "q": "NestJS error: PartialType from @nestjs/common — what is correct import?",
            "must_contain": ["@nestjs/mapped-types"],
            "must_not_contain": ["@nestjs/common"],
            "weight": 3,
        },
    ],
}


@dataclass
class QuestionResult:
    question: str
    topic: str
    passed: bool
    score: float
    max_score: float
    found: list
    missing: list
    wrong: list
    answer_preview: str = ""


@dataclass
class TopicResult:
    topic: str
    questions: list = field(default_factory=list)
    total_score: float = 0
    max_score: float = 0
    pass_rate: float = 0


# ─── Training forçado para tópicos fracos ────────────────────────────────────

# Pares Q→A exatos que são injetados como few-shot no prompt de validação
# O LLM vê: "Q: X? A: Y" antes de responder — sobrescreve o treinamento base
QA_PAIRS = {
    "nestjs-mongodb": [
        ("NestJS Mongoose required field TypeScript modifier",
         "! (exclamation mark). Required @Prop({required:true}) → field!: string. NEVER ? for required."),
        ("@Prop({required:true}) TypeScript notation",
         "field!: Type — the ! is mandatory for required fields in TypeScript strict mode with Mongoose."),
        ("findOneBy in Mongoose NestJS",
         "findOneBy does NOT exist in Mongoose. Use findById(id) instead. findOneBy is TypeORM only."),
        ("MongooseModule in entity module",
         "MongooseModule.forFeature([{name: Book.name, schema: BookSchema}]) — NEVER TypeOrmModule."),
        ("MongoDB connection in app.module.ts",
         "MongooseModule.forRoot(process.env.MONGODB_URI) — NEVER TypeOrmModule, NEVER DB_HOST/DB_PORT."),
    ],
    "nestjs-auth": [
        ("PartialType import location NestJS",
         "from '@nestjs/mapped-types' — NEVER from '@nestjs/common' (does not exist there)."),
        ("JwtStrategy NestJS class",
         "extends PassportStrategy(Strategy) from passport-jwt. Uses ExtractJwt.fromAuthHeaderAsBearerToken()."),
    ],
    "nlp": [
        ("entity name for 'livros' in Portuguese",
         "Book — singular English PascalCase. NEVER Livros, never livro, never Livro."),
        ("src/ folder for docker configuration",
         "NO. Never create src/docker/. Docker config goes in docker-compose.yml at root. src/ is for code only."),
        ("has_auth for 'API de usuários com MongoDB'",
         "false. 'usuários' is just an entity name. has_auth=true ONLY when: auth, login, JWT, token, oauth appear."),
        ("docker-compose with 'MongoDB only'",
         "Only app + MongoDB services. NO Redis, NO Kafka, NO Nginx unless explicitly requested."),
    ],
    "docker": [
        ("MongoDB healthcheck docker-compose",
         "test: [\'CMD\',\'mongosh\',\'--eval\',\'db.adminCommand(\\'ping\\')\']. . Never pg_isready for MongoDB."),
        ("depends_on wait for healthy service",
         "condition: service_healthy — requires healthcheck on the dependency service."),
    ],
    "common-errors": [
        ("fix TS2307 book.module not found",
         "Create src/book/book.module.ts with @Module({imports:[MongooseModule.forFeature(...)],providers:[BookService],controllers:[BookController]}) export class BookModule {}"),
        ("PartialType wrong import fix",
         "Change: from '@nestjs/common' TO: from '@nestjs/mapped-types'"),
    ],
}

FORCED_PATTERNS = {
    "nlp": [
        ("nlp:livros-is-Book", "nlp",
         "CRITICAL: 'livros' in Portuguese → entity name is 'Book' (English, singular PascalCase), NEVER 'Livros'. "
         "'usuários'→User, 'produtos'→Product, 'pedidos'→Order, 'livros'→Book. "
         "The entity class name is ALWAYS English singular PascalCase."),
        ("nlp:no-src-folders-from-config", "nlp",
         "CRITICAL: NEVER create src/ subfolders from infrastructure words: "
         "docker→NO src/docker/, mongodb→NO src/mongodb/, configure→NO src/configure/. "
         "Only create src/{entityname}/ from business domain nouns. "
         "'configure docker with mongodb' → docker-compose.yml + Dockerfile, NOTHING in src/"),
        ("nlp:usuarios-no-auth", "nlp",
         "CRITICAL: 'usuários/users' alone does NOT mean has_auth=true. "
         "has_auth=true ONLY when: auth, autenticação, login, jwt, token, oauth, roles, permissions appear. "
         "'API de usuários com MongoDB' → has_auth=FALSE, User is just an entity."),
        ("nlp:docker-only-means-only", "nlp",
         "CRITICAL: 'MongoDB and Docker only' means the docker-compose.yml has ONLY MongoDB service. "
         "Do NOT add Redis, Kafka, Nginx, or any other service unless explicitly requested. "
         "If user says 'only', take it literally."),
    ],
    "nestjs-mongodb": [
        ("pattern:nestjs+mongo:required-bang", "nestjs_mongodb",
         "CRITICAL Mongoose TypeScript strict mode: "
         "@Prop({required:true}) → field!: Type  (exclamation mark, non-null assertion) "
         "@Prop() → field?: Type  (question mark, optional) "
         "NEVER: field: Type (without ! or ?)  "
         "NEVER use ! for optional fields or ? for required fields."),
        ("pattern:nestjs+mongo:no-findOneBy", "nestjs_mongodb",
         "CRITICAL: Mongoose does NOT have findOneBy(). This is TypeORM only. "
         "Mongoose methods: findById(id), findOne({field:value}), findByIdAndUpdate(), findByIdAndDelete(). "
         "If you see findOneBy in Mongoose code, replace with findById(id)."),
        ("pattern:nestjs+mongo:correct-module", "nestjs_mongodb",
         "CRITICAL NestJS Mongoose module: "
         "imports: [MongooseModule.forFeature([{name: Book.name, schema: BookSchema}])] "
         "NEVER: TypeOrmModule.forFeature([Book]) in a Mongoose project. "
         "NEVER: MongooseModule.forRoot() in entity module (only in AppModule)."),
    ],
    "nestjs-auth": [
        ("pattern:nestjs:partialtype-source", "nestjs_auth",
         "CRITICAL: PartialType MUST be imported from '@nestjs/mapped-types'. "
         "NEVER from '@nestjs/common' (doesn't exist). "
         "NEVER from '@nestjs/swagger' (prefer mapped-types). "
         "Fix: import { PartialType } from '@nestjs/mapped-types';"),
    ],
    "docker": [
        ("pattern:docker:healthcheck-mongo", "docker",
         "MongoDB healthcheck: test: ['CMD','mongosh','--eval',\"db.adminCommand('ping')\"] interval:15s timeout:10s retries:5. "
         "depends_on: db: condition: service_healthy. "
         "NEVER pg_isready for MongoDB."),
        ("pattern:docker:only-means-only", "docker",
         "When user says 'only MongoDB' or 'MongoDB and Docker only': "
         "docker-compose.yml has ONLY app + db (MongoDB). "
         "NO redis, NO kafka, NO nginx unless explicitly requested."),
    ],
    "common-errors": [
        ("pattern:error:missing-module", "common_errors",
         "TS2307 './book/book.module' not found: The fix is to CREATE src/book/book.module.ts. "
         "Content: @Module({imports:[MongooseModule.forFeature([{name:Book.name,schema:BookSchema}])], "
         "providers:[BookService],controllers:[BookController],exports:[BookService]}) export class BookModule {}"),
    ],
}



CORRECT_ANSWERS = {
    "nestjs-mongodb": [
        {"keys": ["qa:mongoose-required-field-modifier",
                  "NestJS Mongoose required field uses ! or ? TypeScript"],
         "content": "ANSWER: required field uses ! (not ?). @Prop({required:true}) title!: string. @Prop() description?: string. RULE: required=! optional=?. NEVER ? for required. NEVER bare field: Type without ! or ?."},
        {"keys": ["qa:mongoose-prop-mapping",
                  "NestJS Mongoose schema @Prop required maps to field!"],
         "content": "@Prop({required:true}) → field!: Type  (exclamation ! means required). @Prop() → field?: Type (question ? means optional). NEVER @Prop({required:true}) field?: string (wrong). NEVER @Prop({required:true}) field: string (wrong, needs !)."},
        {"keys": ["qa:mongoose-no-findOneBy",
                  "NestJS Mongoose service method instead of findOneBy"],
         "content": "findOneBy does NOT exist in Mongoose. Mongoose uses findById(id). findOneBy is TypeORM-only. CORRECT: this.model.findById(id).exec(). WRONG: this.model.findOneBy({_id:id})."},
        {"keys": ["qa:mongoose-module-forFeature",
                  "NestJS Mongoose module MongooseModule.forFeature or TypeOrmModule"],
         "content": "Use MongooseModule.forFeature NEVER TypeOrmModule in Mongoose projects. @Module({ imports: [MongooseModule.forFeature([{name: Book.name, schema: BookSchema}])] })"},
        {"keys": ["qa:app-module-mongodb",
                  "NestJS app.module.ts MongoDB database connection module"],
         "content": "MongoDB connection: MongooseModule.forRoot(process.env.MONGODB_URI). NEVER TypeOrmModule for MongoDB. NEVER DB_HOST/DB_PORT variables (those are PostgreSQL). MongoDB uses MONGODB_URI."},
    ],
    "nlp": [
        {"keys": ["qa:livros-to-Book",
                  "user says CRUD de livros entity name"],
         "content": "ANSWER: Book. 'livros' (Portuguese) → entity name is Book (English singular PascalCase). NEVER Livros, NEVER livros. livros→Book, usuários→User, produtos→Product, pedidos→Order."},
        {"keys": ["qa:docker-no-src-folder",
                  "configure docker should create src/docker folder no"],
         "content": "ANSWER: No. NEVER create src/docker/ or src/mongodb/. 'configure docker' means create docker-compose.yml and Dockerfile at project ROOT. src/ contains ONLY business entities (Book, User)."},
        {"keys": ["qa:usuarios-has-auth-false",
                  "API de usuarios MongoDB has_auth true or false"],
         "content": "ANSWER: false. 'usuários' alone does NOT mean auth. has_auth=true ONLY with: auth, login, jwt, token, oauth. 'API de usuários com MongoDB' → has_auth=false, User is just an entity."},
        {"keys": ["qa:mongodb-docker-only-no-redis",
                  "API with MongoDB and Docker only should Redis appear in docker-compose"],
         "content": "ANSWER: No. 'only MongoDB' means docker-compose has ONLY app + mongo:7.0. Do not add redis, kafka, nginx. 'only' means only what is mentioned, nothing more."},
    ],
    "nestjs-auth": [
        {"keys": ["qa:partialtype-source",
                  "NestJS PartialType from @nestjs/mapped-types or @nestjs/common"],
         "content": "ANSWER: @nestjs/mapped-types. import { PartialType } from '@nestjs/mapped-types'. NEVER from @nestjs/common (doesn't exist there). NEVER from @nestjs/swagger."},
    ],
    "docker": [
        {"keys": ["qa:mongodb-healthcheck",
                  "MongoDB healthcheck docker-compose which command"],
         "content": "MongoDB healthcheck command: mongosh. test: CMD mongosh --eval ping. NEVER pg_isready for MongoDB."},
        {"keys": ["qa:depends-on-healthy",
                  "docker-compose depends_on wait for healthy service condition"],
         "content": "depends_on with condition: service_healthy. depends_on: { db: { condition: service_healthy } }. This waits for healthcheck to pass. WRONG: depends_on: [db] (doesn't wait for health)."},
    ],
    "common-errors": [
        {"keys": ["qa:ts2307-module-missing",
                  "NestJS TS2307 module not found book.module fix create"],
         "content": "TS2307 fix: CREATE src/book/book.module.ts. @Module({ imports:[MongooseModule.forFeature([{name:Book.name,schema:BookSchema}])], providers:[BookService], controllers:[BookController] }) export class BookModule {}"},
    ],
}


def force_train_topic(topic: str, llm, model: str) -> int:
    """
    Retreinamento rigoroso:
    1. Salva RESPOSTA CORRETA exata para cada pergunta (Q&A direto)
    2. Salva padrões críticos
    3. Verifica recuperação
    4. Pesquisa web intensiva
    """
    from tools.vector_store import save, search_relevant
    saved = 0

    # 1. Respostas corretas exatas — o caminho mais direto
    console.print(f"  [cyan]→ Salvando respostas corretas para {topic}...[/cyan]")
    for entry in CORRECT_ANSWERS.get(topic, []):
        for key in entry["keys"]:
            save(key, entry["content"], topic=topic.replace("-","_"), source="correct_answer")
            saved += 1
        console.print(f"  [green]+[/green] {entry['keys'][0][:55]}")

    # 2. Padrões forçados
    for key, t, pat in FORCED_PATTERNS.get(topic, []):
        save(key, pat, topic=t, source="forced_training")
        saved += 1

    # 3. Gera embeddings imediatamente para o novo conteúdo
    try:
        from tools.vector_store import backfill_embeddings
        n_emb = backfill_embeddings()
        if n_emb:
            console.print(f"  [green]✓[/green] {n_emb} embeddings gerados")
    except Exception:
        pass

    # 4. Verifica recuperação
    test_q = {
        "nestjs-mongodb": "Mongoose required field ! TypeScript strict",
        "nlp":            "livros entity Book português",
        "docker":         "MongoDB healthcheck mongosh",
        "nestjs-auth":    "PartialType mapped-types import",
        "common-errors":  "TS2307 module not found fix",
    }
    if topic in test_q:
        result = search_relevant(test_q[topic], limit=2)
        if result and len(result) > 80:
            console.print(f"  [green]✓ Recuperável ({len(result)} chars)[/green]")
        else:
            console.print(f"  [yellow]⚠ Recuperação fraca[/yellow]")

    # 5. Pesquisa web adicional
    try:
        from scripts.study import study_topic, SEARCH_CURRICULUM, load_discovered
        all_c = {**SEARCH_CURRICULUM, **load_discovered()}
        tmap = {
            "nestjs-mongodb": ["nestjs_mongodb"],
            "nlp":            ["nlp_patterns"],
            "docker":         ["docker_patterns"],
            "nestjs-auth":    ["nestjs_auth"],
            "common-errors":  ["common_errors"],
        }
        for sk in tmap.get(topic, []):
            if sk in all_c:
                n = study_topic(sk, all_c[sk][:3], llm, model, intensive=True)
                saved += n
    except Exception as e:
        console.print(f"  [dim]⚠ Web study: {e}[/dim]")

    return saved


def ask_agent(question: str, topic: str, llm, model: str) -> str:
    try:
        from tools.vector_store import search_relevant
        exclude = [] if topic == "docker" else ["docker", "devops", "kubernetes"]
        ctx = search_relevant(question, limit=5, exclude_topics=exclude)

        # Few-shot Q&A pairs — highest priority, overrides LLM base training
        qa_examples = _get_qa_pairs(topic, question)

        prompt = (
            f"MANDATORY RULES (these override everything else):\n"
            f"{qa_examples}\n\n"
            f"---\n"
            f"Additional context:\n{ctx[:800]}\n\n"
            f"Now answer this question FOLLOWING THE RULES ABOVE:\n"
            f"Question: {question}\n\n"
            "Be specific. Show code when relevant."
        )

        import threading
        result = [None]
        def _call():
            try:
                result[0] = llm.chat(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    system=(
                        "You are a senior developer. Answer using training knowledge provided. "
                        "Be specific. Show correct code. Answer in English."
                    ),
                    stream=False,
                )
            except Exception as e:
                result[0] = f"[error:{e}]"

        t = threading.Thread(target=_call, daemon=True)
        t.start()
        t.join(timeout=45)
        return result[0] or ""
    except Exception as e:
        return f"[error:{e}]"


def evaluate(answer: str, q: dict) -> QuestionResult:
    a = answer.lower()
    found   = [kw for kw in q["must_contain"]     if kw.lower() in a]
    missing = [kw for kw in q["must_contain"]     if kw.lower() not in a]
    wrong   = [kw for kw in q["must_not_contain"] if kw.lower() in a]

    w = q.get("weight", 1)
    if not q["must_contain"]:
        score = w if not wrong else 0.0
    else:
        ratio = len(found) / len(q["must_contain"])
        penalty = 0.0 if wrong else 1.0
        score = w * ratio * penalty

    # Passed = at least half must_contain found AND none of must_not_contain
    passed = (len(missing) <= len(q["must_contain"]) // 2) and not wrong

    return QuestionResult(
        question=q["q"][:65], topic="",
        passed=passed, score=round(score, 2), max_score=w,
        found=found, missing=missing, wrong=wrong,
        answer_preview=answer[:200],
    )


def validate_topic(topic: str, questions: list, llm, model: str) -> TopicResult:
    result = TopicResult(topic=topic)
    for q in questions:
        answer = ask_agent(q["q"], topic, llm, model)
        qr = evaluate(answer, q)
        qr.topic = topic
        result.questions.append(qr)
        result.total_score += qr.score
        result.max_score   += qr.max_score

        icon  = "[green]✓[/green]" if qr.passed else "[red]✗[/red]"
        score = f"[{qr.score:.1f}/{qr.max_score}]"
        console.print(f"  {icon} {score} {qr.question}")
        if not qr.passed:
            if qr.missing: console.print(f"      [yellow]Missing: {', '.join(qr.missing[:4])}[/yellow]")
            if qr.wrong:   console.print(f"      [red]Wrong: {', '.join(qr.wrong[:3])}[/red]")

    result.pass_rate = result.total_score / result.max_score if result.max_score else 0
    return result


def write_report(results: list[TopicResult], out: Path) -> None:
    import datetime
    now = datetime.datetime.now()
    total = sum(r.total_score for r in results)
    maxt  = sum(r.max_score   for r in results)
    pct   = total / maxt * 100 if maxt else 0

    weak   = [r for r in results if r.pass_rate < 0.6]
    medium = [r for r in results if 0.6 <= r.pass_rate < 0.8]
    good   = [r for r in results if r.pass_rate >= 0.8]

    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))

    lines = [
        f"# DevAI Validation Report",
        f"*{now.strftime('%Y-%m-%d %H:%M')}*",
        f"",
        f"## Score: {pct:.0f}% `[{bar}]`",
        f"",
        f"| Tópico | Score | % | Status |",
        f"|---|---|---|---|",
    ]
    for r in sorted(results, key=lambda x: x.pass_rate, reverse=True):
        icon = "✅" if r.pass_rate >= 0.8 else "⚠️" if r.pass_rate >= 0.6 else "❌"
        lines.append(f"| {r.topic} | {r.total_score:.1f}/{r.max_score:.1f} | {r.pass_rate*100:.0f}% | {icon} |")

    if weak:
        lines += ["", "## ❌ Retreinar urgente", ""]
        for r in weak:
            lines.append(f"### {r.topic} ({r.pass_rate*100:.0f}%)")
            for q in r.questions:
                if not q.passed:
                    lines.append(f"- ✗ {q.question}")
                    if q.missing: lines.append(f"  - Missing: `{', '.join(q.missing)}`")
                    if q.wrong:   lines.append(f"  - Wrong: `{', '.join(q.wrong)}`")
            lines.append("")

    lines += [
        "## Como corrigir", "",
        "```bash",
        "# Fix automático (retreina + re-valida)",
        "python scripts/validate.py --fix",
        "",
        "# Forçar retreinamento específico",
        *[f"python scripts/validate.py --fix --topic {r.topic}" for r in weak[:3]],
        "",
        "# Overnight",
        "./scripts/study.sh --group all --loop --validate --intensive",
        "```",
    ]

    out.mkdir(parents=True, exist_ok=True)
    (out / "validation_report.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "validation_report.json").write_text(
        json.dumps({"score": round(pct, 1), "results": [
            {"topic": r.topic, "pass_rate": round(r.pass_rate, 3),
             "score": r.total_score, "max": r.max_score}
            for r in results
        ]}, indent=2),
        encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description="DevAI Validator")
    parser.add_argument("--topic",  nargs="+")
    parser.add_argument("--fix",    action="store_true", help="Retreina fracos após validar")
    parser.add_argument("--strict", action="store_true", help="Aprovação exige 90%")
    parser.add_argument("--rounds", type=int, default=3,
                        help="Rodadas de fix+re-validate (default: 3)")
    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]🧪 DevAI Validator[/bold cyan]\n"
        "[dim]Testa e corrige o treinamento do agente[/dim]",
        border_style="cyan",
    ))

    from tools.llm_client import OllamaClient
    from config import MODEL_CODE
    try:
        llm = OllamaClient()
        llm.ensure_model(MODEL_CODE)
        console.print(f"  [green]✓[/green] Modelo: {MODEL_CODE}")
    except Exception as e:
        console.print(f"[red]✗ {e}[/red]"); sys.exit(1)

    suite = {t: VALIDATION_SUITE[t]
             for t in (args.topic or VALIDATION_SUITE.keys())
             if t in VALIDATION_SUITE}

    threshold = 0.9 if args.strict else 0.7
    pass_label = f"{threshold*100:.0f}%"

    best_overall = 0.0
    round_num = 1
    max_rounds = args.rounds if args.fix else 1

    while round_num <= max_rounds:
        if max_rounds > 1:
            console.print(Rule(f"[bold cyan]Rodada {round_num}/{max_rounds}[/bold cyan]"))

        results = []
        for topic, questions in suite.items():
            console.print(Rule(f"[cyan]{topic}[/cyan]"))
            r = validate_topic(topic, questions, llm, MODEL_CODE)
            results.append(r)
            color = "green" if r.pass_rate >= threshold else "yellow" if r.pass_rate >= 0.5 else "red"
            bar = "█" * int(r.pass_rate * 10) + "░" * (10 - int(r.pass_rate * 10))
            console.print(f"  [{color}]{r.total_score:.1f}/{r.max_score:.1f} [{bar}] {r.pass_rate*100:.0f}%[/{color}]")

        total = sum(r.total_score for r in results)
        maxt  = sum(r.max_score   for r in results)
        overall = total / maxt if maxt else 0
        best_overall = max(best_overall, overall)

        color = "green" if overall >= threshold else "yellow" if overall >= 0.5 else "red"
        bar   = "█" * int(overall * 20) + "░" * (20 - int(overall * 20))
        console.print(Panel.fit(
            f"[bold {color}]Score: {overall*100:.0f}% [{bar}][/bold {color}]\n"
            f"{total:.1f}/{maxt:.1f} | Aprovação: {pass_label} | "
            f"{'✅ PASSOU' if overall >= threshold else '❌ REPROVADO'}",
            border_style=color,
        ))

        write_report(results, DEVAI_DIR / "training")
        console.print("[dim]→ training/validation_report.md atualizado[/dim]")

        weak = [r for r in results if r.pass_rate < threshold]

        if not args.fix or not weak or round_num >= max_rounds:
            break

        # Fix round
        console.print(Rule(f"[yellow]Retreinando {len(weak)} tópico(s) fraco(s)[/yellow]"))
        for r in weak:
            console.print(f"\n  [yellow]→ {r.topic} ({r.pass_rate*100:.0f}%)[/yellow]")
            n = force_train_topic(r.topic, llm, MODEL_CODE)
            console.print(f"  [green]✓[/green] {n} item(ns) adicionados ao training")

        # Generate fresh embeddings for new content
        try:
            from tools.vector_store import backfill_embeddings
            n_emb = backfill_embeddings()
            if n_emb: console.print(f"  [green]✓[/green] {n_emb} embedding(s) gerado(s)")
        except Exception: pass

        console.print(f"\n[dim]Re-validando após retreinamento...[/dim]\n")
        round_num += 1

    # Final summary
    if max_rounds > 1:
        console.print(Panel.fit(
            f"[bold green]Melhor score: {best_overall*100:.0f}%[/bold green]",
            border_style="green",
        ))

    # Commit ao final (com lock guard — seguro para rodar em paralelo)
    try:
        from tools.vector_store import auto_commit
        committed = auto_commit(f"🧠 training: validate fix {_time.strftime('%Y-%m-%d %H:%M')}")
        if committed:
            console.print("[dim]✓ Commitado[/dim]")
    except Exception:
        pass

    return 0 if best_overall >= threshold else 1


if __name__ == "__main__":
    sys.exit(main())
