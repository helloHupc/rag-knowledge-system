from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import fitz

from app.ingestion.parsers.common import normalize_text
from app.ingestion.types import ParsedBlock


class PdfParser:
    def parse(self, file_path: Path) -> list[ParsedBlock]:
        blocks: list[ParsedBlock] = []
        with fitz.open(file_path) as document:
            for page_index, page in enumerate(document, start=1):
                text = normalize_text(self._extract_text_in_reading_order(page))
                if not text:
                    continue
                blocks.append(
                    ParsedBlock(
                        text=text,
                        page_no=page_index,
                        metadata={"parser": "pymupdf"},
                    )
                )
        return blocks

    def parse_with_images(self, file_path: Path, extract_images: bool = True) -> list[ParsedBlock]:
        """解析PDF，可选择提取图片内容"""
        # 首先获取文本内容
        blocks = self.parse(file_path)

        if not extract_images:
            return blocks

        # 提取图片
        try:
            images = self._extract_images(file_path)
            if not images:
                return blocks

            # 导入图片解析器
            from app.ingestion.parsers.image_parser import ImageParser
            image_parser = ImageParser()

            # 识别图片内容
            image_blocks = image_parser.parse_batch(images)

            # 为图片块添加PDF特定的元数据
            for i, block in enumerate(image_blocks):
                block.metadata.update({
                    "source_pdf": file_path.name,
                    "image_index": i,
                    "extraction_method": "pdf_image",
                })

            blocks.extend(image_blocks)

        except Exception as e:
            # 图片提取失败不影响文本内容
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Image extraction failed for PDF %s: %s", file_path, e)

        return blocks

    def _extract_images(self, file_path: Path) -> List[bytes]:
        """从PDF中提取所有图片"""
        images = []

        try:
            with fitz.open(file_path) as doc:
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    image_list = page.get_images(full=True)

                    for img in image_list:
                        xref = img[0]
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        images.append(image_bytes)

            return images

        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.exception("Failed to extract images from PDF: %s", file_path)
            return []

    @staticmethod
    def _extract_text_in_reading_order(page) -> str:
        text_blocks = []
        for block in page.get_text("blocks"):
            block_text = str(block[4]).strip()
            block_type = block[6] if len(block) > 6 else 0
            if block_type != 0 or not block_text:
                continue
            x0, y0 = float(block[0]), float(block[1])
            text_blocks.append((y0, x0, block_text))

        if not text_blocks:
            return page.get_text("text")

        sorted_text = "\n".join(text for _, _, text in sorted(text_blocks, key=lambda item: (item[0], item[1])))
        return sorted_text


class PdfWithImagesParser(PdfParser):
    """支持图片提取的PDF解析器"""

    def parse(self, file_path: Path) -> list[ParsedBlock]:
        """解析PDF，包括图片内容"""
        return self.parse_with_images(file_path, extract_images=True)
