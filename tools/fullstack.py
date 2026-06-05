"""
Fullstack — define combinações válidas de backend + frontend
e gera os arquivos compartilhados (docker-compose, Makefile, README, nginx).
"""

from pathlib import Path
from rich.console import Console

console = Console()

# ─── Combinações suportadas ────────────────────────────────────────────────────

COMBOS: dict[str, dict] = {
    "nestjs+nextjs":      {"backend": "nestjs",      "frontend": "nextjs",  "port_back": 3001, "port_front": 3000},
    "nestjs+angular":     {"backend": "nestjs",      "frontend": "angular", "port_back": 3001, "port_front": 4200},
    "spring-boot+nextjs": {"backend": "spring-boot", "frontend": "nextjs",  "port_back": 8080, "port_front": 3000},
    "spring-boot+angular":{"backend": "spring-boot", "frontend": "angular", "port_back": 8080, "port_front": 4200},
    "python+nextjs":      {"backend": "python",      "frontend": "nextjs",  "port_back": 8000, "port_front": 3000},
    "python+angular":     {"backend": "python",      "frontend": "angular", "port_back": 8000, "port_front": 4200},
    "dotnet+nextjs":      {"backend": "dotnet",      "frontend": "nextjs",  "port_back": 5000, "port_front": 3000},
    "dotnet+angular":     {"backend": "dotnet",      "frontend": "angular", "port_back": 5000, "port_front": 4200},
}

ALIASES = {
    "nest+next":    "nestjs+nextjs",
    "nest+angular": "nestjs+angular",
    "spring+next":  "spring-boot+nextjs",
    "spring+ng":    "spring-boot+angular",
    "fastapi+next": "python+nextjs",
    "fastapi+ng":   "python+angular",
    "dotnet+next":  "dotnet+nextjs",
    "dotnet+ng":    "dotnet+angular",
}

def resolve_combo(stack: str) -> tuple[str, dict] | tuple[None, None]:
    """Resolve alias e retorna (combo_key, combo_config) ou (None, None)."""
    key = ALIASES.get(stack, stack)
    cfg = COMBOS.get(key)
    return (key, cfg) if cfg else (None, None)

def is_fullstack(stack: str) -> bool:
    return "+" in stack or stack in ALIASES

# ─── Arquivos compartilhados gerados estaticamente ────────────────────────────

def write_docker_compose(name: str, combo: dict, path: Path):
    backend  = combo["backend"]
    frontend = combo["frontend"]
    pb = combo["port_back"]
    pf = combo["port_front"]

    # Imagem do backend
    back_img = {
        "nestjs":      f"  build:\n    context: ./backend\n  environment:\n    - NODE_ENV=production\n    - DB_HOST=postgres\n    - DB_PORT=5432\n    - DB_NAME={name}\n    - DB_USER=postgres\n    - DB_PASS=postgres\n    - JWT_SECRET=${{JWT_SECRET}}",
        "spring-boot": f"  build:\n    context: ./backend\n  environment:\n    - SPRING_DATASOURCE_URL=jdbc:postgresql://postgres:5432/{name}\n    - SPRING_DATASOURCE_USERNAME=postgres\n    - SPRING_DATASOURCE_PASSWORD=postgres\n    - JWT_SECRET=${{JWT_SECRET}}",
        "python":      f"  build:\n    context: ./backend\n  environment:\n    - DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/{name}\n    - SECRET_KEY=${{JWT_SECRET}}",
        "dotnet":      f"  build:\n    context: ./backend/{name}.Api\n  environment:\n    - ConnectionStrings__Default=Host=postgres;Database={name};Username=postgres;Password=postgres\n    - JwtSettings__Secret=${{JWT_SECRET}}",
    }.get(backend, f"  build:\n    context: ./backend")

    front_env = {
        "nextjs":  f"    - NEXT_PUBLIC_API_URL=http://localhost:{pb}/api/v1",
        "angular": f"    - API_URL=http://localhost:{pb}/api/v1",
    }.get(frontend, "")

    content = f"""version: '3.9'

services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: {name}
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    ports:
      - "6379:6379"

  backend:
{back_img}
    ports:
      - "{pb}:{pb}"
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped

  frontend:
    build:
      context: ./frontend
    ports:
      - "{pf}:{pf}"
    environment:
{front_env}
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  postgres_data:
"""
    (path / "docker-compose.yml").write_text(content)
    (path / "docker-compose.dev.yml").write_text(f"""version: '3.9'
# Desenvolvimento local: só levanta infra, backend e frontend rodam no host
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: {name}
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  postgres_data:
""")


def write_makefile(name: str, combo: dict, path: Path):
    backend  = combo["backend"]
    frontend = combo["frontend"]
    pb = combo["port_back"]
    pf = combo["port_front"]

    back_run = {
        "nestjs":      "cd backend && npm run start:dev",
        "spring-boot": "cd backend && ./mvnw spring-boot:run",
        "python":      "cd backend && source .venv/bin/activate && uvicorn src.main:app --reload --port 8000",
        "dotnet":      f"cd backend/{name}.Api && dotnet run",
    }.get(backend, "cd backend && echo 'configure run command'")

    back_test = {
        "nestjs":      "cd backend && npm run test",
        "spring-boot": "cd backend && ./mvnw test",
        "python":      "cd backend && source .venv/bin/activate && pytest",
        "dotnet":      "cd backend && dotnet test",
    }.get(backend, "cd backend && echo 'configure test command'")

    back_install = {
        "nestjs":      "cd backend && npm install",
        "spring-boot": "cd backend && ./mvnw dependency:resolve",
        "python":      "cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt",
        "dotnet":      "cd backend && dotnet restore",
    }.get(backend, "")

    front_run = {
        "nextjs":  "cd frontend && npm run dev",
        "angular": "cd frontend && ng serve",
    }.get(frontend, "cd frontend && npm start")

    content = f""".PHONY: help install dev dev-back dev-front test build docker-up docker-down

help: ## Mostra este menu
\t@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {{FS = ":.*?## "}}; {{printf "\\033[36m%-20s\\033[0m %s\\n", $$1, $$2}}'

install: ## Instala dependências de backend e frontend
\t{back_install}
\tcd frontend && npm install

dev-back: ## Roda o backend em modo desenvolvimento
\t{back_run}

dev-front: ## Roda o frontend em modo desenvolvimento
\t{front_run}

dev: ## Roda backend e frontend simultaneamente
\t@echo "Iniciando {name}..."
\t@make dev-back & make dev-front

test: ## Roda todos os testes
\t{back_test}
\tcd frontend && npm test

test-back: ## Testa só o backend
\t{back_test}

test-front: ## Testa só o frontend
\tcd frontend && npm test

build: ## Build de produção
\tcd frontend && npm run build

docker-up: ## Sobe toda a stack com Docker Compose
\tdocker compose up -d

docker-up-dev: ## Sobe só a infra (postgres + redis) para dev local
\tdocker compose -f docker-compose.dev.yml up -d

docker-down: ## Para todos os containers
\tdocker compose down

docker-logs: ## Mostra logs dos containers
\tdocker compose logs -f

db-migrate: ## Roda as migrações do banco
\t@echo "Configure db-migrate para seu backend"

lint: ## Lint em todo o projeto
\tcd backend && npm run lint || true
\tcd frontend && npm run lint || true
"""
    (path / "Makefile").write_text(content)


def write_nginx_conf(name: str, combo: dict, path: Path):
    pb = combo["port_back"]
    pf = combo["port_front"]

    nginx_dir = path / "nginx"
    nginx_dir.mkdir(exist_ok=True)
    (nginx_dir / "nginx.conf").write_text(f"""events {{ worker_connections 1024; }}

http {{
    upstream backend  {{ server backend:{pb}; }}
    upstream frontend {{ server frontend:{pf}; }}

    server {{
        listen 80;
        server_name _;

        # API → backend
        location /api/ {{
            proxy_pass         http://backend;
            proxy_set_header   Host $host;
            proxy_set_header   X-Real-IP $remote_addr;
            proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header   X-Forwarded-Proto $scheme;
        }}

        # Todo o resto → frontend
        location / {{
            proxy_pass         http://frontend;
            proxy_set_header   Host $host;
            proxy_set_header   X-Real-IP $remote_addr;
            proxy_http_version 1.1;
            proxy_set_header   Upgrade $http_upgrade;
            proxy_set_header   Connection 'upgrade';
            proxy_cache_bypass $http_upgrade;
        }}
    }}
}}
""")


def write_root_readme(name: str, description: str, combo: dict, path: Path):
    backend  = combo["backend"]
    frontend = combo["frontend"]
    pb = combo["port_back"]
    pf = combo["port_front"]

    (path / "README.md").write_text(f"""# {name}

{description}

## Stack

| Camada    | Tecnologia   | Porta |
|-----------|-------------|-------|
| Backend   | {backend}   | {pb}  |
| Frontend  | {frontend}  | {pf}  |
| Banco     | PostgreSQL  | 5432  |
| Cache     | Redis       | 6379  |

## Estrutura

```
{name}/
  backend/      ← {backend}
  frontend/     ← {frontend}
  nginx/        ← proxy reverso (produção)
  docker-compose.yml
  docker-compose.dev.yml
  Makefile
  .env.example
```

## Início rápido

```bash
# 1. Copie e edite o .env
cp .env.example .env

# 2. Sobe banco e redis
make docker-up-dev

# 3. Instala dependências
make install

# 4. Roda backend e frontend
make dev-back   # terminal 1
make dev-front  # terminal 2

# Ou ambos juntos (requer tmux/GNU parallel)
make dev
```

## Comandos úteis

```bash
make help         # lista todos os comandos
make test         # roda todos os testes
make docker-up    # sobe stack completa
make docker-down  # para tudo
```

## API

- Swagger: http://localhost:{pb}/api (backend)
- App:     http://localhost:{pf} (frontend)
""")


def write_root_env_example(name: str, combo: dict, path: Path):
    pb = combo["port_back"]
    backend = combo["backend"]

    extras_back = {
        "nestjs":      f"NODE_ENV=development\nPORT={pb}\n",
        "spring-boot": f"SERVER_PORT={pb}\nSPRING_PROFILES_ACTIVE=dev\n",
        "python":      f"APP_PORT={pb}\n",
        "dotnet":      f"ASPNETCORE_URLS=http://localhost:{pb}\n",
    }.get(backend, "")

    (path / ".env.example").write_text(f"""# ── Banco de dados ──────────────────────────────
DB_HOST=localhost
DB_PORT=5432
DB_NAME={name}
DB_USER=postgres
DB_PASS=postgres

# ── Auth ────────────────────────────────────────
JWT_SECRET=change-me-in-production-min-32-chars
JWT_EXPIRES_IN=7d

# ── Backend ─────────────────────────────────────
{extras_back}
# ── Frontend ────────────────────────────────────
NEXT_PUBLIC_API_URL=http://localhost:{pb}/api/v1

# ── Redis (opcional) ────────────────────────────
REDIS_URL=redis://localhost:6379
""")


def write_vscode_workspace(name: str, path: Path):
    """Arquivo .code-workspace para abrir backend e frontend juntos no VS Code."""
    import json
    ws = {
        "folders": [
            {"name": "root", "path": "."},
            {"name": "backend", "path": "./backend"},
            {"name": "frontend", "path": "./frontend"},
        ],
        "settings": {
            "editor.formatOnSave": True,
            "editor.defaultFormatter": "esbenp.prettier-vscode",
        },
        "extensions": {
            "recommendations": [
                "dbaeumer.vscode-eslint",
                "esbenp.prettier-vscode",
                "ms-azuretools.vscode-docker",
                "PKief.material-icon-theme",
            ]
        }
    }
    (path / f"{name}.code-workspace").write_text(json.dumps(ws, indent=2))


def write_shared_files(name: str, description: str, combo: dict, project_path: Path):
    """Gera todos os arquivos raiz do projeto fullstack."""
    write_docker_compose(name, combo, project_path)
    write_makefile(name, combo, project_path)
    write_nginx_conf(name, combo, project_path)
    write_root_readme(name, description, combo, project_path)
    write_root_env_example(name, combo, project_path)
    write_vscode_workspace(name, project_path)
    console.print("[green]✓ docker-compose, Makefile, nginx, README, .env.example, workspace[/green]")
