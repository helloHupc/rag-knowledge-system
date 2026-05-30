"""Tests for image recognition and parsing."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import get_settings, reset_settings_cache
from app.core.errors import AppError, ErrorCode
from app.ingestion.parsers.image_parser import ImageParser, SUPPORTED_IMAGE_EXTENSIONS
from app.ingestion.types import ParsedBlock
from app.integrations.image_recognition import (
    ImageRecognitionProvider,
    MultimodalProvider,
    PaddleOCRProvider,
    RecognitionResult,
    create_image_recognition_provider,
)
from app.integrations.image_caption import ImageCaptionProvider


# ── RecognitionResult ──────────────────────────────────────────


def test_recognition_result_defaults():
    result = RecognitionResult(text="hello")
    assert result.text == "hello"
    assert result.confidence == 1.0
    assert result.provider_name == ""
    assert result.model_name == ""
    assert result.processing_time_ms == 0
    assert result.metadata == {}


def test_recognition_result_with_metadata():
    result = RecognitionResult(
        text="test",
        confidence=0.95,
        provider_name="paddle_ocr",
        model_name="PaddleOCR-VL-1.5",
        processing_time_ms=500,
        metadata={"job_id": "123"},
    )
    assert result.confidence == 0.95
    assert result.metadata["job_id"] == "123"


# ── create_image_recognition_provider ──────────────────────────


def test_create_paddle_ocr_provider():
    settings = get_settings().model_copy(
        update={
            "image_recognition_provider": "paddle_ocr",
            "paddle_ocr_token": "test-token",
        }
    )
    provider = create_image_recognition_provider(settings)
    assert isinstance(provider, PaddleOCRProvider)
    assert provider.is_configured()


def test_create_multimodal_provider():
    settings = get_settings().model_copy(
        update={
            "image_recognition_provider": "multimodal",
            "multimodal_api_base": "https://api.example.com/v1",
            "multimodal_api_key": "test-key",
            "multimodal_model": "gpt-4-vision",
        }
    )
    provider = create_image_recognition_provider(settings)
    assert isinstance(provider, MultimodalProvider)
    assert provider.is_configured()


def test_create_default_provider():
    settings = get_settings().model_copy(
        update={"image_recognition_provider": "unknown"}
    )
    provider = create_image_recognition_provider(settings)
    assert isinstance(provider, PaddleOCRProvider)


# ── PaddleOCRProvider ──────────────────────────────────────────


def test_paddle_ocr_not_configured_without_token():
    settings = get_settings().model_copy(
        update={"paddle_ocr_token": None}
    )
    provider = PaddleOCRProvider(settings)
    assert not provider.is_configured()


def test_paddle_ocr_configured_with_token():
    settings = get_settings().model_copy(
        update={"paddle_ocr_token": "test-token"}
    )
    provider = PaddleOCRProvider(settings)
    assert provider.is_configured()


# ── MultimodalProvider ─────────────────────────────────────────


def test_multimodal_not_configured_without_api():
    settings = get_settings().model_copy(
        update={
            "multimodal_api_base": None,
            "multimodal_api_key": None,
            "multimodal_model": None,
        }
    )
    provider = MultimodalProvider(settings)
    assert not provider.is_configured()


def test_multimodal_configured_with_full_api():
    settings = get_settings().model_copy(
        update={
            "multimodal_api_base": "https://api.example.com/v1",
            "multimodal_api_key": "test-key",
            "multimodal_model": "gpt-4-vision",
        }
    )
    provider = MultimodalProvider(settings)
    assert provider.is_configured()


# ── ImageParser ────────────────────────────────────────────────


def test_supported_image_extensions():
    assert ".jpg" in SUPPORTED_IMAGE_EXTENSIONS
    assert ".jpeg" in SUPPORTED_IMAGE_EXTENSIONS
    assert ".png" in SUPPORTED_IMAGE_EXTENSIONS
    assert ".gif" in SUPPORTED_IMAGE_EXTENSIONS
    assert ".bmp" in SUPPORTED_IMAGE_EXTENSIONS
    assert ".tiff" in SUPPORTED_IMAGE_EXTENSIONS
    assert ".tif" in SUPPORTED_IMAGE_EXTENSIONS
    assert ".webp" in SUPPORTED_IMAGE_EXTENSIONS


def test_image_parser_rejects_nonexistent_file():
    mock_provider = MagicMock(spec=ImageRecognitionProvider)
    mock_caption = MagicMock(spec=ImageCaptionProvider)
    mock_caption.is_configured.return_value = False
    parser = ImageParser(recognition_provider=mock_provider, caption_provider=mock_caption)

    with pytest.raises(AppError) as exc_info:
        parser.parse(Path("/nonexistent/image.png"))
    assert exc_info.value.code == ErrorCode.DOCUMENT_PARSE_FAILED


def test_image_parser_rejects_unsupported_format(tmp_path):
    mock_provider = MagicMock(spec=ImageRecognitionProvider)
    mock_caption = MagicMock(spec=ImageCaptionProvider)
    mock_caption.is_configured.return_value = False
    parser = ImageParser(recognition_provider=mock_provider, caption_provider=mock_caption)

    fake_file = tmp_path / "test.txt"
    fake_file.write_text("hello")

    with pytest.raises(AppError) as exc_info:
        parser.parse(fake_file)
    assert exc_info.value.code == ErrorCode.UNSUPPORTED_FILE_TYPE


def test_image_parser_processes_text_result(tmp_path):
    mock_provider = MagicMock(spec=ImageRecognitionProvider)
    mock_provider.recognize_image = AsyncMock(
        return_value=RecognitionResult(
            text="Hello World\nThis is a test",
            confidence=0.95,
            provider_name="test",
            model_name="test-model",
        )
    )
    mock_caption = MagicMock(spec=ImageCaptionProvider)
    mock_caption.is_configured.return_value = False

    parser = ImageParser(recognition_provider=mock_provider, caption_provider=mock_caption)

    img_file = tmp_path / "test.png"
    img_file.write_bytes(b"fake-png-data")

    blocks = parser.parse(img_file)
    assert len(blocks) == 1
    assert blocks[0].text == "Hello World\nThis is a test"
    assert blocks[0].metadata["parser"] == "image_recognition"
    assert blocks[0].metadata["provider"] == "test"
    assert blocks[0].metadata["file_type"] == "image"


def test_image_parser_processes_table_result(tmp_path):
    mock_provider = MagicMock(spec=ImageRecognitionProvider)
    mock_provider.recognize_image = AsyncMock(
        return_value=RecognitionResult(
            text="| Name | Value |\n| --- | --- |\n| A | 1 |\n| B | 2 |",
            confidence=0.9,
            provider_name="test",
            model_name="test-model",
        )
    )
    mock_caption = MagicMock(spec=ImageCaptionProvider)
    mock_caption.is_configured.return_value = False

    parser = ImageParser(recognition_provider=mock_provider, caption_provider=mock_caption)

    img_file = tmp_path / "test.png"
    img_file.write_bytes(b"fake-png-data")

    blocks = parser.parse(img_file)
    assert len(blocks) == 1
    assert blocks[0].metadata.get("chunk_type") == "table"
    assert "headers" in blocks[0].metadata
    assert "_table_rows" in blocks[0].metadata


def test_image_parser_handles_empty_result(tmp_path):
    mock_provider = MagicMock(spec=ImageRecognitionProvider)
    mock_provider.recognize_image = AsyncMock(
        return_value=RecognitionResult(text="", confidence=0.0)
    )
    mock_caption = MagicMock(spec=ImageCaptionProvider)
    mock_caption.is_configured.return_value = False

    parser = ImageParser(recognition_provider=mock_provider, caption_provider=mock_caption)

    img_file = tmp_path / "test.png"
    img_file.write_bytes(b"fake-png-data")

    blocks = parser.parse(img_file)
    assert len(blocks) == 1
    assert "识别为空" in blocks[0].text


def test_image_parser_raises_when_no_provider_configured(tmp_path):
    mock_provider = MagicMock(spec=ImageRecognitionProvider)
    mock_provider.is_configured.return_value = False
    mock_caption = MagicMock(spec=ImageCaptionProvider)
    mock_caption.is_configured.return_value = False

    parser = ImageParser(recognition_provider=mock_provider, caption_provider=mock_caption)
    parser.recognition_mode = "none"  # 模拟无配置

    img_file = tmp_path / "test.png"
    img_file.write_bytes(b"fake-png-data")

    with pytest.raises(AppError) as exc_info:
        parser.parse(img_file)
    assert exc_info.value.code == ErrorCode.IMAGE_RECOGNITION_FAILED


def test_image_parser_batch_parse(tmp_path):
    mock_provider = MagicMock(spec=ImageRecognitionProvider)
    mock_provider.recognize_batch = AsyncMock(
        return_value=[
            RecognitionResult(text="Image 1 content", confidence=0.9),
            RecognitionResult(text="Image 2 content", confidence=0.8),
        ]
    )
    mock_caption = MagicMock(spec=ImageCaptionProvider)
    mock_caption.is_configured.return_value = False

    parser = ImageParser(recognition_provider=mock_provider, caption_provider=mock_caption)

    img1 = tmp_path / "test1.png"
    img1.write_bytes(b"fake-png-1")
    img2 = tmp_path / "test2.jpg"
    img2.write_bytes(b"fake-jpg-2")

    blocks = parser.parse_batch([img1, img2])
    assert len(blocks) == 2
    assert blocks[0].text == "Image 1 content"
    assert blocks[1].text == "Image 2 content"


# ── Table detection ────────────────────────────────────────────


def test_contains_table_with_markdown():
    mock_provider = MagicMock(spec=ImageRecognitionProvider)
    mock_caption = MagicMock(spec=ImageCaptionProvider)
    mock_caption.is_configured.return_value = False
    parser = ImageParser(recognition_provider=mock_provider, caption_provider=mock_caption)

    assert parser._contains_table("| A | B |\n| --- | --- |\n| 1 | 2 |")
    assert not parser._contains_table("Hello World")


def test_contains_table_with_pipes():
    mock_provider = MagicMock(spec=ImageRecognitionProvider)
    parser = ImageParser(recognition_provider=mock_provider)

    assert parser._contains_table("Name | Value\nA | 1\nB | 2")
    assert not parser._contains_table("Single line")


def test_parse_markdown_table():
    mock_provider = MagicMock(spec=ImageRecognitionProvider)
    mock_caption = MagicMock(spec=ImageCaptionProvider)
    mock_caption.is_configured.return_value = False
    parser = ImageParser(recognition_provider=mock_provider, caption_provider=mock_caption)

    text = "| Name | Age |\n| --- | --- |\n| Alice | 30 |\n| Bob | 25 |"
    result = parser._parse_markdown_table(text)

    assert result is not None
    headers, rows = result
    assert headers == ["Name", "Age"]
    assert len(rows) == 2
    assert rows[0] == ["Alice", "30"]
    assert rows[1] == ["Bob", "25"]


def test_parse_markdown_table_invalid():
    mock_provider = MagicMock(spec=ImageRecognitionProvider)
    mock_caption = MagicMock(spec=ImageCaptionProvider)
    mock_caption.is_configured.return_value = False
    parser = ImageParser(recognition_provider=mock_provider, caption_provider=mock_caption)

    assert parser._parse_markdown_table("No table here") is None
    assert parser._parse_markdown_table("") is None
