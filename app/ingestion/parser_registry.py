from __future__ import annotations

from pathlib import Path

from app.core.errors import AppError, ErrorCode
from app.ingestion.parsers.base import DocumentParser
from app.ingestion.parsers.chat_parser import ChatParser
from app.ingestion.parsers.csv_parser import CsvParser
from app.ingestion.parsers.docx_parser import DocxParser
from app.ingestion.parsers.eml_parser import EmlParser
from app.ingestion.parsers.html_parser import HtmlParser
from app.ingestion.parsers.markdown_parser import MarkdownParser
from app.ingestion.parsers.pdf_parser import PdfParser, PdfWithImagesParser
from app.ingestion.parsers.image_parser import ImageParser
from app.ingestion.parsers.text_parser import TextParser
from app.ingestion.parsers.xlsx_parser import XlsxParser


class ParserRegistry:
    def __init__(self) -> None:
        text_parser = TextParser()
        markdown_parser = MarkdownParser()
        image_parser = ImageParser()
        
        self._parsers: dict[str, DocumentParser] = {
            "pdf": PdfParser(),
            "pdf_with_images": PdfWithImagesParser(),
            "docx": DocxParser(),
            "xlsx": XlsxParser(),
            "txt": text_parser,
            "text": text_parser,
            "md": markdown_parser,
            "markdown": markdown_parser,
            "html": HtmlParser(),
            "htm": HtmlParser(),
            "csv": CsvParser(),
            "eml": EmlParser(),
            "jsonl": ChatParser(),
            "chat.jsonl": ChatParser(),
            "jpg": image_parser,
            "jpeg": image_parser,
            "png": image_parser,
            "gif": image_parser,
            "bmp": image_parser,
            "tiff": image_parser,
            "tif": image_parser,
            "webp": image_parser,
        }

    def get_parser(self, file_ext: str) -> DocumentParser:
        parser = self._parsers.get(file_ext.lower())
        if parser is None:
            raise AppError(
                code=ErrorCode.UNSUPPORTED_FILE_TYPE,
                message=f"unsupported parser for extension: {file_ext}",
            )
        return parser

    def parse(self, file_ext: str, file_path: Path):
        return self.get_parser(file_ext).parse(file_path)
