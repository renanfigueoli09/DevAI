#!/usr/bin/env bash
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  DevAI — Treinamento + Validação paralelos (logs em tempo real)         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# Uso:
#   ./scripts/train_and_validate.sh                       # all, valida a cada 5min
#   ./scripts/train_and_validate.sh --group nestjs
#   VAL_INTERVAL=120 ./scripts/train_and_validate.sh      # valida a cada 2min

set -e
DEVAI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$DEVAI_DIR/.venv/bin/python"
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

GROUP="all"
VAL_INTERVAL="${VAL_INTERVAL:-300}"
STUDY_PID=""
TAIL_PID=""

cleanup() {
    echo -e "
  ${YELLOW}Encerrando todos os processos...${NC}"
    [ -n "$STUDY_PID" ] && kill "$STUDY_PID" 2>/dev/null
    [ -n "$TAIL_PID"  ] && kill "$TAIL_PID"  2>/dev/null
    kill -- -$$ 2>/dev/null
    echo -e "  ${GREEN}✓ Encerrado${NC}"
    exit 0
}
trap cleanup INT TERM

for arg in "$@"; do
    case $arg in
        --group=*) GROUP="${arg#*=}" ;;
        --group)   shift; GROUP="$1" ;;
        --validate-interval=*) VAL_INTERVAL="${arg#*=}" ;;
    esac
done

echo ""
echo -e "  ${CYAN}⚡ DevAI — Treino + Validação paralelos${NC}"
echo -e "  ${CYAN}Grupo: $GROUP | Validação a cada $((VAL_INTERVAL/60))min${NC}"
echo -e "  ${CYAN}Logs: training/study.log | training/validation.log${NC}"
echo ""

auto_commit_val() {
    local ROUND=$1
    local LOCK="$DEVAI_DIR/.git/index.lock"
    local waited=0
    while [ -f "$LOCK" ] && [ $waited -lt 15 ]; do sleep 1; waited=$((waited+1)); done
    [ -f "$LOCK" ] && rm -f "$LOCK" 2>/dev/null
    git -C "$DEVAI_DIR" add training/ README.md 2>/dev/null
    if ! git -C "$DEVAI_DIR" diff --cached --quiet 2>/dev/null; then
        git -C "$DEVAI_DIR" commit -m "🧠 training: validate #$ROUND $(date '+%Y-%m-%d %H:%M')" 2>/dev/null \
            && git -C "$DEVAI_DIR" push 2>/dev/null \
            && echo -e "  ${GREEN}✓ Commitado (validate #$ROUND)${NC}" || true
    fi
}

# Inicia study em background
echo -e "  ${CYAN}→ Iniciando treinamento...${NC}"
"$DEVAI_DIR/scripts/study.sh" --group "$GROUP" --intensive --loop \
    > "$DEVAI_DIR/training/study.log" 2>&1 &
STUDY_PID=$!
echo -e "  ${GREEN}✓ Study PID: $STUDY_PID${NC}"

# Mostra logs do study em tempo real
tail -f "$DEVAI_DIR/training/study.log" &
TAIL_PID=$!

# Aguarda study iniciar
echo -e "\n  ${CYAN}Aguardando 30s para iniciar validações...${NC}"
sleep 30

ROUND=1
while kill -0 $STUDY_PID 2>/dev/null; do
    echo -e "\n  ${CYAN}══════ Validação #$ROUND — $(date '+%H:%M') ══════${NC}\n"
    "$VENV_PYTHON" "$DEVAI_DIR/scripts/validate.py" --fix --rounds 3 \
        2>&1 | tee -a "$DEVAI_DIR/training/validation.log"
    auto_commit_val $ROUND
    ROUND=$((ROUND + 1))
    echo -e "\n  ${CYAN}Próxima validação em $((VAL_INTERVAL/60))min...${NC}"
    sleep "$VAL_INTERVAL"
done

kill $TAIL_PID 2>/dev/null
echo -e "\n  ${YELLOW}Study encerrado (PID $STUDY_PID)${NC}"
