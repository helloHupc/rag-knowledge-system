from __future__ import annotations

import fitz

from app.ingestion.parsers.pdf_parser import PdfParser


def test_pdf_parser_sorts_text_blocks_by_visual_reading_order(tmp_path):
    pdf_path = tmp_path / "out-of-order-blocks.pdf"
    document = fitz.open()
    page = document.new_page(width=595, height=842)

    page.insert_text((72, 220), "6.3.3 approval")
    page.insert_text((72, 565), "note after code")
    page.insert_text((72, 590), "6.3.4 next section")
    page.insert_text((84, 280), "$re = $this->flowInterfaceService->agreeFlow(...);")
    document.save(pdf_path)
    document.close()

    blocks = PdfParser().parse(pdf_path)

    assert len(blocks) == 1
    text = blocks[0].text
    assert text.index("$re = $this->flowInterfaceService->agreeFlow") < text.index("note after code")
    assert text.index("note after code") < text.index("6.3.4 next section")
