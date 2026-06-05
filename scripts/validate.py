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

import argparse, json, re, sys, time
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


def force_train_topic(topic: str, llm, model: str) -> int:
    """Força treinamento intensivo para um tópico fraco: salva padrões críticos + pesquisa web."""
    from tools.vector_store import save
    saved = 0

    # 1. Salva padrões forçados (sem LLM, alta prioridade)
    patterns = FORCED_PATTERNS.get(topic, [])
    for key, t, content in patterns:
        save(key, content, topic=t, source="forced_training")
        console.print(f"  [green]+[/green] Padrão crítico salvo: {key[:45]}")
        saved += 1

    # 2. Pesquisa web intensiva (6 resultados + exemplos)
    from scripts.study import study_topic, SEARCH_CURRICULUM, load_discovered
    all_curriculum = {**SEARCH_CURRICULUM, **load_discovered()}

    # Map validation topic → study topic key
    topic_map = {
        "nlp":             ["nlp_patterns"],
        "nestjs-mongodb":  ["nestjs_mongodb"],
        "nestjs-typeorm":  ["nestjs_postgres"],
        "nestjs-auth":     ["nestjs_auth"],
        "nestjs-core":     ["nestjs_core"],
        "docker":          ["docker_patterns", "docker_stacks"],
        "spring-mongodb":  ["spring_mongodb"],
        "fastapi":         ["fastapi_mongodb", "fastapi_postgres"],
        "common-errors":   ["common_errors"],
    }
    for study_key in topic_map.get(topic, [topic]):
        searches = all_curriculum.get(study_key, [])
        if searches:
            console.print(f"  [dim]→ Pesquisando {study_key} ({len(searches)} queries)...[/dim]")
            n = study_topic(study_key, searches, llm, model, intensive=True)
            saved += n

    return saved


# ─── Validação ────────────────────────────────────────────────────────────────

def ask_agent(question: str, topic: str, llm, model: str) -> str:
    try:
        from tools.vector_store import search_relevant
        # Include infra for docker topic
        exclude = [] if topic == "docker" else ["docker", "devops", "kubernetes"]
        ctx = search_relevant(question, limit=5, exclude_topics=exclude)

        prompt = (
            f"Training knowledge:\n{ctx[:1200]}\n\n"
            f"Question: {question}\n\n"
            "Answer concisely and specifically using the training knowledge. "
            "Show code when relevant."
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

    return 0 if best_overall >= threshold else 1


if __name__ == "__main__":
    sys.exit(main())
