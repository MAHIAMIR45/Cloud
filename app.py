"""
YT Shorts AI — Render Proxy API (Self-Contained)
=================================================
agent.py ya kisi aur file ki zaroorat NAHI.
Sirf yeh file + render_requirements.txt chahiye.

Render Deploy:
  Build Command : pip install -r render_requirements.txt
  Start Command : gunicorn render_api:app --bind 0.0.0.0:$PORT

Render Environment Variables:
  CF_ACCOUNT_ID  — Cloudflare account ID
  CF_API_TOKEN   — Cloudflare API token (Workers AI Read)
"""

import os
import re
import json
import ssl
import requests
from datetime import datetime
from flask import Flask, jsonify, request
from requests.adapters import HTTPAdapter

app = Flask(__name__)


# ── SSL Adapter — UNEXPECTED_EOF fix ─────────────────────────────────────────
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


# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a world-class YouTube Shorts viral growth strategist and SEO expert. Your SOLE job is to maximize views, clicks, and watch time for every video. You know exactly how the YouTube algorithm works.

TODAY'S DATE: {current_date}
CURRENT YEAR: {current_year}
IMPORTANT: Always use the correct year {current_year} in titles, tags, and descriptions — never use any past year.

TRENDING_TOPIC: "{trending_topic}"

### YOUR TRAFFIC MAXIMIZATION RULES:

#### TITLE FORMULA (most important — decides 80% of clicks):
- Length: 40-55 characters MAXIMUM (longer titles get cut off on mobile)
- MUST use one of these proven viral structures:
  * "This [topic] SHOCKED Everyone..." (curiosity gap)
  * "Nobody Knew This About [topic]" (exclusivity)
  * "The Truth About [topic] EXPOSED" (controversy)
  * "[Number] Seconds That Changed [topic] Forever" (specificity)
  * "Why [topic] Has Everyone Talking" (social proof)
  * "[topic] Just Changed Everything..." (urgency)
- ALWAYS end with "..." to create open loops in viewer's brain
- Use ALL CAPS on ONE power word only: SHOCKED, EXPOSED, REVEALED, INSANE, WILD
- Add exactly 2 hashtags at end: one broad (#shorts) one topic-specific

#### DESCRIPTION FORMULA (drives SEO and suggested video traffic):
Line 1: Restate the hook as a question — makes people read more
Line 2-3: 2 sentences with high-search keywords naturally embedded
Line 4: "Watch till the end — you won't believe what happens next."
Line 5-6: 3 related questions people search on YouTube (drives suggested traffic)
Line 7: Call to action: "Follow for daily [topic] updates you won't find anywhere else."
Blank line, then: 25-30 hashtags in this order:
  - 5 MEGA hashtags (100M+ views): #shorts #viral #trending #fyp #foryou
  - 5 LARGE hashtags (10M+ views): topic-category tags
  - 10 MEDIUM hashtags (1M-10M): specific topic tags
  - 5 NICHE hashtags (under 1M): very specific long-tail tags
  - 5 TRENDING hashtags: current trending tags related to topic

#### TAGS ARRAY (YouTube backend search — 30 tags):
Mix: broad terms + specific terms + question phrases + trending phrases

### OUTPUT: Reply ONLY with raw valid JSON. No markdown, no code blocks, no explanation.

{
    "trend_analysis": {
        "virality_score_1_to_10": 9,
        "target_upload_hour_est": 12,
        "scheduling_reason": "Specific reason this time slot maximizes views for this trend type"
    },
    "youtube_metadata": {
        "title": "Apply TITLE FORMULA above. 40-55 chars. ONE power word in CAPS. End with ...",
        "description": "Apply DESCRIPTION FORMULA above. Min 150 words. Include 25-30 hashtags at end.",
        "tags": ["30 tags as JSON array"]
    },
    "production_assets": {
        "voiceover_script": "Exactly 55 seconds when read at normal speed. Start with shocking fact.",
        "image_prompts": [
            "SCENE 1 HOOK: specific visual. Suffix: ultra photorealistic, 8K, vertical 9:16, no text no watermark",
            "SCENE 2 CONTEXT: different angle. Suffix: hyper-realistic, cinematic, vertical 9:16, no text no watermark",
            "SCENE 3 TENSION: dramatic moment. Suffix: DSLR photorealistic, vertical 9:16, no text no watermark",
            "SCENE 4 DETAIL: close-up detail. Suffix: ultra HD, vertical 9:16, no text no watermark",
            "SCENE 5 SCALE: epic wide shot. Suffix: cinematic wide angle, vertical 9:16, no text no watermark",
            "SCENE 6 EMOTION: human emotion. Suffix: photorealistic, vertical 9:16, no text no watermark",
            "SCENE 7 FINALE: most powerful image. Suffix: cinematic, award-winning, vertical 9:16, no text no watermark"
        ]
    }
}

### ABSOLUTE RULES:
1. Title MUST be under 55 characters
2. Description MUST have minimum 25 hashtags at the end
3. Tags MUST be a JSON array of 25-30 strings
4. Image prompts MUST be specific to THIS topic
5. Script MUST start with a shocking fact — never with greetings
6. Every hashtag in description must start with # symbol"""


# ── JSON cleanup helpers ──────────────────────────────────────────────────────
def _fix_json_strings(s: str) -> str:
    result = []
    in_str = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == '\\' and in_str:
            result.append(c)
            i += 1
            if i < len(s):
                result.append(s[i])
            i += 1
            continue
        if c == '"':
            in_str = not in_str
            result.append(c)
        elif in_str and c == '\n':
            result.append('\\n')
        elif in_str and c == '\r':
            result.append('\\r')
        elif in_str and c == '\t':
            result.append('\\t')
        else:
            result.append(c)
        i += 1
    return ''.join(result)


def _parse_package(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```json\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        raw = match.group(0)
    raw = re.sub(r'(?<!\\)[\x00-\x08\x0b\x0c\x0e-\x1f]', ' ', raw)
    raw = _fix_json_strings(raw)
    package = json.loads(raw)
    tags = package.get("youtube_metadata", {}).get("tags", [])
    if isinstance(tags, str):
        package["youtube_metadata"]["tags"] = [t.strip() for t in tags.split(",")]
    return package


# ── Core CF call ──────────────────────────────────────────────────────────────
def _call_cloudflare(topic: str, model: str) -> dict:
    account_id = os.environ.get("CF_ACCOUNT_ID", "").strip()
    api_token  = os.environ.get("CF_API_TOKEN",  "").strip()
    if not account_id or not api_token:
        raise ValueError("CF_ACCOUNT_ID aur CF_API_TOKEN Render env vars mein set karo")

    if not model.startswith("@cf/"):
        model = "@cf/meta/llama-3.1-8b-instruct"

    now = datetime.utcnow()
    filled = (SYSTEM_PROMPT
              .replace("{trending_topic}", topic)
              .replace("{current_year}", str(now.year))
              .replace("{current_date}", now.strftime("%B %d, %Y")))

    payload = {
        "messages": [
            {"role": "system", "content": filled},
            {"role": "user",   "content":
                f"Today is {now.strftime('%B %d, %Y')}. "
                f"Generate a viral YouTube Shorts package. "
                f"Use year {now.year} everywhere. Output raw JSON only: {topic}"}
        ],
        "max_tokens": 4000,
        "temperature": 0.75
    }

    url      = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    session  = _cf_session()
    response = session.post(
        url,
        headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
        json=payload,
        timeout=90
    )

    if response.status_code != 200:
        raise Exception(f"Cloudflare API Error {response.status_code}: {response.text[:300]}")

    res_json = response.json()
    if not res_json.get("success", False):
        raise Exception(f"Cloudflare Error: {res_json.get('errors', [])}")

    result = res_json.get("result", {})
    if isinstance(result, str):
        raw = result
    elif isinstance(result, dict):
        resp = result.get("response", "")
        if isinstance(resp, str):
            raw = resp
        elif isinstance(resp, dict):
            raw = resp.get("text", "") or resp.get("content", "") or json.dumps(resp)
        else:
            raw = json.dumps(result)
    else:
        raw = str(result)

    return _parse_package(raw)


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    cf_ready = bool(os.environ.get("CF_ACCOUNT_ID") and os.environ.get("CF_API_TOKEN"))
    return jsonify({
        "status": "online",
        "service": "YT Shorts AI — Render Proxy API",
        "cf_credentials": "✅ set" if cf_ready else "❌ missing — set CF_ACCOUNT_ID & CF_API_TOKEN",
        "endpoints": ["POST /ai"]
    })


@app.route("/ai", methods=["POST"])
def ai_generate():
    """
    Body: { "topic": "trending topic", "model": "@cf/meta/llama-3.1-8b-instruct" }
    Returns: { "success": true, "package": { ...full AI package... } }
    """
    data  = request.json or {}
    topic = (data.get("topic") or "").strip()
    model = data.get("model", "@cf/meta/llama-3.1-8b-instruct")

    if not topic:
        return jsonify({"success": False, "error": "topic field required"})

    try:
        pkg = _call_cloudflare(topic, model)
        return jsonify({"success": True, "package": pkg})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
