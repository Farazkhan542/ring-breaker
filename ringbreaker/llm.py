"""Google models (Gemini, Gemma) through Google ADK, with a response cache and a deterministic fallback so the demo
always completes. Order: live model chain -> cached response -> template text."""
import asyncio
import hashlib
import json
import logging
import os
import re

from . import config

log = logging.getLogger(__name__)


def llm_available() -> bool:
    if config.LLM_MODE == "off":
        return False
    vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in ("1", "true")
    return bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("RB_GEMMA_API_KEY")
                or (vertex and os.environ.get("GOOGLE_CLOUD_PROJECT")))


def _cache_path(name: str, prompt: str):
    key = hashlib.sha256(f"{name}|{prompt}".encode()).hexdigest()[:24]
    return config.CACHE_DIR / f"{name}-{key}.json"


def _model(model: str):
    """Gemma is served through the Gemini API with its own key (RB_GEMMA_API_KEY) even when Gemini models run on
    Vertex AI; every other model uses the default backend from the environment."""
    key = os.environ.get("RB_GEMMA_API_KEY")
    if model.startswith("gemma") and key:
        from google.adk.models.google_llm import Gemini
        return Gemini(model=model, client_kwargs={"vertexai": False, "api_key": key})
    return model


async def _run_adk_agent(name: str, instruction: str, prompt: str, model: str, json_mode: bool) -> str:
    from google.adk.agents import LlmAgent
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    gen_cfg = types.GenerateContentConfig(response_mime_type="application/json") if json_mode else None
    agent = LlmAgent(name=name, model=_model(model), instruction=instruction, generate_content_config=gen_cfg)
    runner = InMemoryRunner(agent=agent, app_name="ringbreaker")
    session = await runner.session_service.create_session(app_name="ringbreaker", user_id="officer")
    text = ""
    async for event in runner.run_async(user_id="officer", session_id=session.id,
                                        new_message=types.Content(role="user", parts=[types.Part(text=prompt)])):
        if event.is_final_response() and event.content and event.content.parts:
            text = "".join(p.text or "" for p in event.content.parts if not getattr(p, "thought", False))
    return text.strip()


def parse_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None


async def generate(name: str, instruction: str, facts: dict, fallback, *, models: list[str] | None = None,
                   json_mode: bool = False, timeout: float | None = None, budget: float | None = None,
                   cache_first: bool | None = None) -> dict:
    """Run an ADK agent on `facts`. Returns {"text" (or "data" in json_mode), "source", "model"}.
    source is live | cache | fallback (live means a Google model answered now: Gemini or Gemma)."""
    models = models or [config.MODEL_ID, *config.FALLBACK_MODELS]
    timeout = timeout or config.LLM_TIMEOUT_S
    budget = budget or config.LLM_BUDGET_S
    prompt = json.dumps(facts, indent=1, sort_keys=True, default=str)
    path = _cache_path(name, instruction + prompt)
    cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def out(text, source, model):
        if json_mode:
            return {"data": parse_json(text) if isinstance(text, str) else text, "source": source, "model": model}
        return {"text": text, "source": source, "model": model}

    if cached and (config.CACHE_FIRST if cache_first is None else cache_first):
        return out(cached["text"], "cache", cached.get("model"))
    if llm_available():
        loop = asyncio.get_running_loop()
        deadline = loop.time() + budget
        for model in models:  # busy (503), missing or slow model: try the next one
            left = deadline - loop.time()
            if left < 1.5:
                break
            try:
                text = await asyncio.wait_for(_run_adk_agent(name, instruction, prompt, model, json_mode),
                                              min(timeout, left))
            except Exception as e:  # quota, overload, network, auth: next model, then cache, then template
                log.warning("model call %s on %s failed: %s", name, model, (str(e) or type(e).__name__)[:200])
                continue
            if text and (not json_mode or parse_json(text) is not None):
                try:
                    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps({"text": text, "model": model}), encoding="utf-8")
                except OSError:
                    pass
                return out(text, "live", model)
    if cached:
        return out(cached["text"], "cache", cached.get("model"))
    return out(fallback, "fallback", None)
