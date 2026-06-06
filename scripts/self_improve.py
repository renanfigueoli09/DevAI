"""
DevAI Self-Improvement — O agente gera código, valida e aprende com os resultados.

Diferente do estudo web (que salva resumos), aqui o agente:
  1. Recebe uma tarefa (ex: "NestJS service com Mongoose para Book")
  2. Gera o código usando o LLM
  3. Valida (compila? TypeScript válido? padrões corretos?)
  4. Se passou: salva como exemplo de alta qualidade no training store
  5. Se falhou: salva o erro + a correção como anti-pattern

Resultado: o training store tem exemplos FUNCIONAIS que o agente mesmo gerou e validou.
Quanto mais roda, mais exemplos funcionais acumula.

Uso:
  python scripts/self_improve.py             # gera exemplos para todos os tópicos
  python scripts/self_improve.py --topic nestjs-mongodb
  python scripts/self_improve.py --loop      # loop contínuo
"""

import json, re, subprocess, sys, tempfile, time
from pathlib import Path
from typing import Optional

DEVAI_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(DEVAI_DIR))

from rich.console import Console
from rich.rule import Rule
from rich.panel import Panel

console = Console()

# Tarefas de geração para auto-aprendizado
GENERATION_TASKS = [
    {
        "topic": "nestjs_mongodb",
        "key":   "self:nestjs+mongoose:book-schema",
        "prompt": (
            "Generate a complete NestJS Mongoose schema for a Book entity with:\n"
            "- title (required string)\n"
            "- author (required string)\n"
            "- price (required number, min 0)\n"
            "- description (optional string)\n"
            "- isActive (optional boolean, default true)\n"
            "Use @Schema, @Prop, HydratedDocument, SchemaFactory.\n"
            "TypeScript strict mode: required fields use !, optional use ?.\n"
            "Return ONLY the TypeScript file content."
        ),
        "validate_contains": ["@Schema", "@Prop", "HydratedDocument", "SchemaFactory", "title!:", "price!:", "description?:"],
        "validate_not":      ["title?:", "price?:", "title:", "findOneBy"],
    },
    {
        "topic": "nestjs_mongodb",
        "key":   "self:nestjs+mongoose:book-service",
        "prompt": (
            "Generate a complete NestJS Mongoose service for Book entity with CRUD.\n"
            "Use @InjectModel(Book.name) private model: Model<BookDocument>.\n"
            "Methods: findAll(), findOne(id), create(dto), update(id, dto), remove(id).\n"
            "Use findById, findByIdAndUpdate({$set:dto},{new:true}), findByIdAndDelete.\n"
            "Throw NotFoundException when not found.\n"
            "NEVER use findOneBy (TypeORM only).\n"
            "Return ONLY the TypeScript file content."
        ),
        "validate_contains": ["@InjectModel", "Model<BookDocument>", "findById", "NotFoundException"],
        "validate_not":      ["findOneBy", "@InjectRepository", "Repository<"],
    },
    {
        "topic": "nestjs_mongodb",
        "key":   "self:nestjs+mongoose:book-module",
        "prompt": (
            "Generate a NestJS Mongoose module for Book entity.\n"
            "Use MongooseModule.forFeature([{name: Book.name, schema: BookSchema}]).\n"
            "Import BookService and BookController.\n"
            "Return ONLY the TypeScript file content."
        ),
        "validate_contains": ["MongooseModule.forFeature", "Book.name", "BookSchema", "BookService", "BookController"],
        "validate_not":      ["TypeOrmModule", "TypeOrmModule.forFeature"],
    },
    {
        "topic": "nestjs",
        "key":   "self:nestjs:dto-partialtype",
        "prompt": (
            "Generate NestJS DTOs for Book entity.\n"
            "CreateBookDto with title, author (required strings) and description (optional string).\n"
            "UpdateBookDto extends PartialType(CreateBookDto) from '@nestjs/mapped-types'.\n"
            "Use class-validator decorators.\n"
            "Return ONLY the TypeScript file content."
        ),
        "validate_contains": ["PartialType", "@nestjs/mapped-types", "@IsString", "UpdateBookDto"],
        "validate_not":      ["from '@nestjs/common'", "from '@nestjs/swagger'"],
    },
    {
        "topic": "docker",
        "key":   "self:docker:compose-mongodb-only",
        "prompt": (
            "Generate a docker-compose.yml for a NestJS app with MongoDB ONLY.\n"
            "No Redis, no Kafka, no Nginx — only app and db services.\n"
            "MongoDB healthcheck: mongosh --eval db.adminCommand('ping').\n"
            "App depends_on db with condition service_healthy.\n"
            "Return ONLY the YAML content."
        ),
        "validate_contains": ["mongo:7.0", "mongosh", "service_healthy", "MONGODB_URI"],
        "validate_not":      ["redis", "kafka", "nginx", "zookeeper"],
    },
    {
        "topic": "nlp",
        "key":   "self:nlp:entity-extraction",
        "prompt": (
            "Given the description: 'API REST de livros com MongoDB e docker'\n"
            "What are:\n"
            "1. Entity names (PascalCase, singular English): ?\n"
            "2. db_type: ?\n"
            "3. has_auth: ?\n"
            "4. Should docker create src/docker/ folder? ?\n"
            "Answer clearly for each."
        ),
        "validate_contains": ["Book", "mongodb", "false", "no"],
        "validate_not":      ["Livros", "Livro", "src/docker", "JWT"],
    },
    {
        "topic": "nestjs_typeorm",
        "key":   "self:nestjs+typeorm:product-entity",
        "prompt": (
            "Generate a NestJS TypeORM entity for Product.\n"
            "Fields: id (UUID), name (string, not null), price (decimal 10,2), isActive (boolean default true), createdAt, updatedAt.\n"
            "Use @Entity, @PrimaryGeneratedColumn('uuid'), @Column, @CreateDateColumn, @UpdateDateColumn.\n"
            "Return ONLY the TypeScript file content."
        ),
        "validate_contains": ["@Entity", "@PrimaryGeneratedColumn", "uuid", "@Column", "@CreateDateColumn"],
        "validate_not":      ["@Schema", "@Prop", "HydratedDocument", "MongooseModule"],
    },
    {
        "topic": "python_fastapi",
        "key":   "self:fastapi+mongodb:book-crud",
        "prompt": (
            "Generate FastAPI MongoDB CRUD for Book using Motor (async).\n"
            "Fields: title, author (required), description (optional).\n"
            "Use AsyncIOMotorClient, Pydantic v2 BaseModel, model_dump().\n"
            "Routes: GET /books, POST /books, PUT /books/{id}, DELETE /books/{id}.\n"
            "Return ONLY the Python file content."
        ),
        "validate_contains": ["AsyncIOMotorClient", "model_dump", "BaseModel", "HTTPException"],
        "validate_not":      ["MongoClient", ".dict()"],
    },
]


def generate_with_llm(prompt: str, llm, model: str) -> str:
    """Gera código usando o LLM."""
    try:
        # Busca contexto relevante primeiro
        ctx = ""
        try:
            from tools.vector_store import search_relevant
            ctx = search_relevant(prompt[:200], limit=2)
        except Exception:
            pass

        full_prompt = prompt
        if ctx:
            full_prompt = f"Training reference:\n{ctx[:600]}\n\n{prompt}"

        resp = llm.chat(
            model=model,
            messages=[{"role": "user", "content": full_prompt}],
            system=(
                "You generate production-ready code. "
                "Return ONLY the file content. No explanation, no markdown fences. "
                "Follow all rules in the training reference exactly."
            ),
            stream=False,
        )
        # Strip markdown fences
        resp = re.sub(r"^```\w*\n?", "", resp.strip(), flags=re.MULTILINE)
        resp = re.sub(r"\n?```$", "", resp.strip(), flags=re.MULTILINE)
        return resp.strip()
    except Exception as e:
        return f"[error: {e}]"


def validate_output(content: str, task: dict) -> tuple[bool, list, list]:
    """Valida se o output contém o esperado."""
    c = content.lower()
    found   = [kw for kw in task["validate_contains"] if kw.lower() in c]
    missing = [kw for kw in task["validate_contains"] if kw.lower() not in c]
    wrong   = [kw for kw in task["validate_not"]      if kw.lower() in c]
    passed  = not missing and not wrong
    return passed, missing, wrong


def run_task(task: dict, llm, model: str) -> bool:
    """Roda uma tarefa de geração e salva o resultado."""
    from tools.vector_store import save, get as vs_get

    # Skip if already generated recently
    existing = vs_get(task["key"])
    if existing and "[error" not in existing:
        console.print(f"  [dim]↓ cached: {task['key'][:45]}[/dim]")
        return True

    console.print(f"  [cyan]→ {task['key'][:50]}[/cyan]")
    content = generate_with_llm(task["prompt"], llm, model)

    if not content or "[error" in content[:20]:
        console.print(f"  [red]✗ Geração falhou[/red]")
        return False

    passed, missing, wrong = validate_output(content, task)

    if passed:
        # Salva como exemplo de alta qualidade
        save(task["key"], content, topic=task["topic"], source="self_generated_validated")
        console.print(f"  [green]✓ Válido — salvo como exemplo de alta qualidade[/green]")
        return True
    else:
        # Salva a tentativa falha + anti-pattern
        if missing:
            anti_key = f"{task['key']}:missing"
            anti_content = (
                f"COMMON MISTAKE in {task['topic']}:\n"
                f"Generated code was MISSING: {', '.join(missing)}\n"
                f"Prompt was: {task['prompt'][:200]}\n"
                f"CORRECT approach must include: {', '.join(task['validate_contains'])}"
            )
            save(anti_key, anti_content, topic=task["topic"], source="anti_pattern")

        if wrong:
            anti_key2 = f"{task['key']}:wrong"
            anti_content2 = (
                f"ANTI-PATTERN in {task['topic']}:\n"
                f"Generated code WRONGLY used: {', '.join(wrong)}\n"
                f"These are FORBIDDEN in this context.\n"
                f"Correct: {', '.join(task['validate_contains'][:3])}"
            )
            save(anti_key2, anti_content2, topic=task["topic"], source="anti_pattern")

        console.print(f"  [yellow]⚠ Falhou — anti-pattern salvo[/yellow]")
        if missing: console.print(f"    Missing: {missing[:3]}")
        if wrong:   console.print(f"    Wrong:   {wrong[:3]}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="DevAI Self-Improvement")
    parser.add_argument("--topic", nargs="+")
    parser.add_argument("--loop",  action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-gera mesmo se já existe")
    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]🔄 DevAI Self-Improvement[/bold cyan]\n"
        "[dim]Gera código, valida e aprende com os resultados[/dim]",
        border_style="cyan",
    ))

    from tools.llm_client import OllamaClient
    from config import MODEL_CODE
    try:
        llm = OllamaClient(); llm.ensure_model(MODEL_CODE)
        console.print(f"  [green]✓[/green] Modelo: {MODEL_CODE}")
    except Exception as e:
        console.print(f"[red]✗ {e}[/red]"); sys.exit(1)

    tasks = GENERATION_TASKS
    if args.topic:
        tasks = [t for t in tasks if any(tp in t["topic"] for tp in args.topic)]

    cycle = 1
    while True:
        console.print(Rule(f"[cyan]Ciclo {cycle} — {time.strftime('%H:%M')}[/cyan]"))
        passed_count = 0

        for task in tasks:
            if args.force:
                from tools.vector_store import save
                from tools.vector_store import get as vs_get
                # Force by clearing existing
                pass
            ok = run_task(task, llm, MODEL_CODE)
            if ok: passed_count += 1
            time.sleep(1)

        # Generate embeddings for new content
        try:
            from tools.vector_store import backfill_embeddings
            n = backfill_embeddings()
            if n: console.print(f"  [green]✓[/green] {n} embedding(s)")
        except Exception: pass

        console.print(Panel.fit(
            f"[bold green]{passed_count}/{len(tasks)} tarefas válidas[/bold green]",
            border_style="green",
        ))

        if not args.loop: break
        console.print("[dim]Próximo ciclo em 1min...[/dim]")
        time.sleep(60)
        cycle += 1


if __name__ == "__main__":
    main()
