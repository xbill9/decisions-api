"""Offline tests: no network, no API key, no Gemma server.

HTTP calls go through httpx.MockTransport, so these check what we send and
how we read the reply, not the services themselves.
"""

import json
import re

import httpx
import pytest

import bench
import decide
import scale
from tickets import QUESTIONS, TICKETS

KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


# --- the answer key ----------------------------------------------------------
def test_ticket_labels_are_valid_options():
    depts = set(QUESTIONS["dept"]["criteria"])
    levels = range(len(QUESTIONS["urgency"]["criteria"]))
    for text, dept, refund, urgency in TICKETS:
        assert dept in depts, text
        assert isinstance(refund, bool), text
        assert urgency in levels, text


def test_tickets_are_unique_and_counted():
    texts = [t[0] for t in TICKETS]
    assert len(texts) == len(set(texts))
    assert len(TICKETS) == 48  # README quotes 48; change both together


def test_questions_respect_api_limits():
    for key, q in QUESTIONS.items():
        assert KEY_RE.match(key)
        assert q["type"] in {"noul", "choice", "score"}
        if q["type"] in {"choice", "score"}:
            assert 2 <= len(q["criteria"]) <= 255


def test_scale_questions_fit_limits():
    qs = scale.questions(100)
    assert len(qs) == 100
    assert all(KEY_RE.match(k) for k in qs)
    assert len({q["instructions"] for q in qs.values()}) == 100


# --- prompt and schema for the generative backends --------------------------
def test_schema_enums_match_questions():
    s = decide._schema(QUESTIONS)
    assert s["required"] == list(QUESTIONS)
    assert s["properties"]["dept"]["enum"] == list(QUESTIONS["dept"]["criteria"])
    assert s["properties"]["wants_refund"] == {"type": "boolean"}
    assert s["properties"]["urgency"]["enum"] == [0, 1, 2]
    assert s["additionalProperties"] is False


def test_prompt_names_every_key_and_option():
    p = decide._prompt("my ticket", QUESTIONS)
    assert "my ticket" in p
    for key, q in QUESTIONS.items():
        assert f'"{key}"' in p
        if q["type"] == "choice":
            for opt in q["criteria"]:
                assert f'"{opt}"' in p


# --- pick(): one comparable answer per backend ------------------------------
def test_pick_noul_threshold():
    assert decide.pick({"type": "noul", "noul": 0.5}) is True
    assert decide.pick({"type": "noul", "noul": 0.49}) is False


def test_pick_score_uses_most_likely_level_not_mean():
    # weighted mean 1.5 would round to 2 or truncate to 1; the most likely level is 2
    a = {"type": "score", "score": 1.5, "probabilities": {"0": 0.05, "1": 0.40, "2": 0.55}}
    assert decide.pick(a) == 2


def test_generated_answers_round_trip_through_pick():
    raw = {"dept": "billing", "wants_refund": True, "urgency": 1}
    answers = decide._to_answers(raw, QUESTIONS)
    assert {k: decide.pick(a) for k, a in answers.items()} == raw
    assert all(a["confidence"] is None for a in answers.values())


# --- HTTP request/response handling ------------------------------------------
@pytest.fixture
def mock_http(monkeypatch):
    seen = {}

    def install(handler):
        def wrapped(request):
            seen["request"] = request
            return handler(request)
        monkeypatch.setattr(decide, "_http", httpx.Client(transport=httpx.MockTransport(wrapped)))
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        return seen

    return install


def test_decisions_request_and_response(mock_http):
    reply = {"answers": {"x": {"type": "noul", "noul": 0.9, "confidence": 0.9}},
             "usage": {"total_input_tokens": 12, "total_output_tokens": 0}}
    seen = mock_http(lambda r: httpx.Response(200, json=reply))
    q = {"x": {"type": "noul", "instructions": "?"}}
    out = decide.decisions("hello", q)
    req = seen["request"]
    assert req.url.path == "/v1beta/decisions"
    assert req.headers["x-goog-api-key"] == "test-key"
    assert json.loads(req.content) == {"model": decide.DECISION_MODEL, "input": "hello", "questions": q}
    assert out["answers"] == reply["answers"]
    assert out["latency_s"] >= 0


def test_decisions_error_raises_with_status(mock_http):
    mock_http(lambda r: httpx.Response(400, json={"error": {"code": "safety", "message": "blocked"}}))
    with pytest.raises(RuntimeError, match="decisions 400"):
        decide.decisions("hello", {"x": {"type": "noul", "instructions": "?"}})


def test_gemma_parses_constrained_json(mock_http):
    content = json.dumps({"dept": "shipping", "wants_refund": False, "urgency": 2})
    reply = {"choices": [{"message": {"content": content}}],
             "usage": {"prompt_tokens": 300, "completion_tokens": 20}}
    seen = mock_http(lambda r: httpx.Response(200, json=reply))
    out = decide.gemma("where is my parcel", QUESTIONS)
    body = json.loads(seen["request"].content)
    assert body["response_format"]["json_schema"]["schema"] == decide._schema(QUESTIONS)
    assert body["temperature"] == 0
    assert {k: decide.pick(a) for k, a in out["answers"].items()} == {
        "dept": "shipping", "wants_refund": False, "urgency": 2}
    assert out["usage"] == {"total_input_tokens": 300, "total_output_tokens": 20}


# --- bench.summarize: the numbers in the README ------------------------------
def _row(i, backend, pred, conf=None, lat=0.1):
    t = TICKETS[i]
    gold = {"dept": t[1], "wants_refund": t[2], "urgency": t[3]}
    return {"ticket": i, "backend": backend, "gold": gold, "pred": pred, "latency_s": lat,
            "confidence": conf or {q: None for q in QUESTIONS},
            "usage": {"total_input_tokens": 100, "total_output_tokens": 0}}


def test_summarize_counts_and_confidence_split():
    g0 = {"dept": TICKETS[0][1], "wants_refund": TICKETS[0][2], "urgency": TICKETS[0][3]}
    wrong = {**g0, "dept": "other", "urgency": (g0["urgency"] + 1) % 3}
    hi = {q: 0.9 for q in QUESTIONS}
    lo = {"dept": 0.4, "wants_refund": 0.9, "urgency": 0.4}
    rows = [_row(0, "decisions", g0, hi, 0.2), _row(0, "decisions", wrong, lo, 0.4)]
    rows[1]["ticket"] = 0  # same ticket twice is fine for counting
    s = bench.summarize(rows, ["decisions"])["backends"]["decisions"]
    assert s["accuracy"]["dept"] == {"correct": 1, "of": 2, "rate": 0.5}
    assert s["accuracy"]["wants_refund"]["correct"] == 2
    assert s["accuracy"]["all_three"]["correct"] == 1
    assert s["by_confidence"]["dept"] == {"conf>=0.7": {"n": 1, "correct": 1}, "conf<0.7": {"n": 1, "correct": 0}}
    assert s["latency_s"]["median"] == pytest.approx(0.3)
    assert s["cost_usd"] == pytest.approx(200 * 0.10 / 1e6)


def test_summarize_counts_errors_separately():
    g = {"dept": TICKETS[1][1], "wants_refund": TICKETS[1][2], "urgency": TICKETS[1][3]}
    rows = [_row(1, "gemma", g), {"ticket": 2, "backend": "gemma", "gold": {}, "error": "boom"}]
    s = bench.summarize(rows, ["gemma"])["backends"]["gemma"]
    assert s["errors"] == 1
    assert s["accuracy"]["dept"]["of"] == 1


def test_pct():
    assert bench.pct([1, 2, 3, 4, 5], 0.5) == 3
    assert bench.pct([0, 10], 0.9) == pytest.approx(9)


# --- the agent's tool output -------------------------------------------------
def test_agent_flags_low_confidence_for_review():
    agent = pytest.importorskip("triage_agent.agent")
    res = {"latency_s": 0.2, "answers": {
        "dept": {"type": "choice", "choice": "billing", "confidence": 0.58,
                 "probabilities": {"billing": 0.58, "technical": 0.42}},
        "wants_refund": {"type": "noul", "noul": 0.95, "confidence": 0.95},
    }}
    out = agent._summarize(res)
    assert out["needs_human_review"] == ["dept"]
    assert out["wants_refund"]["answer"] is True
    assert out["latency_ms"] == 200


def test_agent_gemma_result_has_no_review_list():
    agent = pytest.importorskip("triage_agent.agent")
    res = {"latency_s": 1.0, "answers": decide._to_answers(
        {"dept": "billing", "wants_refund": False, "urgency": 0}, QUESTIONS)}
    assert "needs_human_review" not in agent._summarize(res)
