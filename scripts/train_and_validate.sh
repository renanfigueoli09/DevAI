#!/usr/bin/env bash
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  DevAI — Loop coordenado: Fix → Score → Expand                         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# Duas fases:
#   FASE 1 (Fix): valida → identifica fracos → estuda os fracos → re-valida
#                 Repete até score >= SCORE_MIN
#
#   FASE 2 (Expand): score aprovado → estuda novos tópicos indefinidamente
#                    Valida a cada N ciclos para garantir que score não caiu
#
# Uso:
#   ./scripts/train_and_validate.sh
#   ./scripts/train_and_validate.sh --group nestjs --score 80
#   ./scripts/train_and_validate.sh --expand-only   # pula fase 1, vai direto para expansão

set -euo pipefail
DEVAI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$DEVAI_DIR/.venv/bin/python"
STATE_FILE="$DEVAI_DIR/training/session_state.json"
LOG_FILE="$DEVAI_DIR/training/train_validate.log"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'

# ── Config ────────────────────────────────────────────────────────────────────
GROUP="all"
SCORE_MIN=70          # % mínimo para passar para fase 2
MAX_FIX_ROUNDS=20     # máximo de rodadas de fix antes de continuar mesmo assim
REVALIDATE_EVERY=3    # revalida a cada N ciclos de expansão
EXPAND_ONLY=false
STUDY_PID=""
TAIL_PID=""

for arg in "$@"; do
    case $arg in
        --group=*)      GROUP="${arg#*=}" ;;
        --group)        shift; GROUP="$1" ;;
        --score=*)      SCORE_MIN="${arg#*=}" ;;
        --expand-only)  EXPAND_ONLY=true ;;
    esac
done

# ── Cleanup ───────────────────────────────────────────────────────────────────
cleanup() {
    echo -e "\n  ${YELLOW}Encerrando...${NC}"
    [ -n "$STUDY_PID" ] && kill "$STUDY_PID" 2>/dev/null || true
    [ -n "$TAIL_PID"  ] && kill "$TAIL_PID"  2>/dev/null || true
    kill -- -$$ 2>/dev/null || true
    echo -e "  ${GREEN}✓ Encerrado${NC}"
    exit 0
}
trap cleanup INT TERM

# ── Helpers ───────────────────────────────────────────────────────────────────
log() { echo -e "$1" | tee -a "$LOG_FILE"; }

auto_commit() {
    local msg="${1:-🧠 training: $(date '+%Y-%m-%d %H:%M')}"
    local LOCK="$DEVAI_DIR/.git/index.lock"
    local waited=0
    while [ -f "$LOCK" ] && [ $waited -lt 15 ]; do sleep 1; waited=$((waited+1)); done
    [ -f "$LOCK" ] && rm -f "$LOCK" 2>/dev/null
    git -C "$DEVAI_DIR" add training/ README.md 2>/dev/null || true
    if ! git -C "$DEVAI_DIR" diff --cached --quiet 2>/dev/null; then
        git -C "$DEVAI_DIR" commit -m "$msg" 2>/dev/null && \
        git -C "$DEVAI_DIR" push 2>/dev/null && \
        log "  ${GREEN}✓ Commitado e push: $msg${NC}" || true
    fi
}

get_score() {
    # Lê score do último validation_report.json
    local report="$DEVAI_DIR/training/validation_report.json"
    if [ -f "$report" ]; then
        python3 -c "
import json
try:
    d = json.load(open('$report'))
    print(int(d.get('score', 0)))
except:
    print(0)
" 2>/dev/null || echo "0"
    else
        echo "0"
    fi
}

get_weak_topics() {
    # Lê study_key dos tópicos fracos (chave usada pelo study.py --topics)
    local report="$DEVAI_DIR/training/validation_report.json"
    if [ -f "$report" ]; then
        python3 -c "
import json, sys
try:
    d = json.load(open('$report'))
    # Usa study_key se disponível, senão normaliza o topic name
    weak = []
    for r in d.get('results', []):
        if float(r.get('pass_rate', 1.0)) < 0.7:
            key = r.get('study_key') or r.get('topic','').replace('-','_').replace(' ','_').lower()
            if key and key not in weak:
                weak.append(key)
    print(' '.join(weak))
except Exception as e:
    sys.stderr.write(str(e)+'\n')
    print('')
" 2>/dev/null || echo ""
    else
        echo ""
    fi
}

run_validate() {
    local rounds="${1:-3}"
    log "\n  ${CYAN}→ Validando (${rounds} rodadas de fix)...${NC}"
    "$VENV_PYTHON" "$DEVAI_DIR/scripts/validate.py" \
        --fix --rounds "$rounds" \
        2>&1 | tee -a "$LOG_FILE"
}

study_weak() {
    local topics="$1"
    if [ -z "$topics" ]; then return; fi
    log "\n  ${YELLOW}→ Estudando tópicos fracos: $topics${NC}"
    "$VENV_PYTHON" "$DEVAI_DIR/scripts/study.py" \
        --topics $topics --intensive --force \
        2>&1 | tee -a "$LOG_FILE"
}

study_expand() {
    log "\n  ${CYAN}→ Expandindo conhecimento (grupo: $GROUP)...${NC}"
    "$VENV_PYTHON" "$DEVAI_DIR/scripts/study.py" \
        --group "$GROUP" --intensive \
        2>&1 | tee -a "$LOG_FILE"
}

# ── Início ────────────────────────────────────────────────────────────────────
mkdir -p "$DEVAI_DIR/training"
: > "$LOG_FILE"  # limpa log

log ""
log "  ${BOLD}${CYAN}⚡ DevAI — Loop coordenado Fix→Score→Expand${NC}"
log "  ${CYAN}Score mínimo: ${SCORE_MIN}% | Grupo: ${GROUP}${NC}"
log "  ${CYAN}Log: $LOG_FILE${NC}"
log ""

# Verifica ambiente
[ ! -f "$VENV_PYTHON" ] && log "  ${RED}✗ Execute ./install.sh primeiro${NC}" && exit 1
if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    log "  → Iniciando Ollama..."
    ollama serve &>/dev/null & sleep 4
fi

# ══════════════════════════════════════════════════════════════════════════════
# FASE 1 — FIX: estuda os fracos até atingir o score mínimo
# ══════════════════════════════════════════════════════════════════════════════
if [ "$EXPAND_ONLY" = false ]; then
    log "\n  ${BOLD}${CYAN}═══ FASE 1: Fix até score ≥ ${SCORE_MIN}% ═══${NC}"
    fix_round=1

    while true; do
        log "\n  ${CYAN}── Fix Round $fix_round/${MAX_FIX_ROUNDS} ──${NC}"

        # 1. Salva padrões críticos + valida
        run_validate 3
        auto_commit "🧠 training: fix round $fix_round"

        # 2. Lê score
        score=$(get_score)
        log "\n  ${BOLD}Score atual: ${score}%${NC}"

        if [ "$score" -ge "$SCORE_MIN" ]; then
            log "\n  ${GREEN}${BOLD}✅ Score ${score}% ≥ ${SCORE_MIN}% — Fase 1 concluída!${NC}"
            break
        fi

        if [ "$fix_round" -ge "$MAX_FIX_ROUNDS" ]; then
            log "\n  ${YELLOW}⚠ Máximo de rodadas atingido (${score}%) — avançando para Fase 2${NC}"
            break
        fi

        # 3. Estuda especificamente os tópicos fracos
        weak=$(get_weak_topics)
        if [ -n "$weak" ]; then
            log "  ${YELLOW}Tópicos fracos: $weak${NC}"
            study_weak "$weak"
        else
            # Sem tópicos fracos identificados — estuda o grupo completo
            study_expand
        fi

        fix_round=$((fix_round + 1))
        sleep 5
    done
fi

# ══════════════════════════════════════════════════════════════════════════════
# FASE 2 — EXPAND: descobre e estuda novos tópicos indefinidamente
# ══════════════════════════════════════════════════════════════════════════════
log "\n  ${BOLD}${CYAN}═══ FASE 2: Expansão contínua ═══${NC}"
log "  ${CYAN}Revalida a cada ${REVALIDATE_EVERY} ciclos para manter score${NC}"

expand_cycle=1

while true; do
    log "\n  ${CYAN}── Ciclo de expansão $expand_cycle — $(date '+%H:%M %d/%m') ──${NC}"

    # Estuda novos tópicos
    study_expand
    auto_commit "🧠 training: expand cycle $expand_cycle"

    # Revalida a cada N ciclos
    if (( expand_cycle % REVALIDATE_EVERY == 0 )); then
        log "\n  ${CYAN}→ Re-validando para garantir score...${NC}"
        run_validate 2
        auto_commit "🧠 training: revalidate cycle $expand_cycle"

        score=$(get_score)
        log "  Score: ${score}%"

        # Se o score caiu, volta para modo fix
        if [ "$score" -lt "$SCORE_MIN" ]; then
            log "\n  ${YELLOW}⚠ Score caiu para ${score}% — voltando ao modo Fix...${NC}"
            weak=$(get_weak_topics)
            [ -n "$weak" ] && study_weak "$weak"
            run_validate 5
            auto_commit "🧠 training: recovery fix"
        fi
    fi

    expand_cycle=$((expand_cycle + 1))
    sleep 10
done
