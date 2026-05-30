from __future__ import annotations

import base64
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode

logger = logging.getLogger(__name__)


class RecognitionProviderType(str, Enum):
    PADDLE_OCR = "paddle_ocr"
    MULTIMODAL = "multimodal"


@dataclass(slots=True)
class RecognitionResult:
    """图片识别结果"""
    text: str
    confidence: float = 1.0
    provider_name: str = ""
    model_name: str = ""
    processing_time_ms: int = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass(slots=True)
class TableRecognitionResult(RecognitionResult):
    """表格识别结果"""
    rows: List[List[str]] = None
    headers: List[str] = None
    
    def __post_init__(self):
        super().__post_init__()
        if self.rows is None:
            self.rows = []
        if self.headers is None:
            self.headers = []


class ImageRecognitionProvider(ABC):
    """图片识别提供者抽象基类"""
    
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
    
    @abstractmethod
    async def recognize_image(
        self, 
        image_data: Union[bytes, Path, str],
        **kwargs
    ) -> RecognitionResult:
        """识别单张图片
        
        Args:
            image_data: 图片数据，可以是字节、文件路径或URL
            **kwargs: 额外参数
            
        Returns:
            RecognitionResult: 识别结果
        """
        pass
    
    @abstractmethod
    async def recognize_batch(
        self, 
        images: List[Union[bytes, Path, str]],
        **kwargs
    ) -> List[RecognitionResult]:
        """批量识别图片
        
        Args:
            images: 图片列表
            **kwargs: 额外参数
            
        Returns:
            List[RecognitionResult]: 识别结果列表
        """
        pass
    
    def is_configured(self) -> bool:
        """检查提供者是否已配置"""
        return True
    
    def probe(self) -> bool:
        """探测提供者是否可用"""
        try:
            # 创建一个简单的测试图片
            test_image = self._create_test_image()
            return self.is_configured()
        except Exception:
            return False
    
    def _create_test_image(self) -> bytes:
        """创建测试图片（1x1像素白色PNG）"""
        # 最小的PNG图片
        png_data = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        return png_data


class PaddleOCRProvider(ImageRecognitionProvider):
    """PaddleOCR在线接口提供者"""
    
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.api_base = "https://paddleocr.aistudio-app.com/api/v2/ocr"
        self.token = settings.paddle_ocr_token
        self.model = "PaddleOCR-VL-1.5"
        self.timeout = 30.0
    
    def is_configured(self) -> bool:
        return bool(self.token)
    
    async def recognize_image(
        self, 
        image_data: Union[bytes, Path, str],
        **kwargs
    ) -> RecognitionResult:
        """使用PaddleOCR识别单张图片"""
        import time
        start_time = time.time()
        
        try:
            # 准备请求数据
            if isinstance(image_data, (str, Path)):
                path = Path(image_data)
                if not path.exists():
                    raise AppError(
                        code=ErrorCode.IMAGE_RECOGNITION_FAILED,
                        message=f"Image file not found: {path}",
                        status_code=400,
                    )
                with open(path, "rb") as f:
                    file_content = f.read()
                filename = path.name
            else:
                file_content = image_data
                filename = "image.jpg"
            
            # 提交OCR任务
            job_id = await self._submit_ocr_job(file_content, filename)
            
            # 轮询结果
            result = await self._poll_job_result(job_id)
            
            processing_time = int((time.time() - start_time) * 1000)
            
            return RecognitionResult(
                text=result.get("text", ""),
                confidence=result.get("confidence", 1.0),
                provider_name="paddle_ocr",
                model_name=self.model,
                processing_time_ms=processing_time,
                metadata={
                    "job_id": job_id,
                    "raw_result": result,
                }
            )
            
        except Exception as e:
            if isinstance(e, AppError):
                raise
            logger.exception("PaddleOCR recognition failed")
            raise AppError(
                code=ErrorCode.IMAGE_RECOGNITION_FAILED,
                message=f"PaddleOCR recognition failed: {e}",
                status_code=500,
            )
    
    async def recognize_batch(
        self, 
        images: List[Union[bytes, Path, str]],
        **kwargs
    ) -> List[RecognitionResult]:
        """批量识别图片（并行处理）"""
        import asyncio
        
        # 使用信号量限制并发数
        semaphore = asyncio.Semaphore(self.settings.image_recognition_batch_size)
        
        async def process_one(image: Union[bytes, Path, str]) -> RecognitionResult:
            async with semaphore:
                return await self.recognize_image(image, **kwargs)
        
        tasks = [process_one(image) for image in images]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常情况
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Batch image %d failed: %s", i, result)
                final_results.append(
                    RecognitionResult(
                        text=f"[识别失败: {result}]",
                        confidence=0.0,
                        provider_name="paddle_ocr",
                        metadata={"error": str(result)},
                    )
                )
            else:
                final_results.append(result)
        
        return final_results
    
    async def _submit_ocr_job(self, file_content: bytes, filename: str) -> str:
        """提交OCR任务"""
        headers = {
            "Authorization": f"bearer {self.token}",
        }
        
        data = {
            "model": self.model,
            "optionalPayload": '{"useDocOrientationClassify": false, "useDocUnwarping": false, "useChartRecognition": true}',
        }
        
        files = {"file": (filename, file_content)}
        
        async with httpx.AsyncClient(timeout=self.timeout, proxy=None) as client:
            response = await client.post(
                f"{self.api_base}/jobs",
                headers=headers,
                data=data,
                files=files,
            )
            
            if response.status_code != 200:
                raise AppError(
                    code=ErrorCode.IMAGE_RECOGNITION_FAILED,
                    message=f"PaddleOCR job submission failed: {response.text}",
                    status_code=response.status_code,
                )
            
            result = response.json()
            return result["data"]["jobId"]
    
    async def _poll_job_result(self, job_id: str) -> Dict[str, Any]:
        """轮询任务结果（带超时和重试）"""
        import asyncio
        
        headers = {
            "Authorization": f"bearer {self.token}",
        }
        
        max_retries = 3
        retry_count = 0
        
        async with httpx.AsyncClient(timeout=self.timeout, proxy=None) as client:
            while True:
                try:
                    response = await client.get(
                        f"{self.api_base}/jobs/{job_id}",
                        headers=headers,
                    )
                    
                    if response.status_code != 200:
                        retry_count += 1
                        if retry_count >= max_retries:
                            raise AppError(
                                code=ErrorCode.IMAGE_RECOGNITION_FAILED,
                                message=f"PaddleOCR job status check failed after {max_retries} retries: {response.text}",
                                status_code=response.status_code,
                            )
                        logger.warning("PaddleOCR status check failed (attempt %d/%d): %s", retry_count, max_retries, response.text)
                        await asyncio.sleep(2 * retry_count)  # 指数退避
                        continue
                    
                    data = response.json()["data"]
                    state = data["state"]
                    
                    if state == "done":
                        # 获取结果
                        result_url = data["resultUrl"]["jsonUrl"]
                        result_response = await client.get(result_url)
                        result_response.raise_for_status()
                        
                        # 解析结果
                        lines = result_response.text.strip().split('\n')
                        all_text = []
                        for line in lines:
                            if not line.strip():
                                continue
                            line_data = json.loads(line.strip())
                            result = line_data["result"]
                            for layout_result in result.get("layoutParsingResults", []):
                                markdown_text = layout_result.get("markdown", {}).get("text", "")
                                if markdown_text:
                                    # 提取纯文本（去除HTML标签）
                                    import re
                                    # 移除HTML标签，保留文本
                                    clean_text = re.sub(r'<[^>]+>', '', markdown_text)
                                    # 移除多余空白行
                                    clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)
                                    clean_text = clean_text.strip()
                                    if clean_text:
                                        all_text.append(clean_text)
                        
                        return {
                            "text": "\n\n".join(all_text),
                            "confidence": 1.0,
                            "raw_data": data,
                        }
                    
                    elif state == "failed":
                        error_msg = data.get("errorMsg", "Unknown error")
                        raise AppError(
                            code=ErrorCode.IMAGE_RECOGNITION_FAILED,
                            message=f"PaddleOCR job failed: {error_msg}",
                            status_code=500,
                        )
                    
                    # 等待后重试
                    await asyncio.sleep(2)
                    
                except httpx.RequestError as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise AppError(
                            code=ErrorCode.IMAGE_RECOGNITION_FAILED,
                            message=f"PaddleOCR request failed after {max_retries} retries: {e}",
                            status_code=500,
                        )
                    logger.warning("PaddleOCR request error (attempt %d/%d): %s", retry_count, max_retries, e)
                    await asyncio.sleep(2 * retry_count)


class MultimodalProvider(ImageRecognitionProvider):
    """多模态大模型提供者（基于OpenAI兼容接口）"""
    
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.api_base = settings.multimodal_api_base
        self.api_key = settings.multimodal_api_key
        self.model = settings.multimodal_model or "gpt-4-vision-preview"
        self.timeout = 60.0
    
    def is_configured(self) -> bool:
        return bool(self.api_base and self.api_key and self.model)
    
    async def recognize_image(
        self, 
        image_data: Union[bytes, Path, str],
        **kwargs
    ) -> RecognitionResult:
        """使用多模态大模型识别单张图片"""
        import time
        start_time = time.time()
        
        try:
            # 准备图片数据
            if isinstance(image_data, (str, Path)):
                path = Path(image_data)
                if not path.exists():
                    raise AppError(
                        code=ErrorCode.IMAGE_RECOGNITION_FAILED,
                        message=f"Image file not found: {path}",
                        status_code=400,
                    )
                with open(path, "rb") as f:
                    image_content = f.read()
                # 确定MIME类型
                mime_type = self._get_mime_type(path.suffix)
            else:
                image_content = image_data
                mime_type = "image/jpeg"
            
            # 编码图片为base64
            image_base64 = base64.b64encode(image_content).decode("utf-8")
            
            # 准备提示词
            prompt = kwargs.get("prompt", "请识别图片中的所有文字内容，包括表格、图表等。如果是表格，请以markdown表格格式输出。")
            
            # 调用API
            result = await self._call_multimodal_api(image_base64, mime_type, prompt)
            
            processing_time = int((time.time() - start_time) * 1000)
            
            return RecognitionResult(
                text=result.get("text", ""),
                confidence=result.get("confidence", 1.0),
                provider_name="multimodal",
                model_name=self.model,
                processing_time_ms=processing_time,
                metadata={
                    "usage": result.get("usage", {}),
                    "model": result.get("model", self.model),
                }
            )
            
        except Exception as e:
            if isinstance(e, AppError):
                raise
            logger.exception("Multimodal recognition failed")
            raise AppError(
                code=ErrorCode.IMAGE_RECOGNITION_FAILED,
                message=f"Multimodal recognition failed: {e}",
                status_code=500,
            )
    
    async def recognize_batch(
        self, 
        images: List[Union[bytes, Path, str]],
        **kwargs
    ) -> List[RecognitionResult]:
        """批量识别图片（并行处理）"""
        import asyncio
        
        # 使用信号量限制并发数
        semaphore = asyncio.Semaphore(self.settings.image_recognition_batch_size)
        
        async def process_one(image: Union[bytes, Path, str]) -> RecognitionResult:
            async with semaphore:
                return await self.recognize_image(image, **kwargs)
        
        tasks = [process_one(image) for image in images]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常情况
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Batch image %d failed: %s", i, result)
                final_results.append(
                    RecognitionResult(
                        text=f"[识别失败: {result}]",
                        confidence=0.0,
                        provider_name="multimodal",
                        metadata={"error": str(result)},
                    )
                )
            else:
                final_results.append(result)
        
        return final_results
    
    async def _call_multimodal_api(
        self, 
        image_base64: str, 
        mime_type: str, 
        prompt: str
    ) -> Dict[str, Any]:
        """调用多模态API"""
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
                        {
                            "type": "text",
                            "text": prompt,
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_base64}",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 4096,
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
            
            # 提取响应内容
            choices = data.get("choices", [])
            if not choices:
                raise AppError(
                    code=ErrorCode.IMAGE_RECOGNITION_FAILED,
                    message="Multimodal API returned no choices",
                    status_code=500,
                )
            
            message = choices[0].get("message", {})
            content = message.get("content", "")
            
            return {
                "text": content,
                "confidence": 1.0,
                "usage": data.get("usage", {}),
                "model": data.get("model", self.model),
            }
    
    def _get_mime_type(self, suffix: str) -> str:
        """根据文件后缀获取MIME类型"""
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


def create_image_recognition_provider(settings: Settings) -> ImageRecognitionProvider:
    """根据配置创建图片识别提供者"""
    provider_type = settings.image_recognition_provider.lower()
    
    if provider_type == RecognitionProviderType.PADDLE_OCR:
        return PaddleOCRProvider(settings)
    elif provider_type == RecognitionProviderType.MULTIMODAL:
        return MultimodalProvider(settings)
    else:
        # 默认使用PaddleOCR
        return PaddleOCRProvider(settings)
