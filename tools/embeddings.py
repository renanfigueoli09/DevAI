"""
Embeddings — busca semântica usando Ollama para gerar vetores.

Modelo: nomic-embed-text (137MB, rápido, bom para código)
Instalar: ollama pull nomic-embed-text

Como funciona:
  1. Ao salvar (search/train): gera embedding do conteúdo e armazena no SQLite
  2. Ao consultar (new/feature/fix): gera embedding da query e encontra os N
     conteúdos mais similares por cosseno — sem depender de palavras exatas

Fallback automático: se Ollama ou o modelo não estiver disponível,
usa busca por palavras-chave (comportamento anterior).
"""

import json
import math
import time
from typing import Optional
from rich.console import Console

console = Console()

EMBED_MODEL   = "nomic-embed-text"
OLLAMA_URL    = "http://localhost:11434"
_model_ok: Optional[bool] = None   # cache do estado do modelo
_last_check   = 0.0
CHECK_INTERVAL = 60.0               # verifica disponibilidade a cada 60s


# ─── Disponibilidade ──────────────────────────────────────────────────────────

def model_available() -> bool:
    """Verifica se nomic-embed-text está disponível no Ollama."""
    global _model_ok, _last_check

    now = time.time()
    if _model_ok is not None and (now - _last_check) < CHECK_INTERVAL:
        return _model_ok

    _last_check = now
    try:
        import requests
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        if r.ok:
            models = [m["name"] for m in r.json().get("models", [])]
            _model_ok = any(EMBED_MODEL in m for m in models)
            return _model_ok
    except Exception:
        pass

    _model_ok = False
    return False


def pull_model_if_needed() -> bool:
    """Puxa o modelo de embedding se não estiver instalado."""
    if model_available():
        return True

    console.print(f"[cyan]→ Baixando modelo de embeddings ({EMBED_MODEL})...[/cyan]")
    console.print("[dim]  Execute: ollama pull nomic-embed-text[/dim]")
    try:
        import subprocess, shutil
        if shutil.which("ollama"):
            subprocess.run(
                ["ollama", "pull", EMBED_MODEL],
                timeout=300, check=True,
                capture_output=False,
            )
            global _model_ok
            _model_ok = True
            return True
    except Exception as e:
        console.print(f"[yellow]⚠ Não foi possível baixar {EMBED_MODEL}: {e}[/yellow]")

    return False


# ─── Geração de embedding ─────────────────────────────────────────────────────

def embed(text: str) -> Optional[list[float]]:
    """
    Gera embedding para o texto usando nomic-embed-text via Ollama.
    Retorna lista de floats ou None se indisponível.
    """
    if not model_available():
        return None

    # Trunca para 2000 chars (contexto do modelo)
    text = text[:2000].strip()
    if not text:
        return None

    try:
        import requests
        r = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
            timeout=15,
        )
        if r.ok:
            data = r.json()
            emb = data.get("embedding") or data.get("embeddings")
            if emb and isinstance(emb, list):
                return emb
    except Exception:
        pass

    return None


def embed_batch(texts: list[str]) -> list[Optional[list[float]]]:
    """Gera embeddings para múltiplos textos."""
    return [embed(t) for t in texts]


# ─── Similaridade ─────────────────────────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosseno entre dois vetores. Retorna 0.0 se inválido."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot  = sum(x * y for x, y in zip(a, b))
    na   = math.sqrt(sum(x * x for x in a))
    nb   = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def top_k_similar(
    query_emb: list[float],
    candidates: list[tuple],   # [(key, content, embedding_json), ...]
    k: int = 5,
    min_score: float = 0.3,
) -> list[tuple[str, str, float]]:
    """
    Retorna os top-k candidatos mais similares à query.
    Retorna lista de (key, content, score).
    """
    scored = []
    for key, content, emb_json in candidates:
        if not emb_json:
            continue
        try:
            emb = json.loads(emb_json) if isinstance(emb_json, str) else emb_json
            score = cosine_similarity(query_emb, emb)
            if score >= min_score:
                scored.append((key, content, score))
        except Exception:
            continue

    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[:k]
