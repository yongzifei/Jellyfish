from __future__ import annotations

from app.models.llm import ModelCategoryKey
from app.services.llm.provider_registry import ProviderSpec, register_many


def bootstrap_builtin_providers() -> None:
    register_many(
        [
            ProviderSpec(
                key="openai",
                display_name="OpenAI",
                aliases=("openai",),
                supported_categories=(
                    ModelCategoryKey.text,
                    ModelCategoryKey.image,
                    ModelCategoryKey.video,
                ),
                default_base_url="https://api.openai.com/v1",
            ),
            ProviderSpec(
                key="volcengine",
                display_name="火山引擎",
                aliases=("火山引擎", "volcengine", "volc", "doubao", "bytedance", "ark"),
                supported_categories=(ModelCategoryKey.image, ModelCategoryKey.video),
                default_base_url="https://ark.cn-beijing.volces.com/api/v3",
            ),
            ProviderSpec(
                key="aliyun_bailian",
                display_name="阿里百炼",
                aliases=("阿里百炼", "aliyun", "bailian", "dashscope"),
                supported_categories=(ModelCategoryKey.text,),
                default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
            ProviderSpec(
                key="comfyui",
                display_name="ComfyUI",
                aliases=("comfyui", "comfy", "minimax h3", "minimax-h3", "hailuo"),
                supported_categories=(ModelCategoryKey.video,),
                default_base_url="http://127.0.0.1:8188",
                # api_key 对应 ComfyUI API 节点鉴权用的 comfy.org API Key；
                # 部分自托管环境会在 ComfyUI 服务端自行配置该凭证，故不强制要求。
                requires_api_key=False,
            ),
        ]
    )
