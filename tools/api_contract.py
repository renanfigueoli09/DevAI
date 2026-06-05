"""
API Contract Extractor

Lê os arquivos gerados do backend e produz um contrato compacto
para o frontend saber exatamente:
  - Quais endpoints existem
  - Quais tipos/DTOs usar
  - Como autenticar
  - A URL base da API

Isso é passado como contexto para cada arquivo do frontend,
garantindo que o frontend seja coerente com o backend gerado.
"""

import re
from pathlib import Path
from rich.console import Console
from config import MODEL_CODE

console = Console()


def extract_api_contract(
    backend_files: list[dict],
    stack: str,
    entities: list[str],
    has_auth: bool,
    api_port: int,
    llm,
) -> dict:
    """
    Extrai o contrato de API a partir dos arquivos do backend.
    Retorna um dict com:
      - endpoints: lista de {method, path, request, response}
      - types: tipos TypeScript/interfaces compartilhadas
      - auth: como autenticar (header, token type)
      - base_url: URL base
      - summary: texto compacto para contexto do frontend
    """
    # Pega só os arquivos mais relevantes (controllers, DTOs, interfaces)
    relevant = _pick_relevant_files(backend_files)

    if not relevant:
        return _fallback_contract(entities, has_auth, api_port, stack)

    console.print("\n[dim]→ Extraindo contrato de API do backend...[/dim]")

    # Monta prompt compacto com os arquivos relevantes
    files_text = ""
    budget = 3000  # tokens budget
    for f in relevant:
        snippet = f"### {f['path']}\n{f['content'][:600]}\n"
        if len(files_text) + len(snippet) > budget:
            break
        files_text += snippet

    prompt = f"""Backend stack: {stack}
Entities: {', '.join(entities)}
Has JWT auth: {has_auth}

Backend files:
{files_text}

Extract the API contract. Return ONLY a raw JSON object:
{{
  "base_url": "http://localhost:{api_port}/api/v1",
  "auth_header": "Authorization: Bearer <token>",
  "auth_endpoint": "/auth/login",
  "endpoints": [
    {{"method": "GET",  "path": "/products",     "response": "Product[]"}},
    {{"method": "GET",  "path": "/products/:id", "response": "Product"}},
    {{"method": "POST", "path": "/products",     "request": "CreateProductDto", "response": "Product"}},
    {{"method": "PUT",  "path": "/products/:id", "request": "UpdateProductDto", "response": "Product"}},
    {{"method": "DELETE","path": "/products/:id","response": "void"}}
  ],
  "types": {{
    "Product": {{"id": "string", "name": "string", "price": "number", "createdAt": "string"}},
    "CreateProductDto": {{"name": "string", "price": "number"}}
  }}
}}"""

    system = (
        "You are an API documentation expert. "
        "Read backend code and extract the REST API contract. "
        "Return ONLY a raw JSON object, no markdown."
    )

    resp = llm.chat(
        model=MODEL_CODE,
        messages=[{"role": "user", "content": prompt}],
        system=system,
        stream=False,
    )

    contract = _parse_json(resp)
    if not contract:
        console.print("[yellow]  ↻ Usando contrato padrão (extração falhou)[/yellow]")
        contract = _fallback_contract(entities, has_auth, api_port, stack)
    else:
        console.print(f"  [green]✓[/green] {len(contract.get('endpoints', []))} endpoint(s) mapeado(s)")

    # Adiciona o summary em texto compacto (fica no shared_ctx do generator)
    contract["summary"] = _build_summary(contract, entities, has_auth, api_port)
    return contract


def _pick_relevant_files(files: list[dict]) -> list[dict]:
    """Prioriza controllers, DTOs e interfaces para extração do contrato."""
    priority = []
    secondary = []
    for f in files:
        path = f.get("path", "").lower()
        if any(x in path for x in ["controller", "dto", "interface", "router", "endpoint", "schema"]):
            priority.append(f)
        elif any(x in path for x in ["service", "entity", "model"]):
            secondary.append(f)

    return (priority + secondary)[:6]  # max 6 arquivos


def _fallback_contract(entities: list[str], has_auth: bool, api_port: int, stack: str) -> dict:
    """Contrato padrão quando a extração falha — inferido das entidades."""
    endpoints = []
    types = {}

    for entity in entities:
        el = entity.lower()
        ep = el + "s"
        type_name = entity

        endpoints += [
            {"method": "GET",    "path": f"/{ep}",     "response": f"{type_name}[]"},
            {"method": "GET",    "path": f"/{ep}/:id", "response": type_name},
            {"method": "POST",   "path": f"/{ep}",     "request": f"Create{type_name}Dto", "response": type_name},
            {"method": "PUT",    "path": f"/{ep}/:id", "request": f"Update{type_name}Dto", "response": type_name},
            {"method": "DELETE", "path": f"/{ep}/:id", "response": "void"},
        ]
        types[type_name] = {"id": "string", "createdAt": "string", "updatedAt": "string"}
        types[f"Create{type_name}Dto"] = {}

    if has_auth:
        endpoints = [
            {"method": "POST", "path": "/auth/login",    "request": "LoginDto",    "response": "TokenResponse"},
            {"method": "POST", "path": "/auth/register", "request": "RegisterDto", "response": "User"},
        ] + endpoints

    return {
        "base_url": f"http://localhost:{api_port}/api/v1",
        "auth_header": "Authorization: Bearer <token>" if has_auth else "none",
        "auth_endpoint": "/auth/login" if has_auth else None,
        "endpoints": endpoints,
        "types": types,
    }


def _build_summary(contract: dict, entities: list[str], has_auth: bool, api_port: int) -> str:
    """Constrói string compacta para incluir no contexto do frontend."""
    lines = [
        f"API base URL: {contract.get('base_url', f'http://localhost:{api_port}/api/v1')}",
        f"Auth: {'JWT Bearer token in Authorization header' if has_auth else 'no auth required'}",
    ]
    if has_auth:
        lines.append(f"Login endpoint: POST {contract.get('auth_endpoint', '/auth/login')}")

    lines.append(f"Entities: {', '.join(entities)}")
    lines.append("Endpoints:")
    for ep in contract.get("endpoints", [])[:15]:
        req = f" body={ep['request']}" if ep.get("request") else ""
        lines.append(f"  {ep['method']:6} {ep['path']}{req} → {ep.get('response','')}")

    if contract.get("types"):
        lines.append("Types (match these exactly in frontend):")
        for tname, fields in list(contract["types"].items())[:5]:
            if fields:
                field_str = ", ".join(f"{k}: {v}" for k, v in list(fields.items())[:4])
                lines.append(f"  {tname}: {{ {field_str} }}")

    return "\n".join(lines)


def _parse_json(text: str) -> dict | None:
    import json
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text.strip())
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return None
