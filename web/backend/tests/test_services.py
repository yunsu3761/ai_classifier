"""
Backend tests — unit tests for core services.
Run with: python -m pytest web/backend/tests/test_services.py -v
"""
import sys
import os
from pathlib import Path

# Add project root
ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(ROOT))

import pytest
import pandas as pd
import json
import tempfile


# ─── Excel Parser Tests ─────────────────────────────────

class TestExcelParser:

    def test_auto_detect_korean_columns(self):
        from web.backend.services.excel_parser import auto_detect_columns
        df = pd.DataFrame(columns=[
            "출원번호", "발명의 명칭", "요약", "대표청구항",
            "AI 요약", "기술분야 요약", "Original CPC Main"
        ])
        mapping = auto_detect_columns(df)
        assert mapping.patent_id_col == "출원번호"
        assert mapping.title_col == "발명의 명칭"
        assert mapping.abstract_col == "요약"
        assert mapping.claims_col == "대표청구항"
        assert mapping.ai_summary_col == "AI 요약"
        assert mapping.tech_field_summary_col == "기술분야 요약"
        assert mapping.cpc_main_col == "Original CPC Main"

    def test_auto_detect_english_columns(self):
        from web.backend.services.excel_parser import auto_detect_columns
        df = pd.DataFrame(columns=["patent_ids", "title", "abstract"])
        mapping = auto_detect_columns(df)
        assert mapping.patent_id_col == "patent_ids"
        assert mapping.title_col == "title"
        assert mapping.abstract_col == "abstract"


# ─── Text Composer Tests ────────────────────────────────

class TestTextComposer:

    def test_compose_patent_text_all_fields(self):
        from web.backend.services.text_composer import compose_patent_text
        from web.backend.models.schemas import ColumnMapping

        mapping = ColumnMapping(
            patent_id_col="출원번호",
            title_col="발명의 명칭",
            abstract_col="요약",
            claims_col="대표청구항",
            ai_summary_col="AI 요약",
            cpc_main_col="CPC Main",
        )
        row = pd.Series({
            "출원번호": "KR10-2024-0001234",
            "발명의 명칭": "고효율 수소환원 장치",
            "요약": "본 발명은 수소를 이용한 환원 기술에 관한 것이다.",
            "대표청구항": "수소가스를 주입하여 철광석을 환원하는 방법.",
            "AI 요약": "수소환원 기반 철 생산 효율화",
            "CPC Main": "C21B 5/00",
        })

        result = compose_patent_text(row, mapping)
        assert result["Patent_ID"] == "KR10-2024-0001234"
        assert result["Title"] == "고효율 수소환원 장치"
        assert "[요약]" in result["Abstract"]
        assert "[대표청구항]" in result["Abstract"]
        assert "[AI요약]" in result["Abstract"]
        assert "[분류코드]" in result["Abstract"]
        assert "C21B 5/00" in result["Abstract"]

    def test_compose_patent_text_minimal(self):
        from web.backend.services.text_composer import compose_patent_text
        from web.backend.models.schemas import ColumnMapping

        mapping = ColumnMapping(
            patent_id_col="id",
            title_col="title",
        )
        row = pd.Series({"id": "US123", "title": "Test Patent"})
        result = compose_patent_text(row, mapping)
        assert result["Patent_ID"] == "US123"
        assert result["Title"] == "Test Patent"

    def test_convert_to_txt(self):
        from web.backend.services.text_composer import convert_patent_excel_to_txt
        from web.backend.models.schemas import ColumnMapping

        mapping = ColumnMapping(
            patent_id_col="id",
            title_col="title",
            abstract_col="abstract",
        )
        df = pd.DataFrame([
            {"id": "P001", "title": "Title A", "abstract": "Abstract A"},
            {"id": "P002", "title": "Title B", "abstract": "Abstract B"},
        ])

        with tempfile.TemporaryDirectory() as tmpdir:
            result = convert_patent_excel_to_txt(df, mapping, Path(tmpdir))
            assert result["count"] == 2
            assert os.path.exists(result["path"])

            # Verify format compatibility
            with open(result["path"], "r", encoding="utf-8") as f:
                lines = f.readlines()
            assert len(lines) == 2
            doc = json.loads(lines[0])
            assert "Patent_ID" in doc
            assert "Title" in doc
            assert "Abstract" in doc


# ─── File Service Tests ─────────────────────────────────

class TestFileService:

    def test_detect_file_type_yaml(self):
        from web.backend.services.file_service import detect_file_type
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            f.write(b"dimensions:\n  test:\n    definition: 'test'\n")
            fname = f.name
        result = detect_file_type(Path(fname))
        assert result == "yaml_config"
        os.unlink(fname)

    def test_detect_file_type_txt(self):
        from web.backend.services.file_service import detect_file_type
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test data\n")
            fname = f.name
        result = detect_file_type(Path(fname))
        assert result == "txt_file"
        os.unlink(fname)


# ─── Schema Tests ───────────────────────────────────────

class TestSchemas:

    def test_column_mapping_optional(self):
        from web.backend.models.schemas import ColumnMapping
        m = ColumnMapping()
        assert m.title_col is None
        assert m.abstract_col is None

    def test_classify_request_defaults(self):
        from web.backend.models.schemas import ClassifyRequest
        r = ClassifyRequest()
        assert r.model == "gpt-5-2025-08-07"
        assert r.max_depth == 2
        assert r.test_samples == 0
        assert r.resume is False

    def test_file_type_enum(self):
        from web.backend.models.schemas import FileType
        assert FileType.PATENT_DATASET == "patent_dataset"
        assert FileType.TECH_DEFINITION == "tech_definition"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
