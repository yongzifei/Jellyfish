---
title: "接入 ComfyUI：MiniMax H3 文生视频"
weight: 13
description: "如何配置 ComfyUI 供应商，并通过其 MiniMax Hailuo H3 节点跑通文生视频。"
---

Jellyfish 内置了一个 `comfyui` 供应商 key，用于通过某个已运行的 ComfyUI 服务器的
HTTP API 调用其自带的 MiniMax Hailuo（节点前端展示名 "MiniMax H3 Text to Video"，
`class_type` 为 `MinimaxHailuo03TextToVideoNode`）文生视频节点。

## 与 OpenAI / 火山方舟的关键差异

- OpenAI / 火山方舟的 `base_url` 直接指向供应商自己的 API 网关；
  `comfyui` 的 `base_url` 指向的是**你自己部署/可访问的 ComfyUI 服务器**
  （例如 `http://127.0.0.1:8188`），Jellyfish 不直接调用 MiniMax。
- `comfyui` 的 `api_key` 不是 MiniMax 的密钥，而是 **comfy.org 签发的 API Key**：
  ComfyUI 把 MiniMax 节点做成了官方 "API 节点"，实际请求经 ComfyUI 自身的
  `/proxy/minimax/...` 网关转发，鉴权信息通过 `POST /prompt` 请求体里的
  `extra_data.api_key_comfy_org` 字段注入节点隐藏输入。
  如果目标 ComfyUI 服务端已经在自己一侧配置好该凭证（例如自托管网关），
  这里的 `api_key` 也可以留空——因此 `comfyui` 的 `requires_api_key=False`。

## 配置步骤

1. 确保目标 ComfyUI 实例可从 Jellyfish 后端网络访问，且已加载官方
   `comfy_api_nodes`（自带 `MinimaxHailuo03TextToVideoNode` 与 `SaveVideo`）。
2. 在 Jellyfish 的供应商管理中新增一个 Provider：
   - `name`：填 `comfyui`（或任意包含 `comfyui`/`comfy`/`minimax h3`/`hailuo`
     的别名，均可被 `resolve_provider_key_from_name` 解析到 `comfyui`）。
   - `video_base_url` 或 `base_url`：填 ComfyUI 服务器地址。
   - `api_key`：填 comfy.org API Key（如目标服务端已自行配置鉴权可留空）。
3. 新增一个 `category=video` 的 Model，`provider_id` 指向上一步的 Provider；
   `Model.name` 建议填 `MiniMax H3` / `MiniMax H3 Max` / `MiniMax H3 Max Turbo`
   之一（大小写、连字符不敏感，未识别时按 `MiniMax H3` 处理）。
4. 将该 Model 设为默认视频模型（或在具体生成入口显式选择），即可像
   OpenAI / 火山方舟一样发起视频生成任务。

## 实现位置

- 供应商能力声明：`app/services/llm/provider_bootstrap.py`
- 任务执行器注册：`app/core/tasks/bootstrap.py`
- 工作流构建（MiniMax H3 节点 + `SaveVideo` 落盘节点）：
  `app/core/integrations/comfyui/video_payload.py`
- HTTP 适配层（`/prompt` 提交、`/history` 轮询、`/view` 取产物）：
  `app/core/integrations/comfyui/video.py`
- 任务生命周期与轮询节奏：`app/core/tasks/video_generation_tasks.py`
  中的 `ComfyUIVideoGenerationTask`

## 参数映射

Jellyfish 通用视频生成入参（`VideoGenerationInput`）到 ComfyUI 节点输入的映射：

| Jellyfish 字段 | 节点字段 | 说明 |
| --- | --- | --- |
| `prompt` | `prompt` | 必填，节点本身要求非空文本 |
| `ratio` | `ratio` | 取值范围与节点完全一致（`16:9`/`4:3`/`1:1`/`3:4`/`9:16`/`21:9`） |
| `seconds` | `duration` | 允许范围 4–15 秒，超出范围会在提交前报错 |
| `seed` | `seed` | 未提供或为 `-1` 时使用节点默认值 `42` |
| `watermark` | `watermark` | 未提供时默认为 `false` |
| `model` | `model` | 归一化为 `MiniMax H3` / `MiniMax H3 Max` / `MiniMax H3 Max Turbo` |

`resolution`（固定 `768P`，在三个模型档位下均合法）与 `prompt_expansion_mode`
（仅 Max/Max Turbo 档位需要，固定 `balanced`）当前未纳入通用契约，属于内部固定
默认值，如需可调整需在 `video_payload.py` 中扩展。
