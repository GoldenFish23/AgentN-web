import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
ROLES_FILE = BASE_DIR / "backend" / "roles.json"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
MAX_EXPERTS = max(1, min(int(os.getenv("MAX_EXPERTS", "4")), 6))
# OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
app = Flask(__name__)
CORS(app, origins=[
    "https://agentn-frontend.onrender.com", 
    "http://localhost:5173",
    "https://*.app.github.dev"
])

with open(ROLES_FILE, "r", encoding="utf-8") as f:
    ROLES = json.load(f)


def openrouter(messages, temperature=0.5, max_tokens=900):
    """Server-side OpenRouter call. The API key never reaches React."""
    api_key = os.getenv("OPENROUTER_API_KEY","")
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

    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    response = requests.post(
        OPENROUTER_URL,
        headers=headers,
        json=payload,
        timeout=120,
    )

    try:
        data = response.json()
    except ValueError:
        data = {}

    if not response.ok:
        message = data.get("error", {}).get("message", f"OpenRouter HTTP {response.status_code}")
        raise RuntimeError(message)

    content = data.get("choices", [{}])[0].get("message", {}).get("content")
    if not content:
        raise RuntimeError("OpenRouter returned no text.")

    return content


def extract_json(text):
    """Extract JSON even if the model accidentally surrounds it with prose."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object found.")
    return json.loads(text[start:end + 1])


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
{{
  "selected": ["role_id"],
  "logic": "short explanation"
}}

Never invent role IDs.
"""

    raw = openrouter(
        [
            {"role": "system", "content": "You are a strict routing classifier."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=400,
    )

    try:
        result = extract_json(raw)
    except Exception:
        result = {
            "selected": ["general"],
            "logic": "Router output was invalid, so the general role was used.",
        }

    selected = []
    for role_id in result.get("selected", []):
        role_id = str(role_id).lower().strip()
        if role_id in ROLES and role_id != "mediator" and role_id not in selected:
            selected.append(role_id)

    selected = selected[:MAX_EXPERTS] or ["general"]

    return selected, result.get(
        "logic",
        "Roles were selected according to question complexity and relevance.",
    )


def run_expert(role_id, user_input, previous_decision=None):
    role = ROLES[role_id]

    context = (
        "There is no previous session context."
        if not previous_decision
        else f"Previous session context:\n{previous_decision[:5000]}"
    )

    # --- YOUR EXCELLENT ADAPTIVE TONE PROMPT ---
    system_prompt = (
        f"IDENTITY: {role_id.upper()}\n"
        f"DESCRIPTION: {role['description']}\n"
        f"GOAL: {role['goal']}\n\n"
        "--- ADAPTIVE TONE INSTRUCTIONS ---\n"
        "1. IF the request is technical or complex: Be concise, specialized, and highly technical.\n"
        "2. IF the request is casual, personal, or a joke: Respond naturally as your persona. Do NOT provide technical roadmaps or phase plans for simple conversation.\n"
        "3. Avoid 'Corporate Speak' unless the user asks for a business plan."
        "4. STYLE: The complete output must be only in proper Markdown format."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"{context}\n\nCURRENT QUESTION:\n{user_input}"},
    ]

    return role_id, openrouter(messages, temperature=0.65, max_tokens=500)


def mediate(user_input, experts, previous_decision=None):
    findings = "\n\n".join(
        f"--- {role.upper()} ---\n{output}"
        for role, output in experts
    )

    previous = (
        "None"
        if not previous_decision
        else previous_decision[:5000]
    )

    # --- YOUR INTENT-SCALING PROMPT + BEAUTIFUL MARKDOWN STRUCTURE ---
    prompt = f"""
You are AgentN's final MEDIATOR.

--- PREVIOUS CONTEXT ---
{previous}

--- EXPERT FINDINGS ---
{findings}

--- MANDATORY MEDIATOR PROTOCOL ---
1. IDENTIFY INTENT: Understand the context and depth of the USER REQUEST.
2. DEPTH SCALING: 
   - IF the prompt has depth (technical, statistical, planning, complex): Reply FORMALLY. Provide a high-density response. Use Markdown tables for comparisons. Every key point must end with a [Role] citation (e.g., [Planner]). DO NOT include your own 'Identity' or 'Description'. Start the response directly.
   - IF the prompt is shallow (casual, personal, simple chat): Reply INFORMALLY. Be a friendly partner. Emojis are encouraged. Answers should be short, warm, and unstructured. NO roadmaps or phase plans for simple chat.
3. FORMATTING (For Formal Replies Only): Structure your response exactly like this:
   ### The Final Verdict
   (Direct, decisive answer)
   ### Head-to-Head Comparison
   (Markdown table comparing options)
   ### Why This Choice?
   (Bulleted list with [Role] citations)
4. STYLE: The complete output must be only in proper Markdown format.

USER REQUEST: {user_input}
"""

    return openrouter(
        [
            {"role": "system", "content": "You are AgentN's consensus mediator."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.55,
        max_tokens=1400,
    )


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "model": MODEL})


@app.get("/api/roles")
def get_roles():
    return jsonify({
        "roles": [
            {"id": role_id, **role}
            for role_id, role in ROLES.items()
        ]
    })


@app.post("/api/agent")
def agent():
    body = request.get_json(silent=True) or {}
    user_input = str(body.get("userInput", "")).strip()
    previous_decision = body.get("previousDecision")

    if not user_input:
        return jsonify({"error": "Please enter a question."}), 400

    try:
        selected, routing_logic = route_question(user_input)

        experts = []
        # Independent expert calls happen concurrently.
        with ThreadPoolExecutor(max_workers=len(selected)) as executor:
            futures = {
                executor.submit(
                    run_expert,
                    role_id,
                    user_input,
                    previous_decision,
                ): role_id
                for role_id in selected
            }

            for future in as_completed(futures):
                try:
                    experts.append(future.result())
                except Exception as exc:
                    # One failed expert should not necessarily kill the panel.
                    experts.append((
                        futures[future],
                        f"This expert failed to respond: {exc}",
                    ))

        successful = [
            (role, output)
            for role, output in experts
            if not output.startswith("This expert failed to respond:")
        ]

        if not successful:
            raise RuntimeError("Every expert call failed. Please try again.")

        final_synthesis = mediate(
            user_input,
            successful,
            previous_decision,
        )

        now = datetime.now(timezone.utc).isoformat()
        return jsonify({
            "sessionId": f"SES-{uuid.uuid4().hex[:12]}",
            "timestamp": now,
            "selectedExperts": selected,
            "routingLogic": routing_logic,
            "experts": [
                {"role": role, "output": output}
                for role, output in experts
            ],
            "finalSynthesis": final_synthesis,
            "model": MODEL,
        })

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# @app.route("/", defaults={"path": ""})
# @app.route("/<path:path>")
# def serve_frontend(path):
#     # API paths are handled above. Everything else goes to the React SPA.
#     if path.startswith("api/"):
#         return jsonify({"error": "Not found"}), 404

#     target = FRONTEND_DIST / path
#     if path and target.exists() and target.is_file():
#         return send_from_directory(FRONTEND_DIST, path)

#     index = FRONTEND_DIST / "index.html"
#     if index.exists():
#         return send_from_directory(FRONTEND_DIST, "index.html")

#     return jsonify({
#         "error": "React build not found. Run npm run build first."
#     }), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
