"""
Natural-language -> Strategy Builder rules.

Four backends, all producing the same shape (matching the frontend's Rule[]
in webapp/frontend/components/StrategyBuilder.tsx):
  - "openai_compat": any OpenAI-chat-completions-API-compatible endpoint
    (a reseller/proxy token, a self-hosted OpenAI-compatible server, etc.)
    via function/tool calling. Requires OPENAI_COMPAT_API_KEY,
    OPENAI_COMPAT_BASE_URL, and OPENAI_COMPAT_MODEL.
  - "anthropic": sends the text to Claude with a strict tool schema. Requires
    ANTHROPIC_API_KEY (see webapp/backend/.env.example).
  - "ollama": a local model via Ollama's structured-output mode. No key, no
    cost, lower accuracy — see the backend's own docstring below.
  - "local": a regex/keyword parser, no external calls, no API key. Handles a
    bounded vocabulary (indicator mentions + period, comparison phrases,
    price-vs-indicator, $ stop/target, session-flat time, entry time-of-day
    window, "mirror the long side" for shorts). Unusual phrasing won't parse —
    falls back gracefully and says so in "notes" rather than guessing silently.

Auto fallback chain (when NL_PARSER_BACKEND is not set):
    openai_compat (if all 3 vars set)  ->  anthropic (if key set)
      ->  local Ollama (always tried next)  ->  regex "local" parser.
Each tier is used only if the ones before it failed or aren't configured, so a
dead cloud endpoint never blocks parsing while Ollama or the regex parser can
still handle the text. Force one tier with
NL_PARSER_BACKEND=openai_compat|anthropic|ollama|local.

Either way, the frontend only ever *populates* the existing rule-builder UI
with the result — nothing runs until the user reviews it and clicks "Run
custom strategy". The backend re-validates every field against
webapp/backend/indicators.py's INDICATOR_REGISTRY before returning it.
"""
import os
import re

from webapp.backend.indicators import INDICATOR_REGISTRY

OPS = ["<", ">", "<=", ">=", "==", "cross_above", "cross_below"]
FIELDS = ["open", "high", "low", "close"]
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


class NLParseError(Exception):
    pass


# ============================== shared validation ============================

def _validate_indicator(iid, params, output):
    spec = INDICATOR_REGISTRY.get(iid)
    if not spec:
        raise NLParseError(f"unknown indicator '{iid}'")
    out = output or spec["outputs"][0]
    if out not in spec["outputs"]:
        out = spec["outputs"][0]
    clean_params = {}
    valid_names = {p["name"] for p in spec["params"]}
    for k, v in (params or {}).items():
        if k in valid_names:
            clean_params[k] = v
    for p in spec["params"]:
        clean_params.setdefault(p["name"], p["default"])
    return clean_params, out


def _validate_rule(r: dict) -> dict:
    iid = r.get("indicator")
    ind_params, out = _validate_indicator(iid, r.get("indParams"), r.get("output"))

    op = r.get("op")
    if op not in OPS:
        raise NLParseError(f"unknown op '{op}'")
    right_kind = r.get("rightKind") if r.get("rightKind") in ("value", "price", "indicator") else "value"
    field = r.get("field") if r.get("field") in FIELDS else "close"
    value = r.get("value")
    if value is None:
        value = 0.0

    out_rule = {
        "indicator": iid, "indParams": ind_params, "output": out, "op": op,
        "rightKind": right_kind, "value": float(value), "field": field,
    }
    if right_kind == "indicator":
        r_iid = r.get("rightIndicator")
        if not r_iid or r_iid not in INDICATOR_REGISTRY:
            # can't represent this comparison without a valid right indicator —
            # fall back to comparing against price(close) rather than dropping
            # the rule silently different from what was asked, but at least valid.
            right_kind = "price"
            out_rule["rightKind"] = "price"
            out_rule["field"] = "close"
        else:
            r_params, r_out = _validate_indicator(r_iid, r.get("rightIndParams"), r.get("rightOutput"))
            out_rule["rightIndicator"] = r_iid
            out_rule["rightIndParams"] = r_params
            out_rule["rightOutput"] = r_out
    return out_rule


OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct")


def _openai_compat_configured() -> bool:
    return bool(os.environ.get("OPENAI_COMPAT_API_KEY") and os.environ.get("OPENAI_COMPAT_BASE_URL")
                and os.environ.get("OPENAI_COMPAT_MODEL"))


def _label_for(backend: str) -> str:
    if backend == "anthropic":
        return f"anthropic ({MODEL})"
    if backend == "ollama":
        return f"ollama ({OLLAMA_MODEL})"
    if backend == "openai_compat":
        return f"openai_compat ({os.environ.get('OPENAI_COMPAT_MODEL')})"
    return backend


def _finalize(result: dict, backend: str) -> dict:
    # LLM backends occasionally return a negative distance (seen from Ollama
    # in practice) — distances are magnitudes, never signed.
    result["stop_dist"] = abs(result["stop_dist"]) if result.get("stop_dist") is not None else None
    result["target_dist"] = abs(result["target_dist"]) if result.get("target_dist") is not None else None
    result["trail_dist"] = abs(result["trail_dist"]) if result.get("trail_dist") is not None else None
    if result.get("trail_ref") not in ("close", "hl"):
        result["trail_ref"] = "close"
    if result.get("trail_dist") is None:
        result["trail_activate_r"] = None
    elif result.get("trail_activate_r") is None:
        result["trail_activate_r"] = 1.0
    result["entry_start_hour_utc"] = _clean_hour(result.get("entry_start_hour_utc"), hi=23)
    result["entry_end_hour_utc"] = _clean_hour(result.get("entry_end_hour_utc"), hi=24)
    result["backend"] = _label_for(backend)
    return result


def _clean_hour(v, hi=24):
    """Coerce an hour-of-day field to an int in [0, hi], or None."""
    if v is None:
        return None
    try:
        h = int(round(float(v)))
    except (TypeError, ValueError):
        return None
    return h if 0 <= h <= hi else None


def parse_strategy_text(text: str) -> dict:
    if not text or not text.strip():
        raise NLParseError("empty strategy description")

    forced = os.environ.get("NL_PARSER_BACKEND")
    if forced:
        if forced == "local":
            result = _parse_local(text)
            result["backend"] = "local"
            return result
        fn = {"anthropic": _parse_with_anthropic, "ollama": _parse_with_ollama,
              "openai_compat": _parse_with_openai_compat}.get(forced)
        if fn is None:
            raise NLParseError(f"unknown NL_PARSER_BACKEND {forced!r}")
        return _finalize(fn(text), forced)

    # Not forced: fallback chain is
    #   cloud backends (openai_compat, then anthropic)  ->  local Ollama  ->  regex parser
    # Each tier is only tried if the one before it failed / isn't configured, so
    # a "configured" but broken cloud endpoint (dead URL, exhausted key) doesn't
    # block parsing when Ollama or the regex parser can still handle it.
    # openai_compat is first since it needs all 3 vars deliberately set — a more
    # explicit choice than a lone ANTHROPIC_API_KEY.
    cloud = []
    if _openai_compat_configured():
        cloud.append(("openai_compat", _parse_with_openai_compat))
    if os.environ.get("ANTHROPIC_API_KEY"):
        cloud.append(("anthropic", _parse_with_anthropic))

    errors = []
    for name, fn in cloud:
        try:
            return _finalize(fn(text), name)
        except NLParseError as e:
            errors.append(f"{name}: {e}")

    # Tier 2: local Ollama. Always attempted here (no fast pre-flight gate —
    # /api/tags can be slow to answer on a loaded box while /api/chat still
    # works). _parse_with_ollama fails fast with a clear message if the server
    # isn't up or the model isn't pulled.
    try:
        result = _finalize(_parse_with_ollama(text), "ollama")
        if errors:
            result["notes"] = (
                "Cloud AI parsing unavailable (" + "; ".join(errors) +
                ") - parsed with local Ollama instead. " + result.get("notes", "")
            ).strip()
        return result
    except NLParseError as e:
        errors.append(f"ollama: {e}")

    # Tier 3: the regex/keyword parser. Make the degradation LOUD (backend label
    # + a note), never silent, since it understands far less free-text phrasing.
    joined = "; ".join(errors) if errors else ""
    try:
        result = _parse_local(text)
    except NLParseError as le:
        raise NLParseError(
            "Every AI backend failed and the local regex parser could not handle "
            f"this text either.\n  AI backends: {joined}\n  local: {le}\n\n"
            "Add a working ANTHROPIC_API_KEY / OpenAI-compatible endpoint, or run "
            "Ollama (`ollama serve` + pull a model), in webapp/backend/.env."
        )
    if joined:
        result["backend"] = "local (AI backends unavailable)"
        result["notes"] = (
            "AI parsing unavailable (" + joined + ") - fell back to the limited "
            "regex parser. Review the rules carefully. " + result.get("notes", "")
        ).strip()
    else:
        result["backend"] = "local"
    return result


# ============================== Anthropic backend =============================

_RULE_SCHEMA = {
    "type": "object",
    "properties": {
        "indicator": {"type": "string", "enum": list(INDICATOR_REGISTRY)},
        "indParams": {"type": "object", "additionalProperties": {"type": "number"}},
        "output": {"type": "string"},
        "op": {"type": "string", "enum": OPS},
        "rightKind": {"type": "string", "enum": ["value", "price", "indicator"]},
        "value": {"type": "number"},
        "field": {"type": "string", "enum": FIELDS},
        "rightIndicator": {"type": "string", "enum": list(INDICATOR_REGISTRY),
                            "description": "Only when rightKind is 'indicator'."},
        "rightIndParams": {"type": "object", "additionalProperties": {"type": "number"}},
        "rightOutput": {"type": "string"},
    },
    "required": ["indicator", "indParams", "output", "op", "rightKind"],
}

TOOL = {
    "name": "build_strategy_rules",
    "description": "Translate a plain-English trading rule description into the "
                    "structured rule format the backtest builder consumes.",
    "input_schema": {
        "type": "object",
        "properties": {
            "long_rules": {"type": "array", "items": _RULE_SCHEMA},
            "short_rules": {"type": "array", "items": _RULE_SCHEMA},
            "stop_dist": {"type": ["number", "null"], "description": "Stop-loss distance in USD, or null for none."},
            "target_dist": {"type": ["number", "null"], "description": "Take-profit distance in USD, or null for none."},
            "session_flat_hour_utc": {"type": ["integer", "null"], "description": "Force-flat UTC hour, or null."},
            "entry_start_hour_utc": {"type": ["integer", "null"],
                                      "description": "Earliest UTC hour (0-23, inclusive) an entry may fire. null = no "
                                                      "time-of-day restriction on entries."},
            "entry_end_hour_utc": {"type": ["integer", "null"],
                                    "description": "Entries only fire strictly BEFORE this UTC hour (0-24, exclusive). "
                                                    "null = no restriction. With entry_start_hour_utc this is the entry "
                                                    "window, e.g. 'only trade the New York morning 13:00-16:00 UTC' -> "
                                                    "start 13, end 16. A window that wraps midnight (start > end, e.g. "
                                                    "the Asian session 22-6) is allowed."},
            "trail_dist": {"type": ["number", "null"],
                           "description": "Trailing-stop distance in USD behind the running extreme, or null if the "
                                           "text doesn't describe a trailing stop / letting winners run."},
            "trail_activate_r": {"type": ["number", "null"],
                                  "description": "R-multiple of profit before the trail activates (default 1.0 if a "
                                                  "trail is used but no activation point is stated)."},
            "trail_ref": {"type": "string", "enum": ["close", "hl"],
                          "description": "'close' (default) or 'hl' (high/low) as the running-extreme reference."},
            "one_trade_per_day": {"type": "boolean"},
            "notes": {"type": "string", "description": "One or two sentences: what you understood, and any "
                                                          "assumption you had to make (defaults used, ambiguity resolved, etc)."},
        },
        "required": ["long_rules", "short_rules", "one_trade_per_day", "notes"],
    },
}


def _registry_prompt() -> str:
    lines = []
    for iid, spec in INDICATOR_REGISTRY.items():
        params = ", ".join(f"{p['name']} (default {p['default']})" for p in spec["params"])
        lines.append(f'- "{iid}" ({spec["name"]}): params [{params}] -> outputs {spec["outputs"]}')
    return "\n".join(lines)


SYSTEM_PROMPT = f"""You translate a trader's plain-English strategy description into a \
structured rule set for a backtesting UI. Every rule has the shape:
  {{indicator, indParams, output, op, rightKind, value?, field?}}
which means:  <indicator's output> <op> <right-hand side>

- "indicator" MUST be one of: {list(INDICATOR_REGISTRY)}. "indParams" holds its
  numeric parameters (e.g. {{"n": 5}} for a 5-period EMA). "output" is one of that
  indicator's outputs (see list below) — use the primary one unless the text is
  specific (e.g. bollinger's "bb_upper"/"bb_lower", macd's "macd_line"/"macd_signal").
- The LEFT side of every rule is always an indicator — there is no "price on the
  left" option. To express "price crosses above/below an indicator", flip it:
  "price crosses above EMA(5)" becomes {{indicator: "ema", ..., op: "cross_below",
  rightKind: "price", field: "close"}} (EMA crossing below price == price crossing
  above EMA — they're the same boolean condition).
- rightKind "value" compares the indicator to a fixed number (set "value"), e.g.
  RSI below 30. rightKind "price" compares it to a price field (set "field": one
  of open/high/low/close), e.g. a candle detaching from a line.
- rightKind "indicator" compares it to ANOTHER indicator (set "rightIndicator",
  "rightIndParams", "rightOutput" — same shape as the left side). Use this for
  indicator-vs-indicator comparisons: "the 9 EMA crosses above the 21 EMA" is
  {{indicator: "ema", indParams: {{"n": 9}}, output: "ema", op: "cross_above",
  rightKind: "indicator", rightIndicator: "ema", rightIndParams: {{"n": 21}},
  rightOutput: "ema"}}. Likewise "MACD line crosses above its signal line" is
  indicator "macd" output "macd_line" vs rightIndicator "macd" rightOutput
  "macd_signal" (both with the same indParams unless the text says otherwise).
- Indicator registry:
{_registry_prompt()}

Bracket fields: stop_dist / target_dist are USD distances from entry (null if the
text doesn't specify one). session_flat_hour_utc forces flat at/after that UTC
hour if mentioned (e.g. "flat by 8pm UTC" -> 20). one_trade_per_day is true unless
the text implies multiple entries per day.

entry_start_hour_utc / entry_end_hour_utc restrict WHEN a new entry may fire (a
time-of-day gate on entries, distinct from session_flat_hour_utc which is when an
open trade is force-closed). Phrases like "only take trades between 13:00 and
16:00 UTC", "trade the New York morning", "entries only in the London session",
"no new positions after 3pm UTC". Give both bounds as UTC hours (start inclusive,
end exclusive); null both if the text places no time restriction on entries.
Common sessions in UTC: Asia ~00:00-07:00, London ~07:00-16:00, New York
~13:00-21:00, NY morning ~13:00-16:00. If only one side is stated ("no entries
after 15:00 UTC") set that bound and leave the other null.

trail_dist / trail_activate_r / trail_ref describe a TRAILING stop — phrases like
"trail the stop", "let winners run", "trailing stop of $X", "ratchet the stop",
"once +1R move the stop to breakeven and trail". Set trail_dist to the USD
distance behind the running extreme (null if no trailing is described — a plain
fixed stop/target is NOT a trailing stop). trail_activate_r is the R-multiple of
profit before it kicks in (default 1.0 if trailing is used but no activation
point is given). trail_ref is "close" unless the text specifically says to
trail off the high/low. A trailing stop can coexist with a fixed target (the
target still exits early if hit first) or replace it (target_dist null) — go
by what the text actually describes.

If the description is ambiguous or underspecified, make the most reasonable
trading interpretation and say what you assumed in "notes". If it names an
indicator/condition with no true equivalent in the registry (e.g. an indicator
that isn't in the list at all), do your best with the closest available
indicator and say so in "notes" — never fail silently, and never substitute
"price" for a second indicator just because you forgot rightKind "indicator"
exists — that changes the meaning of the rule, it doesn't approximate it.

Only emit the rules the text actually asks for — one rule per condition
literally stated. Do not pad a side with extra or "for safety" conditions it
didn't mention (e.g. if the text says "long when price touches the lower
Bollinger Band", emit exactly that one rule — do NOT also add an upper-band
condition to the same side; those two conditions are close to mutually
exclusive and ANDing them together would silently produce almost no trades,
which is not what was asked for).

stop_dist and target_dist are always positive magnitudes (a distance from
entry), never negative, regardless of whether the trade is long or short.

Always call the build_strategy_rules tool with your answer. Never respond in prose."""


def _parse_with_anthropic(text: str) -> dict:
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise NLParseError(
            "ANTHROPIC_API_KEY is not set. Add it to webapp/backend/.env "
            "(see webapp/backend/.env.example) and restart the backend."
        )

    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "build_strategy_rules"},
        messages=[{"role": "user", "content": text.strip()}],
    )

    tool_use = next((b for b in resp.content if b.type == "tool_use"), None)
    if tool_use is None:
        raise NLParseError("model did not return a structured rule set")
    data = tool_use.input

    long_rules = [_validate_rule(r) for r in (data.get("long_rules") or [])]
    short_rules = [_validate_rule(r) for r in (data.get("short_rules") or [])]
    if not long_rules and not short_rules:
        raise NLParseError("could not extract any long or short rule from that description")

    return {
        "long_rules": long_rules,
        "short_rules": short_rules,
        "stop_dist": data.get("stop_dist"),
        "target_dist": data.get("target_dist"),
        "session_flat_hour_utc": data.get("session_flat_hour_utc"),
        "entry_start_hour_utc": data.get("entry_start_hour_utc"),
        "entry_end_hour_utc": data.get("entry_end_hour_utc"),
        "trail_dist": data.get("trail_dist"),
        "trail_activate_r": data.get("trail_activate_r"),
        "trail_ref": data.get("trail_ref", "close"),
        "one_trade_per_day": bool(data.get("one_trade_per_day", True)),
        "notes": data.get("notes", ""),
    }


# =========================== OpenAI-compatible backend =========================
# Any endpoint implementing the OpenAI chat-completions API shape (resold/proxy
# tokens, self-hosted OpenAI-compatible servers, etc.) — same schema/prompt as
# Anthropic, via the widely-supported function/tool-calling mechanism rather
# than the newer (less universally supported) json_schema response_format.

def _parse_with_openai_compat(text: str) -> dict:
    import json

    import requests

    api_key = os.environ.get("OPENAI_COMPAT_API_KEY")
    base_url = os.environ.get("OPENAI_COMPAT_BASE_URL")
    model = os.environ.get("OPENAI_COMPAT_MODEL")
    if not (api_key and base_url and model):
        raise NLParseError(
            "OpenAI-compatible backend needs OPENAI_COMPAT_API_KEY, OPENAI_COMPAT_BASE_URL, "
            "and OPENAI_COMPAT_MODEL all set in webapp/backend/.env."
        )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text.strip()},
        ],
        "tools": [{
            "type": "function",
            "function": {
                "name": TOOL["name"],
                "description": TOOL["description"],
                "parameters": TOOL["input_schema"],
            },
        }],
        "tool_choice": {"type": "function", "function": {"name": TOOL["name"]}},
        "temperature": 0,
    }
    url = base_url.rstrip("/") + "/chat/completions"
    try:
        resp = requests.post(url, json=payload, headers={"Authorization": f"Bearer {api_key}"}, timeout=120)
        resp.raise_for_status()
    except requests.RequestException as e:
        body = getattr(e.response, "text", "") if getattr(e, "response", None) is not None else ""
        # strip HTML error pages (Cloudflare/proxy blocks) down to something readable
        if "<html" in body.lower() or "<!doctype" in body.lower():
            body = re.sub(r"<[^>]+>", " ", body)
        body = re.sub(r"\s+", " ", body).strip()
        raise NLParseError(f"OpenAI-compatible endpoint at {url} failed: {e} {body[:160]}")

    body = resp.json()
    try:
        tool_calls = body["choices"][0]["message"]["tool_calls"]
        args = json.loads(tool_calls[0]["function"]["arguments"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        raise NLParseError(f"Unexpected response shape from {url}: {e} — got: {str(body)[:300]}")

    long_rules = [_validate_rule(r) for r in (args.get("long_rules") or [])]
    short_rules = [_validate_rule(r) for r in (args.get("short_rules") or [])]
    if not long_rules and not short_rules:
        raise NLParseError("could not extract any long or short rule from that description")

    return {
        "long_rules": long_rules,
        "short_rules": short_rules,
        "stop_dist": args.get("stop_dist"),
        "target_dist": args.get("target_dist"),
        "session_flat_hour_utc": args.get("session_flat_hour_utc"),
        "entry_start_hour_utc": args.get("entry_start_hour_utc"),
        "entry_end_hour_utc": args.get("entry_end_hour_utc"),
        "trail_dist": args.get("trail_dist"),
        "trail_activate_r": args.get("trail_activate_r"),
        "trail_ref": args.get("trail_ref", "close"),
        "one_trade_per_day": bool(args.get("one_trade_per_day", True)),
        "notes": args.get("notes", ""),
    }


# ================================= Ollama backend ==============================
# Local model via Ollama's structured-output mode (JSON-schema-constrained
# decoding) — same schema/prompt as the Anthropic path, no API key, no cost,
# but noticeably lower accuracy on tricky phrasing than Claude.

def _parse_with_ollama(text: str) -> dict:
    import json

    import requests

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text.strip()},
        ],
        "format": TOOL["input_schema"],
        "stream": False,
        "options": {"temperature": 0},
        # keep the model resident between calls — Ollama's default 5min idle
        # unload means back-to-back parses often pay a ~10s cold-load on top
        # of generation time for no reason during an active session.
        "keep_alive": "30m",
    }
    try:
        # CPU-only inference of a 7b model with schema-constrained decoding is
        # highly variable (observed 20s-115s+ warm, plus ~10s cold-load after
        # Ollama's idle model unload) — match the frontend proxy's timeout
        # (next.config.mjs experimental.proxyTimeout) so this is never the
        # tighter of the two limits.
        resp = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=590)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise NLParseError(
            f"Could not reach Ollama at {OLLAMA_URL} (model '{OLLAMA_MODEL}'): {e}. "
            "Is `ollama serve` running and has the model been pulled?"
        )

    content = resp.json().get("message", {}).get("content", "")
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise NLParseError(f"Ollama did not return valid JSON: {content[:200]}")

    long_rules = [_validate_rule(r) for r in (data.get("long_rules") or [])]
    short_rules = [_validate_rule(r) for r in (data.get("short_rules") or [])]
    if not long_rules and not short_rules:
        raise NLParseError("could not extract any long or short rule from that description")

    return {
        "long_rules": long_rules,
        "short_rules": short_rules,
        "stop_dist": data.get("stop_dist"),
        "target_dist": data.get("target_dist"),
        "session_flat_hour_utc": data.get("session_flat_hour_utc"),
        "entry_start_hour_utc": data.get("entry_start_hour_utc"),
        "entry_end_hour_utc": data.get("entry_end_hour_utc"),
        "trail_dist": data.get("trail_dist"),
        "trail_activate_r": data.get("trail_activate_r"),
        "trail_ref": data.get("trail_ref", "close"),
        "one_trade_per_day": bool(data.get("one_trade_per_day", True)),
        "notes": data.get("notes", ""),
    }


# ================================ local backend ===============================
# No network, no API key. Bounded regex/keyword vocabulary — see module docstring.

_IND_SYNONYMS = [
    # (regex phrase, indicator id) — longest/most-specific phrases first.
    (r"exponential moving average", "ema"),
    (r"simple moving average", "sma"),
    (r"moving average", "sma"),
    (r"bollinger\s*bands?", "bollinger"),
    (r"\bbb\b", "bollinger"),
    (r"donchian\s*channels?", "donchian"),
    (r"\bdonchian\b", "donchian"),
    (r"relative strength index", "rsi"),
    (r"average true range", "atr"),
    (r"average directional index", "adx"),
    (r"stochastic", "stoch"),
    (r"\bstoch\b", "stoch"),
    (r"commodity channel index", "cci"),
    (r"\bcci\b", "cci"),
    (r"\bmacd\b", "macd"),
    # short codes: allow a glued period number ("ema5", "ema20") as well as
    # "ema", "ema 5", "ema(5)" — only the left boundary is required.
    (r"\bema(?:\b|(?=\d))", "ema"),
    (r"\bsma(?:\b|(?=\d))", "sma"),
    (r"\brsi(?:\b|(?=\d))", "rsi"),
    (r"\batr(?:\b|(?=\d))", "atr"),
    (r"\badx(?:\b|(?=\d))", "adx"),
]

_PRICE_WORDS = r"\b(price|closing price|opening price|close|open|high|low)\b"

# (regex, canonical op). Longest/most-specific first — "crosses above" before "above".
_OP_PATTERNS = [
    (r"cross(?:es|ing)?\s+above", "cross_above"),
    (r"cross(?:es|ing)?\s+below", "cross_below"),
    (r"cross(?:es|ing)?\s+over", "cross_above"),
    (r"cross(?:es|ing)?\s+under", "cross_below"),
    (r"is\s+above", ">"),
    (r"is\s+below", "<"),
    (r"greater\s+than\s+or\s+equal\s+to", ">="),
    (r"less\s+than\s+or\s+equal\s+to", "<="),
    (r"greater\s+than", ">"),
    (r"less\s+than", "<"),
    (r">=", ">="),
    (r"<=", "<="),
    (r"\babove\b", ">"),
    (r"\bbelow\b", "<"),
    (r">", ">"),
    (r"<", "<"),
    (r"equals?", "=="),
    (r"==", "=="),
]

_FLIP_OP = {">": "<", "<": ">", ">=": "<=", "<=": ">=", "==": "==",
            "cross_above": "cross_below", "cross_below": "cross_above"}


def _find_indicator(snippet: str):
    """Returns (indicator_id, span_start, span_end, output) for the first
    indicator mention in snippet, or None."""
    low = snippet.lower()
    for pat, iid in _IND_SYNONYMS:
        m = re.search(pat, low)
        if m:
            output = INDICATOR_REGISTRY[iid]["outputs"][0]
            window = low[max(0, m.start() - 12): m.end() + 20]
            if iid == "bollinger":
                if "lower" in window or "bottom" in window:
                    output = "bb_lower"
                elif "mid" in window or "middle" in window or "basis" in window:
                    output = "bb_mid"
            elif iid == "donchian":
                if "lower" in window or "bottom" in window:
                    output = "donchian_lower"
            elif iid == "macd":
                if "signal" in window:
                    output = "macd_signal"
                elif "hist" in window:
                    output = "macd_hist"
            elif iid == "adx":
                if "+di" in window or "plus di" in window or "plus-di" in window:
                    output = "plus_di"
                elif "-di" in window or "minus di" in window or "minus-di" in window:
                    output = "minus_di"
            return iid, m.start(), m.end(), output
    return None


def _find_period(snippet: str, s: int, e: int):
    after = snippet[e:e + 8]
    m = re.match(r"\s*\(?\s*(\d+)\s*\)?", after)
    if m and m.group(1):
        return int(m.group(1))
    before = snippet[max(0, s - 14):s]
    m2 = re.search(r"(\d+)\s*[-\s]*(?:period|day|bar)?\s*$", before)
    if m2:
        return int(m2.group(1))
    return None


def _resolve_operand(snippet: str):
    found = _find_indicator(snippet)
    if found:
        iid, s, e, output = found
        n = _find_period(snippet, s, e)
        return {"kind": "indicator", "id": iid, "n": n, "output": output}
    m = re.search(_PRICE_WORDS, snippet, re.I)
    if m:
        w = m.group(1).lower()
        field = "close" if "clos" in w or w == "price" else ("open" if "open" in w else w)
        return {"kind": "price", "field": field}
    m2 = re.search(r"[-+]?\d+(?:\.\d+)?", snippet)
    if m2:
        return {"kind": "value", "value": float(m2.group(0))}
    return None


def _make_rule(ind_operand: dict, op: str, other: dict):
    iid = ind_operand["id"]
    spec = INDICATOR_REGISTRY[iid]
    params = {p["name"]: p["default"] for p in spec["params"]}
    if ind_operand.get("n") is not None and spec["params"]:
        params[spec["params"][0]["name"]] = ind_operand["n"]
    output = ind_operand.get("output") or spec["outputs"][0]

    if other["kind"] == "price":
        return {"indicator": iid, "indParams": params, "output": output, "op": op,
                "rightKind": "price", "value": 0.0, "field": other["field"]}
    if other["kind"] == "value":
        return {"indicator": iid, "indParams": params, "output": output, "op": op,
                "rightKind": "value", "value": other["value"], "field": "close"}
    if other["kind"] == "indicator":
        r_iid = other["id"]
        r_spec = INDICATOR_REGISTRY[r_iid]
        r_params = {p["name"]: p["default"] for p in r_spec["params"]}
        if other.get("n") is not None and r_spec["params"]:
            r_params[r_spec["params"][0]["name"]] = other["n"]
        return {"indicator": iid, "indParams": params, "output": output, "op": op,
                "rightKind": "indicator", "value": 0.0, "field": "close",
                "rightIndicator": r_iid, "rightIndParams": r_params,
                "rightOutput": other.get("output") or r_spec["outputs"][0]}
    return None


def _parse_clause(clause: str):
    low = clause.lower()
    # "closes above/below X" -> price(close) <op> X, resolved with the usual flip logic.
    m = re.search(r"clos(?:es|e|ing)\s+(above|below)\s+(?:the\s+)?(.+)", low)
    if m:
        direction, right_text = m.group(1), clause[m.end(1):]
        right_op = _resolve_operand(right_text)
        if right_op and right_op["kind"] == "indicator":
            op = "<" if direction == "above" else ">"  # X < price == price above X
            return _make_rule(right_op, op, {"kind": "price", "field": "close"})
        return None

    for pat, canon in _OP_PATTERNS:
        m = re.search(pat, low)
        if not m:
            continue
        left_op = _resolve_operand(clause[:m.start()])
        right_op = _resolve_operand(clause[m.end():])
        if not left_op or not right_op:
            continue
        if left_op["kind"] == "indicator":
            return _make_rule(left_op, canon, right_op)
        if right_op["kind"] == "indicator":
            return _make_rule(right_op, _FLIP_OP[canon], left_op)
        return None  # neither side is an indicator — not representable
    return None


_STOP_RE = re.compile(r"\$?\s*(\d+(?:\.\d+)?)\s*(?:dollar\s*)?stop|"
                       r"stop(?:[\s-]*loss)?\s*(?:of|at)?\s*\$?\s*(\d+(?:\.\d+)?)", re.I)
_TARGET_RE = re.compile(r"\$?\s*(\d+(?:\.\d+)?)\s*(?:dollar\s*)?target|"
                         r"(?:take[\s-]*profit|target)\s*(?:of|at)?\s*\$?\s*(\d+(?:\.\d+)?)", re.I)
_FLAT_RE = re.compile(r"flat\s*(?:by|at|before)?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:utc)?", re.I)
_MULTI_TRADE_RE = re.compile(r"multiple trades|more than one trade|several trades|many trades a day", re.I)
_MIRROR_RE = re.compile(r"\b(opposite|mirror|reverse|vice versa)\b", re.I)

# Trailing stop: "trailing stop of $5", "trail the stop by $5", "$5 trailing
# stop", "trail by $5" — matched separately from _STOP_RE (and masked out of
# the text before it runs) so "trailing stop of $5" isn't ALSO counted as a
# plain fixed $5 stop.
_TRAIL_RE = re.compile(
    r"trail(?:ing)?\s*(?:the\s*)?stop(?:[\s-]*loss)?\s*(?:of|by|to)?\s*\$?\s*(\d+(?:\.\d+)?)|"
    r"trail\s*(?:by|to)?\s*\$?\s*(\d+(?:\.\d+)?)|"
    r"\$?\s*(\d+(?:\.\d+)?)\s*trail(?:ing)?\s*stop", re.I)
_TRAIL_ACTIVATE_RE = re.compile(r"(?:once|after|at)\s*\+?\s*(\d+(?:\.\d+)?)\s*r\b|\+\s*(\d+(?:\.\d+)?)\s*r\b", re.I)
_TRAIL_HL_RE = re.compile(r"trail\w*.{0,25}\b(high|low)\b|\b(high|low)\b.{0,25}trail", re.I)


def _first_num(m: re.Match):
    if not m:
        return None
    for g in m.groups():
        if g is not None:
            try:
                return float(g)
            except ValueError:
                pass
    return None


def _hour_from(h_str: str, ampm: str | None) -> int:
    h = int(h_str)
    ampm = (ampm or "").lower()
    if ampm == "pm" and h != 12:
        h += 12
    elif ampm == "am" and h == 12:
        h = 0
    return h % 24


def _parse_flat_hour(text: str):
    m = _FLAT_RE.search(text)
    if not m:
        return None
    return _hour_from(m.group(1), m.group(3))


# --- entry time-of-day window (distinct from session-flat) -------------------
_SESSION_HOURS = {
    "asian": (0, 7), "asia": (0, 7), "tokyo": (0, 7),
    "london": (7, 16), "european": (7, 16), "europe": (7, 16),
    "new york morning": (13, 16), "ny morning": (13, 16),
    "new york": (13, 21), "ny": (13, 21), "us session": (13, 21),
}
_ENTRY_BETWEEN_RE = re.compile(
    r"(?:between|from)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*"
    r"(?:to|through|thru|till|until|and|[-–—])\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:utc)?", re.I)
_NO_ENTRY_AFTER_RE = re.compile(
    r"no\s+(?:new\s+)?(?:entr(?:y|ies)|trades?|positions?)[^.]{0,25}?"
    r"after\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:utc)?", re.I)
_ENTRY_CONTEXT_RE = re.compile(r"\b(entr|trade|position|take\s+trades?|only\s+trade)", re.I)


def _parse_entry_window(text: str):
    """Returns (start_hour, end_hour) as ints in [0,24] or None each. start is
    inclusive, end exclusive; start > end means a window wrapping midnight."""
    m = _ENTRY_BETWEEN_RE.search(text)
    if m:
        return _hour_from(m.group(1), m.group(3)), _hour_from(m.group(4), m.group(6))

    m = _NO_ENTRY_AFTER_RE.search(text)
    if m:
        return None, _hour_from(m.group(1), m.group(3))

    low = text.lower()
    if _ENTRY_CONTEXT_RE.search(low):
        # longest session name first so "new york morning" wins over "new york"
        for name, (s, e) in sorted(_SESSION_HOURS.items(), key=lambda kv: -len(kv[0])):
            if re.search(rf"\b{re.escape(name)}\b", low):
                return s, e
    return None, None


def _mirror_rule(r: dict) -> dict:
    return {**r, "op": _FLIP_OP.get(r["op"], r["op"])}


def _split_clauses(segment: str):
    parts = re.split(r"\s*,\s*|\s+and\s+|\s+AND\s+", segment)
    return [p.strip() for p in parts if p.strip()]


_SIDE_MARKER_RE = re.compile(r"\b(long|buy)\b|\b(short|sell)\b", re.I)


def _side_segments(text: str):
    """Splits text at each long/short(buy/sell) marker into (side, segment)
    pairs, so side order in the text doesn't matter (e.g. "short when X, long
    when Y" puts Y in the long segment, not the short one)."""
    markers = [(m.start(), "long" if m.group(1) else "short") for m in _SIDE_MARKER_RE.finditer(text)]
    if not markers:
        return [("long", text)]
    segments = []
    for i, (pos, side) in enumerate(markers):
        end = markers[i + 1][0] if i + 1 < len(markers) else len(text)
        segments.append((side, text[pos:end]))
    return segments


def _parse_local(text: str) -> dict:
    trail_m = _TRAIL_RE.search(text)
    trail_dist = _first_num(trail_m) if trail_m else None
    # mask the trail phrase out before scanning for a plain fixed stop, so
    # "trailing stop of $5" isn't double-counted as a $5 fixed stop too.
    stop_text = text[:trail_m.start()] + text[trail_m.end():] if trail_m else text
    stop_dist = _first_num(_STOP_RE.search(stop_text))
    target_dist = _first_num(_TARGET_RE.search(text))
    session_flat = _parse_flat_hour(text)
    entry_start, entry_end = _parse_entry_window(text)
    one_trade_per_day = not _MULTI_TRADE_RE.search(text)

    trail_activate_r = None
    trail_ref = "close"
    if trail_dist is not None:
        am = _TRAIL_ACTIVATE_RE.search(text)
        trail_activate_r = _first_num(am) if am else 1.0
        if _TRAIL_HL_RE.search(text):
            trail_ref = "hl"

    unparsed = []
    long_rules, short_rules = [], []
    mirrored = False
    for side, segment in _side_segments(text):
        if side == "short" and _MIRROR_RE.search(segment):
            short_rules.extend(_mirror_rule(r) for r in long_rules)
            mirrored = True
            continue
        bucket = long_rules if side == "long" else short_rules
        for clause in _split_clauses(segment):
            r = _parse_clause(clause)
            if r:
                bucket.append(r)
            elif len(clause) > 3 and _find_indicator(clause):
                unparsed.append(clause)

    if not long_rules and not short_rules:
        raise NLParseError(
            "Local parser couldn't extract any rule from that text. Try phrasing like "
            "\"long when RSI(14) is below 30 and price closes above EMA(20)\", or add an "
            "Anthropic API key in webapp/backend/.env for full free-text understanding."
        )

    notes = f"Parsed locally (no LLM) - {len(long_rules)} long rule(s), {len(short_rules)} short rule(s)."
    if mirrored:
        notes += " Short side mirrored from the long rules."
    if trail_dist is not None:
        notes += f" Trailing stop ${trail_dist:g} once +{trail_activate_r:g}R, ref={trail_ref}."
    if entry_start is not None or entry_end is not None:
        _s = f"{entry_start:02d}:00" if entry_start is not None else "open"
        _e = f"{entry_end:02d}:00" if entry_end is not None else "open"
        notes += f" Entry window {_s} to {_e} UTC."
    if unparsed:
        notes += " Could not parse: " + "; ".join(f"\"{c}\"" for c in unparsed[:3]) + "."

    return {
        "long_rules": [_validate_rule(r) for r in long_rules],
        "short_rules": [_validate_rule(r) for r in short_rules],
        "stop_dist": stop_dist,
        "target_dist": target_dist,
        "session_flat_hour_utc": session_flat,
        "entry_start_hour_utc": entry_start,
        "entry_end_hour_utc": entry_end,
        "trail_dist": trail_dist,
        "trail_activate_r": trail_activate_r,
        "trail_ref": trail_ref,
        "one_trade_per_day": one_trade_per_day,
        "notes": notes,
    }
