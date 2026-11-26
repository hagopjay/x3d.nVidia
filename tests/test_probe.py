import base64
import json

from x3dnv import nim as nimmod
from x3dnv import probe

GOOD = ('<?xml version="1.0"?><X3D profile="Interchange" version="4.0"><Scene>'
        '<Viewpoint position="0 0 6"/><DirectionalLight/><Shape><Box size="1 1 1"/></Shape></Scene></X3D>')
GLB = base64.b64encode(b"glTF\x02\x00\x00\x00" + b"\0" * 12).decode()


def fake_transport(method, url, headers, body, timeout):
    assert headers["Authorization"].startswith("Bearer ")
    if url.endswith("/models"):
        ids = ["nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-3-nano-30b-a3b",
               "nvidia/usdcode", "nvidia/cosmos-reason2-8b", "microsoft/trellis"]
        return 200, {}, json.dumps({"data": [{"id": i} for i in ids]}).encode()
    if "trellis" in url:
        return 200, {}, json.dumps({"artifacts": [{"base64": GLB, "finishReason": "SUCCESS"}]}).encode()
    task = json.loads(body)["messages"][0]["content"]
    text = GOOD if "X3D" in task else "from pxr import UsdVol\nUsdVol.ParticleField3DGaussianSplat.Define(s,'/S')"
    return 200, {"x-ratelimit-remaining": "39"}, json.dumps(
        {"choices": [{"message": {"content": f"<think>hm</think>{text}"}}]}).encode()


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
    assert [r["model"] for r in rec["x3d"]] == ["nvidia/nemotron-3-super-120b-a12b",
                                               "nvidia/nemotron-3-nano-30b-a3b", "nvidia/usdcode"]
    assert all(r["check"]["score"] == 5 for r in rec["x3d"])
    assert all(r["mentions_UsdVol"] for r in rec["usd"])
    assert rec["trellis"]["glbs"][0]["bytes"] == 20
    saved = list(tmp_path.glob("probe-*.json"))
    assert saved and "nvapi-fake" not in saved[0].read_text()
