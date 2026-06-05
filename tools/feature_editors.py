"""
Feature Editors — edita arquivos EXISTENTES para adicionar features comuns.

Quando o usuário pede features como "configure o swagger", "adicione CORS",
"configure rate limiting", o agente deve editar main.ts, app.module.ts, etc.
Não apenas instalar a lib e criar arquivos novos.

Cada editor:
  1. Detecta se a feature já está instalada
  2. Instala as dependências npm/pip necessárias
  3. Edita os arquivos corretos (main.ts, app.module.ts, etc.)
  4. Mostra o que foi feito
"""

import subprocess
import shutil
from pathlib import Path
from typing import Optional
from rich.console import Console

console = Console()


def _run_npm(args: list[str], cwd: Path) -> bool:
    if not shutil.which("npm"):
        return False
    r = subprocess.run(
        ["npm", "install", "--legacy-peer-deps", "--no-fund", "--no-audit"] + args,
        cwd=str(cwd), capture_output=True, text=True, timeout=180,
    )
    return r.returncode == 0


def _read(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8", errors="ignore")
    return ""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ── Swagger ───────────────────────────────────────────────────────────────────

def add_swagger(project_path: Path, app_name: str = "API") -> bool:
    """Instala @nestjs/swagger e configura no main.ts."""
    main_ts = project_path / "src" / "main.ts"
    content = _read(main_ts)

    if "SwaggerModule" in content:
        console.print("  [dim]Swagger já configurado em main.ts[/dim]")
        return False

    # Instala pacotes
    console.print("  [dim]→ Instalando @nestjs/swagger...[/dim]")
    _run_npm(["--save", "@nestjs/swagger"], project_path)

    # Insere configuração do Swagger no main.ts
    swagger_import = "import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';"
    swagger_setup = f"""
  // Swagger
  const swaggerConfig = new DocumentBuilder()
    .setTitle('{app_name}')
    .setDescription('{app_name} REST API')
    .setVersion('1.0')
    .addBearerAuth()
    .build();
  SwaggerModule.setup('swagger', app, SwaggerModule.createDocument(app, swaggerConfig), {{
    swaggerOptions: {{ persistAuthorization: true }},
  }});
"""

    # Add import
    if swagger_import not in content:
        content = content.replace(
            "import { NestFactory }",
            f"{swagger_import}\nimport {{ NestFactory }}"
        )

    # Add setup before app.listen
    if "app.listen" in content and "SwaggerModule.setup" not in content:
        content = content.replace(
            "  await app.listen",
            swagger_setup + "  await app.listen"
        )

    _write(main_ts, content)
    console.print(f"  [green]✓[/green] Swagger configurado → http://localhost:3000/swagger")
    return True


# ── CORS ─────────────────────────────────────────────────────────────────────

def add_cors(project_path: Path) -> bool:
    """Habilita CORS no main.ts com configuração completa."""
    main_ts = project_path / "src" / "main.ts"
    content = _read(main_ts)

    if "enableCors" in content:
        console.print("  [dim]CORS já habilitado[/dim]")
        return False

    cors_setup = """
  // CORS
  app.enableCors({
    origin: process.env.CORS_ORIGIN?.split(',') || '*',
    methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization'],
    credentials: true,
  });
"""
    if "app.listen" in content:
        content = content.replace("  await app.listen", cors_setup + "  await app.listen")
        _write(main_ts, content)
        console.print("  [green]✓[/green] CORS configurado")
        return True
    return False


# ── Helmet ────────────────────────────────────────────────────────────────────

def add_helmet(project_path: Path) -> bool:
    """Instala helmet e configura no main.ts."""
    main_ts = project_path / "src" / "main.ts"
    content = _read(main_ts)

    if "helmet" in content.lower():
        console.print("  [dim]Helmet já configurado[/dim]")
        return False

    console.print("  [dim]→ Instalando helmet...[/dim]")
    _run_npm(["--save", "helmet"], project_path)

    helmet_import = "import helmet from 'helmet';"
    helmet_setup = "\n  // Security headers\n  app.use(helmet());\n"

    if helmet_import not in content:
        content = content.replace("import { NestFactory }", f"{helmet_import}\nimport {{ NestFactory }}")

    if "app.listen" in content:
        content = content.replace("  await app.listen", helmet_setup + "  await app.listen")
        _write(main_ts, content)
        console.print("  [green]✓[/green] Helmet (security headers) configurado")
        return True
    return False


# ── Rate Limiting ──────────────────────────────────────────────────────────────

def add_rate_limit(project_path: Path) -> bool:
    """Instala @nestjs/throttler e configura no app.module.ts."""
    app_module = project_path / "src" / "app.module.ts"
    content = _read(app_module)

    if "ThrottlerModule" in content:
        console.print("  [dim]Rate limiting já configurado[/dim]")
        return False

    console.print("  [dim]→ Instalando @nestjs/throttler...[/dim]")
    _run_npm(["--save", "@nestjs/throttler"], project_path)

    throttler_import = "import { ThrottlerModule, ThrottlerGuard } from '@nestjs/throttler';\nimport { APP_GUARD } from '@nestjs/core';"
    throttler_module = "ThrottlerModule.forRoot([{ ttl: 60000, limit: 100 }]),"
    throttler_guard = "    { provide: APP_GUARD, useClass: ThrottlerGuard },"

    if throttler_import not in content:
        content = content.replace("import { Module }", f"{throttler_import}\nimport {{ Module }}")

    # Add to imports array
    if "imports: [" in content and "ThrottlerModule" not in content:
        content = content.replace("imports: [", f"imports: [\n    {throttler_module}")

    # Add to providers
    if "providers: [" in content and "APP_GUARD" not in content:
        content = content.replace("providers: [", f"providers: [\n{throttler_guard}")

    _write(app_module, content)
    console.print("  [green]✓[/green] Rate limiting: 100 req/min (configurável via ThrottlerModule)")
    return True


# ── Winston Logging ────────────────────────────────────────────────────────────

def add_winston(project_path: Path, app_name: str = "app") -> bool:
    """Instala nest-winston e configura logging."""
    main_ts = project_path / "src" / "main.ts"
    content = _read(main_ts)

    if "WINSTON_MODULE_NEST_PROVIDER" in content or "WinstonModule" in content:
        console.print("  [dim]Winston já configurado[/dim]")
        return False

    console.print("  [dim]→ Instalando nest-winston, winston...[/dim]")
    _run_npm(["--save", "nest-winston", "winston"], project_path)

    # Create winston config file
    winston_config_dir = project_path / "src" / "configs"
    winston_config_dir.mkdir(exist_ok=True)
    winston_conf = project_path / "src" / "configs" / "winston.config.ts"

    _write(winston_conf, f"""\
import {{ WinstonModuleOptions, utilities }} from 'nest-winston';
import * as winston from 'winston';

const winstonConfig: WinstonModuleOptions = {{
  level: process.env.NODE_ENV === 'production' ? 'info' : 'debug',
  transports: [
    new winston.transports.Console({{
      format: winston.format.combine(
        winston.format.timestamp(),
        winston.format.ms(),
        utilities.format.nestLike('{app_name}', {{
          colors: true,
          prettyPrint: true,
        }}),
      ),
    }}),
  ],
}};

export default winstonConfig;
""")

    # Update app.module.ts
    app_module = project_path / "src" / "app.module.ts"
    mod_content = _read(app_module)
    if "WinstonModule" not in mod_content:
        winston_import = "import { WinstonModule } from 'nest-winston';\nimport winstonConfig from './configs/winston.config';"
        mod_content = mod_content.replace("import { Module }", f"{winston_import}\nimport {{ Module }}")
        if "imports: [" in mod_content:
            mod_content = mod_content.replace("imports: [", "imports: [\n    WinstonModule.forRoot(winstonConfig),")
        _write(app_module, mod_content)

    # Update main.ts
    winston_import_main = "import { WINSTON_MODULE_NEST_PROVIDER } from 'nest-winston';"
    if winston_import_main not in content:
        content = content.replace("import { NestFactory }", f"{winston_import_main}\nimport {{ NestFactory }}")

    winston_use = "\n  // Winston logging\n  app.useLogger(app.get(WINSTON_MODULE_NEST_PROVIDER));\n"
    if "useLogger" not in content and "app.listen" in content:
        content = content.replace("  await app.listen", winston_use + "  await app.listen")

    _write(main_ts, content)
    console.print("  [green]✓[/green] Winston configurado → src/configs/winston.config.ts")
    return True


# ── Prefix Global ────────────────────────────────────────────────────────────

def add_global_prefix(project_path: Path, prefix: str = "api") -> bool:
    """Adiciona setGlobalPrefix ao main.ts."""
    main_ts = project_path / "src" / "main.ts"
    content = _read(main_ts)

    if "setGlobalPrefix" in content:
        console.print("  [dim]Global prefix já configurado[/dim]")
        return False

    prefix_line = f"\n  app.setGlobalPrefix('{prefix}');\n"
    if "app.listen" in content:
        content = content.replace("  await app.listen", prefix_line + "  await app.listen")
        _write(main_ts, content)
        console.print(f"  [green]✓[/green] Global prefix '/{prefix}' configurado")
        return True
    return False


# ── Auto-search when feature not in training ──────────────────────────────────

def search_and_apply_feature(
    feature_description: str,
    project_path: Path,
    llm,
    model: str,
) -> bool:
    """
    Quando o agente não sabe como implementar uma feature,
    pesquisa na web, aprende e aplica.
    """
    console.print(f"  [dim]→ Pesquisando como implementar: {feature_description[:50]}[/dim]")

    from tools.web_research import web_search
    from tools.research_agent import _summarize
    from tools.vector_store import save

    # Monta query de pesquisa
    stack = "NestJS"
    query = f"{stack} {feature_description} implementation example 2025"
    results = web_search(query, max_results=5)

    if not results:
        return False

    summary = _summarize(query, results, llm, model)
    if not summary:
        return False

    # Salva no training store para uso futuro
    key = f"search:feature:{feature_description[:40].replace(' ','_').lower()}"
    save(key, summary, topic="nestjs-features", source="auto_search_feature")
    console.print(f"  [green]✓[/green] Conhecimento salvo: {key}")

    return True


# ── Feature detector ─────────────────────────────────────────────────────────

FEATURE_HANDLERS = {
    "swagger":     add_swagger,
    "openapi":     add_swagger,
    "cors":        add_cors,
    "helmet":      add_helmet,
    "security":    add_helmet,
    "rate limit":  add_rate_limit,
    "rate-limit":  add_rate_limit,
    "throttle":    add_rate_limit,
    "winston":     add_winston,
    "logging":     add_winston,
    "log":         add_winston,
    "prefix":      add_global_prefix,
}


def detect_and_apply_feature_edits(
    description: str,
    project_path: Path,
    app_name: str = "API",
    llm=None,
    model: str = "",
) -> list[str]:
    """
    Detecta features que precisam de edição em arquivos existentes e as aplica.
    Retorna lista de features aplicadas.
    """
    desc = description.lower()
    applied = []

    for keyword, handler in FEATURE_HANDLERS.items():
        if keyword in desc:
            try:
                if handler.__code__.co_varnames[1] == "app_name":
                    changed = handler(project_path, app_name)
                else:
                    changed = handler(project_path)
                if changed:
                    applied.append(keyword)
            except Exception as e:
                console.print(f"  [yellow]⚠ {keyword}: {e}[/yellow]")

    # Se pediu algo que não foi aplicado e temos LLM, pesquisa
    if llm and not applied and any(w in desc for w in [
        "configure", "adicione", "instale", "setup", "habilite"
    ]):
        search_and_apply_feature(description, project_path, llm, model)

    return applied
