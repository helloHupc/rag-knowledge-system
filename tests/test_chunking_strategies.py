from __future__ import annotations

from app.ingestion.chunking import build_chunks
from app.ingestion.types import ChunkingOptions, ParsedBlock


def test_structural_chunking_keeps_heading_with_body_and_explains_boundary():
    text = "\n".join(
        [
            "# 总则",
            "平台用于统一管理企业知识库。",
            "支持上传、解析、切分和检索。",
            "",
            "## 适用范围",
            "适用于 PDF、Word、Excel 和导出的沟通记录。",
        ]
    )

    chunks = build_chunks(
        [ParsedBlock(text=text, metadata={"parser": "manual"})],
        options=ChunkingOptions(strategy="structural", max_chars=500, overlap_chars=0),
    )

    assert len(chunks) == 2
    assert chunks[0].chunk_text.startswith("# 总则\n平台用于")
    assert chunks[1].chunk_text.startswith("## 适用范围\n适用于")
    assert [chunk.metadata_json["section_heading"] for chunk in chunks] == ["总则", "适用范围"]
    assert all(chunk.metadata_json["split_reason"] == "heading" for chunk in chunks)
    assert all(chunk.metadata_json["section_start_line"] for chunk in chunks)


def test_structural_chunking_keeps_table_of_contents_as_one_section():
    text = "\n".join(
        [
            "2 / 14",
            "出差管理办法",
            "文件编码：BHJY-XZ-ZD01",
            "版本/更改：第三版",
            "页码：共14页",
            "目录",
            "1．目的............................................................................. 3",
            "2．适用范围......................................................................... 3",
            "3．基本规定......................................................................... 3",
            "3.1 出差管理办法总体规定............................................................. 3",
            "3.2 出差管理办法具体规定............................................................. 3",
            "3.2.1 出差申请审批................................................................... 4",
        ]
    )

    chunks = build_chunks(
        [ParsedBlock(text=text, page_no=2, metadata={"parser": "pymupdf"})],
        options=ChunkingOptions(strategy="structural", max_chars=1200, overlap_chars=0),
    )

    assert len(chunks) == 1
    assert chunks[0].metadata_json["split_reason"] == "table_of_contents"
    assert chunks[0].metadata_json["section_heading"] == "目录"
    assert "3.2.1 出差申请审批" in chunks[0].chunk_text


def test_structural_chunking_ignores_page_markers_as_headings():
    text = "\n".join(
        [
            "3 / 14",
            "1．目的",
            "为了适应公司业务发展需要，规范出差申请、审批、报销全流程。",
            "2．适用范围",
            "适用于集团全体员工。",
        ]
    )

    chunks = build_chunks(
        [ParsedBlock(text=text, page_no=3, metadata={"parser": "pymupdf"})],
        options=ChunkingOptions(strategy="structural", max_chars=500, overlap_chars=0),
    )

    headings = [chunk.metadata_json.get("section_heading") for chunk in chunks]
    assert "3 / 14" not in headings
    assert headings == ["1．目的", "2．适用范围"]
    assert chunks[0].chunk_text.startswith("3 / 14\n1．目的")


def test_structural_chunking_attaches_trailing_heading_to_next_page_body():
    blocks = [
        ParsedBlock(
            text="\n".join(
                [
                    "3 / 14",
                    "3.1 出差管理办法总体规定",
                    "适用于差旅申请、审批和报销流程。",
                    "3.2 出差管理办法具体规定",
                ]
            ),
            page_no=3,
            metadata={"parser": "pymupdf"},
        ),
        ParsedBlock(
            text="\n".join(
                [
                    "出差管理办法",
                    "本页内容知识产权归属百合佳缘所有，未经授权许可，不得复制抄袭",
                    "4 / 14",
                    "3.2.1 出差申请审批",
                    "公司员工出差应事先提交出差申请。",
                ]
            ),
            page_no=4,
            metadata={"parser": "pymupdf"},
        ),
    ]

    chunks = build_chunks(
        blocks,
        options=ChunkingOptions(strategy="structural", max_chars=500, overlap_chars=0),
    )

    assert all(chunk.chunk_text != "3.2 出差管理办法具体规定" for chunk in chunks)
    attached = [chunk for chunk in chunks if chunk.chunk_text.startswith("3.2 出差管理办法具体规定\n4 / 14")]
    assert len(attached) == 1
    assert attached[0].page_no == 4
    assert attached[0].metadata_json["section_heading"] == "3.2 出差管理办法具体规定 > 3.2.1 出差申请审批"


def test_structural_chunking_filters_repeated_page_header_and_footer_noise():
    blocks = [
        ParsedBlock(
            text="\n".join(
                [
                    "员工手册",
                    "1 / 3",
                    "1．总则",
                    "平台用于统一管理企业知识库。",
                    "本页内容知识产权归属百合佳缘所有，未经授权许可，不得复制抄袭",
                ]
            ),
            page_no=1,
            metadata={"parser": "pymupdf"},
        ),
        ParsedBlock(
            text="\n".join(
                [
                    "员工手册",
                    "2 / 3",
                    "2．审批流程",
                    "员工应先提交申请，再由主管审批。",
                    "本页内容知识产权归属百合佳缘所有，未经授权许可，不得复制抄袭",
                ]
            ),
            page_no=2,
            metadata={"parser": "pymupdf"},
        ),
        ParsedBlock(
            text="\n".join(
                [
                    "员工手册",
                    "3 / 3",
                    "3．归档要求",
                    "审批记录需要完整保留。",
                    "本页内容知识产权归属百合佳缘所有，未经授权许可，不得复制抄袭",
                ]
            ),
            page_no=3,
            metadata={"parser": "pymupdf"},
        ),
    ]

    chunks = build_chunks(
        blocks,
        options=ChunkingOptions(strategy="structural", max_chars=500, overlap_chars=0),
    )

    chunk_text = "\n".join(chunk.chunk_text for chunk in chunks)
    assert "员工手册" not in chunk_text
    assert "知识产权归属" not in chunk_text
    assert "1 / 3\n1．总则" in chunk_text
    assert [chunk.metadata_json.get("section_heading") for chunk in chunks] == ["1．总则", "2．审批流程", "3．归档要求"]


def test_structural_chunking_merges_short_cross_page_section_continuation():
    blocks = [
        ParsedBlock(
            text="\n".join(
                [
                    "7.1.3.2 应用内部权限管理",
                    "应用内部分为两模块",
                    "1、实际应用模块",
                    "2、应用内部权限管理模块",
                    "应用内部权限管理用户可执行操作",
                    "例如应用有如下操作",
                    "列表展示、添加、编辑、删除",
                ]
            ),
            page_no=29,
            metadata={"parser": "pymupdf"},
        ),
        ParsedBlock(
            text="\n".join(
                [
                    "场景一：",
                    "用户 A 属于数据研发部",
                    "a、如果拥有查看权限，进入此应用，根据表1，可查看",
                    "场景二",
                    "用户 B 属于客服部",
                    "场景三",
                    "应用管理员 张三 权限操作",
                    "7.2 应用外部权限管理",
                    "可在测试环境进行操作，相关数据表如下：",
                ]
            ),
            page_no=30,
            metadata={"parser": "pymupdf"},
        ),
    ]

    chunks = build_chunks(
        blocks,
        options=ChunkingOptions(strategy="structural", max_chars=1200, overlap_chars=0),
    )

    section_chunks = [chunk for chunk in chunks if chunk.metadata_json.get("section_heading") == "7.1.3.2 应用内部权限管理"]
    assert len(section_chunks) == 1
    assert "1、实际应用模块" in section_chunks[0].chunk_text
    assert "场景一：" in section_chunks[0].chunk_text
    assert "场景三" in section_chunks[0].chunk_text
    assert "7.2 应用外部权限管理" not in section_chunks[0].chunk_text
    assert any(chunk.metadata_json.get("section_heading") == "7.2 应用外部权限管理" for chunk in chunks)


def test_structural_chunking_merges_tiny_numbered_sibling_sections_under_parent():
    blocks = [
        ParsedBlock(
            text="\n".join(
                [
                    "9.4 人事管理",
                    "人事流程审批通过后进入相关登记菜单。",
                ]
            ),
            page_no=35,
            metadata={"parser": "pymupdf"},
        ),
        ParsedBlock(
            text="\n".join(
                [
                    "9.4.1 员工管理",
                    "员工信息查看。",
                    "9.4.2 入职管理",
                    "入职登记。",
                    "9.4.3 转正管理",
                    "转正登记。",
                    "9.5 人事统计",
                    "生成统计信息。",
                ]
            ),
            page_no=36,
            metadata={"parser": "pymupdf"},
        ),
    ]

    chunks = build_chunks(
        blocks,
        options=ChunkingOptions(strategy="structural", max_chars=500, overlap_chars=0),
    )

    management_chunks = [chunk for chunk in chunks if chunk.metadata_json.get("section_heading") == "9.4 人事管理"]
    assert len(management_chunks) == 1
    assert "9.4.1 员工管理" in management_chunks[0].chunk_text
    assert "9.4.3 转正管理" in management_chunks[0].chunk_text
    assert "9.5 人事统计" not in management_chunks[0].chunk_text
    assert management_chunks[0].char_count <= 500
    assert any(chunk.metadata_json.get("section_heading") == "9.5 人事统计" for chunk in chunks)


def test_structural_chunking_keeps_numeric_table_values_with_previous_section():
    text = "\n".join(
        [
            "4.3.2 补贴标准",
            "地区/人员",
            "一线城市",
            "第二级M9-M8",
            "5000 元/月",
            "4000 元/月",
            "3000 元/月",
        ]
    )

    chunks = build_chunks(
        [ParsedBlock(text=text, page_no=10, metadata={"parser": "pymupdf"})],
        options=ChunkingOptions(strategy="structural", max_chars=500, overlap_chars=0),
    )

    assert len(chunks) == 1
    assert "5000 元/月\n4000 元/月\n3000 元/月" in chunks[0].chunk_text


def test_parent_child_chunking_groups_by_structure_and_returns_parent_context():
    text = "\n\n".join(
        [
            "# 总则\n制度适用所有员工。请按统一流程提交申请。审批记录需要完整保留。",
            "# 审批要求\n主管审批后进入部门复核。特殊情况需要补充说明和附件。",
        ]
    )

    chunks = build_chunks(
        [ParsedBlock(text=text, metadata={"parser": "manual"})],
        options=ChunkingOptions(
            strategy="parent-child",
            parent_max_chars=70,
            child_max_chars=36,
            overlap_chars=0,
        ),
    )

    parent_indexes = [chunk.metadata_json["parent_index"] for chunk in chunks]
    assert set(parent_indexes) == {0, 1}
    assert all(chunk.chunk_level == "child" for chunk in chunks)
    assert all(chunk.context_text for chunk in chunks)
    assert chunks[0].metadata_json["parent_section_heading"] == "总则"
    assert chunks[-1].metadata_json["parent_section_heading"] == "审批要求"
    assert all(chunk.metadata_json["parent_split_reason"] in {"structural_group", "oversized_section"} for chunk in chunks)
    assert all(chunk.metadata_json["parent_char_count"] >= chunk.metadata_json["child_char_count"] for chunk in chunks)


def test_parent_child_chunking_aggregates_text_blocks_into_document_level_parent():
    parsed_blocks = [
        ParsedBlock(text="# 第一页\n第一页制度内容。", page_no=1, metadata={"parser": "pymupdf"}),
        ParsedBlock(text="# 第二页\n第二页审批内容。", page_no=2, metadata={"parser": "pymupdf"}),
        ParsedBlock(text="# 第三页\n第三页归档内容。", page_no=3, metadata={"parser": "pymupdf"}),
    ]

    chunks = build_chunks(
        parsed_blocks,
        options=ChunkingOptions(
            strategy="parent-child",
            parent_max_chars=1000,
            child_max_chars=200,
            overlap_chars=0,
        ),
    )

    assert len(chunks) == 1
    assert chunks[0].page_no == 1
    assert chunks[0].metadata_json["parent_index"] == 0
    assert chunks[0].metadata_json["parent_total"] == 1
    assert chunks[0].metadata_json["parent_block_count"] == 3
    assert chunks[0].metadata_json["parent_page_start"] == 1
    assert chunks[0].metadata_json["parent_page_end"] == 3
    assert chunks[0].metadata_json["parent_section_heading"] == "第一页 > 第二页 > 第三页"
    assert len({chunk.parent_chunk_uuid for chunk in chunks}) == 1
    assert all(chunk.chunk_level == "child" for chunk in chunks)
    assert all(chunk.context_text for chunk in chunks)


def test_semantic_chunking_obeys_max_sentences_without_detected_breakpoints():
    text = "第一句。第二句。第三句。第四句。第五句。"

    chunks = build_chunks(
        [ParsedBlock(text=text, metadata={"parser": "manual"})],
        options=ChunkingOptions(
            strategy="semantic",
            min_chunk_sentences=1,
            max_chunk_sentences=2,
            similarity_threshold=0.0,
            merge_window=2,
        ),
    )

    assert len(chunks) == 3
    assert [chunk.metadata_json["sentence_start"] for chunk in chunks] == [1, 3, 5]
    assert [chunk.metadata_json["sentence_end"] for chunk in chunks] == [2, 4, 5]
    assert [chunk.metadata_json["semantic_split_reason"] for chunk in chunks] == [
        "max_sentence_limit",
        "max_sentence_limit",
        "tail",
    ]
    assert all(chunk.metadata_json["semantic_segment_total"] == 3 for chunk in chunks)


def test_parent_child_preview_response_includes_explainable_context(client):
    text = "ABCDEFGHIJ" * 12

    resp = client.post(
        "/api/v1/chunking/preview",
        json={
            "text": text,
            "strategy": "parent-child",
            "options": {
                "parent_max_chars": 100,
                "child_max_chars": 40,
                "overlap_chars": 10,
            },
        },
    )

    assert resp.status_code == 200
    result_data = resp.json()["data"]
    first_chunk = result_data["chunks"][0]
    assert first_chunk["chunk_level"] == "child"
    assert first_chunk["chunk_type"] == "text"
    assert first_chunk["context_text"]
    assert first_chunk["parent_chunk_uuid"]
    assert first_chunk["chunk_group_uuid"]
    assert first_chunk["metadata_json"]["parent_char_count"] == len(first_chunk["context_text"])
