"""
Infra Generator — gera infraestrutura completa de ponta a ponta.

Antes de gerar qualquer arquivo:
  1. Lê contexto do projeto (stack, DB, cache, portas, env vars)
  2. Pesquisa na web: versões de imagens Docker, boas práticas, configs
  3. Salva o que aprendeu na knowledge base global
  4. Gera arquivos com dados reais (não hallucina versões)

Gera:
  Dockerfile (multi-stage, produção)
  .dockerignore
  docker-compose.yml (stack completa)
  docker-compose.dev.yml (apenas infra local)
  nginx/nginx.conf (proxy reverso)
  nginx/Dockerfile
  .github/workflows/ci.yml
  scripts/entrypoint.sh
  scripts/wait-for-db.sh
  Makefile (se não existe)
"""

import json
from pathlib import Path
from rich.console import Console
from rich.rule import Rule
from rich.progress import Progress, SpinnerColumn, TextColumn

from tools.knowledge_base import InfraContext, get_global_kb
from tools.web_research import web_search, npm_version, pypi_version, maven_version

console = Console()


# ─── Pesquisa autônoma de versões Docker ──────────────────────────────────────

def _fetch_docker_image(service: str, kb) -> str:
    """Busca a versão mais recente de uma imagem Docker (com cache KB)."""
    cached = kb.get_docker_image(service)
    if cached:
        return f"{cached['image']}:{cached['version']}"

    # Mapeamento de serviço → imagem base
    IMAGE_MAP = {
        "postgres":   ("postgres",    "16-alpine"),
        "mysql":      ("mysql",       "8.0"),
        "mongodb":    ("mongo",       "7.0"),
        "redis":      ("redis",       "7-alpine"),
        "rabbitmq":   ("rabbitmq",    "3-management-alpine"),
        "kafka":      ("bitnami/kafka","latest"),
        "nginx":      ("nginx",       "alpine"),
        "node20":     ("node",        "20-alpine"),
        "node22":     ("node",        "22-alpine"),
        "python312":  ("python",      "3.12-slim"),
        "openjdk21":  ("eclipse-temurin", "21-jre-alpine"),
        "dotnet8":    ("mcr.microsoft.com/dotnet/aspnet", "8.0"),
        "dotnet8sdk": ("mcr.microsoft.com/dotnet/sdk", "8.0"),
    }

    base_image, default_tag = IMAGE_MAP.get(service, ("unknown", "latest"))

    # Tenta buscar tag mais recente via Docker Hub API
    try:
        import requests
        if not base_image.startswith("mcr."):
            r = requests.get(
                f"https://hub.docker.com/v2/repositories/library/{base_image.split('/')[-1]}/tags",
                params={"page_size": 20, "ordering": "last_updated"},
                timeout=6,
            )
            if r.ok:
                tags = [t["name"] for t in r.json().get("results", [])]
                # Prefere tags com "alpine" ou versão específica
                preferred = [t for t in tags if "alpine" in t and not "rc" in t and not "beta" in t]
                if preferred:
                    tag = preferred[0]
                    kb.set_docker_image(service, base_image, tag)
                    return f"{base_image}:{tag}"
    except Exception:
        pass

    kb.set_docker_image(service, base_image, default_tag)
    return f"{base_image}:{default_tag}"


def _research_infra(ctx: InfraContext, kb) -> dict:
    """
    Pesquisa autônoma na web antes de gerar infra.
    Retorna dict com dados pesquisados.
    """
    console.print("[dim]🔍 Pesquisando versões e boas práticas na web...[/dim]")
    data = {}

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console, transient=True) as p:
        t = p.add_task("Buscando imagens Docker...", total=None)

        # Imagens dos serviços necessários (usa db_strategy para identificar imagem correta)
        try:
            from tools.db_strategy import get_strategy
            db_strategy = get_strategy(ctx.database or "postgres")
            if db_strategy.docker_image:
                data["service_images"][ctx.database or "postgres"] = db_strategy.docker_image
        except Exception:
            pass
        services_needed = [ctx.database or "postgres"] if ctx.database not in ("sqlite", "") else []
        if ctx.cache == "redis":   services_needed.append("redis")
        if ctx.queue == "rabbitmq": services_needed.append("rabbitmq")
        if ctx.queue == "kafka":   services_needed.append("kafka")

        data["service_images"] = {}
        for svc in services_needed:
            img = _fetch_docker_image(svc, kb)
            data["service_images"][svc] = img
            p.update(t, description=f"  {svc}: {img}")

        # Imagem do app
        p.update(t, description="Buscando imagem do runtime...")
        if ctx.stack in ("nestjs", "nextjs", "angular"):
            node_img = _fetch_docker_image("node20", kb)
            data["app_base_image"] = node_img
            data["app_build_image"] = node_img
        elif ctx.stack == "spring-boot":
            data["app_base_image"]  = _fetch_docker_image("openjdk21", kb)
            data["app_build_image"] = "maven:3.9-eclipse-temurin-21-alpine"
        elif ctx.stack == "python":
            data["app_base_image"]  = _fetch_docker_image("python312", kb)
            data["app_build_image"] = _fetch_docker_image("python312", kb)
        elif ctx.stack == "dotnet":
            data["app_base_image"]  = _fetch_docker_image("dotnet8", kb)
            data["app_build_image"] = _fetch_docker_image("dotnet8sdk", kb)

        # Boas práticas Docker para a stack
        topic_key = f"dockerfile_{ctx.stack}"
        practice = kb.get_best_practice(topic_key)
        if not practice:
            p.update(t, description=f"Buscando boas práticas Dockerfile {ctx.stack}...")
            results = web_search(f"dockerfile {ctx.stack} production multi-stage best practices 2025", max_results=3)
            if results:
                practice = " | ".join(r.get("body", "")[:200] for r in results[:2])
                kb.set_best_practice(topic_key, practice)
        data["dockerfile_tips"] = practice or ""

    console.print(
        f"  [green]✓[/green] Imagens: {', '.join(data['service_images'].values())}"
        + (f" + {data.get('app_base_image','')}" if data.get("app_base_image") else "")
    )
    return data


# ─── Geradores de arquivo por tipo ────────────────────────────────────────────

def _gen_dockerfile(ctx: InfraContext, research: dict) -> str:
    base  = research.get("app_base_image",  "node:20-alpine")
    build = research.get("app_build_image", base)

    if ctx.stack == "nestjs":
        return f"""# Build stage
FROM {build} AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production && npm cache clean --force
COPY . .
RUN npm run build

# Production stage
FROM {base} AS production
WORKDIR /app
RUN addgroup -g 1001 -S nodejs && adduser -S nestjs -u 1001
COPY --from=builder --chown=nestjs:nodejs /app/dist ./dist
COPY --from=builder --chown=nestjs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nestjs:nodejs /app/package.json ./
USER nestjs
EXPOSE {ctx.app_port}
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \\
  CMD node -e "require('http').get('http://localhost:{ctx.app_port}/health', r => process.exit(r.statusCode === 200 ? 0 : 1)).on('error', () => process.exit(1))"
CMD ["node", "dist/main"]
"""

    elif ctx.stack == "nextjs":
        return f"""FROM {build} AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM {build} AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM {base} AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE {ctx.app_port}
ENV PORT={ctx.app_port}
HEALTHCHECK --interval=30s --timeout=10s CMD wget -qO- http://localhost:{ctx.app_port}/api/health || exit 1
CMD ["node", "server.js"]
"""

    elif ctx.stack == "spring-boot":
        return f"""# Build stage
FROM {build} AS builder
WORKDIR /app
COPY pom.xml .
COPY .mvn .mvn
COPY mvnw .
RUN chmod +x mvnw && ./mvnw dependency:go-offline -q
COPY src ./src
RUN ./mvnw package -DskipTests -q

# Production stage
FROM {base}
WORKDIR /app
RUN addgroup --system spring && adduser --system spring --ingroup spring
COPY --from=builder /app/target/*.jar app.jar
USER spring
EXPOSE {ctx.app_port}
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \\
  CMD wget -qO- http://localhost:{ctx.app_port}/actuator/health || exit 1
ENTRYPOINT ["java", "-XX:+UseContainerSupport", "-XX:MaxRAMPercentage=75.0", "-jar", "app.jar"]
"""

    elif ctx.stack == "python":
        return f"""FROM {build}
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN addgroup --system app && adduser --system --group app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chown -R app:app /app
USER app
EXPOSE {ctx.app_port}
HEALTHCHECK --interval=30s --timeout=10s CMD python -c "import httpx; httpx.get('http://localhost:{ctx.app_port}/health').raise_for_status()"
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "{ctx.app_port}", "--workers", "2"]
"""

    elif ctx.stack == "dotnet":
        return f"""FROM {build} AS build
WORKDIR /src
COPY *.sln .
COPY **/*.csproj ./
RUN dotnet restore
COPY . .
RUN dotnet publish -c Release -o /app/publish --no-restore

FROM {base} AS final
WORKDIR /app
RUN adduser --disabled-password --gecos '' appuser
COPY --from=build /app/publish .
USER appuser
EXPOSE {ctx.app_port}
HEALTHCHECK --interval=30s --timeout=10s CMD curl -f http://localhost:{ctx.app_port}/health || exit 1
ENTRYPOINT ["dotnet", "{ctx.app_name}.Api.dll"]
"""
    return f"FROM {base}\nEXPOSE {ctx.app_port}\n"


def _gen_dockerignore(ctx: InfraContext) -> str:
    base = """.git
.gitignore
.devai
README.md
*.md
.env
.env.*
!.env.example
"""
    if ctx.stack in ("nestjs", "nextjs", "angular"):
        base += "node_modules\ndist\nbuild\n.next\ncoverage\n*.spec.ts\n"
    elif ctx.stack == "spring-boot":
        base += "target\n.mvn/repository\n*.iml\n.idea\n"
    elif ctx.stack == "python":
        base += ".venv\nvenv\n__pycache__\n*.pyc\n.pytest_cache\nhtmlcov\n"
    elif ctx.stack == "dotnet":
        base += "bin\nobj\n*.user\n.vs\n"
    return base


def _gen_compose_full(ctx: InfraContext, research: dict) -> str:
    """
    docker-compose.yml gerado dinamicamente — SOMENTE o que foi pedido.
    Não inclui Redis/Kafka/Bull/WebSocket automaticamente.
    O padrão do projeto de referência é usado apenas quando esses serviços
    são explicitamente solicitados.
    """
    from tools.db_strategy import get_strategy, docker_service_for_db
    name = ctx.app_name
    port = ctx.app_port or 3000

    # Env vars do app
    env_vars = _stack_env_vars(ctx)
    env_lines = "\n".join(f"      {k}: {v}" for k, v in env_vars.items())

    # Serviços de infraestrutura (só o que existe em ctx)
    infra_services = ""

    # Banco de dados principal
    db_strat = get_strategy(ctx.database or "postgres")
    db_svc = docker_service_for_db(db_strat, name)
    if db_svc:
        infra_services += db_svc.replace("{name}", ctx.db_name or name)

    # Redis — somente se pedido
    if ctx.cache == "redis":
        redis_img = research.get("service_images", {}).get("redis", "redis:7-alpine")
        infra_services += f"""
  redis:
    image: {redis_img}
    container_name: {name}-redis
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
    restart: unless-stopped
"""

    # RabbitMQ — somente se pedido
    if ctx.queue == "rabbitmq":
        infra_services += f"""
  rabbitmq:
    image: rabbitmq:3-management-alpine
    container_name: {name}-rabbitmq
    ports:
      - "5672:5672"
      - "15672:15672"
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "ping"]
      interval: 30s
    restart: unless-stopped
"""

    # Kafka — somente se pedido
    if ctx.queue == "kafka":
        infra_services += """
  zookeeper:
    image: wurstmeister/zookeeper:latest
    container_name: {name}-zookeeper
    ports:
      - "2181:2181"
    restart: unless-stopped

  kafka:
    image: wurstmeister/kafka:latest
    container_name: {name}-kafka
    environment:
      KAFKA_ADVERTISED_LISTENERS: INSIDE://kafka:9093
      KAFKA_LISTENERS: INSIDE://kafka:9093
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: INSIDE:PLAINTEXT
      KAFKA_INTER_BROKER_LISTENER_NAME: INSIDE
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: 'true'
    ports:
      - "9093:9093"
    depends_on:
      - zookeeper
    restart: unless-stopped
""".replace("{name}", name)

    # Redis Sentinel — somente se pedido explicitamente
    if getattr(ctx, "redis_sentinel", False):
        infra_services += _redis_sentinel_services(name)

    # Dependências do app
    db_svc_name = "db" if db_strat.docker_image else ""
    depends = [db_svc_name] if db_svc_name else []
    if ctx.cache == "redis":   depends.append("redis")
    if ctx.queue == "kafka":   depends.extend(["kafka", "zookeeper"])
    if ctx.queue == "rabbitmq": depends.append("rabbitmq")

    depends_str = ""
    if depends:
        depends_str = "    depends_on:\n"
        for d in depends:
            depends_str += f"      - {d}\n"

    volumes = "  db-data:"
    if ctx.cache == "redis":
        volumes += "\n  redis-data:"

    return f"""version: '3.9'

services:
  app:
    build: .
    container_name: {name}-app
    ports:
      - "{port}:{port}"
    environment:
      PORT: {port}
{env_lines}
{depends_str}    restart: unless-stopped
    networks:
      - {name}-net

{infra_services}
volumes:
{volumes}

networks:
  {name}-net:
    driver: bridge
"""


def _gen_compose_dev(ctx: InfraContext, research: dict) -> str:
    """
    docker-compose.dev.yml — SOMENTE o que foi pedido.
    Para desenvolvimento local: infra sobe no docker, app roda no host com hot-reload.
    Nunca adiciona Redis/Kafka/Sentinel se não foram solicitados.
    """
    from tools.db_strategy import get_strategy, docker_service_for_db
    name = ctx.app_name

    # Banco de dados principal
    db_strat = get_strategy(ctx.database or "postgres")
    services = ""

    if db_strat.docker_image:
        db_svc = docker_service_for_db(db_strat, name)
        if db_svc:
            # Para dev: nome do container com sufixo -dev
            db_svc = (db_svc
                .replace(f"{name}-mongo",    f"{name}-mongo-dev")
                .replace(f"{name}-postgres", f"{name}-postgres-dev")
                .replace(f"{name}-mysql",    f"{name}-mysql-dev")
                .replace("{name}", ctx.db_name or name))
            services += db_svc

    # Redis simples — só se pedido (SEM sentinel no dev)
    if ctx.cache == "redis":
        services += f"""
  redis:
    image: redis:7-alpine
    container_name: {name}-redis-dev
    command: redis-server --appendonly yes
    ports:
      - "6379:6379"
    networks:
      - {name}-dev
"""

    # Kafka — só se pedido
    if ctx.queue == "kafka":
        services += f"""
  zookeeper:
    image: wurstmeister/zookeeper:latest
    container_name: {name}-zookeeper-dev
    ports:
      - "2181:2181"
    networks:
      - {name}-dev

  kafka:
    image: wurstmeister/kafka:latest
    container_name: {name}-kafka-dev
    environment:
      KAFKA_ADVERTISED_LISTENERS: INSIDE://localhost:9093
      KAFKA_LISTENERS: INSIDE://kafka:9093
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: INSIDE:PLAINTEXT
      KAFKA_INTER_BROKER_LISTENER_NAME: INSIDE
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
    ports:
      - "9093:9093"
    depends_on:
      - zookeeper
    networks:
      - {name}-dev
"""

    # RabbitMQ — só se pedido
    if ctx.queue == "rabbitmq":
        services += f"""
  rabbitmq:
    image: rabbitmq:3-management-alpine
    container_name: {name}-rabbitmq-dev
    ports:
      - "5672:5672"
      - "15672:15672"
    networks:
      - {name}-dev
"""

    networks = f"""
networks:
  {name}-dev:
    driver: bridge
"""

    comment = "# Dev: só infra. App roda no host com hot-reload (npm run start:dev)"
    return f"""version: '3.9'
{comment}
services:
{services}
{networks}"""


def _redis_sentinel_services(name: str) -> str:
    """Gera serviços Redis Sentinel completos (master + slave + 3 sentinels)."""
    return f"""
  redis-master:
    image: redis:7-alpine
    container_name: {name}-redis-master
    command: ["redis-server", "--requirepass", "redis_pass"]
    networks:
      redis-net:
        ipv4_address: 172.30.0.3
    restart: unless-stopped

  redis-slave:
    image: redis:7-alpine
    container_name: {name}-redis-slave
    command: ["redis-server", "/usr/local/etc/redis/redis-slave.conf"]
    depends_on: [redis-master]
    volumes:
      - ./redis/redis-slave.conf:/usr/local/etc/redis/redis-slave.conf
    networks:
      redis-net:
        ipv4_address: 172.30.0.4
    restart: unless-stopped

  redis-sentinel-1:
    image: redis:7
    container_name: {name}-sentinel-1
    command: ["redis-sentinel", "/etc/redis/sentinel.conf"]
    volumes:
      - ./redis/sentinel.conf:/etc/redis/sentinel.conf
    ports: ["26379:26379"]
    networks:
      redis-net:
        ipv4_address: 172.30.0.5
    depends_on: [redis-master]
    restart: unless-stopped
"""


def _stack_env_vars_full(ctx: InfraContext) -> dict:
    """Env vars do stack para o docker-compose."""
    from tools.db_strategy import get_strategy
    db_strat = get_strategy(ctx.database or "mongodb")
    base = {}
    if db_strat.is_nosql:
        pass  # MongoDB URI já está no template
    elif ctx.database == "postgres":
        base["DB_HOST"] = "db"
        base["DB_PORT"] = str(db_strat.docker_port or 5432)
        base["DB_NAME"] = ctx.db_name or ctx.app_name
        base["DB_USER"] = "postgres"
        base["DB_PASS"] = "${DB_PASS:-postgres}"
    return base



def _gen_compose_dev(ctx: InfraContext, research: dict) -> str:
    """docker-compose.dev.yml — só infra para desenvolvimento local."""
    from tools.db_strategy import get_strategy
    db_strat = get_strategy(ctx.database or "postgres")
    db_img    = db_strat.docker_image if db_strat.docker_image else "postgres:16-alpine"
    redis_img = research["service_images"].get("redis", "redis:7-alpine")
    rabbit_img = research["service_images"].get("rabbitmq", "rabbitmq:3-management-alpine")
    db_name   = ctx.db_name
    infra_services = _compose_infra_services(ctx, db_img, redis_img, rabbit_img, "bitnami/kafka:latest", db_name)

    return f"""version: '3.9'
# Desenvolvimento local: sobe apenas a infraestrutura.
# O app roda diretamente no host com hot-reload.
services:
{infra_services}
volumes:
  db-data:
{'  redis-data:' if ctx.cache == 'redis' else ''}
"""


def _compose_infra_services(ctx, db_img, redis_img, rabbit_img, kafka_img, db_name) -> str:
    services = ""

    # Use db_strategy to generate the correct DB service block
    try:
        from tools.db_strategy import get_strategy, docker_service_for_db
        strategy = get_strategy(ctx.database or "postgres")
        db_svc = docker_service_for_db(strategy, ctx.app_name)
        if db_svc:
            db_svc = db_svc.replace("{name}", ctx.db_name or ctx.app_name or "app")
            services += db_svc
            # Skip the manual if/elif blocks below if we got a service from strategy
            # Add Redis/RabbitMQ/Kafka below
            if ctx.cache == "redis":
                services += f"""  redis:
    image: {redis_img}
    container_name: {ctx.app_name}-redis
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
    restart: unless-stopped

"""
            if ctx.queue == "rabbitmq":
                services += f"""  rabbitmq:
    image: {rabbit_img}
    container_name: {ctx.app_name}-rabbitmq
    ports:
      - "5672:5672"
      - "15672:15672"
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "ping"]
      interval: 30s
    restart: unless-stopped

"""
            elif ctx.queue == "kafka":
                services += f"""  kafka:
    image: {kafka_img}
    container_name: {ctx.app_name}-kafka
    ports:
      - "9092:9092"
    restart: unless-stopped

"""
            return services
    except Exception as e:
        pass  # fallback to manual blocks below

    if not services and ctx.database == "postgres":
        services += f"""  db:
    image: {db_img}
    container_name: {ctx.app_name}-postgres
    environment:
      POSTGRES_DB: {db_name}
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${{DB_PASS:-postgres}}
    ports:
      - "{ctx.db_port}:5432"
    volumes:
      - db-data:/var/lib/postgresql/data
      - ./scripts/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d {db_name}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

"""
    elif ctx.database == "mysql":
        services += f"""  db:
    image: {db_img}
    container_name: {ctx.app_name}-mysql
    environment:
      MYSQL_DATABASE: {db_name}
      MYSQL_ROOT_PASSWORD: ${{DB_PASS:-root}}
      MYSQL_USER: app
      MYSQL_PASSWORD: ${{DB_PASS:-app}}
    ports:
      - "{ctx.db_port}:3306"
    volumes:
      - db-data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

"""
    elif ctx.database == "mongodb":
        services += f"""  db:
    image: {db_img}
    container_name: {ctx.app_name}-mongo
    ports:
      - "{ctx.db_port}:27017"
    volumes:
      - db-data:/data/db
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

"""

    # Redis
    if ctx.cache == "redis":
        services += f"""  redis:
    image: {redis_img}
    container_name: {ctx.app_name}-redis
    ports:
      - "{ctx.cache_port}:6379"
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

"""

    # RabbitMQ
    if ctx.queue == "rabbitmq":
        services += f"""  queue:
    image: {rabbit_img}
    container_name: {ctx.app_name}-rabbitmq
    environment:
      RABBITMQ_DEFAULT_USER: guest
      RABBITMQ_DEFAULT_PASS: guest
    ports:
      - "{ctx.queue_port}:5672"
      - "15672:15672"
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

"""

    return services


def _stack_env_vars(ctx: InfraContext) -> dict:
    """Env vars do app para o docker-compose — baseado na db_strategy."""
    from tools.db_strategy import get_strategy
    db_strat = get_strategy(ctx.database or "postgres")
    base = {}

    if db_strat.is_nosql:  # MongoDB
        base["MONGODB_URI"] = f"mongodb://db:{db_strat.docker_port}/{ctx.db_name}"
    elif ctx.database == "mysql" or ctx.database == "mariadb":
        base.update({
            "DB_HOST": "db", "DB_PORT": str(db_strat.docker_port),
            "DB_NAME": ctx.db_name, "DB_USER": "root",
            "DB_PASS": "${DB_PASS:-root}",
        })
    elif ctx.database == "sqlite":
        base["DB_PATH"] = f"/app/{ctx.db_name}.db"
    else:  # postgres (default)
        base.update({
            "DB_HOST": "db", "DB_PORT": str(db_strat.docker_port or 5432),
            "DB_NAME": ctx.db_name, "DB_USER": "postgres",
            "DB_PASS": "${DB_PASS:-postgres}",
        })

    if ctx.cache == "redis":
        base["REDIS_URL"] = "redis://redis:6379"
    if ctx.queue == "rabbitmq":
        base["RABBITMQ_URL"] = "amqp://guest:guest@rabbitmq:5672"
    elif ctx.queue == "kafka":
        base["KAFKA_BROKERS"] = "kafka:9092"

    stack_specific = {
        "nestjs": {
            "NODE_ENV": "production",
            "PORT": str(ctx.app_port),
            "JWT_SECRET": "${JWT_SECRET:-change-me}",
        },
        "nextjs": {
            "NODE_ENV": "production",
            "PORT": str(ctx.app_port),
            "NEXTAUTH_URL": f"http://localhost:{ctx.app_port}",
            "NEXTAUTH_SECRET": "${NEXTAUTH_SECRET:-change-me}",
        },
        "spring-boot": {
            "SPRING_DATASOURCE_URL": f"jdbc:postgresql://db:{ctx.db_port}/{ctx.db_name}",
            "SPRING_DATASOURCE_USERNAME": "postgres",
            "SPRING_DATASOURCE_PASSWORD": "${DB_PASS:-postgres}",
            "SERVER_PORT": str(ctx.app_port),
            "SPRING_PROFILES_ACTIVE": "prod",
        },
        "python": {
            "DATABASE_URL": f"postgresql+asyncpg://postgres:${{DB_PASS:-postgres}}@db:{ctx.db_port}/{ctx.db_name}",
            "SECRET_KEY": "${SECRET_KEY:-change-me}",
            "APP_ENV": "production",
        },
        "dotnet": {
            "ASPNETCORE_ENVIRONMENT": "Production",
            "ASPNETCORE_URLS": f"http://+:{ctx.app_port}",
            f"ConnectionStrings__Default": f"Host=db;Port={ctx.db_port};Database={ctx.db_name};Username=postgres;Password=${{DB_PASS:-postgres}}",
        },
    }

    base.update(stack_specific.get(ctx.stack, {}))
    return base


def _gen_nginx_conf(ctx: InfraContext) -> str:
    return f"""events {{ worker_connections 1024; }}

http {{
    upstream app {{ server app:{ctx.app_port}; }}

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;

    server {{
        listen 80;
        server_name _;

        # Security headers
        add_header X-Frame-Options DENY;
        add_header X-Content-Type-Options nosniff;
        add_header X-XSS-Protection "1; mode=block";
        add_header Referrer-Policy "strict-origin-when-cross-origin";

        # Gzip
        gzip on;
        gzip_types text/plain application/json application/javascript text/css;
        gzip_min_length 1000;

        # API
        location /api/ {{
            limit_req zone=api burst=20 nodelay;
            proxy_pass         http://app;
            proxy_set_header   Host $host;
            proxy_set_header   X-Real-IP $remote_addr;
            proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header   X-Forwarded-Proto $scheme;
            proxy_read_timeout 30s;
            proxy_connect_timeout 5s;
        }}

        location /auth/login {{
            limit_req zone=login burst=5 nodelay;
            proxy_pass http://app;
        }}

        # Health check
        location /health {{
            proxy_pass http://app;
            access_log off;
        }}

        # Static / SPA
        location / {{
            proxy_pass         http://app;
            proxy_http_version 1.1;
            proxy_set_header   Upgrade $http_upgrade;
            proxy_set_header   Connection 'upgrade';
            proxy_cache_bypass $http_upgrade;
        }}
    }}
}}
"""


def _gen_nginx_dockerfile() -> str:
    return """FROM nginx:alpine
COPY nginx.conf /etc/nginx/nginx.conf
RUN nginx -t
EXPOSE 80
"""


def _gen_github_ci(ctx: InfraContext) -> str:
    test_cmd = {
        "nestjs":      "npm ci && npm test",
        "nextjs":      "npm ci && npm test",
        "spring-boot": "./mvnw test -q",
        "python":      "pip install -r requirements-dev.txt && pytest",
        "dotnet":      "dotnet test",
    }.get(ctx.stack, "echo 'no tests configured'")

    build_cmd = {
        "nestjs":      "npm ci && npm run build",
        "nextjs":      "npm ci && npm run build",
        "spring-boot": "./mvnw package -DskipTests -q",
        "python":      "pip install -r requirements.txt",
        "dotnet":      "dotnet build --configuration Release",
    }.get(ctx.stack, "echo 'no build configured'")

    return f"""name: CI

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: {ctx.db_name}_test
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4

      - name: Setup
        run: {build_cmd}

      - name: Test
        env:
          DB_HOST: localhost
          DB_PORT: 5432
          DB_NAME: {ctx.db_name}_test
          DB_USER: postgres
          DB_PASS: postgres
          NODE_ENV: test
        run: {test_cmd}

  docker:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Build Docker image
        run: docker build -t {ctx.app_name}:${{{{ github.sha }}}} .
      - name: Docker lint
        run: docker run --rm -i hadolint/hadolint < Dockerfile || true
"""


def _gen_makefile(ctx: InfraContext) -> str:
    run_cmd = {
        "nestjs":      "npm run start:dev",
        "nextjs":      "npm run dev",
        "spring-boot": "./mvnw spring-boot:run",
        "python":      "source .venv/bin/activate && uvicorn src.main:app --reload",
        "dotnet":      f"dotnet run --project {ctx.app_name}.Api",
    }.get(ctx.stack, "echo configure")

    test_cmd = {
        "nestjs":      "npm test",
        "nextjs":      "npm test",
        "spring-boot": "./mvnw test",
        "python":      "pytest -v",
        "dotnet":      "dotnet test",
    }.get(ctx.stack, "echo configure")

    return f""".PHONY: help dev test build docker-up docker-dev docker-down logs clean

help: ## Mostra ajuda
\t@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {{FS = ":.*?## "}}; {{printf "\\033[36m%-20s\\033[0m %s\\n", $$1, $$2}}'

dev: ## Roda a aplicação em modo desenvolvimento
\t{run_cmd}

test: ## Roda todos os testes
\t{test_cmd}

test-watch: ## Roda testes em modo watch
\tnpm run test:watch 2>/dev/null || {test_cmd}

build: ## Build de produção
\tdocker build -t {ctx.app_name} .

docker-up: ## Sobe stack completa (app + infra)
\tdocker compose up -d
\t@echo "App:      http://localhost:{ctx.app_port}"
\t@echo "DB:       localhost:{ctx.db_port}"

docker-dev: ## Sobe apenas infra (DB + Redis) para dev local
\tdocker compose -f docker-compose.dev.yml up -d
\t@echo "DB:    localhost:{ctx.db_port}"
{'@echo "Redis: localhost:6379"' if ctx.cache == 'redis' else ''}

docker-down: ## Para todos os containers
\tdocker compose down

docker-rebuild: ## Reconstrói e sobe containers
\tdocker compose up -d --build

logs: ## Mostra logs dos containers
\tdocker compose logs -f

logs-app: ## Mostra logs só do app
\tdocker compose logs -f app

clean: ## Remove containers, volumes e imagens
\tdocker compose down -v --rmi local

shell-db: ## Abre shell no banco de dados
\tdocker compose exec db psql -U postgres -d {ctx.db_name}

migrate: ## Roda migrações
\t@echo "Configure o comando de migração para sua stack"
"""


def _gen_entrypoint(ctx: InfraContext) -> str:
    db_check = ""
    if ctx.database == "postgres":
        db_check = """
echo "Aguardando PostgreSQL..."
until pg_isready -h "${DB_HOST:-db}" -p "${DB_PORT:-5432}" -U "${DB_USER:-postgres}"; do
    echo "  PostgreSQL não disponível. Aguardando..."
    sleep 2
done
echo "PostgreSQL pronto."
"""
    elif ctx.database == "mysql":
        db_check = """
echo "Aguardando MySQL..."
until mysqladmin ping -h "${DB_HOST:-db}" --silent; do
    sleep 2
done
echo "MySQL pronto."
"""

    return f"""#!/bin/sh
set -e

{db_check}
echo "Iniciando {ctx.app_name}..."
exec "$@"
"""


def _gen_init_sql(ctx: InfraContext) -> str:
    return f"""-- Inicialização do banco {ctx.db_name}
-- Este arquivo é executado na primeira inicialização do container PostgreSQL

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- para busca full-text

-- Cria usuário de leitura para monitoring (opcional)
-- CREATE USER readonly WITH PASSWORD 'readonly';
-- GRANT CONNECT ON DATABASE {ctx.db_name} TO readonly;
-- GRANT USAGE ON SCHEMA public TO readonly;

SELECT 'Database {ctx.db_name} initialized' AS status;
"""


# ─── Ponto de entrada principal ───────────────────────────────────────────────

def generate_infra(
    ctx: InfraContext,
    project_path: Path,
    what: list[str] = None,  # None = tudo, ou ["docker", "nginx", "cicd"]
) -> list[dict]:
    """
    Gera infraestrutura completa. Retorna lista de {path, content}.
    """
    kb = get_global_kb()

    # Pesquisa autônoma na web
    research = _research_infra(ctx, kb)

    # Define o que gerar
    generate_all = what is None
    want = set(what or [])

    files = []

    def add(path: str, content: str):
        files.append({"path": path, "content": content})

    if generate_all or "docker" in want:
        from tools.knowledge_templates import (
            DOCKERFILE_NESTJS, ENTRYPOINT_SH, ENTRYPOINT_SH_DEV,
            REDIS_SLAVE_CONF, REDIS_SENTINEL_CONF, TSCONFIG_JSON,
            ENV_EXAMPLE_FULL, DOCKER_COMPOSE_DEV,
        )
        name = ctx.app_name

        # Dockerfile
        if ctx.stack in ("nestjs", "nextjs"):
            add("Dockerfile", DOCKERFILE_NESTJS)
        else:
            add("Dockerfile", _gen_dockerfile(ctx, research))

        add(".dockerignore", _gen_dockerignore(ctx))

        # docker-compose
        try:
            compose_content = _gen_compose_full(ctx, research)
            add("docker-compose.yml", compose_content)
        except Exception as e:
            console.print(f"[red]✗ docker-compose.yml: {e}[/red]")
            import traceback; traceback.print_exc()

        add("docker-compose.dev.yml", _gen_compose_dev(ctx, research))

        # Entrypoint scripts
        add(".docker/entrypoint.sh",      ENTRYPOINT_SH)
        add(".docker/entrypoint.dev.sh",  ENTRYPOINT_SH_DEV)

        # Redis Sentinel config files — só se sentinel pedido explicitamente
        if getattr(ctx, "redis_sentinel", False) or ctx.cache == "redis_sentinel":
            add("redis/redis-slave.conf",  REDIS_SLAVE_CONF)
            add("redis/sentinel.conf",     REDIS_SENTINEL_CONF)

        # Scripts SQL só para postgres
        if ctx.database == "postgres":
            add("scripts/init.sql", _gen_init_sql(ctx))

        # .env.example — sempre regenera com as vars corretas do banco detectado
        # (step_shared_files cria uma versão preliminar; aqui corrigimos com o banco real)
        add(".env.example", _gen_env_example(ctx, name))

        # Configs NestJS — só adiciona o que for necessário
        if ctx.stack == "nestjs":
            from tools.knowledge_templates import CONFIG_SERVICE_TS
            cfg_svc = project_path / "src" / "configs" / "config.service.ts"
            if not cfg_svc.exists():
                add("src/configs/config.service.ts", CONFIG_SERVICE_TS)

            # redis.sentinels.config.ts — só se redis sentinel pedido
            if getattr(ctx, "redis_sentinel", False):
                from tools.knowledge_templates import REDIS_SENTINELS_CONFIG_TS
                add("src/configs/redis.sentinels.config.ts", REDIS_SENTINELS_CONFIG_TS)
    return files


def _gen_env_example(ctx: InfraContext, name: str) -> str:
    """Gera .env.example com apenas as variáveis necessárias para o projeto."""
    from tools.db_strategy import get_strategy
    db_strat = get_strategy(ctx.database or "postgres")
    lines = [
        f"# {name} — environment variables",
        f"PORT={ctx.app_port or 3000}",
        f"NODE_ENV=development",
        "",
    ]
    # Banco
    if db_strat.is_nosql:
        lines += [
            "# MongoDB",
            f"MONGODB_URI=mongodb://localhost:{db_strat.docker_port or 27017}/{name.replace('-','_')}",
        ]
    elif ctx.database == "postgres":
        lines += [
            "# PostgreSQL",
            "DB_HOST=localhost", "DB_PORT=5432",
            f"DB_NAME={name.replace('-','_')}",
            "DB_USER=postgres", "DB_PASS=postgres",
        ]
    elif ctx.database in ("mysql", "mariadb"):
        lines += [
            f"# {ctx.database.upper()}",
            "DB_HOST=localhost", f"DB_PORT={db_strat.docker_port or 3306}",
            f"DB_NAME={name.replace('-','_')}",
            "DB_USER=root", "DB_PASS=root",
        ]
    lines.append("")
    # Auth
    lines += ["# Auth", "JWT_SECRET=change-me-in-production", "JWT_EXPIRES_IN=7d", ""]
    # Redis (só se pedido)
    if ctx.cache == "redis":
        lines += ["# Redis", "REDIS_URL=redis://localhost:6379", ""]
    # Kafka (só se pedido)
    if ctx.queue == "kafka":
        lines += [
            "# Kafka",
            "KAFKA_BROKER=localhost:9093",
            f"KAFKA_GROUP_ID={name}-group",
            "",
        ]
    # RabbitMQ (só se pedido)
    if ctx.queue == "rabbitmq":
        lines += ["# RabbitMQ", "RABBITMQ_URL=amqp://guest:guest@localhost:5672", ""]

    return "\n".join(lines) + "\n"


    if generate_all or "nginx" in want:
        add("nginx/nginx.conf",         _gen_nginx_conf(ctx))
        add("nginx/Dockerfile",         _gen_nginx_dockerfile())

    if generate_all or "cicd" in want:
        add(".github/workflows/ci.yml", _gen_github_ci(ctx))

    # Makefile só se não existe
    if (generate_all or "make" in want) and not (project_path / "Makefile").exists():
        add("Makefile", _gen_makefile(ctx))

    return files
