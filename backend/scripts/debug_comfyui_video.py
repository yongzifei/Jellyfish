#!/usr/bin/env python3
"""对接真实 ComfyUI（自托管或 ComfyUI Cloud）调试脚本：发起一次真实的 MiniMax H3 文生视频请求。

用法（在 backend 目录下）::

    COMFY_API_KEY=xxx uv run python scripts/debug_comfyui_video.py --base-url https://your-comfyui-host

注意：
- 这会向目标 ComfyUI 发起真实的 /prompt 请求，若节点执行成功会真实调用 MiniMax，
  可能消耗 comfy.org / MiniMax 侧的真实额度，请确认后再运行。
- 不依赖数据库/完整 FastAPI 应用，仅使用 app.core.integrations.comfyui 与
  app.core.tasks.video_generation_tasks 中已实现的适配层，方便脱离 Jellyfish 主流程单独验证。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.core.contracts.provider import ProviderConfig
from app.core.contracts.video_generation import VideoGenerationInput
from app.core.tasks.video_generation_tasks import VideoGenerationTask


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="ComfyUI 服务器地址，例如 http://127.0.0.1:8188 或 Cloud 实例地址")
    parser.add_argument("--api-key", default=None, help="comfy.org API Key；不传则回落到环境变量 COMFY_API_KEY")
    parser.add_argument("--prompt", default="a jellyfish swimming in deep blue ocean, cinematic lighting")
    parser.add_argument("--ratio", default="16:9", choices=["16:9", "4:3", "1:1", "3:4", "9:16", "21:9"])
    parser.add_argument("--seconds", type=int, default=6, help="4-15 秒")
    parser.add_argument("--model", default="MiniMax H3", help="MiniMax H3 / MiniMax H3 Max / MiniMax H3 Max Turbo")
    parser.add_argument("--poll-interval", type=float, default=3.0)
    parser.add_argument("--timeout", type=float, default=600.0, help="单次 HTTP 请求超时（秒）")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()

    provider_config = ProviderConfig(
        provider="comfyui",  # type: ignore[arg-type]
        api_key=args.api_key or "",
        base_url=args.base_url,
    )
    input_ = VideoGenerationInput.model_validate(
        {
            "prompt": args.prompt,
            "ratio": args.ratio,
            "seconds": args.seconds,
            "model": args.model,
        }
    )

    print(f"[debug] base_url={args.base_url!r} model={args.model!r} ratio={args.ratio!r} seconds={args.seconds}")
    task = VideoGenerationTask(
        provider_config=provider_config,
        input_=input_,
        poll_interval_s=args.poll_interval,
        timeout_s=args.timeout,
    )
    await task.run()
    status = await task.status()
    result = await task.get_result()

    print("[debug] status:")
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if result is None:
        print("[debug] FAILED: no result. See error above.")
        return 1

    print("[debug] result:")
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
