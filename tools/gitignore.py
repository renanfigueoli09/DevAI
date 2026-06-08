"""
Gera .gitignore adequado para cada stack.
"""

from pathlib import Path

_BASE = """# OS
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
Thumbs.db
desktop.ini

# Editors
.idea/
.vscode/
*.swp
*.swo
*~
.project
.classpath
.settings/
*.code-workspace

# DevAI (não versionar contexto local)
.devai/
"""

_NODE = """
# Node
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
pnpm-debug.log*
.pnpm-store/
package-lock.json
yarn.lock
pnpm-lock.yaml

# Build
dist/
build/
.cache/
out/
"""

_TS = """
# TypeScript
*.tsbuildinfo
tsconfig.tsbuildinfo
"""

_ENV = """
# Environment
.env
.env.*
!.env.example
!.env.test
"""

GITIGNORES: dict[str, str] = {

    "nestjs": _BASE + _NODE + _TS + _ENV + """
# NestJS
/dist
/coverage
/test-results
""",

    "nextjs": _BASE + _NODE + _TS + _ENV + """
# Next.js
/.next/
/out/
/coverage/
next-env.d.ts
.vercel
""",

    "angular": _BASE + _NODE + _TS + _ENV + """
# Angular
/dist/
/tmp/
/out-tsc/
/coverage/
.angular/
""",

    "spring-boot": _BASE + _ENV + """
# Java / Maven / Gradle
target/
.gradle/
build/
!gradle/wrapper/gradle-wrapper.jar
*.class
*.war
*.ear
*.jar
!**/src/main/**/build/
!**/src/test/**/build/
hs_err_pid*
replay_pid*

# Spring Boot
application-local.yml
application-local.properties

# Lombok
lombok.config
""",

    "python": _BASE + _ENV + """
# Python
__pycache__/
*.py[cod]
*$py.class
*.pyo
*.pyd
*.so
*.egg
*.egg-info/
dist/
build/
.eggs/
lib/
lib64/
sdist/
wheels/
*.spec

# Virtual env
.venv/
venv/
ENV/
env/

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/
.mypy_cache/
.ruff_cache/

# Alembic
alembic/versions/*.pyc
""",

    "dotnet": _BASE + _ENV + """
# .NET
bin/
obj/
*.user
*.suo
*.userprefs
.vs/
*.nupkg
*.snupkg
**/Properties/launchSettings.json
appsettings.Development.json
appsettings.Local.json
TestResults/
coverage/
""",
}


def write_gitignore(stack: str, project_path: Path) -> None:
    """Escreve o .gitignore correto para a stack no diretório do projeto."""
    content = GITIGNORES.get(stack, _BASE + _ENV)
    target = project_path / ".gitignore"

    if target.exists():
        existing = target.read_text()
        # Adiciona apenas as linhas do DevAI se já existe um .gitignore (ex: gerado pelo nest new)
        if ".devai" not in existing:
            target.write_text(existing + "\n# DevAI\n.devai/\n")
        return

    target.write_text(content)


def write_env_example(
    stack: str, project_path: Path, name: str,
    db_type: str = "postgres",
    has_auth: bool = False,
    extra_services: list | None = None,
) -> None:
    """Escreve um .env.example com variáveis corretas para o banco pedido."""
    from tools.db_strategy import get_strategy
    db_strat = get_strategy(db_type)
    db_name = name.replace("-", "_")

    if db_strat.is_nosql:  # MongoDB
        db_section = f"""
# MongoDB
MONGODB_URI=mongodb://localhost:{db_strat.docker_port}/{db_name}
MONGODB_DB={db_name}
"""
    elif db_type in ("mysql", "mariadb"):
        db_section = f"""
# Database (MySQL/MariaDB)
DB_HOST=localhost
DB_PORT={db_strat.docker_port}
DB_NAME={db_name}
DB_USER=root
DB_PASS=root
"""
    elif db_type == "sqlite":
        db_section = f"""
# Database (SQLite)
DB_PATH=./{db_name}.db
"""
    else:  # postgres (default)
        db_section = f"""
# Database (PostgreSQL)
DB_HOST=localhost
DB_PORT=5432
DB_NAME={db_name}
DB_USER=postgres
DB_PASS=postgres
"""

    auth_section = """
# Auth
JWT_SECRET=change-me-in-production
JWT_EXPIRES_IN=7d
""" if has_auth else ""

    redis_section = ""
    if extra_services:
        has_sentinel = any(s in str(extra_services).lower() for s in ["sentinel","redis-sentinel"])
        has_redis    = any(s in str(extra_services).lower() for s in ["redis"])
        if has_sentinel:
            redis_section = f"""
# Redis Sentinel
REDIS_SENTINEL_HOSTS=localhost:26379,localhost:26380,localhost:26381
REDIS_SENTINEL_NAME=mymaster
REDIS_PASS=redis_pass
"""
        elif has_redis:
            redis_section = """
# Redis
REDIS_URL=redis://localhost:6379
"""

    kafka_section = ""
    if extra_services and "kafka" in extra_services:
        kafka_section = f"""
# Kafka
KAFKA_BROKER=localhost:9093
KAFKA_GROUP_ID={name.replace("-", "_")}-group
"""

    common = f"""# {name}
PORT=3000
NODE_ENV=development
{db_section}{auth_section}{redis_section}{kafka_section}"""

    extras = {
        "nestjs":      "",   # NODE_ENV already in common
        "nextjs":      "NEXTAUTH_SECRET=change-me\nNEXTAUTH_URL=http://localhost:3000\n",
        "angular":     "API_URL=http://localhost:3000\n",
        "spring-boot": (
            "SPRING_PROFILES_ACTIVE=dev\n"
            "SPRING_DATASOURCE_URL=jdbc:postgresql://localhost:5432/"
            f"{name.replace('-','_')}\n"
            "SPRING_DATASOURCE_USERNAME=postgres\n"
            "SPRING_DATASOURCE_PASSWORD=postgres\n"
        ),
        "python":      (
            f"DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/{name.replace('-','_')}\n"
            "SECRET_KEY=change-me\n"
            "ALGORITHM=HS256\n"
        ),
        "dotnet":      (
            f'ConnectionStrings__Default=Host=localhost;Database={name.replace("-","_")};Username=postgres;Password=postgres\n'
        ),
    }

    content = common + extras.get(stack, "")
    env_example = project_path / ".env.example"
    if not env_example.exists():
        env_example.write_text(content)
