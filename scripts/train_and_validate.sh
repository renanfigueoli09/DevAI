#!/usr/bin/env bash
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  DevAI — Treinamento + Validação paralelos                              ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# Roda study (em background) + validate (em loop) simultaneamente.
# Sem conflito de git — só o study commita.
#
# Uso:
#   ./scripts/train_and_validate.sh                     # all + validate a cada 5min
#   ./scripts/train_and_validate.sh --group nestjs      # grupo específico
#   ./scripts/train_and_validate.sh --interval 300      # validação a cada 5min
#   ./scripts/train_and_validate.sh --validate-interval 600  # a cada 10min

set -e
DEVAI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$DEVAI_DIR/.venv/bin/python"
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

GROUP="${1:-all}"
VAL_INTERVAL="${VAL_INTERVAL:-300}"   # 5min entre validações
STUDY_INTERVAL="${STUDY_INTERVAL:-1800}"  # 30min entre ciclos de estudo

# Parse args
for arg in "$@"; do
    case $arg in
        --group=*) GROUP="${arg#*=}" ;;
        --validate-interval=*) VAL_INTERVAL="${arg#*=}" ;;
        --interval=*) STUDY_INTERVAL="${arg#*=}" ;;
    esac
done

echo ""
echo -e "  ${CYAN}⚡ DevAI — Treino + Validação paralelos${NC}"
echo -e "  ${CYAN}Grupo: $GROUP | Validação a cada ${VAL_INTERVAL}s${NC}"
echo ""

# Inicia study em background
echo -e "  ${CYAN}→ Iniciando treinamento em background...${NC}"
nohup "$DEVAI_DIR/scripts/study.sh" --group "$GROUP" --intensive --loop \
    > "$DEVAI_DIR/training/study.log" 2>&1 &
STUDY_PID=$!
echo -e "  ${GREEN}✓ Study PID: $STUDY_PID${NC}"
echo -e "  ${CYAN}  tail -f training/study.log${NC}"

# Aguarda 30s para o study iniciar antes de validar
echo -e "\n  ${CYAN}Aguardando 30s para iniciar validações...${NC}"
sleep 30

# Loop de validação em foreground
ROUND=1
echo ""
while kill -0 $STUDY_PID 2>/dev/null; do
    echo -e "\n  ${CYAN}══ Validação #$ROUND — $(date '+%H:%M') ══${NC}\n"
    "$VENV_PYTHON" "$DEVAI_DIR/scripts/validate.py" --fix --rounds 3 \
        2>&1 | tee -a "$DEVAI_DIR/training/validation.log"
    ROUND=$((ROUND + 1))
    echo -e "\n  ${CYAN}Próxima validação em $((VAL_INTERVAL/60))min...${NC}"
    sleep "$VAL_INTERVAL"
done

echo -e "\n  ${YELLOW}Study encerrado (PID $STUDY_PID)${NC}"
