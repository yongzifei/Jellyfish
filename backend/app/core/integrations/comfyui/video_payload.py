"""ComfyUI 工作流构建：MiniMax Hailuo H3 文生视频节点 + SaveVideo 落盘节点。"""

from __future__ import annotations

from typing import Any

from app.core.integrations.comfyui.video_capabilities import validate_comfyui_video_options
from app.core.integrations.video_capabilities import resolve_effective_ratio
from app.core.contracts.video_generation import VideoGenerationInput

# ComfyUI 节点：MinimaxHailuo03TextToVideoNode（前端展示名 "MiniMax H3 Text to Video"）。
COMFYUI_MINIMAX_H3_NODE_CLASS = "MinimaxHailuo03TextToVideoNode"
COMFYUI_SAVE_VIDEO_NODE_CLASS = "SaveVideo"

# 节点 model 下拉框允许的三个档位；"H3" 为基础档，其余为增强档。
_H3_MODEL_CHOICES = ("MiniMax H3", "MiniMax H3 Max", "MiniMax H3 Max Turbo")
_H3_DEFAULT_MODEL = "MiniMax H3"

# 该节点标准档 resolution 允许 {"768P", "2K"}，增强档允许 {"480P", "768P"}；
# "768P" 在三个档位下均合法，作为固定默认值可避免引入额外可配参数。
_H3_DEFAULT_RESOLUTION = "768P"
_H3_DEFAULT_DURATION = 6
_H3_DEFAULT_SEED = 42
_H3_DEFAULT_PROMPT_EXPANSION_MODE = "balanced"


def _normalize_model_choice(model: str | None) -> str:
    """把用户/模型配置里的简写（如 "minimax h3"、"h3 max"）归一化为节点要求的确切枚举值。"""
    value = (model or "").strip().lower()
    if not value:
        return _H3_DEFAULT_MODEL
    for choice in _H3_MODEL_CHOICES:
        if value == choice.lower():
            return choice
    if "max" in value and "turbo" in value:
        return "MiniMax H3 Max Turbo"
    if "max" in value:
        return "MiniMax H3 Max"
    return _H3_DEFAULT_MODEL


def build_minimax_h3_node_inputs(input_: VideoGenerationInput) -> dict[str, Any]:
    """构建 MinimaxHailuo03TextToVideoNode 的 inputs 字典。"""
    prompt = (input_.prompt or "").strip()
    if not prompt:
        raise RuntimeError("ComfyUI MiniMax H3 text-to-video requires a non-empty prompt")

    model_choice = _normalize_model_choice(input_.model)
    effective_ratio = resolve_effective_ratio(input_)

    node_inputs: dict[str, Any] = {
        "model": model_choice,
        "prompt": prompt,
        "resolution": _H3_DEFAULT_RESOLUTION,
        "ratio": effective_ratio,
        "duration": int(input_.seconds) if input_.seconds is not None else _H3_DEFAULT_DURATION,
        "seed": int(input_.seed) if input_.seed is not None and input_.seed >= 0 else _H3_DEFAULT_SEED,
        "watermark": bool(input_.watermark) if input_.watermark is not None else False,
    }
    if model_choice != _H3_DEFAULT_MODEL:
        node_inputs["prompt_expansion_mode"] = _H3_DEFAULT_PROMPT_EXPANSION_MODE
    return node_inputs


def build_text_to_video_workflow(
    input_: VideoGenerationInput,
    *,
    filename_prefix: str = "jellyfish/minimax_h3",
) -> dict[str, Any]:
    """构建两节点工作流：MiniMax H3 生成 + SaveVideo 落盘，供 /prompt 提交。"""
    validate_comfyui_video_options(input_)
    node_inputs = build_minimax_h3_node_inputs(input_)

    return {
        "1": {
            "class_type": COMFYUI_MINIMAX_H3_NODE_CLASS,
            "inputs": node_inputs,
        },
        "2": {
            "class_type": COMFYUI_SAVE_VIDEO_NODE_CLASS,
            "inputs": {
                "video": ["1", 0],
                "filename_prefix": filename_prefix,
                "format": "mp4",
            },
        },
    }
