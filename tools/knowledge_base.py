"""
Knowledge Base — armazenamento persistente de conhecimento.

Dois níveis:
  Global   → ~/.devai/knowledge.json   (aprendido da web, reutilizável entre projetos)
  Projeto  → .devai/context.json       (contexto específico do projeto)

O sistema salva automaticamente o que aprende via pesquisa web.
Isso compensa a limitação do modelo 7B: o sistema "sabe" coisas que o LLM não sabe.
"""

import json
import time
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional
from rich.console import Console

console = Console()

GLOBAL_KB_FILE = Path.home() / ".devai" / "knowledge.json"


# ─── Estrutura de contexto de projeto ─────────────────────────────────────────

@dataclass
class InfraContext:
    """Tudo que o sistema precisa saber para gerar infra correta."""
    # App
    stack:          str = ""
    app_name:       str = ""
    app_port:       int = 0
    # Banco
    database:       str = ""        # postgres | mysql | sqlite | mongodb
    db_port:        int = 5432
    db_name:        str = ""
    orm:            str = ""        # typeorm | prisma | jpa | sqlalchemy | ef-core
    # Cache
    cache:          str = ""        # redis | memcached | none
    cache_port:     int = 6379
    # Queue
    queue:          str = ""        # rabbitmq | kafka | bullmq | celery | none
    queue_port:     int = 0
    # Env vars encontradas
    env_vars:       list = field(default_factory=list)
    # Pacotes detectados
    packages:       dict = field(default_factory=dict)
    # Infra existente
    has_dockerfile: bool = False
    has_compose:    bool = False
    has_nginx:      bool = False
    has_cicd:       bool = False
    # Versões detectadas
    runtime_version:str = ""        # node 20, java 21, python 3.12, dotnet 8
    # Módulos/features já implementados
    existing_modules: list = field(default_factory=list)

    def to_prompt_context(self) -> str:
        """Serializa para texto compacto para incluir em prompts."""
        lines = []
        if self.stack:           lines.append(f"Stack: {self.stack}")
        if self.app_name:        lines.append(f"App name: {self.app_name}")
        if self.app_port:        lines.append(f"App port: {self.app_port}")
        if self.database:        lines.append(f"Database: {self.database} (port {self.db_port})")
        if self.db_name:         lines.append(f"DB name: {self.db_name}")
        if self.orm:             lines.append(f"ORM: {self.orm}")
        if self.cache:           lines.append(f"Cache: {self.cache} (port {self.cache_port})")
        if self.queue:           lines.append(f"Queue: {self.queue} (port {self.queue_port})")
        if self.runtime_version: lines.append(f"Runtime: {self.runtime_version}")
        if self.env_vars:        lines.append(f"Env vars: {', '.join(self.env_vars[:20])}")
        if self.packages:
            pkgs = [f"{k}@{v}" for k, v in list(self.packages.items())[:10]]
            lines.append(f"Key packages: {', '.join(pkgs)}")
        infra = []
        if self.has_dockerfile:  infra.append("Dockerfile")
        if self.has_compose:     infra.append("docker-compose")
        if self.has_nginx:       infra.append("nginx")
        if self.has_cicd:        infra.append("CI/CD")
        if infra:                lines.append(f"Existing infra: {', '.join(infra)}")
        if self.existing_modules: lines.append(f"Modules: {', '.join(self.existing_modules[:10])}")
        return "\n".join(lines)


# ─── Extração de contexto de infra do projeto ─────────────────────────────────

def extract_infra_context(project_path: Path) -> InfraContext:
    """
    Lê o projeto e extrai tudo relevante para geração de infra.
    Não usa LLM — análise estática de arquivos de configuração.
    """
    ctx = InfraContext(app_name=project_path.name)

    # Detecta stack
    if (project_path / "nest-cli.json").exists():
        ctx.stack = "nestjs"; ctx.app_port = 3000
    elif (project_path / "next.config.js").exists() or (project_path / "next.config.ts").exists():
        ctx.stack = "nextjs"; ctx.app_port = 3000
    elif (project_path / "angular.json").exists():
        ctx.stack = "angular"; ctx.app_port = 4200
    elif (project_path / "pom.xml").exists() or (project_path / "build.gradle").exists():
        ctx.stack = "spring-boot"; ctx.app_port = 8080
    elif (project_path / "requirements.txt").exists() or (project_path / "pyproject.toml").exists():
        ctx.stack = "python"; ctx.app_port = 8000
    elif list(project_path.glob("*.csproj")) or list(project_path.glob("*.sln")):
        ctx.stack = "dotnet"; ctx.app_port = 5000

    # Lê package.json (Node)
    pkg_json = project_path / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            ctx.packages = {k: v for k, v in list(deps.items())[:30]}
            # ORM
            if "typeorm" in deps or "@nestjs/typeorm" in deps:
                ctx.orm = "typeorm"
            elif "prisma" in deps or "@prisma/client" in deps:
                ctx.orm = "prisma"
            elif "mongoose" in deps:
                ctx.orm = "mongoose"; ctx.database = "mongodb"
            elif "sequelize" in deps:
                ctx.orm = "sequelize"
            # Cache
            if "ioredis" in deps or "redis" in deps or "cache-manager-redis" in deps:
                ctx.cache = "redis"
            # Queue
            if "bullmq" in deps or "bull" in deps:
                ctx.queue = "bullmq"
            elif "amqplib" in deps:
                ctx.queue = "rabbitmq"; ctx.queue_port = 5672
        except Exception:
            pass

    # Lê pom.xml (Java)
    pom = project_path / "pom.xml"
    if pom.exists():
        content = pom.read_text()
        ctx.orm = "jpa"
        if "postgresql" in content:     ctx.database = "postgres"
        elif "mysql" in content:        ctx.database = "mysql"; ctx.db_port = 3306
        elif "mongodb" in content:      ctx.database = "mongodb"; ctx.db_port = 27017
        if "spring-data-redis" in content or "lettuce" in content:
            ctx.cache = "redis"
        if "spring-rabbit" in content:  ctx.queue = "rabbitmq"; ctx.queue_port = 5672
        if "kafka" in content:          ctx.queue = "kafka"; ctx.queue_port = 9092
        import re
        java_ver = re.search(r"<java\.version>(\d+)</java\.version>", content)
        if java_ver: ctx.runtime_version = f"java {java_ver.group(1)}"

    # Lê requirements.txt / pyproject.toml (Python)
    req = project_path / "requirements.txt"
    pyp = project_path / "pyproject.toml"
    for cfg_file in [req, pyp]:
        if cfg_file.exists():
            content = cfg_file.read_text().lower()
            ctx.orm = "sqlalchemy"
            if "asyncpg" in content or "psycopg" in content:
                ctx.database = "postgres"
            elif "aiomysql" in content or "mysqlclient" in content:
                ctx.database = "mysql"; ctx.db_port = 3306
            elif "motor" in content or "beanie" in content:
                ctx.database = "mongodb"; ctx.db_port = 27017
            if "redis" in content:      ctx.cache = "redis"
            if "celery" in content:     ctx.queue = "celery"
            if "kafka" in content:      ctx.queue = "kafka"; ctx.queue_port = 9092

    # Detecta .csproj (.NET)
    for csproj in project_path.rglob("*.csproj"):
        try:
            content = csproj.read_text()
            ctx.orm = "ef-core"
            if "Npgsql" in content:  ctx.database = "postgres"
            elif "MySql" in content: ctx.database = "mysql"; ctx.db_port = 3306
            if "StackExchange.Redis" in content: ctx.cache = "redis"
        except Exception:
            pass

    # Fallback DB
    if not ctx.database:
        ctx.database = "postgres"

    ctx.db_name = ctx.app_name.replace("-", "_").lower()

    # Detecta infra existente
    ctx.has_dockerfile = (project_path / "Dockerfile").exists() or bool(list(project_path.glob("**/Dockerfile")))
    ctx.has_compose    = (project_path / "docker-compose.yml").exists() or (project_path / "docker-compose.yaml").exists()
    ctx.has_nginx      = (project_path / "nginx").exists() or bool(list(project_path.glob("**/nginx.conf")))
    ctx.has_cicd       = (project_path / ".github" / "workflows").exists()

    # Env vars existentes
    for env_file in [".env", ".env.example", ".env.dev"]:
        ef = project_path / env_file
        if ef.exists():
            import re
            keys = re.findall(r"^([A-Z_][A-Z0-9_]+)=", ef.read_text(), re.MULTILINE)
            ctx.env_vars.extend(keys)

    # Modules (src/ subfolders)
    src = project_path / "src"
    if src.exists():
        ctx.existing_modules = [
            d.name for d in src.iterdir()
            if d.is_dir() and not d.name.startswith(("_", "."))
            and d.name not in ("common", "config", "database", "core", "shared", "app")
        ]

    # Runtime version (node)
    nvmrc = project_path / ".nvmrc"
    node_ver_file = project_path / ".node-version"
    pkg_engines = ctx.packages.get("engines", {})
    if nvmrc.exists():
        ctx.runtime_version = f"node {nvmrc.read_text().strip()}"
    elif node_ver_file.exists():
        ctx.runtime_version = f"node {node_ver_file.read_text().strip()}"
    elif "node" in str(pkg_engines):
        ctx.runtime_version = f"node {pkg_engines}"

    return ctx


# ─── Knowledge Base Global ─────────────────────────────────────────────────────

class GlobalKnowledge:
    """
    Base de conhecimento global persistente em ~/.devai/knowledge.json.
    Aprende da web e reutiliza entre projetos.
    """

    def __init__(self):
        self._data: dict = self._load()

    def _load(self) -> dict:
        try:
            if GLOBAL_KB_FILE.exists():
                return json.loads(GLOBAL_KB_FILE.read_text())
        except Exception:
            pass
        return {"facts": {}, "docker_images": {}, "best_practices": {}, "updated_at": {}}

    def save(self):
        GLOBAL_KB_FILE.parent.mkdir(parents=True, exist_ok=True)
        GLOBAL_KB_FILE.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))

    def set_fact(self, key: str, value, ttl_hours: int = 168):  # 7 days default
        self._data["facts"][key] = {
            "value": value,
            "expires": time.time() + ttl_hours * 3600,
        }
        self.save()

    def get_fact(self, key: str):
        entry = self._data.get("facts", {}).get(key)
        if entry and time.time() < entry.get("expires", 0):
            return entry["value"]
        return None

    def set_docker_image(self, service: str, image: str, version: str):
        self._data["docker_images"][service] = {
            "image": image, "version": version,
            "updated": time.strftime("%Y-%m-%d"),
        }
        self.save()

    def get_docker_image(self, service: str) -> Optional[dict]:
        return self._data.get("docker_images", {}).get(service)

    def set_best_practice(self, topic: str, content: str):
        self._data["best_practices"][topic] = {
            "content": content,
            "updated": time.strftime("%Y-%m-%d"),
        }
        self.save()

    def get_best_practice(self, topic: str) -> Optional[str]:
        entry = self._data.get("best_practices", {}).get(topic)
        return entry.get("content") if entry else None

    def summary(self) -> str:
        facts = len(self._data.get("facts", {}))
        images = len(self._data.get("docker_images", {}))
        practices = len(self._data.get("best_practices", {}))
        return f"{facts} fatos, {images} imagens Docker, {practices} boas práticas"


# Singleton
_global_kb: Optional[GlobalKnowledge] = None

def get_global_kb() -> GlobalKnowledge:
    global _global_kb
    if _global_kb is None:
        _global_kb = GlobalKnowledge()
    return _global_kb
