"""NVIDIA API Catalog (build.nvidia.com) client: stdlib only, key-safe, paced.

Same contract as x3d.lab PR #5's provider, so numbers are comparable:
  * OpenAI-compatible chat at https://integrate.api.nvidia.com/v1
  * Visual GenAI (TRELLIS etc.) at https://ai.api.nvidia.com/v1/genai/<org>/<model>
  * paced to X3DNV_NVIDIA_RPM (falls back to X3DLAB_NVIDIA_RPM, then 36);
    the free developer tier is 40 requests/minute per key, and x3d.lab and
    x3d.nVidia share ONE key, so split the budget if both run at once.
  * up to 5 retries on 429/5xx (Retry-After honoured, else exponential)
  * max_tokens halved once if the server refuses it
  * <think>...</think> stripped from content (raw kept in the receipt)

The key is read from NVIDIA_API_KEY, else Colab Secrets, else a hidden
getpass prompt. It is never printed, logged or written: receipts carry only
``key_id`` = sha256(key)[:8].
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

CHAT_BASE = "https://integrate.api.nvidia.com/v1"
GENAI_BASE = "https://ai.api.nvidia.com/v1/genai"
THINK = re.compile(r"<think>.*?</think>\s*", re.S)
GLB_B64 = "Z2xURg"  # base64 of b"glTF"


def load_key(interactive: bool = True) -> str:
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    if not key:
        try:  # Colab Secrets (never in the notebook)
            from google.colab import userdata  # type: ignore

            key = (userdata.get("NVIDIA_API_KEY") or "").strip()
        except Exception:
            pass
    if not key and interactive:
        import getpass

        key = getpass.getpass("NVIDIA_API_KEY (hidden): ").strip()
    if not key:
        raise RuntimeError("no NVIDIA_API_KEY (env, Colab Secrets or prompt)")
    return key


def key_id(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:8]


class Pacer:
    """Even spacing at ``rpm`` requests per minute, thread-safe."""

    def __init__(self, rpm: float | None = None, clock=time.monotonic, sleep=time.sleep):
        rpm = rpm or float(os.environ.get("X3DNV_NVIDIA_RPM") or os.environ.get("X3DLAB_NVIDIA_RPM") or 36)
        self.interval = 60.0 / rpm
        self.rpm = rpm
        self._next = 0.0
        self._lock = threading.Lock()
        self._clock, self._sleep = clock, sleep

    def wait(self) -> float:
        with self._lock:
            now = self._clock()
            delay = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.interval
        if delay:
            self._sleep(delay)
        return delay


@dataclass
class Call:
    """One request's receipt. ``content`` excludes <think>; ``raw`` is the JSON body."""

    url: str
    model: str | None
    status: int | None = None
    seconds: float | None = None
    attempts: int = 0
    waited: float = 0.0
    content: str | None = None
    reasoning: str | None = None
    usage: dict | None = None
    raw: Any = None
    error: str | None = None
    headers: dict = field(default_factory=dict)

    def receipt(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "raw"}
        d["raw_keys"] = sorted(self.raw) if isinstance(self.raw, dict) else None
        return d


Transport = Callable[[str, str, dict, bytes | None, float], tuple[int, dict, bytes]]


def urllib_transport(method: str, url: str, headers: dict, body: bytes | None, timeout: float):
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


class NIM:
    def __init__(self, key: str | None = None, rpm: float | None = None,
                 transport: Transport = urllib_transport, log: Callable[[str], None] = print,
                 max_retries: int = 5, timeout: float = 300.0):
        self._key = key if key is not None else load_key()
        self.key_id = key_id(self._key)
        self.pacer = Pacer(rpm)
        self.transport = transport
        self.log = log
        self.max_retries = max_retries
        self.timeout = timeout

    # ----------------------------------------------------------------- core
    def _request(self, method: str, url: str, payload: dict | None, model: str | None) -> Call:
        call = Call(url=url, model=model)
        headers = {"Authorization": f"Bearer {self._key}", "Accept": "application/json"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode()
        t0 = time.monotonic()
        for attempt in range(1, self.max_retries + 2):
            call.attempts = attempt
            call.waited += self.pacer.wait()
            status, hdrs, data = self.transport(method, url, headers, body, self.timeout)
            call.status = status
            call.headers = {k: v for k, v in hdrs.items()
                            if k.lower().startswith(("x-ratelimit", "retry-after", "nvcf", "x-request"))}
            if status == 429 or 500 <= status < 600:
                if attempt > self.max_retries:
                    break
                ra = hdrs.get("Retry-After") or hdrs.get("retry-after")
                delay = float(ra) if ra and str(ra).replace(".", "", 1).isdigit() else min(60, 2 ** attempt)
                self.log(f"[nim] {status} on {model or url}; retry {attempt}/{self.max_retries} in {delay:.0f}s")
                time.sleep(delay)
                continue
            break
        call.seconds = round(time.monotonic() - t0, 3)
        try:
            call.raw = json.loads(data) if data else None
        except ValueError:
            call.raw = {"_text": data[:2000].decode("utf-8", "replace")}
        if not 200 <= (call.status or 0) < 300:
            call.error = json.dumps(call.raw)[:500] if call.raw else f"HTTP {call.status}"
        return call

    # ----------------------------------------------------------------- chat
    def models(self) -> list[str]:
        c = self._request("GET", f"{CHAT_BASE}/models", None, None)
        if c.error:
            raise RuntimeError(c.error)
        return sorted(m["id"] for m in c.raw.get("data", []))

    def chat(self, model: str, messages: list[dict], max_tokens: int = 8192, **kw) -> Call:
        payload = {"model": model, "messages": messages, "max_tokens": max_tokens, **kw}
        c = self._request("POST", f"{CHAT_BASE}/chat/completions", payload, model)
        if c.error and c.status == 400 and "max_tokens" in (c.error or "") and max_tokens > 512:
            self.log(f"[nim] {model} refused max_tokens={max_tokens}; halving once")
            payload["max_tokens"] = max_tokens // 2
            c = self._request("POST", f"{CHAT_BASE}/chat/completions", payload, model)
        if not c.error:
            msg = (c.raw.get("choices") or [{}])[0].get("message", {})
            text = msg.get("content") or ""
            think = THINK.findall(text)
            c.reasoning = msg.get("reasoning_content") or ("".join(think) or None)
            c.content = THINK.sub("", text).strip()
            c.usage = c.raw.get("usage")
        return c

    # ---------------------------------------------------------------- genai
    def genai(self, org_model: str, payload: dict) -> Call:
        """POST a Visual GenAI endpoint, e.g. ``microsoft/trellis``."""
        return self._request("POST", f"{GENAI_BASE}/{org_model}", payload, org_model)

    def trellis(self, image_png: bytes, seed: int = 0, **kw) -> tuple[Call, list[bytes]]:
        """Image -> GLB with Microsoft TRELLIS on the NIM catalog.

        The page's prototype shows ``image``, ``seed``, ``ss_*`` and ``slat_*``
        fields but not the image encoding or the response shape (checked
        26 Nov 2026). We send a data URL and harvest any base64 glb anywhere
        in the response, so the first live run settles both: see the receipt.
        """
        img = "data:image/png;base64," + base64.b64encode(image_png).decode()
        c = self.genai("microsoft/trellis", {"image": img, "seed": seed, **kw})
        return c, harvest_glbs(c.raw)


def harvest_glbs(obj) -> list[bytes]:
    """Find base64-encoded glTF binaries anywhere in a JSON value."""
    found = []

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            s = x.split(",", 1)[1] if x.startswith("data:") else x
            if s.startswith(GLB_B64):
                try:
                    found.append(base64.b64decode(s))
                except Exception:
                    pass

    walk(obj)
    return found


def redact(obj):
    """Shorten long strings (base64) so receipts stay small and readable."""
    if isinstance(obj, dict):
        return {k: redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    if isinstance(obj, str) and len(obj) > 300:
        return obj[:60] + f"...<{len(obj)} chars>"
    return obj
