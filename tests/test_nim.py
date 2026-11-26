import base64
import json

from x3dnv.nim import NIM, Pacer, harvest_glbs, key_id, redact
from x3dnv.x3dcheck import check_x3d, extract_x3d

SECRET = "nvapi-THIS-IS-NOT-A-REAL-KEY"


class Fake:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, json.loads(body) if body else None))
        status, hdrs, payload = self.replies.pop(0)
        return status, hdrs, json.dumps(payload).encode()


def nim(fake):
    n = NIM(key=SECRET, rpm=6000, transport=fake, log=lambda m: None)
    return n


def test_pacer_spacing():
    t = [0.0]
    slept = []
    p = Pacer(rpm=60, clock=lambda: t[0], sleep=lambda s: (slept.append(s), t.__setitem__(0, t[0] + s)))
    p.wait(); p.wait(); p.wait()
    assert slept == [1.0, 1.0]


def test_chat_strips_think_and_never_leaks_key(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    msg = {"choices": [{"message": {"content": "<think>secret plan</think>\n<X3D/>"}}],
           "usage": {"total_tokens": 9}}
    f = Fake([(429, {"Retry-After": "1"}, {"error": "slow"}), (200, {"x-ratelimit-remaining": "39"}, msg)])
    c = nim(f).chat("nvidia/x", [{"role": "user", "content": "hi"}])
    assert c.content == "<X3D/>" and c.reasoning == "<think>secret plan</think>\n"
    assert c.attempts == 2 and c.status == 200 and c.usage == {"total_tokens": 9}
    assert f.calls[0][2]["Authorization"] == f"Bearer {SECRET}"
    assert SECRET not in json.dumps(c.receipt()) and c.headers == {"x-ratelimit-remaining": "39"}


def test_max_tokens_halved_once():
    ok = {"choices": [{"message": {"content": "x"}}]}
    f = Fake([(400, {}, {"detail": "max_tokens too large"}), (200, {}, ok)])
    c = nim(f).chat("m", [], max_tokens=8192)
    assert c.content == "x" and f.calls[1][3]["max_tokens"] == 4096


def test_harvest_glb_and_redact():
    glb = b"glTF\x02\x00\x00\x00" + b"\0" * 20
    b64 = base64.b64encode(glb).decode()
    resp = {"artifacts": [{"base64": b64}], "other": "data:model/gltf-binary;base64," + b64}
    assert harvest_glbs(resp) == [glb, glb]
    assert "chars>" in redact({"x": "a" * 400})["x"]
    assert len(key_id(SECRET)) == 8


def test_x3dcheck():
    good = """Sure!\n```xml\n<?xml version="1.0"?><X3D profile="Interchange" version="4.0"><Scene>
    <Viewpoint position="0 0 6"/><DirectionalLight direction="0 0 -1"/>
    <Shape><Appearance><Material diffuseColor="1 0 0"/></Appearance><Box size="1 1 1"/></Shape>
    </Scene></X3D>\n```"""
    r = check_x3d(extract_x3d(good))
    assert r["score"] == 5, r
    bad = check_x3d('<X3D version="4.0"><Scene><Box size="1 1"/></Scene></X3D>')
    assert bad["score"] == 3 and bad["arity_errors"] and "Viewpoint" in bad["missing"]
    assert check_x3d("<X3D>")["parses"] is False


def test_proxy_mode_sends_no_auth(monkeypatch):
    monkeypatch.setenv("X3DNV_KEY_VIA_PROXY", "1")
    f = Fake([(200, {}, {"data": [{"id": "nvidia/x"}]})])
    n = NIM(rpm=6000, transport=f, log=lambda m: None)
    assert n.models() == ["nvidia/x"] and n.key_id == "proxy"
    assert "Authorization" not in f.calls[0][2]


def test_x3dcheck_case_sensitive_structure():
    lightning = ('<X3D profile="Interchange" version="4.0"><Head><Meta name="a" content="b"/></Head><Scene>'
                 '<Viewpoint position="0 0 6"/><DirectionalLight/><Shape><Box size="1 1 1"/></Shape></Scene></X3D>')
    r = check_x3d(lightning)
    assert r["structure_errors"] == ["X3D/Head"] and r["score"] == 4
