#!/usr/bin/env bash
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  DevAI — Treina, valida e expande. Loop eterno.                         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝
#
# Fluxo:
#   1. Valida — se score < MIN: retreina fracos → volta para 1
#   2. Score >= MIN → vira modo expansão: estuda novos tópicos indefinidamente
#   3. A cada N ciclos de expansão, revalida para garantir que score não caiu
#   4. Se score cair abaixo do MIN, volta para modo fix (passo 1)
#   5. Commita e faz push a cada ciclo
#   6. Nunca para — Ctrl+C para encerrar
#
# Uso:
#   ./scripts/train_and_validate.sh
#   ./scripts/train_and_validate.sh --score 80
#   ./scripts/train_and_validate.sh --group nestjs

set -euo pipefail
DEVAI_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$DEVAI_DIR/.venv/bin/python"
LOG="$DEVAI_DIR/training/train_validate.log"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'
RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'

SCORE_MIN=70
GROUP="all"
REVALIDATE_EVERY=3     # revalida a cada N ciclos de expansão

for arg in "$@"; do
    case $arg in
        --score=*)  SCORE_MIN="${arg#*=}" ;;
        --score)    shift; SCORE_MIN="$1" ;;
        --group=*)  GROUP="${arg#*=}" ;;
        --group)    shift; GROUP="$1" ;;
    esac
done

# ── Cleanup ───────────────────────────────────────────────────────────────────
cleanup() {
    echo -e "\n  ${YELLOW}Ctrl+C — encerrando...${NC}"
    kill -- -$$ 2>/dev/null || true
    exit 0
}
trap cleanup INT TERM

# ── Helpers ───────────────────────────────────────────────────────────────────
log() { echo -e "$1" | tee -a "$LOG"; }

auto_commit() {
    local msg="$1"
    local LOCK="$DEVAI_DIR/.git/index.lock"
    local w=0
    while [ -f "$LOCK" ] && [ $w -lt 15 ]; do sleep 1; w=$((w+1)); done
    [ -f "$LOCK" ] && rm -f "$LOCK" 2>/dev/null
    git -C "$DEVAI_DIR" config user.email "devai@local" 2>/dev/null
    git -C "$DEVAI_DIR" config user.name  "DevAI"       2>/dev/null
    git -C "$DEVAI_DIR" add training/ README.md 2>/dev/null || true
    if ! git -C "$DEVAI_DIR" diff --cached --quiet 2>/dev/null; then
        git -C "$DEVAI_DIR" commit -m "$msg" 2>/dev/null \
            && git -C "$DEVAI_DIR" push 2>/dev/null \
            && log "  ${GREEN}✓ Commitado: $msg${NC}" || true
    fi
}

get_score() {
    local f="$DEVAI_DIR/training/validation_report.json"
    [ -f "$f" ] && python3 -c "
import json
try: print(int(json.load(open('$f')).get('score',0)))
except: print(0)
" 2>/dev/null || echo "0"
}

get_weak_study_keys() {
    local f="$DEVAI_DIR/training/validation_report.json"
    [ -f "$f" ] && python3 -c "
import json, re
MAP = {
    'mongoose':'nestjs_mongodb','mongoosemodule':'nestjs_mongodb',
    'schema.ts':'nestjs_mongodb','service.ts':'nestjs_mongodb',
    'injectmodel':'nestjs_mongodb','findoneBy':'nestjs_mongodb',
    'partialtype':'nestjs_auth','jwtauthguard':'nestjs_auth',
    'docker':'docker_patterns','healthcheck':'docker_patterns',
    'mongosh':'docker_patterns',
    'livros':'nlp_patterns','usuários':'nlp_patterns',
    'spring':'spring_mongodb','@document':'spring_mongodb',
    'fastapi':'fastapi_mongodb','motor':'fastapi_mongodb',
    'ts2307':'common_errors',
}
def key(name):
    n = name.lower()
    for kw,k in MAP.items():
        if kw in n: return k
    return re.sub(r'[^\w]','_',n)[:25]
d = json.load(open('$f'))
seen = set()
out = []
for r in d.get('results',[]):
    if float(r.get('pass_rate',1)) < 0.7:
        k = r.get('study_key') or key(r.get('topic',''))
        if k and k not in seen: seen.add(k); out.append(k)
print(' '.join(out))
" 2>/dev/null || echo ""
}

do_validate() {
    local rounds="${1:-3}"
    log "\n  ${CYAN}▶ Validando (${rounds} rounds de fix)...${NC}"
    # Remove cache de checks dinâmicos para forçar regeneração com novos tópicos
    rm -f "$DEVAI_DIR/training/dynamic_checks.json" 2>/dev/null || true
    "$VENV" "$DEVAI_DIR/scripts/validate.py" --fix --rounds "$rounds" \
        2>&1 | tee -a "$LOG"
}

do_study_weak() {
    local topics="$1"
    [ -z "$topics" ] && return
    log "\n  ${YELLOW}▶ Retreinando fracos: $topics${NC}"
    "$VENV" - "$topics" <<'PYEOF' 2>&1 | tee -a "$LOG"
import sys, os
sys.path.insert(0, os.environ.get('DEVAI_DIR', '.'))
topics = sys.argv[1].split() if len(sys.argv) > 1 else []
from tools.vector_store import save, backfill_embeddings
from scripts.validate import CRITICAL_PATTERNS
from scripts.study import study_topic, SEARCH_CURRICULUM, load_discovered, load_llm

for key, topic, content in CRITICAL_PATTERNS:
    save(key, content, topic=topic, source="force_retrain")

all_c = {**SEARCH_CURRICULUM, **load_discovered()}
llm, model = load_llm()
total = 0
for t in topics[:5]:
    searches = all_c.get(t, [])[:3]
    if searches:
        n = study_topic(t, searches, llm, model, intensive=True)
        total += n
        print(f"  ✓ {t}: {n} itens")
n_emb = backfill_embeddings()
if n_emb: print(f"  ✓ {n_emb} embeddings")
print(f"  Total: {total}")
PYEOF
}

do_expand() {
    log "\n  ${CYAN}▶ Expandindo (grupo: $GROUP)...${NC}"
    # Roda em batches de 5 tópicos — commita entre cada batch
    "$VENV" - "$GROUP" <<'PYEOF' 2>&1 | tee -a "$LOG"
import sys, os, subprocess, time
sys.path.insert(0, os.environ.get('DEVAI_DIR', os.path.dirname(os.path.abspath('.'))))
group = sys.argv[1] if len(sys.argv) > 1 else "all"

from scripts.study import (study_topic, TOPIC_GROUPS, SEARCH_CURRICULUM,
                            load_discovered, load_journal, save_journal,
                            topic_priority, TopicEntry, load_llm)
from tools.vector_store import backfill_embeddings, auto_commit

llm, model = load_llm()
journal    = load_journal()
discovered = load_discovered()
all_c      = {**SEARCH_CURRICULUM, **load_discovered()}
base       = TOPIC_GROUPS.get(group, TOPIC_GROUPS["all"])
now        = time.time()

# Topics ordered by priority
pending = sorted(
    [(t, topic_priority(journal.get(t), now)) for t in base
     if topic_priority(journal.get(t), now) > 0],
    key=lambda x: x[1], reverse=True
)
print(f"  {len(pending)} tópicos para estudar")

BATCH = 5
for i in range(0, len(pending), BATCH):
    batch = pending[i:i+BATCH]
    for topic, prio in batch:
        searches = all_c.get(topic, [])
        if not searches:
            continue
        print(f"  📖 {topic} (prio:{prio:.0f})")
        n = study_topic(topic, searches, llm, model, intensive=True)
        entry = journal.get(topic) or TopicEntry(topic=topic)
        entry.last_studied = time.time()
        entry.times_studied += 1
        entry.items_saved   += n
        journal[topic] = entry
        print(f"    ✓ {n} itens")

    save_journal(journal)
    backfill_embeddings()
    # Commita após cada batch
    if auto_commit(f"🧠 training: expand batch {i//BATCH+1}"):
        print(f"  ✓ Commitado (batch {i//BATCH+1})")

# Discover new topics
from scripts.study import discover_new_topics, _discover_alternative
print("  🔍 Descobrindo novos tópicos...")
all_known = list(set(list(journal.keys()) + base))
new = discover_new_topics(llm, model, all_known)
if not new:
    new = _discover_alternative(llm, model, all_known)
if new:
    for t, searches in new.items():
        n = study_topic(t, searches, llm, model, intensive=True)
        entry = TopicEntry(topic=t, source="discovered")
        entry.last_studied = time.time(); entry.times_studied = 1; entry.items_saved = n
        journal[t] = entry
    save_journal(journal)
    backfill_embeddings()
    if auto_commit(f"🧠 training: new topics {list(new.keys())[:2]}"):
        print(f"  ✓ Commitado (novos tópicos)")
PYEOF
}

# ── Início ────────────────────────────────────────────────────────────────────
mkdir -p "$DEVAI_DIR/training"
: > "$LOG"
log "\n  ${BOLD}${CYAN}⚡ DevAI — Train + Validate loop eterno${NC}"
log "  ${CYAN}Score mínimo: ${SCORE_MIN}% | Grupo: $GROUP${NC}"
log "  ${CYAN}Ctrl+C para parar\n${NC}"

[ ! -f "$VENV" ] && log "  ${RED}✗ Execute ./install.sh primeiro${NC}" && exit 1
if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
    log "  → Iniciando Ollama..."; ollama serve &>/dev/null & sleep 4
fi

# ══════════════════════════════════════════════════════════════════════════════
# FASE 1 — FIX: valida → retreina fracos → repete até score >= MIN
# ══════════════════════════════════════════════════════════════════════════════
log "\n  ${BOLD}${CYAN}═══ FASE 1: Atingindo score ≥ ${SCORE_MIN}% ═══${NC}"
fix_round=1

while true; do
    log "\n  ${CYAN}── Fix #$fix_round ──${NC}"
    do_validate 3
    auto_commit "🧠 training: fix #$fix_round $(date '+%H:%M')"

    score=$(get_score)
    log "\n  ${BOLD}Score: ${score}%${NC}"

    if [ "$score" -ge "$SCORE_MIN" ]; then
        log "\n  ${GREEN}${BOLD}✅ Score ${score}% ≥ ${SCORE_MIN}% — Fase 2!${NC}"
        break
    fi

    weak=$(get_weak_study_keys)
    [ -n "$weak" ] && do_study_weak "$weak" || do_expand
    auto_commit "🧠 training: fix study #$fix_round $(date '+%H:%M')"
    fix_round=$((fix_round + 1))
done

# ══════════════════════════════════════════════════════════════════════════════
# FASE 2 — EXPANSÃO: estuda novos tópicos infinitamente + revalida periodicamente
# ══════════════════════════════════════════════════════════════════════════════
log "\n  ${BOLD}${CYAN}═══ FASE 2: Expansão infinita ═══${NC}"
expand=1

while true; do
    log "\n  ${CYAN}── Expansão #$expand — $(date '+%H:%M %d/%m') ──${NC}"

    # Estuda novos tópicos
    do_expand
    auto_commit "🧠 training: expand #$expand $(date '+%H:%M')"

    # Revalida periodicamente
    if (( expand % REVALIDATE_EVERY == 0 )); then
        log "\n  ${CYAN}▶ Re-validando (ciclo $expand)...${NC}"
        do_validate 2
        auto_commit "🧠 training: revalidate #$expand $(date '+%H:%M')"
        score=$(get_score)
        log "  Score: ${score}%"

        # Score caiu? Volta para modo fix
        if [ "$score" -lt "$SCORE_MIN" ]; then
            log "\n  ${YELLOW}⚠ Score ${score}% < ${SCORE_MIN}% — voltando ao Fix...${NC}"
            fix_round=1
            while true; do
                do_validate 3
                auto_commit "🧠 training: recovery fix #$fix_round"
                score=$(get_score)
                [ "$score" -ge "$SCORE_MIN" ] && break
                weak=$(get_weak_study_keys)
                [ -n "$weak" ] && do_study_weak "$weak" || do_expand
                auto_commit "🧠 training: recovery study #$fix_round"
                fix_round=$((fix_round + 1))
            done
            log "  ${GREEN}✅ Score recuperado: ${score}%${NC}"
        fi
    fi

    expand=$((expand + 1))
done
