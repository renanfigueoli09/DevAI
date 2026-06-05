"""
Vector Store — Armazenamento vetorial com LanceDB (não é SQL).

LanceDB armazena os dados como arquivos Arrow/Parquet + índice vetorial.
Suporta busca semântica nativa sem precisar de servidor.
Pode ser commitado no git junto com o projeto.

Estrutura em disco:
  training/
    vectors/          ← LanceDB (Arrow files)
      knowledge.lance/
    patterns/         ← JSON files por tópico (legível/commitável)
      nestjs.json
      docker.json
      ...
    index.json        ← índice de todos os itens

Fallback: se LanceDB não estiver disponível, usa JSON + SQLite.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Optional

DEVAI_DIR    = Path(os.environ.get("DEVAI_DIR", Path(__file__).parent.parent)).resolve()
TRAINING_DIR = DEVAI_DIR / "training"
VECTORS_DIR  = TRAINING_DIR / "vectors"
PATTERNS_DIR = TRAINING_DIR / "patterns"
INDEX_FILE   = TRAINING_DIR / "index.json"

_db = None          # LanceDB connection
_table = None       # LanceDB table
_use_lance = None   # cached availability check


def _lance_available() -> bool:
    global _use_lance
    if _use_lance is not None:
        return _use_lance
    try:
        import lancedb
        _use_lance = True
    except ImportError:
        _use_lance = False
    return _use_lance


def _get_table():
    """Returns (or creates) the LanceDB table."""
    global _db, _table
    if _table is not None:
        return _table

    import lancedb
    import pyarrow as pa

    VECTORS_DIR.mkdir(parents=True, exist_ok=True)
    _db = lancedb.connect(str(VECTORS_DIR))

    schema = pa.schema([
        pa.field("id",         pa.string()),
        pa.field("topic",      pa.string()),
        pa.field("source",     pa.string()),
        pa.field("content",    pa.string()),
        pa.field("created_at", pa.float64()),
        pa.field("vector",     pa.list_(pa.float32(), 768)),
    ])

    if "knowledge" in _db.table_names():
        _table = _db.open_table("knowledge")
    else:
        _table = _db.create_table("knowledge", schema=schema)

    return _table


def _load_index() -> dict:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_index(idx: dict):
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps(idx, indent=2, ensure_ascii=False))


def _normalize_topic(topic: str) -> str:
    """Normalize topic name: underscores→hyphens, lowercase."""
    return re.sub(r"[^\w-]", "-", topic.lower()).strip("-")


def _save_pattern_file(topic: str, key: str, content: str, source: str):
    """Saves to a readable JSON file per topic (for git commit)."""
    PATTERNS_DIR.mkdir(parents=True, exist_ok=True)
    safe = _normalize_topic(topic)
    pattern_file = PATTERNS_DIR / f"{safe}.json"

    data = {}
    if pattern_file.exists():
        try:
            data = json.loads(pattern_file.read_text())
        except Exception:
            data = {}

    data[key] = {
        "content": content,
        "source": source,
        "updated_at": time.time(),
    }
    pattern_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))


# ─── Public API ───────────────────────────────────────────────────────────────

def save(
    key: str,
    content: str,
    topic: str = "general",
    source: str = "manual",
    embedding: Optional[list] = None,
) -> None:
    """
    Saves an entry to the vector store.
    Auto-generates embedding if nomic-embed-text is available.
    Saves to:
      1. LanceDB (if available) — for fast vector search
      2. JSON pattern files — human-readable, committable
      3. Index file — fast key lookup
    """
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)

    # Generate embedding if not provided
    emb = embedding
    if emb is None:
        try:
            from tools.embeddings import embed, model_available
            if model_available():
                emb = embed(f"{key}\n{content[:600]}")
        except Exception:
            pass

    # Save to LanceDB
    if _lance_available() and emb:
        try:
            import pyarrow as pa
            tbl = _get_table()

            # Delete existing entry with same id
            try:
                tbl.delete(f"id = '{key}'")
            except Exception:
                pass

            # Pad/truncate embedding to 768 dims
            vec = emb[:768] if len(emb) >= 768 else emb + [0.0] * (768 - len(emb))

            tbl.add([{
                "id":         key,
                "topic":      topic,
                "source":     source,
                "content":    content[:4000],
                "created_at": time.time(),
                "vector":     vec,
            }])
        except Exception:
            pass  # fallback to JSON

    topic = _normalize_topic(topic) if topic else "general"
    # Always save to readable JSON files
    _save_pattern_file(topic, key, content, source)

    # Update index
    idx = _load_index()
    idx[key] = {"topic": topic, "source": source, "ts": time.time(), "size": len(content)}
    _save_index(idx)


def search_relevant(
    description: str,
    limit: int = 5,
    topic_filter: Optional[list] = None,
    exclude_topics: Optional[list] = None,
) -> str:
    """
    Semantic vector search — finds most relevant training for the description.
    Falls back to keyword search in JSON files if LanceDB/embeddings unavailable.
    """
    if not description.strip():
        return ""

    # ── Vector search (LanceDB + nomic-embed-text) ────────────────────────────
    if _lance_available():
        try:
            from tools.embeddings import embed, model_available
            if model_available():
                query_emb = embed(description[:400])
                if query_emb:
                    tbl = _get_table()
                    vec = query_emb[:768] if len(query_emb) >= 768 else query_emb + [0.0] * (768 - len(query_emb))

                    query = tbl.search(vec).limit(limit * 3)
                    results = query.to_list()

                    # Apply topic filter
                    if topic_filter:
                        results = [r for r in results if any(f in r["topic"] for f in topic_filter)]
                    if exclude_topics:
                        results = [r for r in results if not any(e in r["topic"] for e in exclude_topics)]

                    results = results[:limit]

                    if results:
                        lines = ["=== TRAINING (vector search) ==="]
                        for r in results:
                            lines.append(f"\n[{r['id']}] ({r['topic']})")
                            lines.append(r["content"][:400])
                        return "\n".join(lines)
        except Exception:
            pass

    # ── Fallback: JSON pattern files keyword search ────────────────────────────
    words = set(re.findall(r'\b\w{4,}\b', description.lower()))
    results = []

    for json_file in sorted(PATTERNS_DIR.glob("*.json")):
        topic_name = json_file.stem.replace("_", "-")
        if topic_filter and not any(f.replace("-","_") in json_file.stem for f in topic_filter):
            continue
        if exclude_topics and any(e.replace("-","_") in json_file.stem for e in exclude_topics):
            continue

        try:
            data = json.loads(json_file.read_text())
            for key, entry in data.items():
                content = entry.get("content", "")
                content_words = set(re.findall(r'\b\w{4,}\b', (key + " " + content[:300]).lower()))
                score = len(words & content_words)
                if score > 0:
                    results.append((score, key, content, topic_name))
        except Exception:
            continue

    results.sort(reverse=True)
    if results:
        lines = ["=== TRAINING (keyword search) ==="]
        for _, key, content, topic in results[:limit]:
            lines.append(f"\n[{key}] ({topic})")
            lines.append(content[:350])
        return "\n".join(lines)

    return ""


def get(key: str) -> Optional[str]:
    """Get entry by exact key."""
    # Check JSON files first (faster)
    for json_file in PATTERNS_DIR.glob("*.json"):
        try:
            data = json.loads(json_file.read_text())
            if key in data:
                return data[key]["content"]
        except Exception:
            continue
    return None


def list_all() -> list[dict]:
    idx = _load_index()
    now = time.time()
    return [
        {
            "key": k, "topic": v.get("topic", "?"),
            "source": v.get("source", "?"), "size": v.get("size", 0),
            "age_hours": int((now - v.get("ts", now)) / 3600),
            "has_embedding": _lance_available(),
        }
        for k, v in sorted(idx.items(), key=lambda x: x[1].get("ts", 0), reverse=True)
    ]


def stats() -> dict:
    idx = _load_index()
    topics: dict[str, int] = {}
    for v in idx.values():
        t = v.get("topic", "general")
        topics[t] = topics.get(t, 0) + 1

    has_lance = _lance_available()
    with_emb = 0
    if has_lance:
        try:
            with_emb = _get_table().count_rows()
        except Exception:
            pass

    return {
        "total": len(idx),
        "with_embedding": with_emb,
        "without_embedding": len(idx) - with_emb,
        "topics": topics,
        "storage": "lancedb+json" if has_lance else "json",
    }


def clear_all():
    import shutil
    if PATTERNS_DIR.exists():
        shutil.rmtree(str(PATTERNS_DIR))
    if VECTORS_DIR.exists():
        shutil.rmtree(str(VECTORS_DIR))
    if INDEX_FILE.exists():
        INDEX_FILE.unlink()
    global _db, _table
    _db = _table = None


def backfill_embeddings() -> int:
    """Generate embeddings for entries that don't have them yet."""
    try:
        from tools.embeddings import embed, model_available
        if not model_available():
            return 0
        idx = _load_index()
        count = 0
        for key, meta in list(idx.items())[:30]:
            content = get(key)
            if content:
                emb = embed(f"{key}\n{content[:600]}")
                if emb:
                    save(key, content, topic=meta.get("topic","general"),
                         source=meta.get("source","manual"), embedding=emb)
                    count += 1
        return count
    except Exception:
        return 0


def _merge_duplicate_patterns():
    """Merges topic files that are duplicates due to naming inconsistency."""
    if not PATTERNS_DIR.exists():
        return
    seen: dict[str, Path] = {}
    for f in PATTERNS_DIR.glob("*.json"):
        normalized = _normalize_topic(f.stem)
        canonical = PATTERNS_DIR / f"{normalized}.json"
        if f.stem != normalized:
            # This file has wrong name (e.g. common-errors.json → common_errors.json)
            try:
                existing = json.loads(canonical.read_text()) if canonical.exists() else {}
                current  = json.loads(f.read_text())
                merged   = {**existing, **current}
                canonical.write_text(json.dumps(merged, indent=2, ensure_ascii=False))
                f.unlink()
            except Exception:
                pass


def export_markdown() -> Path:
    export_dir = TRAINING_DIR / "export"
    export_dir.mkdir(parents=True, exist_ok=True)

    # First: merge any duplicate files (common_errors.json + common-errors.json → common-errors.json)
    seen_normalized: dict[str, Path] = {}
    for jf in list(PATTERNS_DIR.glob("*.json")):
        norm = re.sub(r"_", "-", jf.stem.lower())
        norm_path = PATTERNS_DIR / f"{norm}.json"
        if norm != jf.stem.lower():
            # Rename to normalized name, merging if both exist
            if norm_path.exists():
                try:
                    existing = json.loads(norm_path.read_text())
                    duplicate = json.loads(jf.read_text())
                    existing.update(duplicate)
                    norm_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
                    jf.unlink()
                except Exception:
                    pass
            else:
                jf.rename(norm_path)

    # Merge any duplicate files (common_errors.json + common-errors.json → common_errors.json)
    _merge_duplicate_patterns()

    for json_file in PATTERNS_DIR.glob("*.json"):
        try:
            data = json.loads(json_file.read_text())
            md = export_dir / json_file.with_suffix(".md").name
            lines = [f"# {json_file.stem}\n\n*{len(data)} items*\n"]
            for key, entry in data.items():
                import datetime
                dt = datetime.datetime.fromtimestamp(entry.get("updated_at", 0)).strftime("%Y-%m-%d")
                lines += [f"\n## {key}\n*{entry.get('source','?')} | {dt}*\n\n```\n{entry.get('content','')}\n```\n"]
            md.write_text("\n".join(lines))
        except Exception:
            continue

    s = stats()
    (export_dir / "README.md").write_text(
        f"# DevAI Training Knowledge\n\n"
        f"*{s['total']} items | storage: {s['storage']} | "
        f"{s['with_embedding']} with embeddings*\n\n" +
        "\n".join(f"- **{t}**: {c} items" for t, c in sorted(s["topics"].items()))
    )

    return export_dir


def _infer_topic(key: str, content: str) -> str:
    text = (key + " " + content[:200]).lower()
    for topic, kws in [
        ("nestjs-mongodb",  ["mongoose", "schema", "prop", "injectmodel", "hydrateddocument"]),
        ("nestjs-typeorm",  ["typeorm", "entity", "repository", "injectrepository"]),
        ("nestjs-auth",     ["jwt", "passport", "strategy", "guard", "bearer"]),
        ("nestjs-kafka",    ["kafka", "producer", "consumer", "eventemitter"]),
        ("nestjs-redis",    ["redis", "cache", "bull", "ioredis", "sentinel"]),
        ("nestjs",          ["nestjs", "nest", "@module", "controller", "injectable"]),
        ("spring-boot",     ["spring", "java", "springboot", "@restcontroller", "@service"]),
        ("python-fastapi",  ["fastapi", "pydantic", "uvicorn", "async def"]),
        ("dotnet",          ["aspnet", "csharp", "dotnet", "iservicecollection"]),
        ("nextjs",          ["nextjs", "next.js", "app router", "server component"]),
        ("docker",          ["docker", "compose", "dockerfile", "container", "healthcheck"]),
        ("typescript",      ["typescript", "interface", "decorator", "reflect-metadata"]),
    ]:
        if any(kw in text for kw in kws):
            return topic
    return "general"
