"""
Training Store — SQLite com busca semântica por embeddings.

Armazena tudo que foi aprendido via:
  devai search "X"           → pesquisa web salva aqui
  devai train --file X       → arquivo analisado salvo aqui
  devai train --project /X/  → projeto de referência salvo aqui

Na hora de gerar código (new/feature/fix):
  search_relevant(description) → cosine similarity → top-K mais relevantes

Localização: $DEVAI_DIR/training/knowledge.db  (commitável no git)
"""

import json
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional
from rich.console import Console

console = Console()

DEVAI_DIR    = Path(os.environ.get("DEVAI_DIR", Path(__file__).parent.parent)).resolve()
TRAINING_DIR = DEVAI_DIR / "training"
DB_PATH      = TRAINING_DIR / "knowledge.db"


def _get_conn() -> sqlite3.Connection:
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            topic      TEXT    NOT NULL DEFAULT 'general',
            key        TEXT    NOT NULL UNIQUE,
            content    TEXT    NOT NULL,
            source     TEXT    DEFAULT 'manual',
            embedding  TEXT,
            created_at REAL    DEFAULT (unixepoch()),
            updated_at REAL    DEFAULT (unixepoch())
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_topic ON knowledge(topic)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_key   ON knowledge(key)")
    conn.commit()
    return conn


# ─── Salvar ──────────────────────────────────────────────────────────────────

def save(
    key:     str,
    content: str,
    topic:   str = "general",
    source:  str = "manual",
    generate_embedding: bool = True,
) -> None:
    """
    Salva item no training store.
    Gera embedding automaticamente se nomic-embed-text estiver disponível.
    """
    embedding_json = None

    if generate_embedding:
        try:
            from tools.embeddings import embed, model_available
            if model_available():
                emb = embed(f"{key}\n{content[:800]}")
                if emb:
                    embedding_json = json.dumps(emb)
        except Exception:
            pass

    try:
        conn = _get_conn()
        conn.execute("""
            INSERT INTO knowledge (topic, key, content, source, embedding, updated_at)
            VALUES (?, ?, ?, ?, ?, unixepoch())
            ON CONFLICT(key) DO UPDATE SET
                content    = excluded.content,
                topic      = excluded.topic,
                source     = excluded.source,
                embedding  = COALESCE(excluded.embedding, embedding),
                updated_at = unixepoch()
        """, (topic, key, content, source, embedding_json))
        conn.commit()
        conn.close()

        if embedding_json:
            console.print(f"  [dim]✓ Embedding gerado para: {key[:40]}[/dim]")
    except Exception as e:
        console.print(f"[dim]⚠ training store save: {e}[/dim]")


def backfill_embeddings() -> int:
    """
    Gera embeddings para itens que ainda não têm.
    Chamado em background quando o modelo está disponível.
    """
    try:
        from tools.embeddings import embed, model_available
        if not model_available():
            return 0

        conn = _get_conn()
        rows = conn.execute(
            "SELECT key, content FROM knowledge WHERE embedding IS NULL LIMIT 20"
        ).fetchall()

        updated = 0
        for key, content in rows:
            emb = embed(f"{key}\n{content[:800]}")
            if emb:
                conn.execute(
                    "UPDATE knowledge SET embedding = ? WHERE key = ?",
                    (json.dumps(emb), key)
                )
                updated += 1

        if updated:
            conn.commit()
            console.print(f"  [dim]✓ {updated} embedding(s) gerado(s)[/dim]")
        conn.close()
        return updated
    except Exception:
        return 0


# ─── Consultar ────────────────────────────────────────────────────────────────

def get(key: str) -> Optional[str]:
    """Busca item pelo key exato."""
    try:
        conn = _get_conn()
        row = conn.execute(
            "SELECT content FROM knowledge WHERE key = ?", (key,)
        ).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def search_relevant(
    description: str,
    limit: int = 5,
    topic_filter: list[str] | None = None,   # ex: ["nestjs", "mongodb"] — exclui docker/devops
    exclude_topics: list[str] | None = None,  # ex: ["docker", "devops", "github-actions"]
) -> str:
    """
    Busca semântica: encontra conteúdos relevantes para a descrição.

    topic_filter:    se fornecido, só retorna itens desses tópicos
    exclude_topics:  exclui itens desses tópicos (evita poluir código com Docker/CI)

    1. Busca por embedding (cosine similarity) — preciso
    2. Fallback: busca por palavras-chave (LIKE)
    """
    if not description.strip():
        return ""

    # ── Cláusula de filtro de tópico ────────────────────────────────────────
    def _topic_ok(topic: str) -> bool:
        if topic_filter and not any(f in topic for f in topic_filter):
            return False
        if exclude_topics and any(e in topic for e in exclude_topics):
            return False
        return True

    # ── Tentativa 1: busca semântica por embedding ─────────────────────────
    try:
        from tools.embeddings import embed, model_available, top_k_similar
        if model_available():
            query_emb = embed(description[:500])
            if query_emb:
                conn = _get_conn()
                # Aplica filtro de tópico na query SQL quando possível
                if topic_filter:
                    placeholders = ",".join("?" * len(topic_filter))
                    rows = conn.execute(
                        f"SELECT key, content, embedding FROM knowledge "
                        f"WHERE embedding IS NOT NULL "
                        f"AND ({" OR ".join(f"topic LIKE ?" for _ in topic_filter)})",
                        [f"%{t}%" for t in topic_filter]
                    ).fetchall()
                elif exclude_topics:
                    exc_clause = " AND ".join(f"topic NOT LIKE ?" for _ in exclude_topics)
                    rows = conn.execute(
                        f"SELECT key, content, embedding FROM knowledge "
                        f"WHERE embedding IS NOT NULL AND {exc_clause}",
                        [f"%{t}%" for t in exclude_topics]
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT key, content, embedding FROM knowledge "
                        "WHERE embedding IS NOT NULL"
                    ).fetchall()
                conn.close()

                if rows:
                    results = top_k_similar(query_emb, rows, k=limit, min_score=0.25)
                    if results:
                        lines = ["=== TRAINING ==="]
                        for key, content, score in results:
                            lines.append(f"\n[{key}]")
                            lines.append(content[:350])
                        return "\n".join(lines)
    except Exception:
        pass

    # ── Fallback: busca por palavras-chave ─────────────────────────────────
    try:
        words = re.findall(r'\b\w{4,}\b', description.lower())
        if not words:
            return ""

        conn = _get_conn()
        like_clauses = " OR ".join("(key LIKE ? OR content LIKE ?)" for _ in words[:5])
        params = []
        for w in words[:5]:
            params.extend([f"%{w}%", f"%{w}%"])

        topic_clause = ""
        topic_params = []
        if topic_filter:
            topic_clause = f" AND ({" OR ".join("topic LIKE ?" for _ in topic_filter)})"
            topic_params = [f"%{t}%" for t in topic_filter]
        elif exclude_topics:
            topic_clause = " AND " + " AND ".join("topic NOT LIKE ?" for _ in exclude_topics)
            topic_params = [f"%{t}%" for t in exclude_topics]

        rows = conn.execute(
            f"SELECT key, content FROM knowledge WHERE ({like_clauses}){topic_clause} LIMIT {limit}",
            params + topic_params
        ).fetchall()
        conn.close()

        if rows:
            lines = ["=== TRAINING ==="]
            for key, content in rows:
                lines.append(f"\n[{key}]")
                lines.append(content[:300])
            return "\n".join(lines)
    except Exception:
        pass

    return ""


# ─── Gerenciamento ────────────────────────────────────────────────────────────

def list_all() -> list[dict]:
    try:
        conn = _get_conn()
        rows = conn.execute("""
            SELECT topic, key, source,
                   length(content),
                   CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END,
                   updated_at
            FROM knowledge ORDER BY updated_at DESC
        """).fetchall()
        conn.close()
        return [
            {
                "topic":     r[0], "key": r[1], "source": r[2],
                "size":      r[3], "has_embedding": bool(r[4]),
                "age_hours": int((time.time() - r[5]) / 3600),
            }
            for r in rows
        ]
    except Exception:
        return []


def delete(key: str) -> None:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM knowledge WHERE key = ?", (key,))
        conn.commit()
        conn.close()
    except Exception:
        pass


def clear_all() -> None:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM knowledge")
        conn.commit()
        conn.close()
    except Exception:
        pass


def export_markdown() -> Path:
    """Exporta todo o banco para Markdown commitável."""
    export_dir = TRAINING_DIR / "export"
    export_dir.mkdir(parents=True, exist_ok=True)

    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT topic, key, content, source, updated_at FROM knowledge ORDER BY topic, key"
        ).fetchall()
        conn.close()
    except Exception:
        return export_dir

    by_topic: dict[str, list] = {}
    for topic, key, content, source, updated_at in rows:
        by_topic.setdefault(topic, []).append((key, content, source, updated_at))

    for topic, items in by_topic.items():
        safe = re.sub(r"[^\w]", "_", topic)
        md = export_dir / f"{safe}.md"
        import datetime
        lines = [f"# {topic}\n\n*{len(items)} items*\n"]
        for key, content, source, ts in items:
            dt = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            lines += [f"\n## {key}\n*{source} | {dt}*\n\n{content}\n"]
        md.write_text("\n".join(lines), encoding="utf-8")

    idx = export_dir / "README.md"
    items_total = sum(len(v) for v in by_topic.values())
    try:
        from tools.embeddings import model_available
        embed_note = "✓ Semantic search ativo" if model_available() else "○ Instale nomic-embed-text para busca semântica"
    except Exception:
        embed_note = ""
    idx.write_text(
        f"# DevAI Training\n\n*{items_total} items | {embed_note}*\n\n" +
        "\n".join(f"- [{t}]({re.sub(r'[^\\w]','_',t)}.md) — {len(v)} items"
                  for t, v in sorted(by_topic.items())),
        encoding="utf-8"
    )

    console.print(f"[green]✓ Exportado: {export_dir}[/green]")
    console.print("[dim]  git add training/ && git commit -m 'training: update'[/dim]")
    return export_dir


def stats() -> dict:
    """Retorna estatísticas do training store."""
    try:
        conn = _get_conn()
        total = conn.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        with_emb = conn.execute(
            "SELECT COUNT(*) FROM knowledge WHERE embedding IS NOT NULL"
        ).fetchone()[0]
        topics = conn.execute(
            "SELECT topic, COUNT(*) FROM knowledge GROUP BY topic ORDER BY COUNT(*) DESC"
        ).fetchall()
        conn.close()
        return {
            "total": total,
            "with_embedding": with_emb,
            "without_embedding": total - with_emb,
            "topics": {t: c for t, c in topics},
        }
    except Exception:
        return {"total": 0, "with_embedding": 0, "without_embedding": 0, "topics": {}}


def _infer_topic(key: str, content: str) -> str:
    """Infere tópico a partir do key/conteúdo."""
    text = (key + " " + content[:200]).lower()
    for topic, keywords in [
        ("nestjs",     ["nestjs", "nest", "@nestjs", "module", "controller", "service"]),
        ("mongodb",    ["mongo", "mongoose", "schema", "document"]),
        ("docker",     ["docker", "compose", "dockerfile", "container"]),
        ("kafka",      ["kafka", "producer", "consumer", "topic", "microservice"]),
        ("redis",      ["redis", "sentinel", "cache", "ioredis"]),
        ("auth",       ["jwt", "auth", "passport", "token", "bearer"]),
        ("typescript", ["typescript", "interface", "decorator", "type"]),
        ("spring",     ["spring", "java", "maven", "gradle"]),
        ("python",     ["fastapi", "pydantic", "sqlalchemy", "django"]),
        ("webpack",    ["webpack", "vite", "rollup", "esbuild"]),
    ]:
        if any(kw in text for kw in keywords):
            return topic
    return "general"
