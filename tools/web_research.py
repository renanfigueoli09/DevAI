"""
Web Research — busca na web e em registries de pacotes.

Fontes consultadas (todas gratuitas, sem API key):
  • npm registry        → versões de pacotes Node/TS
  • PyPI                → versões de pacotes Python
  • Maven Central       → versões de artefatos Java
  • NuGet               → versões de pacotes .NET
  • GitHub Releases API → versões de CLIs (nest, ng, dotnet)
  • DuckDuckGo Search   → comandos de framework, breaking changes, boas práticas

Cache local em ~/.devai/cache.json com TTL de 24h.
"""

import json
import time
import hashlib
import requests
from pathlib import Path
from typing import Optional
from rich.console import Console

console = Console()

CACHE_FILE = Path.home() / ".devai" / "cache.json"
CACHE_TTL  = 60 * 60 * 24   # 24 horas
TIMEOUT    = 8               # segundos por request

# ─── Cache ────────────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    try:
        if CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_cache(cache: dict):
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(cache, indent=2))
    except Exception:
        pass


def _cache_key(source: str, query: str) -> str:
    return hashlib.md5(f"{source}:{query}".encode()).hexdigest()


def _get_cached(source: str, query: str) -> Optional[str]:
    cache = _load_cache()
    key   = _cache_key(source, query)
    entry = cache.get(key)
    if entry and time.time() - entry.get("ts", 0) < CACHE_TTL:
        return entry.get("value")
    return None


def _set_cached(source: str, query: str, value: str):
    cache = _load_cache()
    cache[_cache_key(source, query)] = {"value": value, "ts": time.time()}
    _save_cache(cache)


# ─── Registries de pacotes ────────────────────────────────────────────────────

def npm_version(package: str) -> Optional[str]:
    """Versão mais recente de um pacote npm."""
    cached = _get_cached("npm", package)
    if cached:
        return cached
    try:
        r = requests.get(
            f"https://registry.npmjs.org/{package}/latest",
            timeout=TIMEOUT, headers={"Accept": "application/json"}
        )
        if r.ok:
            v = r.json().get("version")
            if v:
                _set_cached("npm", package, v)
                return v
    except Exception:
        pass
    return None


def pypi_version(package: str) -> Optional[str]:
    """Versão mais recente de um pacote PyPI."""
    cached = _get_cached("pypi", package)
    if cached:
        return cached
    try:
        r = requests.get(f"https://pypi.org/pypi/{package}/json", timeout=TIMEOUT)
        if r.ok:
            v = r.json().get("info", {}).get("version")
            if v:
                _set_cached("pypi", package, v)
                return v
    except Exception:
        pass
    return None


def maven_version(group: str, artifact: str) -> Optional[str]:
    """Versão mais recente de um artefato Maven."""
    key = f"{group}:{artifact}"
    cached = _get_cached("maven", key)
    if cached:
        return cached
    try:
        r = requests.get(
            "https://search.maven.org/solrsearch/select",
            params={"q": f"g:{group} AND a:{artifact}", "rows": "1", "wt": "json"},
            timeout=TIMEOUT,
        )
        if r.ok:
            docs = r.json().get("response", {}).get("docs", [])
            if docs:
                v = docs[0].get("latestVersion")
                if v:
                    _set_cached("maven", key, v)
                    return v
    except Exception:
        pass
    return None


def nuget_version(package: str) -> Optional[str]:
    """Versão mais recente de um pacote NuGet."""
    cached = _get_cached("nuget", package)
    if cached:
        return cached
    try:
        r = requests.get(
            f"https://api.nuget.org/v3-flatcontainer/{package.lower()}/index.json",
            timeout=TIMEOUT,
        )
        if r.ok:
            versions = r.json().get("versions", [])
            # Filtra pre-releases
            stable = [v for v in versions if not any(x in v for x in ["-alpha", "-beta", "-rc", "-preview"])]
            v = stable[-1] if stable else (versions[-1] if versions else None)
            if v:
                _set_cached("nuget", package, v)
                return v
    except Exception:
        pass
    return None


def github_release_version(owner: str, repo: str) -> Optional[str]:
    """Versão mais recente de um release do GitHub (sem auth, rate limit 60/h)."""
    key = f"{owner}/{repo}"
    cached = _get_cached("github", key)
    if cached:
        return cached
    try:
        r = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/releases/latest",
            timeout=TIMEOUT,
            headers={"Accept": "application/vnd.github+json"},
        )
        if r.ok:
            v = r.json().get("tag_name", "").lstrip("v")
            if v:
                _set_cached("github", key, v)
                return v
    except Exception:
        pass
    return None


# ─── DuckDuckGo Search ────────────────────────────────────────────────────────

def web_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Busca no DuckDuckGo com timeout agressivo para não travar.
    Fallback em cascata: ddgs → duckduckgo_search → DuckDuckGo API → []
    """
    cached = _get_cached("ddg", query)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    results = []

    # 1. Tenta ddgs (nome novo do pacote)
    try:
        from ddgs import DDGS
        with DDGS(timeout=8) as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if results:
            _set_cached("ddg", query, json.dumps(results))
            return results
    except ImportError:
        pass
    except Exception:
        pass

    # 2. Fallback: duckduckgo_search (nome antigo, com filtro de warning)
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from duckduckgo_search import DDGS as DDGS_OLD
            with DDGS_OLD(timeout=8) as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
        if results:
            _set_cached("ddg", query, json.dumps(results))
            return results
    except ImportError:
        pass
    except Exception:
        pass

    # 3. Fallback: DuckDuckGo Instant Answer API (sem autenticação)
    try:
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_redirect": "1", "no_html": "1"},
            timeout=TIMEOUT,
        )
        if r.ok:
            data = r.json()
            abstract = data.get("AbstractText", "")
            if abstract:
                results = [{"title": data.get("Heading", query),
                            "href": data.get("AbstractURL", ""),
                            "body": abstract}]
            for rt in data.get("RelatedTopics", [])[:max_results]:
                if isinstance(rt, dict) and rt.get("Text"):
                    results.append({"title": rt.get("Text", "")[:80],
                                    "href": rt.get("FirstURL", ""),
                                    "body": rt.get("Text", "")})
        if results:
            _set_cached("ddg", query, json.dumps(results))
    except Exception:
        pass

    return results


def search_and_summarize(query: str, llm=None, model: str = None) -> str:
    """
    Busca na web e usa o LLM para sumarizar os resultados.
    Retorna uma string com a resposta sintetizada.
    """
    results = web_search(query, max_results=5)
    if not results:
        return f"Nenhum resultado para: {query}"

    if not llm:
        # Sem LLM, retorna texto bruto
        return "\n".join(f"• {r.get('title','')}: {r.get('body','')[:200]}" for r in results[:3])

    snippets = "\n".join(
        f"[{i+1}] {r.get('title','')}\n{r.get('body','')[:300]}"
        for i, r in enumerate(results[:4])
    )
    prompt = f"Query: {query}\n\nSearch results:\n{snippets}\n\nSummarize the key facts briefly in 3-5 sentences."
    return llm.chat(
        model=model or "qwen2.5-coder:7b",
        messages=[{"role": "user", "content": prompt}],
        system="You are a technical research assistant. Summarize search results concisely and factually.",
        stream=False,
    )


# ─── Versões por stack ────────────────────────────────────────────────────────

def fetch_stack_versions(stack: str) -> dict:
    """
    Busca as versões mais recentes dos pacotes principais de cada stack.
    Retorna dict com versões para incluir no contexto do LLM.
    """
    cached = _get_cached("stack_versions", stack)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    console.print(f"[dim]🔍 Buscando versões atuais para {stack}...[/dim]")
    versions = {}

    if stack == "nestjs":
        versions = {
            "@nestjs/core":           npm_version("@nestjs/core"),
            "@nestjs/common":         npm_version("@nestjs/common"),
            "@nestjs/typeorm":        npm_version("@nestjs/typeorm"),
            "@nestjs/jwt":            npm_version("@nestjs/jwt"),
            "@nestjs/passport":       npm_version("@nestjs/passport"),
            "@nestjs/swagger":        npm_version("@nestjs/swagger"),
            "typeorm":                npm_version("typeorm"),
            "class-validator":        npm_version("class-validator"),
            "class-transformer":      npm_version("class-transformer"),
            "typescript":             npm_version("typescript"),
            "@nestjs/cli":            npm_version("@nestjs/cli"),
        }

    elif stack == "nextjs":
        versions = {
            "next":                   npm_version("next"),
            "react":                  npm_version("react"),
            "react-dom":              npm_version("react-dom"),
            "typescript":             npm_version("typescript"),
            "tailwindcss":            npm_version("tailwindcss"),
            "axios":                  npm_version("axios"),
            "zustand":                npm_version("zustand"),
            "@tanstack/react-query":  npm_version("@tanstack/react-query"),
            "react-hook-form":        npm_version("react-hook-form"),
            "zod":                    npm_version("zod"),
            "next-auth":              npm_version("next-auth"),
        }

    elif stack == "angular":
        versions = {
            "@angular/core":          npm_version("@angular/core"),
            "@angular/cli":           npm_version("@angular/cli"),
            "@angular/common":        npm_version("@angular/common"),
            "@angular/router":        npm_version("@angular/router"),
            "@angular/forms":         npm_version("@angular/forms"),
            "rxjs":                   npm_version("rxjs"),
            "typescript":             npm_version("typescript"),
            "zone.js":                npm_version("zone.js"),
        }

    elif stack == "spring-boot":
        versions = {
            "spring-boot":            maven_version("org.springframework.boot", "spring-boot-starter"),
            "spring-data-jpa":        maven_version("org.springframework.boot", "spring-boot-starter-data-jpa"),
            "spring-security":        maven_version("org.springframework.boot", "spring-boot-starter-security"),
            "lombok":                 maven_version("org.projectlombok", "lombok"),
            "mapstruct":              maven_version("org.mapstruct", "mapstruct"),
            "jjwt":                   maven_version("io.jsonwebtoken", "jjwt-api"),
            "springdoc-openapi":      maven_version("org.springdoc", "springdoc-openapi-starter-webmvc-ui"),
            "postgresql-driver":      maven_version("org.postgresql", "postgresql"),
        }

    elif stack == "python":
        versions = {
            "fastapi":                pypi_version("fastapi"),
            "uvicorn":                pypi_version("uvicorn"),
            "sqlalchemy":             pypi_version("sqlalchemy"),
            "alembic":                pypi_version("alembic"),
            "pydantic":               pypi_version("pydantic"),
            "pydantic-settings":      pypi_version("pydantic-settings"),
            "asyncpg":                pypi_version("asyncpg"),
            "python-jose":            pypi_version("python-jose"),
            "passlib":                pypi_version("passlib"),
            "pytest":                 pypi_version("pytest"),
            "pytest-asyncio":         pypi_version("pytest-asyncio"),
            "httpx":                  pypi_version("httpx"),
        }

    elif stack == "dotnet":
        versions = {
            "Microsoft.EntityFrameworkCore":             nuget_version("Microsoft.EntityFrameworkCore"),
            "Npgsql.EntityFrameworkCore.PostgreSQL":     nuget_version("Npgsql.EntityFrameworkCore.PostgreSQL"),
            "Microsoft.AspNetCore.Authentication.JwtBearer": nuget_version("Microsoft.AspNetCore.Authentication.JwtBearer"),
            "Swashbuckle.AspNetCore":                    nuget_version("Swashbuckle.AspNetCore"),
            "NSubstitute":                               nuget_version("NSubstitute"),
            "FluentValidation":                          nuget_version("FluentValidation"),
            "xunit":                                     nuget_version("xunit"),
        }

    # Remove None values
    versions = {k: v for k, v in versions.items() if v}

    if versions:
        _set_cached("stack_versions", stack, json.dumps(versions))

    return versions


def fetch_scaffold_command(stack: str) -> dict:
    """
    Busca o comando de scaffold mais atual para a stack.
    Retorna dict com command, flags, notes.
    """
    cached = _get_cached("scaffold_cmd", stack)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    # Comandos conhecidos com flags mais recentes
    KNOWN = {
        "nestjs": {
            "command": "npx @nestjs/cli new {name} --package-manager npm --strict --skip-git",
            "check":   "@nestjs/cli",
            "runtime": "node",
        },
        "nextjs": {
            "command": (
                "npx create-next-app@latest {name} "
                "--typescript --tailwind --eslint --app --src-dir "
                "--import-alias '@/*' --no-git"
            ),
            "check":   "create-next-app",
            "runtime": "node",
        },
        "angular": {
            "command": (
                "npx @angular/cli@latest new {name} "
                "--routing --style=scss --skip-git "
                "--standalone --ssr=false"
            ),
            "check":   "@angular/cli",
            "runtime": "node",
        },
        "spring-boot": {
            "command": "curl https://start.spring.io/starter.zip [params]",
            "check":   None,
            "runtime": "java",
        },
        "python": {
            "command": "python3 -m venv .venv && pip install fastapi uvicorn[standard]",
            "check":   None,
            "runtime": "python3",
        },
        "dotnet": {
            "command": "dotnet new sln -n {name} && dotnet new webapi -n {name}.Api",
            "check":   "dotnet",
            "runtime": "dotnet",
        },
    }

    result = KNOWN.get(stack, {"command": "", "check": None, "runtime": ""})

    # Tenta buscar versão mais recente do CLI
    if stack == "nestjs":
        v = npm_version("@nestjs/cli")
        if v:
            result["cli_version"] = v
            result["command"] = f"npx @nestjs/cli@{v} new {{name}} --package-manager npm --strict --skip-git"

    elif stack == "nextjs":
        v = npm_version("create-next-app")
        if v:
            result["cli_version"] = v
            result["command"] = (
                f"npx create-next-app@{v} {{name}} "
                "--typescript --tailwind --eslint --app --src-dir "
                "--import-alias '@/*' --no-git"
            )

    elif stack == "angular":
        v = npm_version("@angular/cli")
        if v:
            result["cli_version"] = v
            result["command"] = (
                f"npx @angular/cli@{v} new {{name}} "
                "--routing --style=scss --skip-git --standalone --ssr=false"
            )

    elif stack == "dotnet":
        v = github_release_version("dotnet", "sdk")
        if v:
            result["cli_version"] = v

    _set_cached("scaffold_cmd", stack, json.dumps(result))
    return result


def versions_to_context(versions: dict, stack: str) -> str:
    """Converte dict de versões em texto para o contexto do LLM."""
    if not versions:
        return ""
    lines = [f"CURRENT PACKAGE VERSIONS for {stack} (use these exact versions):"]
    for pkg, ver in versions.items():
        lines.append(f"  {pkg}: {ver}")
    return "\n".join(lines)


def clear_cache():
    """Limpa o cache de pesquisas."""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
    console.print("[green]✓ Cache limpo[/green]")


def cache_info() -> dict:
    """Retorna info sobre o cache atual."""
    cache = _load_cache()
    now = time.time()
    valid   = sum(1 for v in cache.values() if now - v.get("ts", 0) < CACHE_TTL)
    expired = len(cache) - valid
    size    = CACHE_FILE.stat().st_size if CACHE_FILE.exists() else 0
    return {"total": len(cache), "valid": valid, "expired": expired, "size_kb": size // 1024}
