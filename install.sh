#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  DevAI — Script de instalação                                          ║
# ╚══════════════════════════════════════════════════════════════════════════╝
set -e

DEVAI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$DEVAI_DIR/.venv"
PYTHON="${PYTHON:-python3}"

echo ""
echo "  ⚡ DevAI — Instalação"
echo "  Diretório: $DEVAI_DIR"
echo ""

# ─── Python ───────────────────────────────────────────────────────────────
if ! command -v "$PYTHON" &>/dev/null; then
    echo "  ✗ Python 3 não encontrado."
    echo "    sudo apt install python3 python3-venv python3-pip"
    exit 1
fi
PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  ✓ Python $PY_VERSION"

# ─── venv ─────────────────────────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "  → Criando venv..."

    # Tenta criar venv normalmente
    if "$PYTHON" -m venv "$VENV_DIR" 2>/dev/null; then
        echo "  ✓ venv criado"
    else
        # Fallback: instala python3-venv e tenta novamente
        echo "  ⚠  venv falhou — tentando instalar python3-venv..."
        if command -v apt-get &>/dev/null; then
            sudo apt-get install -y python3-venv python3-pip python3-full 2>/dev/null || true
            "$PYTHON" -m venv "$VENV_DIR"
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y python3-virtualenv 2>/dev/null || true
            "$PYTHON" -m venv "$VENV_DIR"
        else
            echo "  ✗ Não foi possível criar o venv."
            echo "    Instale: sudo apt install python3-venv python3-full"
            exit 1
        fi
    fi
fi

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# ─── Garante que pip existe no venv ───────────────────────────────────────
if [ ! -f "$VENV_PIP" ]; then
    echo "  → pip não encontrado no venv — instalando..."

    # Tenta ensurepip
    if "$VENV_PYTHON" -m ensurepip --upgrade 2>/dev/null; then
        echo "  ✓ pip instalado via ensurepip"

    # Tenta baixar get-pip.py
    elif command -v curl &>/dev/null; then
        echo "  → Baixando get-pip.py..."
        curl -sS https://bootstrap.pypa.io/get-pip.py | "$VENV_PYTHON"
        echo "  ✓ pip instalado via get-pip.py"

    elif command -v wget &>/dev/null; then
        wget -qO- https://bootstrap.pypa.io/get-pip.py | "$VENV_PYTHON"
        echo "  ✓ pip instalado via get-pip.py"

    else
        # Última tentativa: recria o venv sem pip isolado
        echo "  → Recriando venv com --system-site-packages..."
        rm -rf "$VENV_DIR"
        "$PYTHON" -m venv "$VENV_DIR" --system-site-packages
        if [ ! -f "$VENV_PIP" ]; then
            echo "  ✗ Não foi possível instalar o pip."
            echo "    Execute: sudo apt install python3-pip python3-full"
            exit 1
        fi
    fi
fi

# ─── Dependências Python ──────────────────────────────────────────────────
echo "  → Instalando dependências Python..."
"$VENV_PYTHON" -m pip install --quiet --upgrade pip
"$VENV_PYTHON" -m pip install --quiet -r "$DEVAI_DIR/requirements.txt"
"$VENV_PYTHON" -m pip install --quiet ddgs 2>/dev/null || \
    "$VENV_PYTHON" -m pip install --quiet duckduckgo-search 2>/dev/null || true
echo "  ✓ Dependências instaladas"

# ─── Ollama ───────────────────────────────────────────────────────────────
echo ""
echo "  ── Ollama ──────────────────────────────────────────"
if command -v ollama &>/dev/null; then
    echo "  ✓ Ollama instalado"
    MODELS=$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' | tr '\n' ' ')
    if [ -n "$MODELS" ]; then
        echo "  ✓ Modelos: $MODELS"
    else
        echo "  ⚠  Sem modelos instalados. Execute:"
        echo "     ollama pull qwen2.5-coder:7b"
    fi

    # Modelo de embeddings para busca semântica no training store
    if ollama list 2>/dev/null | grep -q "nomic-embed-text"; then
        echo "  ✓ Embeddings: nomic-embed-text (busca semântica ativa)"
    else
        echo "  → Instalando modelo de embeddings (nomic-embed-text)..."
        ollama pull nomic-embed-text 2>/dev/null && \
            echo "  ✓ nomic-embed-text instalado" || \
            echo "  ⚠  Execute depois: ollama pull nomic-embed-text"
    fi
else
    echo "  ⚠  Ollama não encontrado → https://ollama.com"
    echo "     Após instalar: ollama pull qwen2.5-coder:7b"
fi

# ─── Ferramentas das stacks ───────────────────────────────────────────────
echo ""
echo "  ── Stacks disponíveis ──────────────────────────────"

check_tool() {
    local name="$1" cmd="$2" hint="$3"
    if command -v "$cmd" &>/dev/null; then
        local ver
        ver=$("$cmd" --version 2>/dev/null | head -1 | tr -d '\n') || ver="?"
        echo "  ✓ $name ($ver)"
    else
        echo "  ○ $name não encontrado → $hint"
    fi
}

check_tool "Node.js" "node"   "https://nodejs.org (recomendado: nvm)"
check_tool "Java"    "java"   "sudo apt install openjdk-21-jdk"
check_tool ".NET"    "dotnet" "https://dot.net/download"
check_tool "git"     "git"    "sudo apt install git"

command -v nest &>/dev/null && echo "  ✓ NestJS CLI" || echo "  ○ NestJS CLI (usará npx)"
command -v ng   &>/dev/null && echo "  ✓ Angular CLI" || echo "  ○ Angular CLI (usará npx)"

# ─── Launcher ─────────────────────────────────────────────────────────────
LAUNCHER="$DEVAI_DIR/devai"
cat > "$LAUNCHER" << EOF
#!/usr/bin/env bash
export PYTHONPATH="$DEVAI_DIR:\$PYTHONPATH"
exec "$VENV_PYTHON" "$DEVAI_DIR/main.py" "\$@"
EOF
chmod +x "$LAUNCHER"
chmod +x "$DEVAI_DIR/scripts/study.sh" 2>/dev/null || true
echo ""
echo "  ✓ Launcher: $LAUNCHER"
echo "  ✓ Scripts:  $DEVAI_DIR/scripts/study.sh"

# ─── Aliases ──────────────────────────────────────────────────────────────
SHELL_RC=""
[[ "$SHELL" == *"zsh"*  ]] && SHELL_RC="$HOME/.zshrc"
[[ "$SHELL" == *"bash"* ]] && SHELL_RC="$HOME/.bashrc"
[[ "$OSTYPE" == "darwin"* && "$SHELL" == *"bash"* ]] && SHELL_RC="$HOME/.bash_profile"
[ -z "$SHELL_RC" ] && [ -f "$HOME/.zshrc"  ] && SHELL_RC="$HOME/.zshrc"
[ -z "$SHELL_RC" ] && [ -f "$HOME/.bashrc" ] && SHELL_RC="$HOME/.bashrc"

if [ -n "$SHELL_RC" ]; then
    # Remove bloco antigo se existir
    sed -i '/# DevAI — Agente/,/alias devask/d' "$SHELL_RC" 2>/dev/null || true

    cat >> "$SHELL_RC" << EOF

# DevAI — Agente autônomo de desenvolvimento
export DEVAI_DIR="$DEVAI_DIR"
alias devai='$LAUNCHER'
alias devnew='devai new'
alias devfeat='devai feature'
alias devstudy='devai study'
alias devask='devai ask'
alias devfix='devai fix'
alias devtrain='devai train'
alias devsearch='devai search'
EOF
    echo "  ✓ Aliases em $SHELL_RC"
    echo "    devai · devnew · devfeat · devstudy · devask · devfix · devtrain"
else
    echo "  ⚠  Adicione ao .bashrc/.zshrc:"
    echo "     alias devai='$LAUNCHER'"
fi

# ─── Teste ────────────────────────────────────────────────────────────────
echo ""
echo "  → Testando importações..."
if "$VENV_PYTHON" -c "import requests, rich; print('  ✓ requests + rich OK')"; then
    :
else
    echo "  ✗ Erro. Tente: \"$VENV_PYTHON\" -m pip install requests rich"
    exit 1
fi

# ─── Fim ──────────────────────────────────────────────────────────────────
echo ""
echo "  ═══════════════════════════════════════════════════════"
echo "  ✅  DevAI instalado com sucesso!"
echo "  ═══════════════════════════════════════════════════════"
echo ""
if [ -n "$SHELL_RC" ]; then
    echo "  Recarregue o shell:   source $SHELL_RC"
fi
echo ""
echo "  Uso rápido:"
echo "    devai new nestjs minha-api \"API com MongoDB e JWT\""
echo "    devai \"cria api de pedidos com spring boot e postgres\""
echo "    devai fix                      ← conserta erros de build"
echo "    devai train --project /ref/    ← aprende padrões de projeto"
echo "    devai search \"nestjs kafka 2025\""
echo ""
