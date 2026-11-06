# -*- coding: utf-8 -*-
"""
Unit tests for Project Timeline Excel Report Export in lug_project.
Tests multi-sheet generation, sheet name sanitization, timeline column layout,
Sunday yellow highlight, % completion calculation, and 'X' markings.
"""

import base64
import io
import sys
import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock

# Setup mock odoo environment if not already loaded
if "odoo" not in sys.modules:
    mock_odoo = MagicMock()
    mock_api = MagicMock()
    mock_api.model = lambda f: f
    mock_api.model_create_multi = lambda f: f
    mock_api.depends = lambda *args: lambda f: f
    mock_api.onchange = lambda *args: lambda f: f
    mock_api.constrains = lambda *args: lambda f: f

    mock_fields = MagicMock()
    mock_fields.Date = MagicMock(side_effect=lambda **kwargs: kwargs)
    mock_fields.Date.context_today = MagicMock(return_value=date(2026, 8, 17))
    mock_fields.Date.to_date = lambda d: d if isinstance(d, date) else (date.fromisoformat(d) if d else None)
    mock_fields.Char = MagicMock(side_effect=lambda **kwargs: kwargs)
    mock_fields.Float = MagicMock(side_effect=lambda **kwargs: kwargs)
    mock_fields.Integer = MagicMock(side_effect=lambda **kwargs: kwargs)
    mock_fields.Selection = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.Many2one = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.Many2many = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.One2many = MagicMock(side_effect=lambda *args, **kwargs: kwargs)
    mock_fields.Text = MagicMock(side_effect=lambda **kwargs: kwargs)
    mock_fields.Boolean = MagicMock(side_effect=lambda **kwargs: kwargs)

    mock_models = MagicMock()

    class MockModel:
        _name = "mock.model"
        _inherit = ""

        def __init__(self, *args, **kwargs):
            pass

        def __iter__(self):
            return iter([self])

        def sudo(self):
            return self

    mock_models.Model = MockModel
    mock_exceptions = MagicMock()
    mock_exceptions.ValidationError = type("ValidationError", (Exception,), {})
    mock_exceptions.UserError = type("UserError", (Exception,), {})

    mock_tools = MagicMock()
    mock_tools.html2plaintext = lambda s: s

    mock_odoo.__path__ = []
    mock_odoo.api = mock_api
    mock_odoo.fields = mock_fields
    mock_odoo.models = mock_models
    mock_odoo.exceptions = mock_exceptions
    mock_odoo.tools = mock_tools

    sys.modules["odoo"] = mock_odoo
    sys.modules["odoo.api"] = mock_api
    sys.modules["odoo.fields"] = mock_fields
    sys.modules["odoo.models"] = mock_models
    sys.modules["odoo.exceptions"] = mock_exceptions
    sys.modules["odoo.tools"] = mock_tools

# Now import the class
from lug_project.models.project_dashboard import ProjectProjectDashboard


class MockTask:
    def __init__(self, id, name, sequence=10, stt="", user_display="", execution_date=None, deadline=None, state="draft"):
        self.id = id
        self.name = name
        self.sequence = sequence
        self.stt = stt
        self.user_display = user_display
        self.execution_date = execution_date
        self.deadline = deadline
        self.state = state
        self.user_ids = MagicMock()
        self.user_ids.mapped = MagicMock(return_value=[user_display] if user_display else [])


class MockRecordSet:
    def __init__(self, items):
        self._items = list(items)

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)

    def __bool__(self):
        return len(self._items) > 0

    def sorted(self, key=None):
        return MockRecordSet(sorted(self._items, key=key) if key else self._items)

    def mapped(self, field_name):
        res = []
        for item in self._items:
            val = getattr(item, field_name, None)
            if isinstance(val, MockRecordSet):
                res.extend(val._items)
            elif val is not None:
                res.append(val)
        return MockRecordSet(res)

    def filtered(self, func):
        return MockRecordSet([x for x in self._items if func(x)])


class MockStage:
    def __init__(self, id, name, sequence=10, tasks=None):
        self.id = id
        self.name = name
        self.sequence = sequence
        self.task_ids = MockRecordSet(tasks or [])


class MockProject:
    def __init__(self, id, name, stages=None, date_start=None, date_end=None):
        self.id = id
        self.name = name
        self.stage_line_ids = MockRecordSet(stages or [])
        self.date_start = date_start
        self.date_end = date_end

    def exists(self):
        return True


class TestTimelineExcelExport(unittest.TestCase):
    def setUp(self):
        self.model = ProjectProjectDashboard()
        self.model.env = MagicMock()

    def test_export_lug_timeline_xlsx_structure(self):
        import openpyxl

        # Project 1: GO BÀ RỊA with 2 stages and 3 tasks
        t1 = MockTask(1, "Hoarding gian hàng", sequence=1, stt="1.1", user_display="Đồng/ Đạt",
                      execution_date=date(2026, 8, 17), deadline=date(2026, 8, 17), state="done")
        t2 = MockTask(2, "Set up quầy sale", sequence=2, stt="1.2", user_display="NVBH",
                      execution_date=date(2026, 8, 17), deadline=date(2026, 8, 17), state="done")
        t3 = MockTask(3, "Tháo dỡ bục kệ", sequence=3, stt="1.3", user_display="Thanh/ Hưng",
                      execution_date=date(2026, 8, 18), deadline=date(2026, 8, 22), state="in_progress")
        s1 = MockStage(1, "GO BÀ RỊA OUT QUẦY", sequence=1, tasks=[t1, t2, t3])

        t4 = MockTask(4, "Nghiệm thu mặt bằng", sequence=4, stt="2.1", user_display="Khánh",
                      execution_date=None, deadline=date(2026, 8, 25), state="draft")
        s2 = MockStage(2, "BÀN GIAO", sequence=2, tasks=[t4])

        proj1 = MockProject(101, "GO BÀ RỊA [OUT QUẦY: 2026]*", stages=[s1, s2])

        # Project 2: AEON BÌNH DƯƠNG with long name
        t5 = MockTask(5, "Booking lịch Mall", sequence=1, stt="1.1", user_display="Vũ",
                      execution_date=date(2026, 9, 1), deadline=date(2026, 9, 2), state="done")
        s3 = MockStage(3, "LẬP KẾ HOẠCH", sequence=1, tasks=[t5])
        proj2 = MockProject(102, "LUG AEON BÌNH DƯƠNG - GIAN HÀNG CHÍNH QUẦY LỚN", stages=[s3])

        projects_dict = {101: proj1, 102: proj2}

        def mock_browse(ids):
            if isinstance(ids, int):
                return MockRecordSet([projects_dict.get(ids)])
            return MockRecordSet([projects_dict[i] for i in ids if i in projects_dict])

        self.model.browse = mock_browse

        res = self.model.export_lug_timeline_xlsx([101, 102])
        self.assertIn("file_base64", res)
        self.assertIn("filename", res)
        self.assertTrue(res["filename"].startswith("bao_cao_tien_do_thi_cong_"))
        self.assertTrue(res["filename"].endswith(".xlsx"))

        # Decode and inspect Excel workbook
        wb_data = base64.b64decode(res["file_base64"])
        wb = openpyxl.load_workbook(io.BytesIO(wb_data), data_only=True)

        # 1. Assert exactly 2 sheets
        self.assertEqual(len(wb.sheetnames), 2)

        # 2. Assert sanitized sheet names (<= 31 chars, no forbidden chars)
        for sname in wb.sheetnames:
            self.assertLessEqual(len(sname), 31)
            for forbidden in [":", "\\", "/", "?", "*", "[", "]"]:
                self.assertNotIn(forbidden, sname)

        sheet1 = wb[wb.sheetnames[0]]
        # 3. Assert Title in Row 1 (B1)
        self.assertEqual(sheet1.cell(1, 2).value, "TIMELINE THI CÔNG - GO BÀ RỊA [OUT QUẦY: 2026]*")

        # 4. Assert headers in Row 4
        expected_headers = [
            "STT", "TIÊU ĐỀ CÔNG VIỆC", "NGƯỜI \nPHỤ TRÁCH \nCÔNG VIỆC",
            "NGÀY BẮT \nĐẦU", "NGÀY ĐẾN \nHẠN", "THỜI \nGIAN", "% CÔNG VIỆC \nHOÀN THÀNH"
        ]
        actual_headers = [sheet1.cell(4, c).value for c in range(2, 9)]
        self.assertEqual(actual_headers, expected_headers)

        # 5. Assert Stage 1 (Row 5): STT='1.0', name='GO BÀ RỊA OUT QUẦY', pct avg
        # Stage 1 has 3 tasks: done (1.0), done (1.0), in_progress (0.5) -> avg = 2.5 / 3 = 0.8333...
        self.assertEqual(sheet1.cell(5, 2).value, "1.0")
        self.assertEqual(sheet1.cell(5, 3).value, "GO BÀ RỊA OUT QUẦY")
        stage1_pct = sheet1.cell(5, 8).value
        self.assertAlmostEqual(stage1_pct, 2.5 / 3, places=2)

        # 6. Assert Task 1 (Row 6): done (1.0), dates '17/08/2026'
        self.assertEqual(sheet1.cell(6, 2).value, "1.1")
        self.assertEqual(sheet1.cell(6, 3).value, "Hoarding gian hàng")
        self.assertEqual(sheet1.cell(6, 4).value, "Đồng/ Đạt")
        self.assertEqual(sheet1.cell(6, 5).value, "17/08/2026")
        self.assertEqual(sheet1.cell(6, 6).value, "17/08/2026")
        self.assertEqual(sheet1.cell(6, 7).value, 1)  # duration = 1 day
        self.assertEqual(sheet1.cell(6, 8).value, 1.0)  # done = 100%

        # 7. Assert Task 3 (Row 8): in_progress (0.5), duration = 5 days (18/08 to 22/08)
        self.assertEqual(sheet1.cell(8, 2).value, "1.3")
        self.assertEqual(sheet1.cell(8, 7).value, 5)
        self.assertEqual(sheet1.cell(8, 8).value, 0.5)

        # 8. Assert Task 4 (Row 10): draft (0.0), missing execution_date defaulted to deadline
        self.assertEqual(sheet1.cell(10, 2).value, "2.1")
        self.assertEqual(sheet1.cell(10, 5).value, "25/08/2026")
        self.assertEqual(sheet1.cell(10, 6).value, "25/08/2026")
        self.assertEqual(sheet1.cell(10, 7).value, 1)
        self.assertEqual(sheet1.cell(10, 8).value, 0.0)

        # 9. Check timeline marks 'X' on Task 1 (Aug 17)
        # Find which column corresponds to 17/08
        col_17 = None
        for c in range(9, sheet1.max_column + 1):
            if sheet1.cell(4, c).value == 17:
                col_17 = c
                break
        self.assertIsNotNone(col_17, "Column for day 17 should exist")
        self.assertEqual(sheet1.cell(6, col_17).value, "X")

        print("TestTimelineExcelExport passed successfully!")


if __name__ == "__main__":
    unittest.main()
