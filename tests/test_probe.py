import base64
import json

from x3dnv import nim as nimmod
from x3dnv import probe

GOOD = ('<?xml version="1.0"?><X3D profile="Interchange" version="4.0"><Scene>'
        '<Viewpoint position="0 0 6"/><DirectionalLight/><Shape><Box size="1 1 1"/></Shape></Scene></X3D>')
GLB = base64.b64encode(b"glTF\x02\x00\x00\x00" + b"\0" * 12).decode()


def fake_transport(method, url, headers, body, timeout):
    assert headers.get("Authorization", "Bearer ").startswith("Bearer ")
    if url.endswith("/models"):
        ids = ["nvidia/nemotron-3.5-super-vl-120b-a12b", "nvidia/nemotron-3.5-lightning-30b-a3b",
               "nvidia/usdcode", "nvidia/cosmos-reason2-8b", "microsoft/trellis"]
        return 200, {}, json.dumps({"data": [{"id": i} for i in ids]}).encode()
    if "trellis" in url:
        return 200, {}, json.dumps({"artifacts": [{"base64": GLB, "finishReason": "SUCCESS"}]}).encode()
    task = json.loads(body)["messages"][0]["content"]
    text = GOOD if "X3D" in task else "from pxr import UsdVol\nUsdVol.ParticleField3DGaussianSplat.Define(s,'/S')"
    return 200, {"x-ratelimit-remaining": "39"}, json.dumps(
        {"choices": [{"message": {"content": f"<think>hm</think>{text}"}, "finish_reason": "stop"}]}).encode()


def test_probe_offline(tmp_path, monkeypatch):
    real = nimmod.NIM
    monkeypatch.setattr(probe, "NIM", lambda rpm=None, log=print: real(
        key="nvapi-fake", rpm=6000, transport=fake_transport, log=log))
    png = tmp_path / "in.png"
    png.write_bytes(b"\x89PNG fake")
    rec = probe.main(["--out", str(tmp_path), "--trellis", str(png)])
    assert rec["catalog"]["count"] == 5
    assert rec["catalog"]["groups"]["usd"] == ["nvidia/usdcode"]
    assert rec["catalog"]["groups"]["world"] == ["nvidia/cosmos-reason2-8b"]
    assert [r["model"] for r in rec["x3d"]] == ["nvidia/nemotron-3.5-super-vl-120b-a12b",
                                               "nvidia/nemotron-3.5-lightning-30b-a3b", "nvidia/usdcode"]
    assert rec["missing_models"] == ["nvidia/nemotron-3-super-120b-a12b"]
    assert rec["max_tokens"] == 16384 and all(r["truncated"] is False for r in rec["usd"])
    assert all(r["check"]["score"] == 5 for r in rec["x3d"])
    assert all(r["mentions_UsdVol"] for r in rec["usd"])
    assert rec["trellis"]["glbs"][0]["bytes"] == 20
    saved = list(tmp_path.glob("probe-*.json"))
    assert saved and "nvapi-fake" not in saved[0].read_text()


def test_probe_flags_truncation_and_only(tmp_path, monkeypatch):
    real = nimmod.NIM
    sent = []

    def tr(method, url, headers, body, timeout):
        if url.endswith("/models"):
            return fake_transport(method, url, headers, body, timeout)
        sent.append(json.loads(body))
        return 200, {}, json.dumps({"choices": [{"message": {"content": "<think>long"},
                                                 "finish_reason": "length"}]}).encode()

    monkeypatch.setattr(probe, "NIM", lambda rpm=None, log=print: real(key="k", rpm=6000, transport=tr, log=log))
    rec = probe.main(["--out", str(tmp_path), "--only", "usd", "--max-tokens", "4096", "--no-think",
                      "--models", "nvidia/usdcode"])
    assert rec["x3d"] == [] and rec["usd"][0]["truncated"] is True
    assert sent[0]["max_tokens"] == 4096 and sent[0]["chat_template_kwargs"] == {"enable_thinking": False}
