"""
DevAI Integration Tests — testa pedidos reais e verifica o resultado gerado.

Ao invés de perguntar ao LLM "o que é X?", gera código real e verifica se:
  - Usou o banco correto
  - Usou o ORM correto
  - Gerou os arquivos corretos
  - Não misturou TypeORM com Mongoose
  - .env tem as vars corretas
  - docker-compose tem os serviços corretos
  - Não adicionou auth quando não foi pedido

Cada teste tem um peso e requisitos must_contain / must_not_contain.

Uso:
  python scripts/integration_test.py                # roda todos os testes
  python scripts/integration_test.py --suite nestjs # só nestjs
  python scripts/integration_test.py --fix          # retreina os que falharam
"""

import argparse, json, re, shutil, subprocess, sys, tempfile, time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEVAI_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(DEVAI_DIR))

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

console = Console()


@dataclass
class FileCheck:
    """Verifica um arquivo gerado."""
    path_pattern: str          # glob ou path relativo (ex: "src/book/*.schema.ts")
    must_contain:  list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    must_exist:    bool = True  # arquivo deve existir?
    weight:        float = 1.0


@dataclass
class IntegrationTest:
    name:        str
    description: str           # o pedido em português (vai para devai new)
    stack:       str
    project:     str
    checks:      list[FileCheck]
    weight:      float = 1.0
    suite:       str = "all"


# ─── Suite de testes ──────────────────────────────────────────────────────────

TESTS: list[IntegrationTest] = [

    # ── NestJS + MongoDB ──────────────────────────────────────────────────────
    IntegrationTest(
        name="nestjs-mongodb-basic",
        description="CRUD de livros com MongoDB",
        stack="nestjs", project="test-livros",
        suite="nestjs",
        weight=3.0,
        checks=[
            FileCheck("src/book/book.schema.ts",
                must_contain=["@Schema", "@Prop", "HydratedDocument", "export class Book"],
                must_not_contain=["@Entity", "@Column", "TypeOrmModule", "Book & Document"]),
            FileCheck("src/book/book.service.ts",
                must_contain=["@InjectModel", "Model<", "findById"],
                must_not_contain=["@InjectRepository", "Repository<", "findOneBy"]),
            FileCheck("src/book/book.module.ts",
                must_contain=["MongooseModule.forFeature"],
                must_not_contain=["TypeOrmModule.forFeature"]),
            FileCheck(".env.example",
                must_contain=["MONGODB_URI"],
                must_not_contain=["DB_HOST", "DB_PORT", "POSTGRES"]),
            FileCheck("src/book/book.dto.ts",
                must_contain=["@nestjs/mapped-types", "PartialType"],
                must_not_contain=["from '@nestjs/common'"]),
        ],
    ),

    IntegrationTest(
        name="nestjs-mongodb-no-auth",
        description="API de livros com MongoDB sem autenticação",
        stack="nestjs", project="test-no-auth",
        suite="nestjs",
        weight=2.0,
        checks=[
            FileCheck("src/book/book.controller.ts",
                must_not_contain=["JwtAuthGuard", "@UseGuards", "jwt.guard"],
                weight=3.0),
            FileCheck(".env.example",
                must_not_contain=["JWT_SECRET", "JWT_EXPIRES"]),
        ],
    ),

    IntegrationTest(
        name="nestjs-mongodb-docker",
        description="CRUD de produtos com MongoDB e docker",
        stack="nestjs", project="test-docker-mongo",
        suite="nestjs",
        weight=2.0,
        checks=[
            FileCheck("docker-compose.yml",
                must_contain=["mongo:7", "mongosh", "MONGODB_URI", "service_healthy"],
                must_not_contain=["postgres:", "redis:", "DB_HOST"]),
            FileCheck("Dockerfile",
                must_contain=["FROM node", "npm run build"],
                must_exist=True),
        ],
    ),

    IntegrationTest(
        name="nestjs-redis-sentinel",
        description="API com MongoDB e cache redis-sentinel",
        stack="nestjs", project="test-sentinel",
        suite="nestjs",
        weight=2.0,
        checks=[
            FileCheck("docker-compose.yml",
                must_contain=["mongo", "sentinel"],
                must_not_contain=["DB_HOST", "DB_PORT"]),
            FileCheck(".env.example",
                must_contain=["MONGODB_URI", "REDIS_SENTINEL"],
                must_not_contain=["DB_HOST", "DB_PORT"]),
        ],
    ),

    IntegrationTest(
        name="nestjs-postgres-auth",
        description="API de usuários com PostgreSQL e autenticação JWT",
        stack="nestjs", project="test-pg-auth",
        suite="nestjs",
        weight=2.0,
        checks=[
            FileCheck("src/user/user.entity.ts",
                must_contain=["@Entity", "@Column", "@PrimaryGeneratedColumn"],
                must_not_contain=["@Schema", "@Prop", "HydratedDocument"]),
            FileCheck("src/user/user.service.ts",
                must_contain=["@InjectRepository", "Repository<"],
                must_not_contain=["@InjectModel", "Model<"]),
            FileCheck(".env.example",
                must_contain=["DB_HOST", "JWT_SECRET"],
                must_not_contain=["MONGODB_URI"]),
        ],
    ),

    # ── Entity detection ──────────────────────────────────────────────────────
    IntegrationTest(
        name="entity-pt-br-livros",
        description="CRUD de livros com MongoDB",
        stack="nestjs", project="test-entity-pt",
        suite="nlp",
        weight=3.0,
        checks=[
            # Entity must be Book, not Livros
            FileCheck("src/book/",
                must_exist=True,
                must_not_contain=[]),   # folder must exist
            FileCheck("src/livros/",
                must_exist=False),      # folder must NOT exist
        ],
    ),

    IntegrationTest(
        name="entity-pt-br-pedidos",
        description="API de pedidos com PostgreSQL",
        stack="nestjs", project="test-entity-pedidos",
        suite="nlp",
        weight=2.0,
        checks=[
            FileCheck("src/order/",
                must_exist=True),
            FileCheck("src/pedido/",
                must_exist=False),
            FileCheck("src/pedidos/",
                must_exist=False),
        ],
    ),

    # ── Spring Boot ───────────────────────────────────────────────────────────
    IntegrationTest(
        name="spring-mongodb",
        description="CRUD de produtos com MongoDB",
        stack="spring-boot", project="test-spring-mongo",
        suite="spring",
        weight=2.0,
        checks=[
            FileCheck("src/main/java/**/Product.java",
                must_contain=["@Document", "MongoRepository"],
                must_not_contain=["@Entity", "JpaRepository"]),
            FileCheck("src/main/resources/application.properties",
                must_contain=["mongodb"],
                must_not_contain=["postgresql", "datasource.url"]),
        ],
    ),

    # ── FastAPI ───────────────────────────────────────────────────────────────
    IntegrationTest(
        name="fastapi-mongodb",
        description="API FastAPI de livros com MongoDB",
        stack="python", project="test-fastapi-mongo",
        suite="python",
        weight=2.0,
        checks=[
            FileCheck("main.py",
                must_contain=["AsyncIOMotorClient", "FastAPI"],
                must_not_contain=["MongoClient", "pymongo.MongoClient"]),
            FileCheck(".env.example",
                must_contain=["MONGODB_URI"],
                must_not_contain=["DB_HOST"]),
        ],
    ),
]


# ─── Runner ───────────────────────────────────────────────────────────────────

@dataclass
class CheckResult:
    test_name:  str
    file_check: str
    passed:     bool
    score:      float
    max_score:  float
    found:      list
    missing:    list
    wrong:      list
    detail:     str = ""


def _run_generation(test: IntegrationTest, tmp_dir: Path) -> Optional[Path]:
    """Gera o projeto usando o domain extractor + generator diretamente (sem CLI)."""
    try:
        from tools.domain_extractor import extract_domain, _has_auth_requested
        from tools.db_strategy import detect_database, get_strategy
        from tools.manifests import get_manifest
        from tools.generator import generate_files
        from tools.file_writer import write_files
        from tools.gitignore import write_env_example
        from tools.llm_client import OllamaClient
        from config import MODEL_CODE

        llm = OllamaClient()
        project_path = tmp_dir / test.project
        project_path.mkdir(parents=True, exist_ok=True)

        # Domain extraction (clean)
        db_type  = detect_database(test.description)
        has_auth = _has_auth_requested(test.description)
        domain   = extract_domain(test.description, llm)
        domain["db_type"]  = db_type
        domain["has_auth"] = has_auth

        # Extra services
        desc_lower = test.description.lower()
        extra = []
        if "sentinel" in desc_lower: extra.append("redis-sentinel")
        elif "redis" in desc_lower:  extra.append("redis")
        if "kafka" in desc_lower:    extra.append("kafka")

        # Write .env.example
        write_env_example(test.stack, project_path, test.project,
                          db_type=db_type, has_auth=has_auth, extra_services=extra)

        # Generate backend files
        entities = domain.get("entities", [])
        specs = get_manifest(test.stack, test.project, entities, has_auth, db_type=db_type)
        files = generate_files(specs, test.stack, test.project,
                                test.description, domain, llm, project_path)
        write_files(files, base_path=project_path, confirm=False, preview=False)

        # Generate docker-compose
        try:
            from tools.infra_generator import generate_infra, InfraContext
            strat = get_strategy(db_type)
            ctx = InfraContext(
                app_name=test.project, stack=test.stack, database=db_type,
                orm=strat.orm, extra_services=extra, has_auth=has_auth,
            )
            infra_files = generate_infra(ctx, research="")
            for fname, fcontent in infra_files.items():
                p = project_path / fname
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(fcontent, encoding="utf-8")
        except Exception as _ie:
            console.print(f"  [dim]⚠ Infra: {_ie}[/dim]")

        return project_path

    except Exception as e:
        console.print(f"  [red]✗ Generation failed: {e}[/red]")
        return None


def _check_file(project_path: Path, fc: FileCheck) -> CheckResult:
    """Verifica um FileCheck contra os arquivos gerados."""
    pattern = fc.path_pattern

    # Find matching files
    if pattern.endswith("/"):
        # Directory check
        matches = [project_path / pattern.rstrip("/")]
        is_dir_check = True
    else:
        matches = list(project_path.glob(pattern)) or [project_path / pattern]
        is_dir_check = False

    # Check existence
    if not fc.must_exist:
        for m in matches:
            if m.exists():
                return CheckResult(
                    test_name="", file_check=pattern, passed=False,
                    score=0, max_score=fc.weight,
                    found=[], missing=[], wrong=[],
                    detail=f"Should NOT exist: {m.relative_to(project_path)}"
                )
        return CheckResult("", pattern, True, fc.weight, fc.weight, [], [], [])

    # Find first existing match
    content = ""
    found_path = None
    for m in matches:
        if is_dir_check:
            if m.exists() and m.is_dir():
                found_path = m
                content = " ".join(str(f) for f in m.iterdir())
                break
        elif m.exists():
            found_path = m
            content = m.read_text(encoding="utf-8", errors="ignore")
            break

    if fc.must_exist and not found_path:
        return CheckResult("", pattern, False, 0, fc.weight, [], [],
                           wrong=[], detail=f"File not found: {pattern}")

    c_lower = content.lower()

    # Strip negation lines for must_not check
    def _strip_neg(text: str) -> str:
        lines = text.split("\n")
        return "\n".join(l for l in lines if not any(
            n in l.lower() for n in ["never","not ","don't","avoid","wrong:","← typeorm","typeorm only","← wrong"]
        ))

    content_for_must_not = _strip_neg(c_lower)

    found   = [kw for kw in fc.must_contain     if kw.lower() in c_lower]
    missing = [kw for kw in fc.must_contain     if kw.lower() not in c_lower]
    wrong   = [kw for kw in fc.must_not_contain if kw.lower() in content_for_must_not]

    if not fc.must_contain:
        score = fc.weight if not wrong else 0
    else:
        ratio = len(found) / len(fc.must_contain)
        score = fc.weight * ratio * (0 if wrong else 1)

    passed = not missing and not wrong

    return CheckResult(
        test_name="", file_check=pattern,
        passed=passed, score=round(score, 2), max_score=fc.weight,
        found=found, missing=missing, wrong=wrong,
    )


def run_test(test: IntegrationTest) -> tuple[float, float, list[CheckResult]]:
    """Runs a single integration test."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        console.print(f"  [dim]→ Gerando: {test.description[:55]}[/dim]")
        project_path = _run_generation(test, tmp_path)
        if not project_path:
            return 0, test.weight, []

        results = []
        for fc in test.checks:
            r = _check_file(project_path, fc)
            r.test_name = test.name
            results.append(r)

        total  = sum(r.score for r in results)
        max_sc = sum(r.max_score for r in results)
        return total, max_sc, results


def write_integration_report(all_results: list, score: float, out: Path) -> None:
    """Writes integration test report."""
    import datetime
    now = datetime.datetime.now()
    pct = score
    bar = "█" * int(pct/5) + "░" * (20 - int(pct/5))

    lines = [
        f"# DevAI Integration Test Report",
        f"*{now.strftime('%Y-%m-%d %H:%M')}*",
        f"",
        f"## Score: {pct:.0f}% `[{bar}]`",
        f"",
        f"| Test | Score | Status |",
        f"|---|---|---|",
    ]

    for test_name, total, max_sc, results in all_results:
        pct_t = total/max_sc*100 if max_sc else 0
        icon = "✅" if pct_t >= 80 else "⚠️" if pct_t >= 50 else "❌"
        lines.append(f"| {test_name} | {total:.1f}/{max_sc:.1f} ({pct_t:.0f}%) | {icon} |")

    failing = [(n, rs) for n, t, m, rs in all_results if t/m*100 < 80 if m]
    if failing:
        lines += ["", "## ❌ Falhas Detalhadas", ""]
        for test_name, results in failing:
            lines.append(f"### {test_name}")
            for r in results:
                if not r.passed:
                    lines.append(f"- **{r.file_check}**")
                    if r.missing: lines.append(f"  - Missing: `{', '.join(r.missing[:4])}`")
                    if r.wrong:   lines.append(f"  - Wrong:   `{', '.join(r.wrong[:3])}`")
                    if r.detail:  lines.append(f"  - {r.detail}")

    lines += ["", "## Fix", "```bash",
              "python scripts/integration_test.py --fix",
              "python scripts/validate.py --fix --loop",
              "```"]

    out.mkdir(parents=True, exist_ok=True)
    (out / "integration_report.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "integration_report.json").write_text(
        json.dumps({
            "score": round(pct, 1),
            "results": [{"test": n, "score": t, "max": m, "pass_rate": round(t/m,3) if m else 0}
                        for n,t,m,_ in all_results]
        }, indent=2), encoding="utf-8")


def force_train_from_failures(all_results: list, llm, model: str) -> None:
    """Studies topics that caused test failures."""
    from scripts.study import study_topic, SEARCH_CURRICULUM, load_discovered
    from scripts.validate import CRITICAL_PATTERNS
    from tools.vector_store import save, backfill_embeddings

    # Always save all critical patterns first
    for key, topic, content in CRITICAL_PATTERNS:
        save(key, content, topic=topic, source="integration_fix")

    all_c = {**SEARCH_CURRICULUM, **load_discovered()}

    # Find which study topics to target
    failed_keys = set()
    KEY_MAP = {
        "schema":    "nestjs_mongodb",
        "service":   "nestjs_mongodb",
        "module":    "nestjs_mongodb",
        "mongoose":  "nestjs_mongodb",
        ".env":      "nestjs_mongodb",
        "docker":    "docker_patterns",
        "entity":    "nestjs_postgres",
        "jwt":       "nestjs_auth",
        "spring":    "spring_mongodb",
        "fastapi":   "fastapi_mongodb",
        "livros":    "nlp_patterns",
        "pedidos":   "nlp_patterns",
    }

    for test_name, total, max_sc, results in all_results:
        if max_sc and total/max_sc < 0.8:
            for r in results:
                if not r.passed:
                    for kw, key in KEY_MAP.items():
                        if kw in r.file_check.lower() or kw in test_name.lower():
                            failed_keys.add(key)

    console.print(f"  [yellow]→ Retreinando: {', '.join(failed_keys)}[/yellow]")
    for key in failed_keys:
        if key in all_c:
            n = study_topic(key, all_c[key][:3], llm, model, intensive=True)
            if n: console.print(f"  [green]✓[/green] {key}: {n} itens")

    n_emb = backfill_embeddings()
    if n_emb: console.print(f"  [green]✓[/green] {n_emb} embeddings")


def main():
    parser = argparse.ArgumentParser(description="DevAI Integration Tests")
    parser.add_argument("--suite", default="all",
                        choices=["all","nestjs","nlp","spring","python"])
    parser.add_argument("--fix",   action="store_true",
                        help="Retreina falhas e re-testa")
    parser.add_argument("--loop",  action="store_true",
                        help="Loop até todos passarem")
    parser.add_argument("--test",  nargs="+", help="Testes específicos pelo nome")
    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]🧪 DevAI Integration Tests[/bold cyan]\n"
        "[dim]Testa pedidos reais — verifica arquivos gerados[/dim]",
        border_style="cyan",
    ))

    llm = model = None
    if args.fix:
        try:
            from tools.llm_client import OllamaClient
            from config import MODEL_CODE
            llm = OllamaClient(); llm.ensure_model(MODEL_CODE)
            model = MODEL_CODE
            console.print(f"  [green]✓[/green] Modelo: {model}")
        except Exception as e:
            console.print(f"[red]✗ LLM: {e}[/red]"); sys.exit(1)

    # Select tests
    tests_to_run = [t for t in TESTS
                    if (args.suite == "all" or t.suite == args.suite)
                    and (not args.test or t.name in args.test)]

    console.print(f"  Rodando {len(tests_to_run)} teste(s)\n")

    best_score = 0.0
    attempt = 1
    max_attempts = 10 if args.loop else 1

    while attempt <= max_attempts:
        if args.loop or attempt > 1:
            console.print(Rule(f"[cyan]Tentativa {attempt}/{max_attempts}[/cyan]"))

        all_results = []
        total_score = max_score = 0.0

        for test in tests_to_run:
            console.print(Rule(f"[cyan]{test.name}[/cyan]"))
            t_score, t_max, t_results = run_test(test)
            all_results.append((test.name, t_score, t_max, t_results))
            total_score += t_score
            max_score   += t_max

            pct = t_score/t_max*100 if t_max else 0
            color = "green" if pct >= 80 else "yellow" if pct >= 50 else "red"
            bar = "█" * int(pct/10) + "░" * (10 - int(pct/10))
            console.print(f"  [{color}]{t_score:.1f}/{t_max:.1f} [{bar}] {pct:.0f}%[/{color}]")

            for r in t_results:
                icon = "✓" if r.passed else "✗"
                c = "green" if r.passed else "red"
                console.print(f"    [{c}]{icon}[/{c}] {r.file_check}")
                if not r.passed:
                    if r.missing: console.print(f"      [yellow]Missing: {r.missing[:4]}[/yellow]")
                    if r.wrong:   console.print(f"      [red]Wrong: {r.wrong[:3]}[/red]")
                    if r.detail:  console.print(f"      [dim]{r.detail}[/dim]")

        overall = total_score / max_score * 100 if max_score else 0
        best_score = max(best_score, overall)
        color = "green" if overall >= 80 else "yellow" if overall >= 50 else "red"
        bar   = "█" * int(overall/5) + "░" * (20 - int(overall/5))

        console.print(Panel.fit(
            f"[bold {color}]Score: {overall:.0f}% [{bar}][/bold {color}]\n"
            f"{total_score:.1f}/{max_score:.1f} | "
            f"{'✅ PASSOU' if overall >= 80 else '❌ REPROVADO'}",
            border_style=color,
        ))

        out_dir = DEVAI_DIR / "training"
        write_integration_report(all_results, overall, out_dir)
        console.print("[dim]→ training/integration_report.md atualizado[/dim]")

        try:
            from tools.vector_store import auto_commit
            auto_commit(f"🧠 training: integration test {overall:.0f}%")
        except Exception: pass

        if overall >= 80 or not args.loop:
            break

        if args.fix and llm:
            console.print(Rule(f"[yellow]Retreinando falhas[/yellow]"))
            force_train_from_failures(all_results, llm, model)

        attempt += 1
        time.sleep(5)

    if args.loop and attempt > 1:
        console.print(Panel.fit(
            f"[bold green]Melhor score: {best_score:.0f}%[/bold green]",
            border_style="green",
        ))

    return 0 if best_score >= 80 else 1


if __name__ == "__main__":
    sys.exit(main())
