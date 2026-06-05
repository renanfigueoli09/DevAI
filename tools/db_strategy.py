"""
Database Strategy — centraliza tudo sobre banco de dados.

Para cada banco detectado na descrição, define:
  - ORM/ODM correto (TypeORM, Mongoose, Prisma, SQLAlchemy, EF Core)
  - Pacotes npm/pip/maven a instalar
  - Imagem Docker com healthcheck
  - Variáveis de ambiente
  - Padrão de arquivo (entity vs schema vs model vs document)

Bancos suportados:
  SQL  → PostgreSQL, MySQL, SQLite, MariaDB → TypeORM (NestJS/Spring)
  NoSQL → MongoDB → Mongoose (NestJS) / Motor (Python)
  Cache → Redis → ioredis / redis-py (não é "banco" principal)
  Multi → Prisma suporta qualquer SQL + MongoDB
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DbStrategy:
    db_type:       str             # postgres | mysql | mongodb | sqlite | mariadb
    orm:           str             # typeorm | mongoose | prisma | sqlalchemy | motor | ef-core
    is_nosql:      bool = False
    docker_image:  str = ""
    docker_port:   int = 0
    npm_packages:  list = field(default_factory=list)
    npm_dev_pkgs:  list = field(default_factory=list)
    pip_packages:  list = field(default_factory=list)
    maven_deps:    list = field(default_factory=list)  # groupId:artifactId:version
    nuget_pkgs:    list = field(default_factory=list)
    env_template:  dict = field(default_factory=dict)  # {VAR: "value with {name} placeholder"}
    file_suffix:   str = "entity"  # entity | schema | model | document


# ─── Definições por banco ──────────────────────────────────────────────────────

STRATEGIES: dict[str, DbStrategy] = {

    "postgres": DbStrategy(
        db_type="postgres", orm="typeorm", is_nosql=False,
        docker_image="postgres:16-alpine", docker_port=5432,
        npm_packages=["@nestjs/typeorm", "typeorm", "pg"],
        npm_dev_pkgs=["@types/pg"],
        pip_packages=["sqlalchemy>=2.0", "asyncpg>=0.29", "alembic>=1.13"],
        maven_deps=["org.springframework.boot:spring-boot-starter-data-jpa",
                    "org.postgresql:postgresql"],
        nuget_pkgs=["Npgsql.EntityFrameworkCore.PostgreSQL"],
        env_template={
            "DB_HOST": "localhost",
            "DB_PORT": "5432",
            "DB_NAME": "{name}",
            "DB_USER": "postgres",
            "DB_PASS": "postgres",
            "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/{name}",
            "SPRING_DATASOURCE_URL": "jdbc:postgresql://localhost:5432/{name}",
            "ConnectionStrings__Default": "Host=localhost;Database={name};Username=postgres;Password=postgres",
        },
        file_suffix="entity",
    ),

    "mysql": DbStrategy(
        db_type="mysql", orm="typeorm", is_nosql=False,
        docker_image="mysql:8.0", docker_port=3306,
        npm_packages=["@nestjs/typeorm", "typeorm", "mysql2"],
        pip_packages=["sqlalchemy>=2.0", "aiomysql>=0.2", "alembic>=1.13"],
        maven_deps=["org.springframework.boot:spring-boot-starter-data-jpa",
                    "com.mysql:mysql-connector-j"],
        nuget_pkgs=["Pomelo.EntityFrameworkCore.MySql"],
        env_template={
            "DB_HOST": "localhost",
            "DB_PORT": "3306",
            "DB_NAME": "{name}",
            "DB_USER": "root",
            "DB_PASS": "root",
            "DATABASE_URL": "mysql+aiomysql://root:root@localhost:3306/{name}",
            "SPRING_DATASOURCE_URL": "jdbc:mysql://localhost:3306/{name}",
        },
        file_suffix="entity",
    ),

    "mongodb": DbStrategy(
        db_type="mongodb", orm="mongoose", is_nosql=True,
        docker_image="mongo:7.0", docker_port=27017,
        npm_packages=["@nestjs/mongoose", "mongoose"],
        npm_dev_pkgs=["@types/mongoose"],
        pip_packages=["motor>=3.3", "beanie>=1.25", "pymongo>=4.6"],
        maven_deps=["org.springframework.boot:spring-boot-starter-data-mongodb"],
        nuget_pkgs=["MongoDB.Driver", "MongoDB.EntityFrameworkCore"],
        env_template={
            "MONGODB_URI": "mongodb://localhost:27017/{name}",
            "MONGODB_DB":  "{name}",
            "SPRING_DATA_MONGODB_URI": "mongodb://localhost:27017/{name}",
        },
        file_suffix="schema",
    ),

    "sqlite": DbStrategy(
        db_type="sqlite", orm="typeorm", is_nosql=False,
        docker_image="",  # sem docker para SQLite
        docker_port=0,
        npm_packages=["@nestjs/typeorm", "typeorm", "better-sqlite3"],
        npm_dev_pkgs=["@types/better-sqlite3"],
        pip_packages=["sqlalchemy>=2.0", "aiosqlite>=0.19"],
        env_template={
            "DB_PATH": "./{name}.db",
            "DATABASE_URL": "sqlite+aiosqlite:///./{name}.db",
        },
        file_suffix="entity",
    ),

    "mariadb": DbStrategy(
        db_type="mariadb", orm="typeorm", is_nosql=False,
        docker_image="mariadb:11", docker_port=3306,
        npm_packages=["@nestjs/typeorm", "typeorm", "mariadb"],
        env_template={
            "DB_HOST": "localhost", "DB_PORT": "3306",
            "DB_NAME": "{name}", "DB_USER": "root", "DB_PASS": "root",
        },
        file_suffix="entity",
    ),
}

# Aliases para detecção de texto livre
DB_ALIASES: dict[str, str] = {
    "postgres":   "postgres", "postgresql": "postgres", "pg":      "postgres",
    "mysql":      "mysql",    "mariadb":    "mariadb",
    "mongodb":    "mongodb",  "mongo":      "mongodb",  "mongoose": "mongodb",
    "nosql":      "mongodb",  "document":   "mongodb",  "atlas":    "mongodb",
    "sqlite":     "sqlite",   "sqlite3":    "sqlite",
    "sqlserver":  "postgres", "mssql":      "postgres",  # fallback
}


# ─── Detecção automática ──────────────────────────────────────────────────────

def detect_database(description: str, default: str = "postgres") -> str:
    """Detecta o banco de dados pedido na descrição. Retorna o db_type."""
    text = description.lower()
    for alias, db_type in DB_ALIASES.items():
        if alias in text:
            return db_type
    return default


def get_strategy(db_type: str) -> DbStrategy:
    """Retorna a estratégia para o banco. Fallback para postgres."""
    return STRATEGIES.get(db_type, STRATEGIES["postgres"])


def strategy_for_description(description: str) -> DbStrategy:
    """Detecta banco e retorna estratégia em uma chamada."""
    db_type = detect_database(description)
    return get_strategy(db_type)


# ─── Docker config por banco ──────────────────────────────────────────────────

def docker_service_for_db(strategy: DbStrategy, name: str) -> str:
    """Gera o bloco YAML do serviço do banco para docker-compose."""
    db = strategy.db_type
    img = strategy.docker_image
    port = strategy.docker_port

    if not img:
        return ""  # SQLite não precisa de serviço

    if db == "postgres":
        return f"""  db:
    image: {img}
    container_name: {name}-postgres
    environment:
      POSTGRES_DB: {name}
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${{DB_PASS:-postgres}}
    ports:
      - "{port}:{port}"
    volumes:
      - db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d {name}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
"""

    if db == "mongodb":
        return f"""  db:
    image: {img}
    container_name: {name}-mongo
    environment:
      MONGO_INITDB_DATABASE: {name}
    ports:
      - "{port}:{port}"
    volumes:
      - db-data:/data/db
    healthcheck:
      test: ["CMD", "mongosh", "--eval", "db.adminCommand('ping')"]
      interval: 15s
      timeout: 10s
      retries: 5
    restart: unless-stopped
"""

    if db in ("mysql", "mariadb"):
        image_name = "MySQL" if db == "mysql" else "MariaDB"
        return f"""  db:
    image: {img}
    container_name: {name}-{db}
    environment:
      MYSQL_DATABASE: {name}
      MYSQL_ROOT_PASSWORD: ${{DB_PASS:-root}}
      MYSQL_USER: app
      MYSQL_PASSWORD: ${{DB_PASS:-root}}
    ports:
      - "{port}:{port}"
    volumes:
      - db-data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "root", "-p${{DB_PASS:-root}}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
"""

    # Genérico
    return f"""  db:
    image: {img}
    container_name: {name}-db
    ports:
      - "{port}:{port}"
    volumes:
      - db-data:/data
    restart: unless-stopped
"""


# ─── App module config por ORM ────────────────────────────────────────────────

def nestjs_db_module_config(strategy: DbStrategy, name: str) -> str:
    """Retorna a config do módulo de banco para o AppModule do NestJS."""
    if strategy.orm == "mongoose":
        return (
            "MongooseModule.forRoot(configService.get('MONGODB_URI', "
            f"'mongodb://localhost:27017/{name}'))"
        )
    elif strategy.orm == "typeorm":
        db_map = {
            "postgres": "postgres",
            "mysql":    "mysql",
            "mariadb":  "mariadb",
            "sqlite":   "better-sqlite3",
        }
        db_type = db_map.get(strategy.db_type, "postgres")
        if strategy.db_type == "sqlite":
            return (
                "TypeOrmModule.forRoot({"
                f"type: '{db_type}', "
                "database: configService.get('DB_PATH', './{name}.db'), "
                "entities: [__dirname + '/**/*.entity.js'], "
                "synchronize: true})"
            )
        return (
            "TypeOrmModule.forRootAsync({useFactory: (c: ConfigService) => ({"
            f"type: '{db_type}', "
            "host: c.get('DB_HOST', 'localhost'), "
            "port: +c.get('DB_PORT', 5432), "
            "database: c.get('DB_NAME'), "
            "username: c.get('DB_USER', 'postgres'), "
            "password: c.get('DB_PASS'), "
            "entities: [__dirname + '/**/*.entity.js'], "
            "synchronize: c.get('NODE_ENV') !== 'production'"
            "}), inject: [ConfigService]})"
        )
    return "// configure database module"


def python_db_config(strategy: DbStrategy, name: str) -> str:
    """Retorna a URL de conexão do Python para cada banco."""
    if strategy.db_type == "mongodb":
        return f"mongodb://localhost:27017/{name}"
    elif strategy.db_type == "mysql":
        return f"mysql+aiomysql://root:root@localhost:3306/{name}"
    elif strategy.db_type == "sqlite":
        return f"sqlite+aiosqlite:///./{name}.db"
    return f"postgresql+asyncpg://postgres:postgres@localhost:5432/{name}"
