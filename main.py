import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)

# Google Cloud Vision OCR endpoint
VISION_URL = "https://vision.googleapis.com/v1/images:annotate"

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
    # prompt ҳоло барои Vision истифода намешавад, ихтиёрӣ аст
    # prompt = (data.get("prompt") or "").strip()

    if not image_b64:
        return jsonify(detail="image required"), 400

    vision_key = _get_env("VISION_API_KEY") or _get_env("GEMINI_API_KEY")
    if not vision_key:
        return jsonify(detail="VISION_API_KEY not configured"), 503

    payload = {
        "requests": [
            {
                "image": {"content": image_b64},
                "features": [{"type": "TEXT_DETECTION"}],
            }
        ]
    }

    try:
        r = requests.post(
            f"{VISION_URL}?key={vision_key}",
            json=payload,
            timeout=60,
        )
    except requests.RequestException as e:
        return jsonify(detail=str(e)), 502

    if r.status_code != 200:
        try:
            j = r.json()
            msg = (
                j.get("error", {}).get("message")
                or j.get("message")
                or r.text
            )
        except Exception:
            msg = r.text
        return jsonify(detail=msg, upstream_status=r.status_code), 502

    body = r.json()
    responses = body.get("responses") or []
    if not responses:
        return jsonify(detail="Empty Vision response"), 502

    first = responses[0] or {}
    text = (
        (first.get("fullTextAnnotation") or {}).get("text")
        or (
            (first.get("textAnnotations") or [{}])[0].get("description")
            or ""
        )
    ).strip()

    if not text:
        return jsonify(detail="No text found"), 502

    return jsonify(text=text)