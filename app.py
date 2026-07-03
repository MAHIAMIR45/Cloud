"""
YT Shorts AI — Render Proxy API
================================
Render.com pe deploy karo. HF Spaces ya koi bhi platform yeh URL call kare
to Cloudflare Workers AI se seedha baat hogi bina IP-block ke.

Deploy command (Render):
    gunicorn render_api:app

Render Environment Variables:
    CF_ACCOUNT_ID  — Cloudflare account ID
    CF_API_TOKEN   — Cloudflare API token (Workers AI Read)
"""

import os
import ssl
import requests
from flask import Flask, jsonify, request
from requests.adapters import HTTPAdapter

app = Flask(__name__)


# ── SSL Adapter (UNEXPECTED_EOF fix) ─────────────────────────────────────────
class _SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.options |= getattr(ssl, "OP_IGNORE_UNEXPECTED_EOF", 0)
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)


def _cf_session() -> requests.Session:
    s = requests.Session()
    s.mount("https://", _SSLAdapter())
    return s


# ── Health check ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    cf_ready = bool(os.environ.get("CF_ACCOUNT_ID") and os.environ.get("CF_API_TOKEN"))
    return jsonify({
        "status": "online",
        "service": "YT Shorts AI — Render Proxy API",
        "cf_credentials": "✅ set" if cf_ready else "❌ missing (set CF_ACCOUNT_ID & CF_API_TOKEN)",
        "endpoints": ["POST /ai"]
    })


# ── Main AI endpoint ──────────────────────────────────────────────────────────
@app.route("/ai", methods=["POST"])
def ai_generate():
    """
    Body (JSON):
        topic  — trending topic string (required)
        model  — Cloudflare model ID (optional, default llama-3.1-8b)

    Returns:
        { "success": true, "package": { ...full AI package... } }
    """
    data      = request.json or {}
    topic     = (data.get("topic") or "").strip()
    model     = data.get("model", "@cf/meta/llama-3.1-8b-instruct")

    if not topic:
        return jsonify({"success": False, "error": "topic field required"})

    account_id = os.environ.get("CF_ACCOUNT_ID", "").strip()
    api_token  = os.environ.get("CF_API_TOKEN",  "").strip()

    if not account_id or not api_token:
        return jsonify({
            "success": False,
            "error": "CF_ACCOUNT_ID aur CF_API_TOKEN Render env vars mein set karo"
        })

    try:
        from agent import generate_autonomous_package
        pkg = generate_autonomous_package(topic, model=model)
        return jsonify({"success": True, "package": pkg})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
