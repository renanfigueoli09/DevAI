"""
Code Fixer — correções determinísticas em arquivos TypeScript/Python/Java/C#.

Roda em DOIS momentos:
  1. Pós-geração (via generator.py)
  2. Pré-compilação (via fix_project — scan de todos os arquivos existentes)

Corrige sem LLM:
  - PartialType do lugar errado
  - TypeORM repo.create() sem cast
  - Imports com paths errados
  - Barrel imports (./dto → ./entity.dto)
  - Decorators inexistentes (MinArrayLength → ArrayMinSize)
  - Partial usado como valor em vez de PartialType
  - Conteúdo lixo (arquivo começa com 'typescript;')
"""

import re
import json
import subprocess
import shutil
from pathlib import Path
from typing import Optional
from rich.console import Console

console = Console()


# ─── Validação de conteúdo ────────────────────────────────────────────────────

GARBAGE_PREFIXES = [
    "typescript", "javascript", "python", "java ", "csharp", "---", "```",
]

def is_valid_content(content: str, path: str) -> tuple[bool, str]:
    if not content or len(content.strip()) < 20:
        return False, "vazio ou muito curto"

    first = content.strip().splitlines()[0].strip().lower()
    for prefix in GARBAGE_PREFIXES:
        if first.startswith(prefix.lower()):
            return False, f"conteúdo lixo: '{first[:30]}'"

    ext = Path(path).suffix
    if ext in (".ts", ".tsx"):
        has_code = any(kw in content for kw in [
            "import ", "export ", "class ", "interface ", "type ", "const ",
            "function ", "@Injectable", "@Controller", "@Entity", "@Module",
        ])
        if not has_code:
            return False, "sem código TypeScript reconhecível"

    if ext == ".py":
        if not any(kw in content for kw in ["import ", "from ", "def ", "class ", "async "]):
            return False, "sem código Python reconhecível"

    if ext == ".java":
        if not any(kw in content for kw in ["import ", "class ", "public ", "@"]):
            return False, "sem código Java reconhecível"

    if ext == ".cs":
        if not any(kw in content for kw in ["using ", "namespace ", "class ", "public ", "["]):
            return False, "sem código C# reconhecível"

    return True, ""


# ─── Fixes determinísticos TypeScript ─────────────────────────────────────────

# Cada fix: (descrição, padrão_regex, substituição)
TS_FIXES: list[tuple[str, str, str]] = [

    # PartialType só existe em @nestjs/mapped-types (não em @nestjs/common nem @nestjs/swagger)
    ("PartialType from @nestjs/common",
     r"(import\s*\{[^}]*\bPartialType\b[^}]*\}\s*from\s*)'@nestjs/common'",
     r"\1'@nestjs/mapped-types'"),

    ("PartialType from @nestjs/swagger",
     r"(import\s*\{[^}]*\bPartialType\b[^}]*\}\s*from\s*)'@nestjs/swagger'",
     r"\1'@nestjs/mapped-types'"),

    ("PartialType from @nestjs/typeorm",
     r"(import\s*\{[^}]*\bPartialType\b[^}]*\}\s*from\s*)'@nestjs/typeorm'",
     r"\1'@nestjs/mapped-types'"),

    # ApiProperty/Swagger decorators não são de @nestjs/core
    ("ApiProperty from @nestjs/core",
     r"(import\s*\{[^}]*\bApiProperty\b[^}]*\}\s*from\s*)'@nestjs/core'",
     r"\1'@nestjs/swagger'"),

    # class-validator decorators não são de @nestjs/common
    ("validators from @nestjs/common",
     r"(import\s*\{[^}]*)(\bIsEmail|IsNotEmpty|IsString|IsNumber|IsBoolean|IsUUID|MinLength|MaxLength|IsOptional|IsEnum|IsArray|ValidateNested|IsInt|Min|Max|IsPositive|ArrayMinSize|ArrayMaxSize)(\b[^}]*\}\s*from\s*)'@nestjs/common'",
     r"\1\2\3'class-validator'"),

    # class-transformer não é de @nestjs/common
    ("Transform/Exclude from @nestjs/common",
     r"(import\s*\{[^}]*(?:Type|Expose|Exclude|Transform)\b[^}]*\}\s*from\s*)'@nestjs/common'",
     r"\1'class-transformer'"),

    # MinArrayLength não existe → ArrayMinSize
    ("MinArrayLength → ArrayMinSize",
     r"\bMinArrayLength\b",
     "ArrayMinSize"),

    # MaxArrayLength não existe → ArrayMaxSize
    ("MaxArrayLength → ArrayMaxSize",
     r"\bMaxArrayLength\b",
     "ArrayMaxSize"),

    # IsPhoneNumber pode não existir em algumas versões
    ("Partial() como valor → PartialType()",
     r"\bextends\s+Partial\s*\(",
     "extends PartialType("),

    # TypeORM: repo.create(dto) sem cast causa TS2769
    # this.repo.create(dto) → this.repo.create(dto as any)
    ("TypeORM create without cast",
     r"this\.repo\.create\((\w+)\)",
     r"this.repo.create(\1 as any)"),

    # repo.save(repo.create(dto)) em uma linha → separar
    ("TypeORM save(create()) one-liner",
     r"this\.repo\.save\(this\.repo\.create\((\w+)\s+as\s+any\)\)",
     r"this.repo.save(this.repo.create(\1 as any))"),

    # findById não existe em TypeORM/Mongoose → findOne
    ("findById → findOne in controllers",
     r"\bthis\.\w+Service\.findById\(",
     lambda m: m.group(0).replace("findById", "findOne")),

    # Mongoose: this.model.findOneBy (TypeORM method) → this.model.findById
    ("model.findOneBy → findById (Mongoose)",
     r"this\.(?:model|\w+Model)\.findOneBy\(",
     lambda m: m.group(0).replace("findOneBy", "findById")),

    # TypeORM repo: this.repo.findOneBy({id}) stays as-is (correct for TypeORM)
    # Mongoose: this.model.findById(id) → this.model.findById(id).exec() — exec() optional


    # findById não existe no service → findOne (controller chama findById mas service tem findOne)
    ("controller.findById → findOne (any service)",
     r"this\.([A-Za-z]+Service)\.findById\(",
     r"this.\1.findOne("),

    # auth.module: '../users/users.module' → '../user/user.module' (plural fix)
    # Suporta aspas simples e duplas
    ("users.module plural single-quote",
     r"from '\.\./(users)/users\.module'",
     "from '../user/user.module'"),
    ("users.module plural double-quote",
     r'from "\.\./(users)/users\.module"',
     'from "../user/user.module"'),

    ("users.service plural single-quote",
     r"from '\.\./(users)/users\.service'",
     "from '../user/user.service'"),

    # user.entity → user.schema para projetos MongoDB
    ("user.entity → user.schema single-quote",
     r"from '(\.\.?/[^']*user)\.entity'",
     r"from '\1.schema'"),
    ("user.entity → user.schema double-quote",
     r'from "(\.\.?/[^"]*user)\.entity"',
     r'from "\1.schema"'),

    # './user.schema' em auth.service → '../user/user.schema'
    ("./user.schema → ../user/user.schema",
     r"from '\./user\.schema'",
     "from '../user/user.schema'"),

    # UsersModule → UserModule (quando o módulo real é singular)
    ("UsersModule import → UserModule",
     r"import\s*\{\s*UsersModule\s*\}",
     "import { UserModule }"),
    ("UsersModule in array → UserModule",
     r"\bUsersModule\b",
     "UserModule"),

    # JwtAuthGuard path antigo (guards/jwt-auth.guard) → novo (jwt.guard)
    ("JwtAuthGuard old path guards/",
     r"from\s+'(\.\.?/)*auth/guards/jwt-auth\.guard'",
     "from '../auth/jwt.guard'"),

    ("JwtAuthGuard nested path",
     r"from\s+'(\.\.?/)*auth/guards/jwt-auth\.guard'",
     "from '../../auth/jwt.guard'"),

    # LocalAuthGuard
    ("LocalAuthGuard old path",
     r"from\s+'(\.\.?/)*auth/guards/local-auth\.guard'",
     "from '../auth/local.strategy'"),

    # Barrel import ./dto → deve ser ./entity.dto ou ../../entity/entity.dto
    # Só remove se não existe o arquivo dto/index.ts
    # (resolvido pelo fix_import_paths_in_file abaixo)
]


def fix_ts_content(content: str, path: str) -> str:
    """Aplica todos os fixes determinísticos em um arquivo TypeScript."""
    if not path.endswith((".ts", ".tsx")):
        return content

    for desc, pattern, replacement in TS_FIXES:
        try:
            new_content = re.sub(pattern, replacement, content)
            if new_content != content:
                content = new_content
        except re.error:
            pass

    # Fix específico: remove 'typescript;' ou 'javascript;' no início
    lines = content.splitlines()
    if lines and re.match(r"^(typescript|javascript|java|python|csharp)\s*;?\s*$",
                          lines[0].strip(), re.IGNORECASE):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
        content = "\n".join(lines)

    return content


def fix_dto_imports(content: str, file_path: str, project_path: Path) -> str:
    """
    Corrige imports de './dto' barrel para o arquivo .dto.ts correto.
    Ex: import X from './dto' → import X from './product.dto'
    """
    if not file_path.endswith(".ts"):
        return content

    abs_path = Path(file_path) if Path(file_path).is_absolute() else project_path / file_path
    current_dir = abs_path.parent

    def replace_barrel(m):
        full_match  = m.group(0)
        import_path = m.group(1)

        # Só corrige imports de './dto' ou '../dto' etc (barrel)
        base = import_path.rstrip("/").split("/")[-1]
        if base != "dto":
            return full_match

        # Procura arquivos .dto.ts no diretório atual
        dto_files = list(current_dir.glob("*.dto.ts"))
        if dto_files:
            # Usa o primeiro .dto.ts encontrado
            rel = dto_files[0].stem  # ex: product.dto
            new_path = import_path.replace("dto", rel)
            return full_match.replace(f"'{import_path}'", f"'{new_path}'")

        # Procura no diretório pai
        dto_files_parent = list(current_dir.parent.glob("*.dto.ts"))
        if dto_files_parent:
            rel = dto_files_parent[0].stem
            return full_match.replace(f"'{import_path}'", f"'../{rel}'")

        return full_match

    return re.sub(r"from\s+'(\.[^']+)'", replace_barrel, content)


def fix_guard_import_path(content: str, file_path: str, project_path: Path) -> str:
    """Corrige o path do JwtAuthGuard baseado na estrutura real de arquivos."""
    if "JwtAuthGuard" not in content and "LocalAuthGuard" not in content:
        return content

    abs_path = Path(file_path) if Path(file_path).is_absolute() else project_path / file_path

    # Encontra o arquivo jwt.guard.ts no projeto
    guard_files = list(project_path.rglob("jwt.guard.ts"))
    if not guard_files:
        guard_files = list(project_path.rglob("jwt-auth.guard.ts"))
    if not guard_files:
        return content

    guard_path = guard_files[0]
    try:
        rel = guard_path.relative_to(abs_path.parent)
        rel_str = "./" + str(rel).replace("\\", "/").replace(".ts", "")
        # Fix the import
        content = re.sub(
            r"from\s+'[^']*(?:jwt-auth\.guard|jwt\.guard)'",
            f"from '{rel_str}'",
            content,
        )
    except ValueError:
        pass

    return content


# ─── Barrel files ─────────────────────────────────────────────────────────────

def generate_barrel_files(files: list[dict], stack: str) -> list[dict]:
    """Gera barrel index.ts APENAS quando necessário (diretório tem múltiplos .ts)."""
    if stack not in ("nestjs", "nextjs", "angular"):
        return []

    barrels = []
    by_dir: dict[str, list[str]] = {}
    for f in files:
        path = f.get("path", "")
        if not path.endswith((".ts", ".tsx")):
            continue
        dirname = str(Path(path).parent)
        by_dir.setdefault(dirname, []).append(path)

    barrel_dirs = {"exceptions", "guards", "decorators", "interceptors", "pipes", "filters", "strategies"}
    for dirpath, filepaths in by_dir.items():
        dirname_lower = Path(dirpath).name.lower()
        if dirname_lower not in barrel_dirs:
            continue
        index_path = f"{dirpath}/index.ts"
        if any(f.get("path") == index_path for f in files):
            continue
        exports = [f"export * from './{Path(fp).stem}';" for fp in sorted(filepaths)
                   if not fp.endswith("index.ts")]
        if exports:
            barrels.append({"path": index_path, "content": "\n".join(exports) + "\n"})

    return barrels


# ─── Integração app.module.ts ─────────────────────────────────────────────────

# These directory names are hallucinated by LLMs from training context
_INVALID_DIRS = {
    "dockerhub", "container", "containers", "image", "images", "files",
    "docker-hub", "docker_hub", "hub", "registry", "repository", "repo",
    "ci", "cd", "cicd", "pipeline", "actions", "workflows", "workflow",
    "kubernetes", "k8s", "helm", "charts", "nginx", "proxy",
    "undefined", "null", "none", "example", "placeholder", "todo",
    "lorem", "ipsum", "test-dir", "sample", "demo-dir",
}


def cleanup_invalid_dirs(project_path: Path) -> list[str]:
    """
    Remove directories criados por alucinação do LLM.
    Mantém apenas estruturas NestJS/Spring/Python válidas.
    Retorna lista de diretórios removidos.
    """
    import shutil
    removed = []

    src = project_path / "src"
    if not src.exists():
        return removed

    for d in list(src.iterdir()):
        if not d.is_dir():
            continue
        name = d.name.lower()

        # Pula diretórios NestJS legítimos
        if name in {"app", "common", "auth", "config", "configs", "shared",
                    "decorators", "guards", "interceptors", "filters",
                    "pipes", "middlewares", "interfaces", "utils", "helpers",
                    "modules", "entities", "schemas", "models", "dto", "dtos"}:
            continue

        # Remove se é um nome inválido / alucinado
        if name in _INVALID_DIRS:
            try:
                shutil.rmtree(str(d))
                removed.append(d.name)
            except Exception:
                pass

    return removed


def ensure_db_in_app_module(app_module_path: Path, db_type: str, db_name: str = "app") -> bool:
    """
    Garante que app.module.ts tem a conexão do banco configurada.
    Funciona para qualquer banco: MongoDB (Mongoose), PostgreSQL/MySQL/SQLite (TypeORM).
    Determinístico — não depende do LLM.
    Retorna True se algo foi alterado.
    """
    if not app_module_path.exists():
        return False

    content = app_module_path.read_text(encoding="utf-8", errors="ignore")

    # Verifica se já tem conexão do banco
    has_db = (
        "MongooseModule.forRoot" in content or
        "MongooseModule.forRootAsync" in content or
        "TypeOrmModule.forRoot" in content or
        "TypeOrmModule.forRootAsync" in content or
        "SequelizeModule.forRoot" in content
    )
    if has_db:
        return False

    db_type = db_type or "postgres"

    # ── MongoDB / Mongoose ────────────────────────────────────────────────────
    if db_type == "mongodb":
        import_line  = "import { MongooseModule } from '@nestjs/mongoose';"
        module_entry = (
            f"MongooseModule.forRoot("
            f"process.env.MONGODB_URI || 'mongodb://localhost:27017/{db_name}'),"
        )

    # ── PostgreSQL / MySQL / MariaDB / SQLite — TypeORM ────────────────────────
    elif db_type in ("postgres", "mysql", "mariadb", "sqlite"):
        import_line  = "import { TypeOrmModule } from '@nestjs/typeorm';"
        db_type_ts   = {
            "postgres": "postgres", "mysql": "mysql",
            "mariadb": "mariadb",   "sqlite": "better-sqlite3",
        }[db_type]
        if db_type == "sqlite":
            module_entry = (
                f"TypeOrmModule.forRoot({{ type: '{db_type_ts}', "
                f"database: process.env.DB_PATH || './{db_name}.db', "
                f"entities: [__dirname + '/**/*.entity.js'], synchronize: true }}),"
            )
        else:
            module_entry = (
                f"TypeOrmModule.forRootAsync({{ useFactory: () => ({{ "
                f"type: '{db_type_ts}', "
                f"host: process.env.DB_HOST || 'localhost', "
                f"port: +(process.env.DB_PORT || '{5432 if db_type == 'postgres' else 3306}'), "
                f"database: process.env.DB_NAME || '{db_name}', "
                f"username: process.env.DB_USER || 'root', "
                f"password: process.env.DB_PASS || '', "
                f"entities: [__dirname + '/**/*.entity.js'], "
                f"synchronize: process.env.NODE_ENV !== 'production' }}) }}),"
            )
    else:
        return False

    # Adiciona o import se não existe
    if import_line not in content:
        # Insere após outros imports
        import_idx = content.rfind("import {")
        if import_idx < 0:
            import_idx = 0
        eol = content.find("\n", import_idx) + 1
        content = content[:eol] + import_line + "\n" + content[eol:]

    # Adiciona o módulo no array de imports
    # Encontra imports: [ ... ]
    imports_idx = content.find("imports: [")
    if imports_idx < 0:
        imports_idx = content.find("imports:[")
    if imports_idx < 0:
        return False

    bracket_start = content.find("[", imports_idx)
    if bracket_start < 0:
        return False

    # Insere o DB module logo após o [
    insert_at = bracket_start + 1
    content = (content[:insert_at] +
               "\n    " + module_entry +
               content[insert_at:])

    app_module_path.write_text(content, encoding="utf-8")
    return True


def integrate_module_into_app(
    app_module_path: Path,
    new_module_name: str,
    new_module_import_path: str,
) -> Optional[str]:
    if not app_module_path.exists():
        return None
    content = app_module_path.read_text(encoding="utf-8")
    if new_module_name in content:
        return content

    import_stmt = f"import {{ {new_module_name} }} from '{new_module_import_path}';"
    last_import = list(re.finditer(r"^import .+;$", content, re.MULTILINE))
    if last_import:
        pos = last_import[-1].end()
        content = content[:pos] + "\n" + import_stmt + content[pos:]
    else:
        content = import_stmt + "\n" + content

    imports_match = re.search(r"imports:\s*\[([^\]]*)\]", content, re.DOTALL)
    if imports_match:
        old_imports = imports_match.group(1)
        if old_imports.strip():
            new_imports = old_imports.rstrip() + f",\n    {new_module_name}"
        else:
            new_imports = f"\n    {new_module_name}\n  "
        content = content[:imports_match.start(1)] + new_imports + content[imports_match.end(1):]

    return content


# ─── Scan e fix de projeto existente ─────────────────────────────────────────

def scan_and_fix_project(project_path: Path, stack: str) -> int:
    """
    Escaneia TODOS os arquivos de um projeto e aplica fixes determinísticos.
    Chamado pelo fix_project ANTES de rodar o compilador.
    Retorna número de arquivos modificados.
    """
    if stack not in ("nestjs", "nextjs", "angular", "python", "spring-boot", "dotnet"):
        return 0

    modified = 0
    extensions = {
        "nestjs": [".ts"], "nextjs": [".ts", ".tsx"], "angular": [".ts"],
        "python": [".py"], "spring-boot": [".java"], "dotnet": [".cs"],
    }
    exts = extensions.get(stack, [".ts"])

    ignore_dirs = {"node_modules", ".git", "dist", "build", "__pycache__",
                   ".venv", "venv", "target", ".gradle", "obj", "bin"}

    console.print(f"  [dim]→ Aplicando fixes determinísticos em todos os {', '.join(exts)}...[/dim]")

    for ext in exts:
        for fpath in project_path.rglob(f"*{ext}"):
            # Skip ignored dirs
            if any(part in ignore_dirs for part in fpath.parts):
                continue

            try:
                original = fpath.read_text(encoding="utf-8", errors="ignore")
                fixed = original

                if ext == ".ts":
                    fixed = fix_ts_content(fixed, str(fpath))
                    fixed = fix_dto_imports(fixed, str(fpath), project_path)
                    fixed = fix_guard_import_path(fixed, str(fpath), project_path)

                if fixed != original:
                    fpath.write_text(fixed, encoding="utf-8")
                    modified += 1
                    rel = fpath.relative_to(project_path)
                    console.print(f"    [green]✓[/green] {rel}")
            except Exception:
                pass

    if modified:
        console.print(f"  [green]✓ {modified} arquivo(s) corrigido(s) deterministicamente[/green]")
    else:
        console.print("  [dim]✓ Sem fixes determinísticos necessários[/dim]")

    return modified


# ─── Post-geração ─────────────────────────────────────────────────────────────

def fix_all(files: list[dict], stack: str, project_path: Optional[Path] = None) -> list[dict]:
    """Aplica todos os fixes em arquivos recém-gerados (pós-geração)."""
    valid = []
    rejected = []

    for f in files:
        path    = f.get("path", "")
        content = f.get("content", "")

        ok, reason = is_valid_content(content, path)
        if not ok:
            rejected.append(f"{path}: {reason}")
            continue

        content = fix_ts_content(content, path)
        if project_path:
            content = fix_dto_imports(content, path, project_path)

        valid.append({**f, "content": content})

    barrels = generate_barrel_files(valid, stack)
    valid.extend(barrels)

    if rejected:
        console.print(f"  [yellow]⚠ {len(rejected)} arquivo(s) rejeitado(s):[/yellow]")
        for r in rejected[:3]:
            console.print(f"    [dim]- {r}[/dim]")

    # Sanitize file paths — no spaces allowed
    sanitized = []
    for f in valid:
        path = f.get("path", "")
        if " " in path:
            # kebab-case: "banco mongodb.dto.ts" → "banco-mongodb.dto.ts"
            new_path = path.replace(" ", "-").lower()
            # Fix the content to match new names
            entity_old = Path(path).stem.split(".")[0].replace("-", " ")
            entity_new = entity_old.replace(" ", "-")
            content_fixed = f.get("content", "").replace(
                entity_old.title().replace(" ", ""),
                entity_new.title().replace("-", ""),
            )
            sanitized.append({**f, "path": new_path, "content": content_fixed})
            console.print(f"  [yellow]⚠ Path com espaço sanitizado: {path} → {new_path}[/yellow]")
        else:
            sanitized.append(f)

    return sanitized


# ─── NestJS preinstall ────────────────────────────────────────────────────────

# Pacotes que SEMPRE devem estar no NestJS (sem versões fixas — deixa o npm resolver)
NESTJS_REQUIRED = [
    "@nestjs/config",
    "@nestjs/swagger",
    "@nestjs/typeorm",
    "@nestjs/jwt",
    "@nestjs/passport",
    "@nestjs/mapped-types",
    "@nestjs/cache-manager",
    "typeorm",
    "class-validator",
    "class-transformer",
    "passport",
    "passport-jwt",
    "passport-local",
    "bcrypt",
    "uuid",
    "joi",
    # pg is a transitive dep of typeorm — NOT listed to avoid pg-protocol conflicts
]

NESTJS_DEV_REQUIRED = [
    "@types/passport-jwt",
    "@types/passport-local",
    "@types/bcrypt",
    "@types/uuid",
]



def apply_fixes_to_project(project_path: Path) -> int:
    """
    Aplica todos os fixes determinísticos a arquivos TypeScript EXISTENTES no projeto.
    Chamado pelo repair loop ANTES de compilar, para corrigir o que o LLM gerou errado.
    Retorna o número de arquivos modificados.
    """
    if not project_path.exists():
        return 0

    modified = 0
    ts_files = [
        f for f in project_path.rglob("*.ts")
        if not any(p in str(f) for p in [
            "node_modules", ".git", "dist", "__pycache__", ".next"
        ])
    ]

    for ts_file in ts_files:
        try:
            original = ts_file.read_text(encoding="utf-8", errors="ignore")
            fixed = fix_ts_content(original, str(ts_file))

            # fix_dto_imports: procura .dto.ts no mesmo diretório
            fixed = _fix_barrel_dto_import(fixed, ts_file, project_path)
            # fix module internal paths (module.ts importing '../entity' instead of './entity')
            fixed = _fix_module_internal_paths(fixed, ts_file)
            # fix guard paths
            fixed = fix_guard_import_path(fixed, str(ts_file), project_path)

            if fixed != original:
                ts_file.write_text(fixed, encoding="utf-8")
                modified += 1
        except Exception:
            pass

    return modified


def _fix_barrel_dto_import(content: str, file_path: Path, project_path: Path) -> str:
    """Substitui import de './dto' pelo arquivo .dto.ts real do módulo."""
    if "from './dto'" not in content and 'from "./dto"' not in content:
        return content

    current_dir = file_path.parent
    # Procura *.dto.ts no mesmo diretório
    dto_files = list(current_dir.glob("*.dto.ts"))
    if dto_files:
        dto_stem = dto_files[0].stem  # ex: "product.dto"
        content = content.replace("from './dto'", f"from './{dto_stem}'")
        content = content.replace('from "./dto"', f'from "./{dto_stem}"')
        return content

    # Procura pelo padrão {entity}.dto.ts baseado no nome do arquivo atual
    entity_name = file_path.stem.split(".")[0]  # ex: "product" de "product.service.ts"
    dto_candidates = list(project_path.rglob(f"{entity_name}.dto.ts"))
    if dto_candidates:
        rel = dto_candidates[0].relative_to(current_dir)
        rel_str = "./" + str(rel).replace("\\", "/").replace(".ts", "")
        content = content.replace("from './dto'", f"from '{rel_str}'")
        content = content.replace('from "./dto"', f'from "{rel_str}"')

    return content


def _fix_module_internal_paths(content: str, file_path: Path) -> str:
    """
    Corrige imports errados em *.module.ts que vão um nível acima desnecessariamente.
    Ex: product.module.ts importando '../product.entity' → './product.entity'
    """
    if not file_path.name.endswith(".module.ts"):
        return content

    entity = file_path.stem.replace(".module", "")  # ex: "product"
    # Imports que vão um nível acima mas deveriam ser locais
    wrong_prefixes = [
        (f"from '../{entity}.entity'",    f"from './{entity}.entity'"),
        (f"from '../{entity}.service'",   f"from './{entity}.service'"),
        (f"from '../{entity}.controller'",f"from './{entity}.controller'"),
        (f"from '../{entity}.dto'",       f"from './{entity}.dto'"),
        (f'from "../{entity}.entity"',    f'from "./{entity}.entity"'),
        (f'from "../{entity}.service"',   f'from "./{entity}.service"'),
        (f'from "../{entity}.controller"',f'from "./{entity}.controller"'),
    ]
    for wrong, correct in wrong_prefixes:
        content = content.replace(wrong, correct)

    return content


def preinstall_nestjs_deps(project_path: Path) -> bool:
    """Instala pacotes NestJS necessários que ainda não estão em node_modules."""
    if not shutil.which("npm"):
        return False
    if not (project_path / "package.json").exists():
        return False

    # Verifica quais estão realmente em node_modules (não só em package.json)
    to_install = [p for p in NESTJS_REQUIRED
                  if not (project_path / "node_modules" / p).exists()]
    to_install_dev = [p for p in NESTJS_DEV_REQUIRED
                      if not (project_path / "node_modules" / p).exists()]

    if to_install:
        console.print(f"  [dim]→ Instalando {len(to_install)} pacotes faltantes...[/dim]")
        r = subprocess.run(
            ["npm", "install", "--save", "--prefer-offline",
             "--legacy-peer-deps", "--no-fund", "--no-audit"] + to_install,
            cwd=str(project_path), capture_output=True, text=True, timeout=300,
        )
        if r.returncode != 0:
            # Tenta um por vez para isolar o problemático
            for pkg in to_install:
                subprocess.run(
                    ["npm", "install", "--save", "--prefer-offline",
                     "--legacy-peer-deps", "--no-fund", "--no-audit", pkg],
                    cwd=str(project_path), capture_output=True, text=True, timeout=120,
                )

    if to_install_dev:
        subprocess.run(
            ["npm", "install", "--save-dev", "--prefer-offline",
             "--legacy-peer-deps", "--no-fund", "--no-audit"] + to_install_dev,
            cwd=str(project_path), capture_output=True, text=True, timeout=180,
        )

    return True
