"""ComfyUI（MiniMax Hailuo H3 文生视频）集成：payload 构建 + httpx MockTransport 单测。"""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.integrations.comfyui.video import ComfyUIVideoApiAdapter
from app.core.integrations.comfyui.video_payload import build_text_to_video_workflow
from app.core.contracts.provider import ProviderConfig
from app.core.contracts.video_generation import VideoGenerationInput
from app.core.tasks.video_generation_tasks import ComfyUIVideoGenerationTask, VideoGenerationTask


def _patch_httpx_client(monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport) -> None:
    real_client = httpx.AsyncClient

    def factory(**kwargs: object) -> httpx.AsyncClient:
        timeout = kwargs.get("timeout", 60.0)
        return real_client(transport=transport, timeout=timeout)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def test_build_workflow_normalizes_default_model_and_ratio() -> None:
    inp = VideoGenerationInput.model_validate({"prompt": "a cat surfing", "ratio": "16:9"})
    workflow = build_text_to_video_workflow(inp)

    node = workflow["1"]
    assert node["class_type"] == "MinimaxHailuo03TextToVideoNode"
    assert node["inputs"]["model"] == "MiniMax H3"
    assert node["inputs"]["prompt"] == "a cat surfing"
    assert node["inputs"]["ratio"] == "16:9"
    assert node["inputs"]["duration"] == 6
    assert node["inputs"]["seed"] == 42
    assert node["inputs"]["watermark"] is False
    assert "prompt_expansion_mode" not in node["inputs"]

    save_node = workflow["2"]
    assert save_node["class_type"] == "SaveVideo"
    assert save_node["inputs"]["video"] == ["1", 0]


def test_build_workflow_maps_max_variant_and_custom_duration() -> None:
    inp = VideoGenerationInput.model_validate(
        {"prompt": "舞", "model": "minimax h3 max", "ratio": "9:16", "seconds": 10, "seed": 7, "watermark": True}
    )
    workflow = build_text_to_video_workflow(inp)
    node_inputs = workflow["1"]["inputs"]
    assert node_inputs["model"] == "MiniMax H3 Max"
    assert node_inputs["duration"] == 10
    assert node_inputs["seed"] == 7
    assert node_inputs["watermark"] is True
    assert node_inputs["prompt_expansion_mode"] == "balanced"


def test_build_workflow_rejects_out_of_range_duration() -> None:
    inp = VideoGenerationInput.model_validate({"prompt": "舞", "ratio": "16:9", "seconds": 30})
    with pytest.raises(ValueError, match="seconds must be <= 15"):
        build_text_to_video_workflow(inp)


def test_build_workflow_requires_prompt() -> None:
    # 合同层允许仅凭参考图生成（无 prompt），但 MiniMax H3 文生视频节点必须要 prompt。
    inp = VideoGenerationInput.model_validate({"ratio": "16:9", "key_frame_base64": "aGVsbG8="})
    with pytest.raises(RuntimeError):
        build_text_to_video_workflow(inp)


@pytest.mark.asyncio
async def test_comfyui_queue_prompt_sends_api_key_in_extra_data(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url).rstrip("/").endswith("/prompt")
        body = json.loads(request.content.decode())
        assert body["prompt"]["1"]["class_type"] == "MinimaxHailuo03TextToVideoNode"
        assert body["extra_data"]["api_key_comfy_org"] == "comfy-key"
        return httpx.Response(200, json={"prompt_id": "p-1"})

    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    cfg = ProviderConfig(provider="comfyui", api_key="comfy-key", base_url="http://127.0.0.1:8188")
    inp = VideoGenerationInput.model_validate({"prompt": "a cat", "ratio": "16:9"})
    prompt_id = await ComfyUIVideoApiAdapter().queue_prompt(cfg=cfg, input_=inp, timeout_s=30.0)
    assert prompt_id == "p-1"


def test_resolve_comfyui_api_key_prefers_provider_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.integrations.comfyui.video import resolve_comfyui_api_key

    monkeypatch.setattr("app.core.integrations.comfyui.video.settings.comfy_api_key", "env-key")
    cfg_with_db_key = ProviderConfig(provider="comfyui", api_key="db-key")
    assert resolve_comfyui_api_key(cfg_with_db_key) == "db-key"

    cfg_without_db_key = ProviderConfig(provider="comfyui", api_key="")
    assert resolve_comfyui_api_key(cfg_without_db_key) == "env-key"


def test_resolve_comfyui_api_key_empty_when_neither_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.integrations.comfyui.video import resolve_comfyui_api_key

    monkeypatch.setattr("app.core.integrations.comfyui.video.settings.comfy_api_key", None)
    cfg = ProviderConfig(provider="comfyui", api_key="")
    assert resolve_comfyui_api_key(cfg) == ""


@pytest.mark.asyncio
async def test_comfyui_queue_prompt_falls_back_to_env_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert body["extra_data"]["api_key_comfy_org"] == "env-only-key"
        return httpx.Response(200, json={"prompt_id": "p-2"})

    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    monkeypatch.setattr("app.core.integrations.comfyui.video.settings.comfy_api_key", "env-only-key")
    cfg = ProviderConfig(provider="comfyui", api_key="", base_url="http://127.0.0.1:8188")
    inp = VideoGenerationInput.model_validate({"prompt": "a cat", "ratio": "16:9"})
    prompt_id = await ComfyUIVideoApiAdapter().queue_prompt(cfg=cfg, input_=inp, timeout_s=30.0)
    assert prompt_id == "p-2"


@pytest.mark.asyncio
async def test_comfyui_get_history_returns_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert "/history/p-1" in str(request.url)
        return httpx.Response(
            200,
            json={
                "p-1": {
                    "status": {"status_str": "success", "completed": True},
                    "outputs": {"2": {"videos": [{"filename": "out.mp4", "subfolder": "", "type": "output"}]}},
                }
            },
        )

    _patch_httpx_client(monkeypatch, httpx.MockTransport(handler))
    cfg = ProviderConfig(provider="comfyui", api_key="", base_url="http://127.0.0.1:8188")
    adapter = ComfyUIVideoApiAdapter()
    entry = await adapter.get_history(cfg=cfg, prompt_id="p-1", timeout_s=30.0)
    assert adapter.is_completed(entry) is True
    assert adapter.is_execution_error(entry) is None
    video_file = adapter.find_output_video(entry)
    assert video_file == {"filename": "out.mp4", "subfolder": "", "type": "output"}
    url = adapter.build_view_url(cfg=cfg, filename="out.mp4", subfolder="", file_type="output")
    assert url == "http://127.0.0.1:8188/view?filename=out.mp4&subfolder=&type=output"


def test_comfyui_is_execution_error_detects_failure() -> None:
    adapter = ComfyUIVideoApiAdapter()
    entry = {"status": {"status_str": "error", "messages": [["execution_error", {"exception": "boom"}]]}}
    assert adapter.is_execution_error(entry) is not None


class _FakeComfyUIAdapter:
    """伪造 ComfyUIVideoApiAdapter：先返回未完成历史，再返回带视频产物的历史。"""

    def __init__(self, *, fail: bool = False) -> None:
        self._calls = 0
        self._fail = fail

    async def queue_prompt(self, *, cfg: ProviderConfig, input_: VideoGenerationInput, timeout_s: float) -> str:
        return "prompt-1"

    async def get_history(self, *, cfg: ProviderConfig, prompt_id: str, timeout_s: float) -> dict:
        self._calls += 1
        if self._calls == 1:
            return {}
        if self._fail:
            return {"status": {"status_str": "error", "messages": ["boom"]}}
        return {
            "status": {"status_str": "success", "completed": True},
            "outputs": {"2": {"videos": [{"filename": "out.mp4", "subfolder": "", "type": "output"}]}},
        }

    def is_execution_error(self, entry: dict) -> str | None:
        return ComfyUIVideoApiAdapter().is_execution_error(entry)

    def is_completed(self, entry: dict) -> bool:
        return ComfyUIVideoApiAdapter().is_completed(entry)

    def find_output_video(self, entry: dict) -> dict | None:
        return ComfyUIVideoApiAdapter().find_output_video(entry)

    def build_view_url(self, *, cfg: ProviderConfig, filename: str, subfolder: str, file_type: str) -> str:
        return ComfyUIVideoApiAdapter().build_view_url(cfg=cfg, filename=filename, subfolder=subfolder, file_type=file_type)


@pytest.mark.asyncio
async def test_comfyui_task_polls_until_video_output_ready() -> None:
    cfg = ProviderConfig(provider="comfyui", api_key="key", base_url="http://127.0.0.1:8188")
    inp = VideoGenerationInput.model_validate({"prompt": "a cat", "ratio": "16:9"})
    task = ComfyUIVideoGenerationTask(
        adapter=_FakeComfyUIAdapter(),  # type: ignore[arg-type]
        provider_config=cfg,
        input_=inp,
        poll_interval_s=0.0,
        timeout_s=5.0,
    )
    await task.run()
    result = await task.get_result()
    assert result is not None
    assert result.provider == "comfyui"
    assert result.provider_task_id == "prompt-1"
    assert result.url == "http://127.0.0.1:8188/view?filename=out.mp4&subfolder=&type=output"


@pytest.mark.asyncio
async def test_comfyui_task_surfaces_execution_error() -> None:
    cfg = ProviderConfig(provider="comfyui", api_key="", base_url="http://127.0.0.1:8188")
    inp = VideoGenerationInput.model_validate({"prompt": "a cat", "ratio": "16:9"})
    task = ComfyUIVideoGenerationTask(
        adapter=_FakeComfyUIAdapter(fail=True),  # type: ignore[arg-type]
        provider_config=cfg,
        input_=inp,
        poll_interval_s=0.0,
        timeout_s=5.0,
    )
    await task.run()
    result = await task.get_result()
    assert result is None
    status = await task.status()
    assert "ComfyUI execution failed" in status["error"]


@pytest.mark.asyncio
async def test_video_generation_task_dispatches_to_comfyui() -> None:
    from app.bootstrap import bootstrap_all_registries

    bootstrap_all_registries()
    cfg = ProviderConfig(provider="comfyui", api_key="", base_url="http://127.0.0.1:8188")
    inp = VideoGenerationInput.model_validate({"prompt": "a cat", "ratio": "16:9"})
    task = VideoGenerationTask(provider_config=cfg, input_=inp)
    assert isinstance(task._impl, ComfyUIVideoGenerationTask)  # type: ignore[attr-defined]
