"""ComfyUI：工作流提交（/prompt）与执行历史查询（/history）。"""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import urlencode

from app.config import settings
from app.core.integrations.comfyui.video_payload import build_text_to_video_workflow
from app.core.contracts.provider import ProviderConfig
from app.core.contracts.video_generation import VideoGenerationInput

DEFAULT_COMFYUI_BASE_URL = "http://127.0.0.1:8188"


def resolve_comfyui_api_key(cfg: ProviderConfig) -> str:
    """解析实际使用的 comfy.org API Key：DB 里 Provider.api_key 优先，其次回落到环境变量 COMFY_API_KEY。"""
    api_key = (cfg.api_key or "").strip()
    if api_key:
        return api_key
    return (settings.comfy_api_key or "").strip()


class ComfyUIVideoApiAdapter:
    """ComfyUI 工作流 HTTP：提交 MiniMax H3 文生视频工作流并轮询产物。"""

    async def queue_prompt(
        self,
        *,
        cfg: ProviderConfig,
        input_: VideoGenerationInput,
        timeout_s: float,
    ) -> str:
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("httpx is required for video generation tasks") from e

        base_url = (cfg.base_url or DEFAULT_COMFYUI_BASE_URL).rstrip("/")
        workflow = build_text_to_video_workflow(input_)

        body: dict[str, Any] = {
            "prompt": workflow,
            "client_id": uuid.uuid4().hex,
        }
        # MiniMax H3 是 ComfyUI 的 API 节点，鉴权走 comfy.org 签发的 API Key，
        # 通过 extra_data.api_key_comfy_org 注入节点隐藏输入（而非 Authorization 头）。
        api_key = resolve_comfyui_api_key(cfg)
        if api_key:
            body["extra_data"] = {"api_key_comfy_org": api_key}

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.post(f"{base_url}/prompt", json=body)
            r.raise_for_status()
            data: dict[str, Any] = r.json()
            prompt_id = str(data.get("prompt_id") or "")
            if not prompt_id:
                raise RuntimeError(f"ComfyUI queue prompt missing prompt_id: {data!r}")
            return prompt_id

    async def get_history(
        self,
        *,
        cfg: ProviderConfig,
        prompt_id: str,
        timeout_s: float,
    ) -> dict[str, Any]:
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("httpx is required for video generation tasks") from e

        base_url = (cfg.base_url or DEFAULT_COMFYUI_BASE_URL).rstrip("/")

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(f"{base_url}/history/{prompt_id}")
            r.raise_for_status()
            data: dict[str, Any] = r.json()
            entry = data.get(prompt_id)
            return entry if isinstance(entry, dict) else {}

    def build_view_url(self, *, cfg: ProviderConfig, filename: str, subfolder: str, file_type: str) -> str:
        base_url = (cfg.base_url or DEFAULT_COMFYUI_BASE_URL).rstrip("/")
        query = urlencode({"filename": filename, "subfolder": subfolder, "type": file_type})
        return f"{base_url}/view?{query}"

    def find_output_video(self, history_entry: dict[str, Any]) -> dict[str, Any] | None:
        """从 /history 返回的节点输出中提取视频文件描述（不同 ComfyUI 版本字段名不完全一致，做兼容扫描）。"""
        outputs = history_entry.get("outputs")
        if not isinstance(outputs, dict):
            return None
        for node_output in outputs.values():
            if not isinstance(node_output, dict):
                continue
            for value in node_output.values():
                if not isinstance(value, list):
                    continue
                for item in value:
                    if isinstance(item, dict) and item.get("filename"):
                        return item
        return None

    def is_execution_error(self, history_entry: dict[str, Any]) -> str | None:
        status = history_entry.get("status")
        if not isinstance(status, dict):
            return None
        if status.get("status_str") == "error":
            messages = status.get("messages")
            return str(messages) if messages else "ComfyUI execution failed"
        return None

    def is_completed(self, history_entry: dict[str, Any]) -> bool:
        status = history_entry.get("status")
        if isinstance(status, dict) and status.get("completed") is True:
            return True
        return bool(history_entry.get("outputs"))
