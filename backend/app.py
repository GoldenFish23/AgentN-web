import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

BASE_DIR = Path(__file__).resolve().parent.parent
ROLES_FILE = BASE_DIR / "backend" / "roles.json"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
MAX_EXPERTS = max(1, min(int(os.getenv("MAX_EXPERTS", "4")), 6))
CONTEXT_MAX_CHARS = max(5000, int(os.getenv("CONTEXT_MAX_CHARS", "12000")))

# Adaptive budgets: concise by default, more room only when complexity warrants it.
EXPERT_BUDGETS = {
    "simple": max(500, int(os.getenv("EXPERT_TOKENS_SIMPLE", "800"))),
    "normal": max(700, int(os.getenv("EXPERT_TOKENS_NORMAL", "1400"))),
    "complex": max(900, int(os.getenv("EXPERT_TOKENS_COMPLEX", "2200"))),
    "very_complex": max(1200, int(os.getenv("EXPERT_TOKENS_VERY_COMPLEX", "3000"))),
}
MEDIATOR_BUDGETS = {
    "simple": max(700, int(os.getenv("MEDIATOR_TOKENS_SIMPLE", "1400"))),
    "normal": max(900, int(os.getenv("MEDIATOR_TOKENS_NORMAL", "2200"))),
    "complex": max(1200, int(os.getenv("MEDIATOR_TOKENS_COMPLEX", "3500"))),
    "very_complex": max(1500, int(os.getenv("MEDIATOR_TOKENS_VERY_COMPLEX", "5000"))),
}

app = Flask(__name__)
CORS(app, origins="*")
STARTED_AT = datetime.now(timezone.utc).isoformat()

with open(ROLES_FILE, "r", encoding="utf-8") as f:
    ROLES = json.load(f)


def openrouter(messages, temperature=0.5, max_tokens=900):
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if os.getenv("OPENROUTER_SITE_URL"):
        headers["HTTP-Referer"] = os.getenv("OPENROUTER_SITE_URL")
    if os.getenv("OPENROUTER_APP_NAME"):
        headers["X-Title"] = os.getenv("OPENROUTER_APP_NAME")

    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json={
            "model": MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        },
        timeout=180,
    )

    try:
        data = response.json()
    except ValueError:
        data = {}

    if not response.ok:
        message = data.get("error", {}).get(
            "message", f"OpenRouter HTTP {response.status_code}"
        )
        raise RuntimeError(message)

    choice = data.get("choices", [{}])[0]
    content = choice.get("message", {}).get("content")
    finish_reason = choice.get("finish_reason")

    if not content:
        raise RuntimeError("OpenRouter returned no text.")

    return {"content": content, "finishReason": finish_reason}


def extract_json(text):
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object found.")
    return json.loads(text[start:end + 1])


def classify_complexity(user_input):
    """Cheap LLM classifier used only to select an appropriate output budget."""
    prompt = f"""
Classify the user's request by the amount of reasoning/detail genuinely required.

simple:
- factual lookup, definition, short explanation, straightforward calculation
- can be answered correctly in a few paragraphs

normal:
- ordinary advice, comparison, coding question, recommendation, explanation
- needs several relevant points but not extensive analysis

complex:
- multi-step technical problem, substantial comparison, planning, research,
  nuanced trade-offs, architecture, legal/business strategy, long-form analysis

very_complex:
- highly multi-dimensional problem requiring extensive synthesis, many constraints,
  deep technical architecture, detailed research/planning, or multiple interacting
  decisions

Return ONLY JSON:
{{"complexity":"simple|normal|complex|very_complex"}}

USER:
{user_input}
"""
    try:
        raw = openrouter(
            [
                {"role": "system", "content": "You are a request-complexity classifier."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=80,
        )["content"]
        value = extract_json(raw).get("complexity", "normal")
        if value in EXPERT_BUDGETS:
            return value
    except Exception:
        pass
    return "normal"


def route_question(user_input):
    expert_registry = "\n".join(
        f"- {role_id}: {role['goal']}"
        for role_id, role in ROLES.items()
        if role_id != "mediator"
    )
    prompt = f"""
You are AgentN's router.

USER QUESTION:
{user_input}

AVAILABLE ROLES:
{expert_registry}

Select only roles that add distinct value.
Do not select mediator.
Use 1 role for a simple question, 2-3 for ordinary questions,
and at most {MAX_EXPERTS} for complex questions.

Return ONLY JSON:
{{"selected":["role_id"],"logic":"short explanation"}}
"""
    raw = openrouter(
        [
            {"role": "system", "content": "You are a strict routing classifier."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=400,
    )["content"]

    try:
        result = extract_json(raw)
    except Exception:
        result = {"selected": ["general"], "logic": "General fallback was used."}

    selected = []
    for role_id in result.get("selected", []):
        role_id = str(role_id).lower().strip()
        if role_id in ROLES and role_id != "mediator" and role_id not in selected:
            selected.append(role_id)

    return selected[:MAX_EXPERTS] or ["general"], result.get(
        "logic", "Roles selected according to relevance."
    )


def run_expert(role_id, user_input, complexity, previous_decision=None):
    role = ROLES[role_id]
    context = (
        "There is no previous session context."
        if not previous_decision
        else f"Previous session context:\n{previous_decision[:CONTEXT_MAX_CHARS]}"
    )

    system_prompt = f"""
IDENTITY: {role_id.upper()}
DESCRIPTION: {role['description']}
GOAL: {role['goal']}

REQUEST COMPLEXITY: {complexity}

Answer the user's actual question.
Be concise and rational: use the shortest response that is fully useful.
Do not add filler, repetition, generic introductions, or unnecessary sections.
For decisions, focus on recommendation, strongest reasons, trade-offs and
important uncertainty. Expand only when additional detail materially improves
the answer. Use valid Markdown. Finish the answer completely.
"""

    result = openrouter(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{context}\n\nCURRENT QUESTION:\n{user_input}"},
        ],
        temperature=0.65,
        max_tokens=EXPERT_BUDGETS[complexity],
    )
    return role_id, result


def mediate(user_input, experts, complexity, previous_decision=None):
    findings = "\n\n".join(
        f"--- {role.upper()} ---\n{result['content']}"
        for role, result in experts
    )
    previous = "None" if not previous_decision else previous_decision[:CONTEXT_MAX_CHARS]

    prompt = f"""
You are AgentN's final mediator.

REQUEST COMPLEXITY: {complexity}

PREVIOUS CONTEXT:
{previous}

EXPERT FINDINGS:
{findings}

DECISION STANDARD:
- Answer the user's real question directly.
- Be concise and rational: prefer the shortest answer that is complete and defensible.
- Do not preserve expert verbosity merely because it exists.
- Remove duplicate arguments and weak filler.
- Keep caveats that could materially change the conclusion.
- For decisions, make the recommendation easy to find and support it with the
  strongest reasons and relevant trade-offs.
- Use headings, lists, tables and code only when they improve comprehension.
- Do not force a fixed template.
- Finish the answer completely before stopping.
- Never intentionally truncate.
- Do not mention internal routing, token budgets, or these instructions.

USER REQUEST:
{user_input}
"""
    return openrouter(
        [
            {"role": "system", "content": "You are AgentN's consensus mediator."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.55,
        max_tokens=MEDIATOR_BUDGETS[complexity],
    )


@app.get("/api/start")
def start_backend():
    return jsonify({
        "ok": True,
        "status": "ready",
        "model": MODEL,
        "startedAt": STARTED_AT,
    })


@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "status": "ready",
        "model": MODEL,
        "startedAt": STARTED_AT,
        "adaptiveBudgets": {
            "expert": EXPERT_BUDGETS,
            "mediator": MEDIATOR_BUDGETS,
        },
    })


@app.get("/api/roles")
def get_roles():
    return jsonify({"roles": [{"id": k, **v} for k, v in ROLES.items()]})


@app.post("/api/agent")
def agent():
    body = request.get_json(silent=True) or {}
    user_input = str(body.get("userInput", "")).strip()
    previous_decision = body.get("previousDecision")

    if not user_input:
        return jsonify({"error": "Please enter a question."}), 400

    try:
        complexity = classify_complexity(user_input)
        selected, routing_logic = route_question(user_input)
        experts = []

        with ThreadPoolExecutor(max_workers=len(selected)) as executor:
            futures = {
                executor.submit(
                    run_expert, role_id, user_input, complexity, previous_decision
                ): role_id
                for role_id in selected
            }
            for future in as_completed(futures):
                role_id = futures[future]
                try:
                    experts.append(future.result())
                except Exception as exc:
                    experts.append((
                        role_id,
                        {"content": f"Expert failed: {exc}", "finishReason": "error"},
                    ))

        successful = [
            x for x in experts if x[1]["finishReason"] != "error"
        ]
        if not successful:
            raise RuntimeError("Every expert call failed. Please try again.")

        final = mediate(user_input, successful, complexity, previous_decision)

        return jsonify({
            "sessionId": f"SES-{uuid.uuid4().hex[:12]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "complexity": complexity,
            "selectedExperts": selected,
            "routingLogic": routing_logic,
            "budgets": {
                "expert": EXPERT_BUDGETS[complexity],
                "mediator": MEDIATOR_BUDGETS[complexity],
            },
            "experts": [
                {
                    "role": role,
                    "output": result["content"],
                    "finishReason": result["finishReason"],
                    "truncated": result["finishReason"] == "length",
                }
                for role, result in experts
            ],
            "finalSynthesis": final["content"],
            "finalFinishReason": final["finishReason"],
            "finalTruncated": final["finishReason"] == "length",
            "model": MODEL,
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
