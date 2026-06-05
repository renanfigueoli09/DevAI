"""
Configurações do DevAI
Edite config/settings.py para customizar modelo, temperatura, etc.
"""

import os
from pathlib import Path

# ─── LLM ───────────────────────────────────────────────────────────────────────
OLLAMA_HOST = os.getenv("DEVAI_OLLAMA_HOST", "http://localhost:11434")

# Modelos recomendados para 7B (em ordem de preferência para código):
#   qwen2.5-coder:7b        ← melhor para código geral
#   deepseek-coder:6.7b     ← ótimo para refactoring
#   codellama:7b            ← fallback confiável
#   mistral:7b              ← bom para análise e escrita de docs
MODEL_CODE    = os.getenv("DEVAI_MODEL_CODE",    "qwen2.5-coder:7b")
MODEL_ANALYST = os.getenv("DEVAI_MODEL_ANALYST", "qwen2.5-coder:7b")

# Temperatura baixa = mais determinístico (melhor para código)
TEMPERATURE = float(os.getenv("DEVAI_TEMPERATURE", "0.2"))

# Contexto máximo em tokens enviados ao modelo por chamada
# 7B costuma ter 4k-8k de contexto real; mantenha margem
MAX_CONTEXT_TOKENS = int(os.getenv("DEVAI_MAX_CONTEXT", "6000"))

# ─── PATHS ─────────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
PROMPTS_DIR   = BASE_DIR / "prompts"

# Onde o índice RAG é salvo (dentro do projeto analisado)
RAG_INDEX_DIR = ".devai"

# ─── AGENTES ───────────────────────────────────────────────────────────────────
# Nível de verbosidade: 0=silencioso, 1=resumido, 2=detalhado
VERBOSE = int(os.getenv("DEVAI_VERBOSE", "1"))

# Se True, pede confirmação antes de escrever qualquer arquivo
CONFIRM_WRITES = os.getenv("DEVAI_CONFIRM_WRITES", "true").lower() == "true"

# Extensões ignoradas na análise de projetos
IGNORE_EXTENSIONS = {
    ".lock", ".log", ".DS_Store", ".env", ".png", ".jpg",
    ".jpeg", ".gif", ".ico", ".svg", ".woff", ".woff2",
    ".ttf", ".eot", ".mp4", ".mp3", ".zip", ".tar", ".gz",
}

IGNORE_DIRS = {
    "node_modules", ".git", "dist", "build", ".next",
    "__pycache__", ".venv", "venv", "env", "target",
    ".gradle", ".idea", ".vscode", "coverage", ".devai",
    "bin", "obj",
}

# ─── STACKS SUPORTADAS ─────────────────────────────────────────────────────────
STACKS = {
    "nestjs":      {"lang": "TypeScript", "runtime": "Node.js",  "test": "Jest"},
    "nextjs":      {"lang": "TypeScript", "runtime": "Node.js",  "test": "Jest + Testing Library"},
    "angular":     {"lang": "TypeScript", "runtime": "Node.js",  "test": "Jasmine + Karma"},
    "spring-boot": {"lang": "Java",       "runtime": "JVM",      "test": "JUnit 5 + Mockito"},
    "python":      {"lang": "Python",     "runtime": "CPython",  "test": "pytest"},
    "dotnet":      {"lang": "C#",         "runtime": ".NET 8",   "test": "xUnit"},
}
