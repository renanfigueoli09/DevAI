#!/usr/bin/env bash
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  DevAI Auto-Study v5 — Loop inteligente (não repete o que já foi feito) ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# USO:
#   ./scripts/study.sh                              # estuda o que ainda não foi feito
#   ./scripts/study.sh --group nestjs               # foca em NestJS
#   ./scripts/study.sh --group all                  # tudo pendente
#   ./scripts/study.sh --group all --intensive      # intensivo (mais pesquisas + exemplos)
#   ./scripts/study.sh --group all --loop           # loop inteligente overnight
#   ./scripts/study.sh --group all --loop --validate --intensive  # máximo
#   ./scripts/study.sh --force                      # re-estuda mesmo os já OK
#   ./scripts/study.sh --status                     # mostra o que já foi estudado e o que falta
#
# VALIDAÇÃO:
#   python scripts/validate.py          # valida e gera relatório
#   python scripts/validate.py --fix    # valida + retreina os fracos
#
# DIÁRIO DE ESTUDO:
#   cat training/study_journal.json     # o que foi estudado, quando e score
#   cat training/discovered_topics.json # novos tópicos descobertos
#   python scripts/study.py --status   # tabela de status
#
# OVERNIGHT COMPLETO:
#   nohup ./scripts/study.sh --group all --intensive --loop --validate \
#     > training/study.log 2>&1 &
#   tail -f training/study.log

set -e
DEVAI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$DEVAI_DIR/.venv/bin/python"
STUDY_PY="$DEVAI_DIR/scripts/study.py"
VALIDATE_PY="$DEVAI_DIR/scripts/validate.py"
LOG_FILE="$DEVAI_DIR/training/study.log"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

echo ""
echo -e "  ${CYAN}⚡ DevAI Auto-Study v5 — Smart Loop${NC}"
echo ""

[ ! -f "$VENV_PYTHON" ] && echo -e "  ${RED}✗ Execute ./install.sh primeiro${NC}" && exit 1
! command -v ollama &>/dev/null && echo -e "  ${RED}✗ Ollama não encontrado${NC}" && exit 1

if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    echo "  → Iniciando Ollama..."; ollama serve &>/dev/null & sleep 4
fi
if ! ollama list 2>/dev/null | grep -q "nomic-embed-text"; then
    echo -e "  ${YELLOW}→ Instalando nomic-embed-text...${NC}"
    ollama pull nomic-embed-text 2>/dev/null && echo -e "  ${GREEN}✓ instalado${NC}" || true
fi
echo -e "  ${GREEN}✓${NC} Ollama OK | $(date '+%H:%M %d/%m/%Y')"
mkdir -p "$DEVAI_DIR/training"

auto_commit() {
    if command -v git &>/dev/null && [ -d "$DEVAI_DIR/.git" ]; then
        cd "$DEVAI_DIR"
        if ! git diff --quiet training/ 2>/dev/null; then
            git add training/ 2>/dev/null
            git commit -m "training: $(date '+%Y-%m-%d %H:%M')" 2>/dev/null \
                && echo -e "  ${GREEN}✓ Commitado${NC}" || true
        fi
    fi
}

# Só status
if [[ "$*" == *"--status"* ]]; then
    "$VENV_PYTHON" "$STUDY_PY" --status "${@/--status/}"
    exit 0
fi

# Só validação
if [[ "$*" == "--validate" ]]; then
    echo -e "  ${CYAN}→ Executando validação...\n${NC}"
    "$VENV_PYTHON" "$VALIDATE_PY" 2>&1 | tee "$DEVAI_DIR/training/validation.log"
    auto_commit; exit 0
fi

LOOP_MODE=false
for arg in "$@"; do [[ "$arg" == "--loop" ]] && LOOP_MODE=true; done

if $LOOP_MODE; then
    ARGS="${*/--loop/}"
    INTERVAL=${STUDY_INTERVAL:-1800}
    echo -e "  ${CYAN}Loop inteligente — só estuda o que ainda não foi feito${NC}"
    echo -e "  ${CYAN}Intervalo: ${INTERVAL}s | Log: $LOG_FILE${NC}\n"
    CYCLE=1
    while true; do
        echo -e "\n  ${CYAN}══════ Ciclo $CYCLE — $(date '+%H:%M %d/%m') ══════${NC}\n"
        "$VENV_PYTHON" "$STUDY_PY" $ARGS 2>&1 | tee -a "$LOG_FILE"
        if (( CYCLE % 3 == 0 )) && [[ "$*" == *"--validate"* ]]; then
            echo -e "\n  ${CYAN}→ Validando (ciclo $CYCLE)...${NC}"
            "$VENV_PYTHON" "$VALIDATE_PY" 2>&1 | tee -a "$LOG_FILE"
        fi
        auto_commit
        CYCLE=$((CYCLE + 1))
        echo -e "\n  ${CYAN}Próximo ciclo em $((INTERVAL/60))min...${NC}"
        sleep "$INTERVAL"
    done
else
    echo -e "  Log: $LOG_FILE\n"
    "$VENV_PYTHON" "$STUDY_PY" "$@" 2>&1 | tee "$LOG_FILE"
    if [[ "$*" == *"--validate"* ]]; then
        echo -e "\n  ${CYAN}→ Validando...${NC}\n"
        "$VENV_PYTHON" "$VALIDATE_PY" 2>&1 | tee -a "$LOG_FILE"
    fi
    auto_commit
    echo -e "\n  ${GREEN}✓ Concluído: $(date '+%H:%M:%S')${NC}"
fi

# Self-improvement: agent generates, validates and learns
# python scripts/self_improve.py           # run once
# python scripts/self_improve.py --loop    # continuous
