"""Gemini through Google ADK, with a response cache and a deterministic fallback so the demo always completes."""
import asyncio
import hashlib
import json
import logging
import os

from . import config

log = logging.getLogger(__name__)


def llm_available() -> bool:
    if config.LLM_MODE == "off":
        return False
    vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true")
    return bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
                or (vertex and os.environ.get("GOOGLE_CLOUD_PROJECT")))


def _cache_path(name: str, prompt: str):
    key = hashlib.sha256(f"{config.MODEL_ID}|{name}|{prompt}".encode()).hexdigest()[:24]
    return config.CACHE_DIR / f"{name}-{key}.json"


async def _run_adk_agent(name: str, instruction: str, prompt: str, model: str) -> str:
    from google.adk.agents import LlmAgent
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    agent = LlmAgent(name=name, model=model, instruction=instruction)
    runner = InMemoryRunner(agent=agent, app_name="ringbreaker")
    session = await runner.session_service.create_session(app_name="ringbreaker", user_id="officer")
    text = ""
    async for event in runner.run_async(user_id="officer", session_id=session.id,
                                        new_message=types.Content(role="user", parts=[types.Part(text=prompt)])):
        if event.is_final_response() and event.content and event.content.parts:
            text = "".join(p.text or "" for p in event.content.parts if not getattr(p, "thought", False))
    return text.strip()


async def generate(name: str, instruction: str, facts: dict, fallback: str) -> dict:
    """Run an ADK agent on `facts`. Returns {"text", "source"} where source is gemini | cache | fallback."""
    prompt = json.dumps(facts, indent=1, sort_keys=True, default=str)
    path = _cache_path(name, instruction + prompt)
    cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if cached and config.CACHE_FIRST:
        return {"text": cached["text"], "source": "cache", "model": cached.get("model")}
    if llm_available():
        loop = asyncio.get_running_loop()
        deadline = loop.time() + config.LLM_BUDGET_S
        for model in [config.MODEL_ID, *config.FALLBACK_MODELS]:  # busy (503) or missing model: try the next one
            left = deadline - loop.time()
            if left < 3:
                break
            try:
                text = await asyncio.wait_for(_run_adk_agent(name, instruction, prompt, model),
                                              min(config.LLM_TIMEOUT_S, left))
            except Exception as e:  # quota, overload, network, auth: try next model, then cache, then template
                log.warning("Gemini call %s on %s failed: %s", name, model, str(e)[:200])
                continue
            if text:
                try:
                    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps({"text": text, "model": model}), encoding="utf-8")
                except OSError:
                    pass
                return {"text": text, "source": "gemini", "model": model}
    if cached:
        return {"text": cached["text"], "source": "cache", "model": cached.get("model")}
    return {"text": fallback, "source": "fallback", "model": None}
