"""Three ways to answer the same closed-set questions.

Every backend takes the same arguments as the Decisions API -- one shared
`input` string and a `questions` dict of noul / choice / score specs -- and
returns the same answer shape, so the benchmark and the agent can swap them.

  decisions  POST /v1beta/decisions, model gemini-decision-1 (scores options,
             returns probabilities; no text generation)
  gemma      Gemma 4 E2B on a local llama-server, JSON constrained to the
             allowed answers
  flashlite  Gemini Flash-Lite via generateContent, JSON constrained the same way

REST is used for the Decisions API on purpose: google-adk 2.x pins
google-genai<3, and the SDK's client.decisions needs google-genai>=3.2.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

API = "https://generativelanguage.googleapis.com/v1beta"
DECISION_MODEL = os.environ.get("DECISION_MODEL", "gemini-decision-1")
FLASHLITE_MODEL = os.environ.get("FLASHLITE_MODEL", "gemini-3.5-flash-lite")
GEMMA_URL = os.environ.get("GEMMA_URL", "http://127.0.0.1:8080")

_http = httpx.Client(timeout=120)


def api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        f = Path.home() / "gemini.key"
        if f.exists():
            key = f.read_text().strip()
    if not key:
        raise RuntimeError("set GEMINI_API_KEY (or put it in ~/gemini.key)")
    return key


# --------------------------------------------------------------------------
# 1. Decisions API
# --------------------------------------------------------------------------
def decisions(input_text: str, questions: dict) -> dict:
    """Returns {"answers": {...}, "usage": {...}, "latency_s": float}."""
    t0 = time.perf_counter()
    r = _http.post(
        f"{API}/decisions",
        headers={"x-goog-api-key": api_key()},
        json={"model": DECISION_MODEL, "input": input_text, "questions": questions},
    )
    dt = time.perf_counter() - t0
    if r.status_code != 200:
        raise RuntimeError(f"decisions {r.status_code}: {r.text[:400]}")
    out = r.json()
    out["latency_s"] = dt
    return out


# --------------------------------------------------------------------------
# Shared prompt + schema for the two generative backends
# --------------------------------------------------------------------------
def _options(q: dict) -> list:
    if q["type"] == "noul":
        return [True, False]
    if q["type"] == "choice":
        return list(q["criteria"].keys())
    return list(range(len(q["criteria"])))  # score: level indices


def _prompt(input_text: str, questions: dict) -> str:
    lines = [
        "Read the INPUT and answer every question. Reply with JSON only.",
        "",
        "INPUT:",
        input_text,
        "",
        "QUESTIONS:",
    ]
    for key, q in questions.items():
        lines.append(f'- "{key}": {q["instructions"]}')
        if q["type"] == "noul":
            c = q.get("criteria") or {}
            lines.append("    answer true or false")
            if c.get("true_description"):
                lines.append(f"    true = {c['true_description']}")
            if c.get("false_description"):
                lines.append(f"    false = {c['false_description']}")
        elif q["type"] == "choice":
            lines.append("    answer exactly one of:")
            for opt, desc in q["criteria"].items():
                lines.append(f'      "{opt}"' + (f": {desc}" if desc else ""))
        else:
            lines.append("    answer the level number:")
            for i, desc in enumerate(q["criteria"]):
                lines.append(f"      {i} = {desc}")
    return "\n".join(lines)


def _schema(questions: dict) -> dict:
    props = {}
    for key, q in questions.items():
        if q["type"] == "noul":
            props[key] = {"type": "boolean"}
        elif q["type"] == "choice":
            props[key] = {"type": "string", "enum": _options(q)}
        else:
            props[key] = {"type": "integer", "enum": _options(q)}
    return {
        "type": "object",
        "properties": props,
        "required": list(questions),
        "additionalProperties": False,
    }


def _to_answers(raw: dict, questions: dict) -> dict:
    """Map a generated JSON object onto the Decisions answer shape.

    Generative backends give one pick and no probabilities, so noul becomes
    1.0 / 0.0 and confidence is None.
    """
    answers = {}
    for key, q in questions.items():
        v = raw.get(key)
        if q["type"] == "noul":
            answers[key] = {"type": "noul", "noul": 1.0 if v else 0.0, "confidence": None}
        elif q["type"] == "choice":
            answers[key] = {"type": "choice", "choice": v, "confidence": None}
        else:
            answers[key] = {"type": "score", "score": v, "confidence": None}
    return answers


# --------------------------------------------------------------------------
# 2. Gemma 4 E2B on llama-server (OpenAI-compatible chat endpoint)
# --------------------------------------------------------------------------
def gemma(input_text: str, questions: dict) -> dict:
    t0 = time.perf_counter()
    r = _http.post(
        f"{GEMMA_URL}/v1/chat/completions",
        json={
            "messages": [{"role": "user", "content": _prompt(input_text, questions)}],
            "temperature": 0,
            "max_tokens": 64 + 16 * len(questions),
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "answers", "schema": _schema(questions)},
            },
            "chat_template_kwargs": {"enable_thinking": False},
        },
    )
    dt = time.perf_counter() - t0
    r.raise_for_status()
    body = r.json()
    raw = json.loads(body["choices"][0]["message"]["content"])
    u = body.get("usage", {})
    return {
        "answers": _to_answers(raw, questions),
        "usage": {
            "total_input_tokens": u.get("prompt_tokens"),
            "total_output_tokens": u.get("completion_tokens"),
        },
        "latency_s": dt,
    }


# --------------------------------------------------------------------------
# 3. Gemini Flash-Lite, generative, same prompt and schema
# --------------------------------------------------------------------------
def flashlite(input_text: str, questions: dict) -> dict:
    t0 = time.perf_counter()
    r = _http.post(
        f"{API}/models/{FLASHLITE_MODEL}:generateContent",
        headers={"x-goog-api-key": api_key()},
        json={
            "contents": [{"role": "user", "parts": [{"text": _prompt(input_text, questions)}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseJsonSchema": _schema(questions),
                "thinkingConfig": {"thinkingLevel": "minimal"},
            },
        },
    )
    dt = time.perf_counter() - t0
    if r.status_code != 200:
        raise RuntimeError(f"flashlite {r.status_code}: {r.text[:400]}")
    body = r.json()
    text = "".join(p.get("text", "") for p in body["candidates"][0]["content"]["parts"])
    u = body.get("usageMetadata", {})
    return {
        "answers": _to_answers(json.loads(text), questions),
        "usage": {
            "total_input_tokens": u.get("promptTokenCount"),
            "total_output_tokens": (u.get("candidatesTokenCount") or 0)
            + (u.get("thoughtsTokenCount") or 0),
        },
        "latency_s": dt,
    }


BACKENDS = {"decisions": decisions, "gemma": gemma, "flashlite": flashlite}


def pick(answer: dict):
    """The single answer a backend committed to, comparable across backends."""
    t = answer["type"]
    if t == "noul":
        return answer["noul"] >= 0.5
    if t == "choice":
        return answer["choice"]
    # score: Decisions returns a probability-weighted mean; take the most likely level
    if answer.get("probabilities"):
        return int(max(answer["probabilities"], key=answer["probabilities"].get))
    return int(answer["score"])
