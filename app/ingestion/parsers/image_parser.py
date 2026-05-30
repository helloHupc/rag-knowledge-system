from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Union

from app.core.config import get_settings
from app.core.errors import AppError, ErrorCode
from app.ingestion.parsers.common import normalize_text
from app.ingestion.types import ParsedBlock
from app.integrations.image_recognition import (
    ImageRecognitionProvider,
    RecognitionResult,
    create_image_recognition_provider,
)
from app.integrations.image_caption import ImageCaptionProvider

logger = logging.getLogger(__name__)

# 支持的图片格式
SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"
}


def _run_async(coro):
    """在同步上下文中运行异步协程"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # 已有运行中的事件循环（如 FastAPI），用 nest_asyncio 或直接在线程中跑
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


class ImageParser:
    """图片解析器"""

    def __init__(self, recognition_provider: Optional[ImageRecognitionProvider] = None, caption_provider: Optional[ImageCaptionProvider] = None):
        self.settings = get_settings()
        self.recognition_provider = recognition_provider or create_image_recognition_provider(self.settings)
        self.caption_provider = caption_provider or ImageCaptionProvider(self.settings)
        
        # 根据配置自动选择识别模式
        ocr_configured = self.recognition_provider.is_configured()
        caption_configured = self.caption_provider.is_configured()
        
        if ocr_configured and caption_configured:
            self.recognition_mode = "hybrid"
        elif ocr_configured:
            self.recognition_mode = "ocr"
        elif caption_configured:
            self.recognition_mode = "caption"
        else:
            self.recognition_mode = "none"
            logger.warning("Neither OCR nor caption provider is configured")

    def parse(self, file_path: Path) -> list[ParsedBlock]:
        """解析单个图片文件"""
        if not file_path.exists():
            raise AppError(
                code=ErrorCode.DOCUMENT_PARSE_FAILED,
                message=f"Image file not found: {file_path}",
                status_code=400,
            )

        # 检查文件格式
        if file_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            raise AppError(
                code=ErrorCode.UNSUPPORTED_FILE_TYPE,
                message=f"Unsupported image format: {file_path.suffix}",
                status_code=400,
            )

        try:
            ocr_result = None
            caption_text = None
            
            # OCR 识别
            if self.recognition_mode in ("ocr", "hybrid"):
                ocr_result = _run_async(
                    self.recognition_provider.recognize_image(file_path)
                )
            
            # 多模态描述
            if self.recognition_mode in ("caption", "hybrid") and self.caption_provider.is_configured():
                caption_text = _run_async(
                    self.caption_provider.caption(file_path)
                )
            
            # 合并结果
            if self.recognition_mode == "caption" and caption_text:
                result = RecognitionResult(
                    text=caption_text,
                    confidence=1.0,
                    provider_name="multimodal_caption",
                    model_name=self.settings.multimodal_model or "unknown",
                )
            elif ocr_result:
                if caption_text and self.recognition_mode == "hybrid":
                    # 合并 OCR 和描述
                    combined_text = ocr_result.text
                    if caption_text:
                        combined_text = f"{ocr_result.text}\n\n[图片描述]\n{caption_text}"
                    result = RecognitionResult(
                        text=combined_text,
                        confidence=ocr_result.confidence,
                        provider_name=ocr_result.provider_name,
                        model_name=ocr_result.model_name,
                        metadata={**ocr_result.metadata, "caption": caption_text},
                    )
                else:
                    result = ocr_result
            else:
                raise AppError(
                    code=ErrorCode.IMAGE_RECOGNITION_FAILED,
                    message="图片识别服务未配置，请配置 PaddleOCR Token 或多模态 API",
                    status_code=422,
                )

            # 处理识别结果
            return self._process_recognition_result(result, file_path)

        except Exception as e:
            if isinstance(e, AppError):
                raise
            logger.exception("Image parsing failed for %s", file_path)
            raise AppError(
                code=ErrorCode.DOCUMENT_PARSE_FAILED,
                message=f"Image parsing failed: {e}",
                status_code=500,
            )

    def parse_batch(self, images: List[Union[bytes, Path, str]]) -> List[ParsedBlock]:
        """批量解析图片文件"""
        if not images:
            return []

        try:
            # 批量调用识别服务
            results = _run_async(
                self.recognition_provider.recognize_batch(images)
            )

            # 处理所有结果
            all_blocks = []
            for image, result in zip(images, results):
                if isinstance(image, (str, Path)):
                    file_path = Path(image)
                else:
                    file_path = Path("image.jpg")  # 默认文件名
                blocks = self._process_recognition_result(result, file_path)
                all_blocks.extend(blocks)

            return all_blocks

        except Exception as e:
            if isinstance(e, AppError):
                raise
            logger.exception("Batch image parsing failed")
            raise AppError(
                code=ErrorCode.DOCUMENT_PARSE_FAILED,
                message=f"Batch image parsing failed: {e}",
                status_code=500,
            )

    def _process_recognition_result(
        self,
        result: RecognitionResult,
        file_path: Path
    ) -> List[ParsedBlock]:
        """处理识别结果，转换为ParsedBlock格式"""
        blocks = []

        # 标准化文本
        text = normalize_text(result.text)
        if not text:
            # 如果没有识别到文本，创建一个空块
            text = f"[图片内容识别为空: {file_path.name}]"

        # 检查是否包含表格
        if self._contains_table(text):
            # 如果是表格，尝试解析为表格格式
            table_blocks = self._parse_table_content(text, file_path, result)
            blocks.extend(table_blocks)
        else:
            # 普通文本
            metadata = {
                "parser": "image_recognition",
                "provider": result.provider_name,
                "model": result.model_name,
                "confidence": result.confidence,
                "processing_time_ms": result.processing_time_ms,
                "source_file": file_path.name,
                "file_type": "image",
            }

            blocks.append(
                ParsedBlock(
                    text=text,
                    page_no=1,  # 图片默认为第1页
                    metadata=metadata,
                )
            )

        return blocks

    def _contains_table(self, text: str) -> bool:
        """检查文本是否包含表格"""
        lines = text.strip().split('\n')
        if len(lines) < 2:
            return False

        # 检查markdown表格语法
        for line in lines:
            if '|' in line and ('---' in line or '---' in line):
                return True

        # 检查竖线分隔的表格
        pipe_count = sum(1 for line in lines if '|' in line)
        if pipe_count >= 2:
            return True

        return False

    def _parse_table_content(
        self,
        text: str,
        file_path: Path,
        result: RecognitionResult
    ) -> List[ParsedBlock]:
        """解析表格内容"""
        blocks = []

        # 尝试解析markdown表格
        table_data = self._parse_markdown_table(text)

        if table_data:
            # 成功解析为表格
            headers, rows = table_data

            metadata = {
                "parser": "image_recognition",
                "provider": result.provider_name,
                "model": result.model_name,
                "confidence": result.confidence,
                "processing_time_ms": result.processing_time_ms,
                "source_file": file_path.name,
                "file_type": "image",
                "chunk_type": "table",
                "headers": headers,
                "_table_rows": [
                    {
                        "row_number": i + 1,
                        "text": " | ".join(row),
                        "fields": dict(zip(headers, row)),
                        "group_key": [],
                    }
                    for i, row in enumerate(rows)
                ],
            }

            # 创建表格块
            table_text = self._format_table_text(headers, rows)
            blocks.append(
                ParsedBlock(
                    text=table_text,
                    page_no=1,
                    metadata=metadata,
                )
            )
        else:
            # 无法解析为表格，作为普通文本处理
            metadata = {
                "parser": "image_recognition",
                "provider": result.provider_name,
                "model": result.model_name,
                "confidence": result.confidence,
                "processing_time_ms": result.processing_time_ms,
                "source_file": file_path.name,
                "file_type": "image",
            }

            blocks.append(
                ParsedBlock(
                    text=text,
                    page_no=1,
                    metadata=metadata,
                )
            )

        return blocks

    def _parse_markdown_table(self, text: str) -> Optional[tuple[List[str], List[List[str]]]]:
        """解析markdown表格"""
        lines = text.strip().split('\n')

        # 查找表格开始
        table_start = -1
        for i, line in enumerate(lines):
            if '|' in line and i + 1 < len(lines) and '---' in lines[i + 1]:
                table_start = i
                break

        if table_start == -1:
            return None

        # 解析表头
        header_line = lines[table_start]
        headers = [cell.strip() for cell in header_line.split('|') if cell.strip()]

        # 跳过分隔行
        data_start = table_start + 2

        # 解析数据行
        rows = []
        for i in range(data_start, len(lines)):
            line = lines[i].strip()
            if not line or '|' not in line:
                break

            row = [cell.strip() for cell in line.split('|') if cell.strip()]
            if len(row) == len(headers):
                rows.append(row)

        if not rows:
            return None

        return headers, rows

    def _format_table_text(self, headers: List[str], rows: List[List[str]]) -> str:
        """格式化表格为文本"""
        lines = []

        # 表头
        lines.append(" | ".join(headers))
        lines.append(" | ".join(["---"] * len(headers)))

        # 数据行
        for row in rows:
            lines.append(" | ".join(row))

        return "\n".join(lines)
