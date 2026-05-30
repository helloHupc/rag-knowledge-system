"""Image captioning using multimodal LLM."""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Union

import httpx

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)

DEFAULT_CAPTION_PROMPT = """请详细描述这张图片的内容，包括：
1. 图片类型（照片/图表/流程图/架构图/表格截图/文档截图等）
2. 主要内容和关键信息
3. 如果是图表，描述数据趋势和关键数值
4. 如果是流程图，描述各个步骤和关系
5. 如果包含文字，列出关键文字内容

用中文回答，描述要详细准确，便于后续检索。"""


class ImageCaptionProvider:
    """用多模态大模型生成图片描述"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api_base = settings.multimodal_api_base
        self.api_key = settings.multimodal_api_key
        self.model = settings.multimodal_model
        self.timeout = 60.0

    def is_configured(self) -> bool:
        return bool(self.api_base and self.api_key and self.model)

    async def caption(
        self,
        image_data: Union[bytes, Path, str],
        prompt: str | None = None,
    ) -> str:
        """生成图片描述"""
        if not self.is_configured():
            raise AppError(
                code=ErrorCode.IMAGE_RECOGNITION_FAILED,
                message="multimodal provider is not configured",
                status_code=422,
            )

        # 读取图片数据
        if isinstance(image_data, (str, Path)):
            path = Path(image_data)
            if not path.exists():
                raise AppError(
                    code=ErrorCode.IMAGE_RECOGNITION_FAILED,
                    message=f"Image file not found: {path}",
                    status_code=400,
                )
            with open(path, "rb") as f:
                image_bytes = f.read()
            mime_type = self._get_mime_type(path.suffix)
        else:
            image_bytes = image_data
            mime_type = "image/jpeg"

        # 编码为 base64
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        # 调用 API
        caption_prompt = prompt or DEFAULT_CAPTION_PROMPT
        return await self._call_api(image_base64, mime_type, caption_prompt)

    async def _call_api(
        self,
        image_base64: str,
        mime_type: str,
        prompt: str,
    ) -> str:
        """调用多模态 API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_base64}",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 1024,
        }

        async with httpx.AsyncClient(timeout=self.timeout, proxy=None) as client:
            response = await client.post(
                f"{self.api_base}/chat/completions",
                headers=headers,
                json=payload,
            )

            if response.status_code != 200:
                raise AppError(
                    code=ErrorCode.IMAGE_RECOGNITION_FAILED,
                    message=f"Multimodal API request failed: {response.text}",
                    status_code=response.status_code,
                )

            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                raise AppError(
                    code=ErrorCode.IMAGE_RECOGNITION_FAILED,
                    message="Multimodal API returned no choices",
                    status_code=500,
                )

            content = choices[0].get("message", {}).get("content", "")
            return content.strip()

    def _get_mime_type(self, suffix: str) -> str:
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
            ".webp": "image/webp",
        }
        return mime_map.get(suffix.lower(), "image/jpeg")
