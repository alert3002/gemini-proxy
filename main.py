import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)

# Модели 1.5 дигар дастрас нест → ба gemini-2.0-flash дар v1 мегузарем
GEMINI_URL = "https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent"

# CORS барои браузер (Vite localhost + production доменҳо)
# Агар хоҳед маҳдуд кунед, origins-ро ба рӯйхат иваз кунед.
CORS(
    app,
    resources={r"/gemini": {"origins": "*"}},
    allow_headers=["Content-Type", "X-Proxy-Token"],
    methods=["POST", "OPTIONS"],
)


def _get_env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


@app.route("/gemini", methods=["POST", "OPTIONS"])
def gemini():
    # Барои CORS preflight (OPTIONS) ягон токен талаб намекунем
    if request.method == "OPTIONS":
        return "", 200

    proxy_token = _get_env("PROXY_TOKEN")
    got = (request.headers.get("X-Proxy-Token") or "").strip()
    # Токенро фақат барои дархости аслӣ (POST) месанҷем
    if request.method == "POST":
        if not proxy_token or got != proxy_token:
            return jsonify(detail="Forbidden"), 403

    data = request.get_json(silent=True) or {}
    image_b64 = (data.get("image") or "").strip()
    prompt = (data.get("prompt") or "").strip()

    if not image_b64 or not prompt:
        return jsonify(detail="image and prompt required"), 400

    gemini_key = _get_env("GEMINI_API_KEY")
    if not gemini_key:
        return jsonify(detail="GEMINI_API_KEY not configured"), 503

    payload = {
        "contents": [{
            "role": "user",
            "parts": [{
                "inline_data": {"mime_type": "image/jpeg", "data": image_b64}
            }]
        }],
        "systemInstruction": {"parts": [{"text": prompt}]}
    }

    try:
        r = requests.post(
            GEMINI_URL,
            headers={"x-goog-api-key": gemini_key},
            json=payload,
            timeout=60,
        )
    except requests.RequestException as e:
        return jsonify(detail=str(e)), 502

    if r.status_code == 429:
        return jsonify(detail="Gemini quota exceeded"), 429

    if r.status_code != 200:
        try:
            j = r.json()
            msg = j.get("error", {}).get("message") or j.get("message") or r.text
        except Exception:
            msg = r.text
        return jsonify(detail=msg, upstream_status=r.status_code), 502

    body = r.json()
    candidates = body.get("candidates") or []
    if not candidates:
        return jsonify(detail="No candidates"), 502

    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join([p.get("text", "") for p in parts if p.get("text")])
    return jsonify(text=text)