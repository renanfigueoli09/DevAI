"""
Cliente Ollama — wrapper simples para chamadas ao LLM local.
Suporta streaming e retorno completo.
"""

import json
import requests
from typing import Generator, Optional
from rich.console import Console
from rich.live import Live
from rich.text import Text

from config import OLLAMA_HOST, TEMPERATURE, MODEL_CODE

console = Console()


class OllamaClient:
    def __init__(self, host: str = OLLAMA_HOST):
        self.host = host.rstrip("/")
        self._check_connection()

    def _check_connection(self):
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=5)
            if r.status_code == 404:
                self._handle_model_not_found(payload.get("model", ""))
                raise RuntimeError(f"Modelo não encontrado: {payload.get('model')}. Veja sugestões acima.")
            r.raise_for_status()
        except Exception as e:
            console.print(f"\n[bold red]❌ Não foi possível conectar ao Ollama em {self.host}[/bold red]")
            console.print("[yellow]Execute: ollama serve[/yellow]")
            raise SystemExit(1) from e

    def list_models(self) -> list[str]:
        r = requests.get(f"{self.host}/api/tags", timeout=10)
        return [m["name"] for m in r.json().get("models", [])]

    def ensure_model(self, model: str):
        """Verifica se o modelo está disponível, puxa se necessário."""
        models = self.list_models()
        if not any(m.startswith(model.split(":")[0]) for m in models):
            if models:
                console.print(f"[yellow]⬇ Modelo '{model}' não encontrado. Puxando...[/yellow]")
                console.print(f"[dim]  Modelos disponíveis: {', '.join(models[:5])}[/dim]")
            else:
                console.print(f"[yellow]⬇ Nenhum modelo instalado. Puxando '{model}'...[/yellow]")
            self._pull_model(model)

    def _handle_model_not_found(self, model: str):
        """Trata erro 404: modelo não encontrado no Ollama."""
        available = self.list_models()
        console.print(f"\n[bold red]❌ Modelo '{model}' não encontrado no Ollama[/bold red]")
        if available:
            console.print(f"[yellow]Modelos disponíveis: {', '.join(available[:8])}[/yellow]")
            console.print(f"[cyan]Sugestão: edite ~/.devai_config ou use:[/cyan]")
            console.print(f"  export DEVAI_MODEL_CODE={available[0]}")
        else:
            console.print("[yellow]Nenhum modelo instalado.[/yellow]")
        console.print(f"[cyan]Para instalar o modelo recomendado:[/cyan]")
        console.print(f"  ollama pull qwen2.5-coder:7b")
        console.print(f"  ollama pull {model}")
        raise SystemExit(1)

    def _pull_model(self, model: str):
        with requests.post(
            f"{self.host}/api/pull",
            json={"name": model},
            stream=True,
            timeout=300,
        ) as r:
            for line in r.iter_lines():
                if line:
                    data = json.loads(line)
                    if "status" in data:
                        console.print(f"  [dim]{data['status']}[/dim]", end="\r")
        console.print(f"[green]✓ Modelo {model} pronto[/green]")

    def chat(
        self,
        model: str,
        messages: list[dict],
        temperature: float = TEMPERATURE,
        stream: bool = True,
        system: Optional[str] = None,
    ) -> str:
        """
        Envia mensagens ao modelo. Retorna a resposta completa como string.
        Se stream=True, exibe tokens conforme chegam.
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_predict": 4096,
            },
        }
        if system:
            payload["system"] = system

        if stream:
            return self._stream_chat(payload)
        else:
            return self._blocking_chat(payload)

    def _stream_chat(self, payload: dict) -> str:
        full_response = []
        with requests.post(
            f"{self.host}/api/chat",
            json=payload,
            stream=True,
            timeout=300,
        ) as r:
            if r.status_code == 404:
                self._handle_model_not_found(payload.get("model",""))
            r.raise_for_status()
            with Live(console=console, refresh_per_second=10) as live:
                for line in r.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    if "message" in data:
                        chunk = data["message"].get("content", "")
                        full_response.append(chunk)
                        live.update(Text("".join(full_response), style="white"))
                    if data.get("done"):
                        break
        console.print()  # newline após o stream
        return "".join(full_response)

    def _blocking_chat(self, payload: dict) -> str:
        payload["stream"] = False
        r = requests.post(
            f"{self.host}/api/chat",
            json=payload,
            timeout=300,
        )
        if r.status_code == 404:
            self._handle_model_not_found(payload.get("model",""))
        r.raise_for_status()
        return r.json()["message"]["content"]

    def generate(
        self,
        model: str,
        prompt: str,
        temperature: float = TEMPERATURE,
        stream: bool = False,
    ) -> str:
        """Geração direta (sem histórico de chat)."""
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
            "options": {"temperature": temperature, "num_predict": 4096},
        }
        if stream:
            full = []
            with requests.post(f"{self.host}/api/generate", json=payload, stream=True, timeout=300) as r:
                for line in r.iter_lines():
                    if line:
                        data = json.loads(line)
                        full.append(data.get("response", ""))
                        if data.get("done"):
                            break
            return "".join(full)
        else:
            r = requests.post(f"{self.host}/api/generate", json=payload, timeout=300)
            return r.json()["response"]
