# -*- coding: utf-8 -*-
"""Báo cáo CV theo hạng mục — cùng nguồn với Báo cáo cá nhân (danh sách công việc cá nhân của user),
bảng nhóm theo hạng mục: Tần suất · % Tiến độ · % QL đánh giá · Số ngày trễ · Hiệu suất từng hạng mục."""

import base64
import io

from odoo import api, models
from odoo.exceptions import ValidationError

_FREQ_LABELS = {"day": "Mỗi ngày", "week": "Mỗi tuần", "month": "Tháng/lần", "adhoc": "Phát sinh"}
_ROMAN = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
    (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)


def _roman(n):
    out, num = [], int(n or 0)
    for value, numeral in _ROMAN:
        while num >= value:
            out.append(numeral)
            num -= value
    return "".join(out)


def _rating(pct):
    """Hiệu suất hạng mục theo % QL đánh giá trung bình."""
    if pct >= 90:
        return "Xuất sắc"
    if pct >= 70:
        return "Tốt"
    if pct >= 50:
        return "Đạt"
    return "Cần cải thiện"


class DailyTaskCategoryReport(models.Model):
    _inherit = "daily.task"

    @api.model
    def _work_group_freq_map(self):
        """{work_group_id: 'day'|'week'|'month'|'adhoc'} — đúng như cột Tần suất trên trang Hạng mục
        (ô Tần suất đã tích trên dòng phân công của tên chi tiết hạng mục)."""
        def compute():
            out = {}
            for line in self.env["daily.task.assign"].sudo().search(
                [("active", "=", True), ("work_group_id", "!=", False)], order="stt, id"
            ):
                key = line._frequency_key()
                if key:
                    out.setdefault(line.work_group_id.id, key)
            return out
        return self._req_cache(("wg_freq_map",), compute)

    def _freq_label(self):
        """Tần suất của việc: theo Hạng mục (tên chi tiết); việc không gắn hạng mục → dòng phân công → mẫu lặp."""
        self.ensure_one()
        task = self.sudo()
        if task.work_group_id:
            # Có hạng mục → đúng cột Tần suất trên trang Hạng mục (trống thì để trống)
            key = self._work_group_freq_map().get(task.work_group_id.id)
            return _FREQ_LABELS.get(key, "") if key else ""
        key = False
        line = task.assign_line_id
        if not key and line:
            key = line._frequency_key() or ("day" if line.plan_daily else False)
        if not key and task.recurring_id:
            key = {"daily": "day", "weekly": "week"}.get(task.recurring_id.recurrence_type, "month")
        return _FREQ_LABELS.get(key, "") if key else ""

    def _to_manager_dict(self):
        data = super()._to_manager_dict()
        data.update({
            "freq_label": self._freq_label(),
            "manager_confirmed": bool(self.manager_confirmed),
            # % QL đánh giá: chỉ có khi quản lý đã xác nhận ở Kiểm tra CV
            "manager_eval_percent": int(self.manager_eval_percent or 0) if self.manager_confirmed else None,
        })
        return data

    @api.model
    def _category_report_groups(self, data):
        groups = []
        for idx, g in enumerate(data.get("groups") or [], start=1):
            rows = g.get("rows") or []
            minutes = sum(int(r.get("duration_minutes") or 0) for r in rows)
            done = sum(1 for r in rows if r.get("state") == "done")
            overdue = sum(1 for r in rows if r.get("is_active_overdue"))
            doing = sum(1 for r in rows if r.get("state") == "in_progress" and not r.get("is_active_overdue"))
            n = len(rows) or 1
            progress = round(sum(int(r.get("progress") or 0) for r in rows) / n)
            ql = round(sum(int(r.get("manager_eval_percent") or 0) for r in rows) / n)
            out_rows = []
            for stt, r in enumerate(rows, start=1):
                out_rows.append({
                    **r,
                    "stt": stt,
                    "late_days": int(r.get("overdue_days") or 0),
                    "late_kind": (
                        "active" if r.get("is_active_overdue")
                        else ("done_late" if int(r.get("overdue_days") or 0) else "")
                    ),
                })
            groups.append({
                "key": g.get("key"),
                "code": _roman(idx),
                "label": (g.get("label") or "Không có hạng mục").upper(),
                "count": len(rows),
                "done": done,
                "doing": doing,
                "overdue": overdue,
                "minutes": minutes,
                "hours": round(minutes / 60.0, 2),
                "progress": progress,
                "ql": ql,
                "rating": self.env["daily.task.rating.tier"].rate(ql) or _rating(ql),
                "rows": out_rows,
            })
        return groups

    @api.model
    def get_category_report(self, year=None, month=None, filters=None):
        """Dữ liệu trang Báo cáo CV theo hạng mục (KPI + biểu đồ như Báo cáo cá nhân + bảng hạng mục)."""
        data = self.get_report_overview(year=year, month=month, filters=filters or {})
        data["cat_groups"] = self._category_report_groups(data) if not data.get("message") else []
        return data

    @api.model
    def export_category_report_excel(self, year=None, month=None, filters=None):
        try:
            import xlsxwriter
        except ImportError as exc:
            raise ValidationError("Thiếu thư viện xlsxwriter. Cài đặt: pip install xlsxwriter") from exc

        data = self.get_category_report(year=year, month=month, filters=filters or {})
        if data.get("message"):
            raise ValidationError(data["message"])
        profile = data.get("profile") or {}
        kpi = data.get("kpi") or {}
        year, month = data["year"], data["month"]

        buffer = io.BytesIO()
        wb = xlsxwriter.Workbook(buffer, {"in_memory": True})
        ws = wb.add_worksheet("Theo_hang_muc")
        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 0)
        ws.hide_gridlines(2)

        FONT = "Times New Roman"
        base = {"font_name": FONT, "font_size": 11, "border": 1, "valign": "vcenter", "border_color": "#c0c4cc"}

        def fmt(**kw):
            return wb.add_format({**base, **kw})

        title_f = wb.add_format({"font_name": FONT, "bold": True, "font_size": 16, "align": "center"})
        sub_f = wb.add_format({"font_name": FONT, "font_size": 11, "align": "center", "font_color": "#475569"})
        kpi_l = fmt(bold=True, align="center", bg_color="#f1f5f9", font_size=10)
        kpi_v = fmt(bold=True, align="center", font_size=13)
        head_f = fmt(bold=True, align="center", text_wrap=True, bg_color="#fde3d4")
        grp_f = fmt(bold=True, bg_color="#b4c7e7", font_size=12)
        grp_c = fmt(bold=True, bg_color="#b4c7e7", align="center", font_size=12)
        grp_meta = fmt(bg_color="#b4c7e7", font_color="#334155")
        cell = fmt(text_wrap=True)
        center = fmt(align="center")
        num2 = fmt(align="center", num_format="0.00")
        done_f = fmt(align="center", bold=True, font_color="#166534", bg_color="#e2f5e2")
        late_active = fmt(align="center", bold=True, font_color="#dc2626", bg_color="#fde2e2")
        late_done = fmt(align="center", font_color="#b45309")

        headers = ["STT", "Tên công việc", "Tần suất", "Mức ưu tiên", "Ngày bắt đầu", "Deadline",
                   "Ngày hoàn thành", "Trạng thái", "Phút", "Giờ", "% Tiến độ", "% QL đánh giá",
                   "Số ngày trễ", "Quá hạn", "Ghi chú"]
        widths = [7, 42, 12, 13, 13, 13, 14, 16, 8, 8, 10, 11, 9, 20, 26]
        for col, w in enumerate(widths):
            ws.set_column(col, col, w)
        last = len(headers) - 1

        ws.merge_range(0, 0, 0, last, "BÁO CÁO CÔNG VIỆC THEO HẠNG MỤC", title_f)
        ws.merge_range(1, 0, 1, last, "Họ và tên: %s · %s" % (
            profile.get("name") or data.get("user_name") or "", profile.get("department") or ""), sub_f)
        ws.merge_range(2, 0, 2, last, "Tháng %s Năm %s" % (month, year), sub_f)

        kpis = [
            ("Tổng công việc", kpi.get("total", 0)), ("Hoàn thành", kpi.get("done", 0)),
            ("Đang thực hiện", kpi.get("in_progress", 0)), ("Quá hạn", kpi.get("overdue", 0)),
            ("Tổng thời gian (giờ)", kpi.get("duration_hours", 0)),
            ("Hiệu suất", "%s%%" % kpi.get("efficiency", 0)),
            ("Tiến độ hoàn thành", "%s%%" % kpi.get("avg_progress", 0)),
        ]
        col = 0
        for label, val in kpis:
            ws.merge_range(4, col, 4, col + 1, label, kpi_l)
            ws.merge_range(5, col, 5, col + 1, val, kpi_v)
            col += 2

        r = 7
        ws.set_row(r, 32)
        for c, h in enumerate(headers):
            ws.write(r, c, h, head_f)
        ws.repeat_rows(r, r)

        for g in data["cat_groups"]:
            r += 1
            ws.set_row(r, 22)
            ws.write(r, 0, g["code"], grp_c)
            ws.write(r, 1, g["label"], grp_f)
            ws.merge_range(r, 2, r, 7, "%s việc  ·  %s hoàn thành  ·  %s đang xử lý  ·  %s quá hạn" % (
                g["count"], g["done"], g["doing"], g["overdue"]), grp_meta)
            ws.write(r, 8, g["minutes"], grp_c)
            ws.write(r, 9, g["hours"], wb.add_format({**base, "bold": True, "bg_color": "#b4c7e7",
                                                       "align": "center", "num_format": "0.00"}))
            ws.write(r, 10, "%s%%" % g["progress"], grp_c)
            ws.write(r, 11, "%s%%" % g["ql"], grp_c)
            ws.write(r, 12, "", grp_c)
            ws.merge_range(r, 13, r, 14, "Hiệu suất: %s" % g["rating"], grp_c)
            for row in g["rows"]:
                r += 1
                is_done = row.get("state") == "done"
                ws.write(r, 0, row["stt"], center)
                ws.write(r, 1, row.get("name") or "", cell)
                ws.write(r, 2, row.get("freq_label") or "", center)
                ws.write(r, 3, row.get("priority_label") or "", center)
                ws.write(r, 4, row.get("assign_date_display") or "", center)
                ws.write(r, 5, row.get("deadline_display") or "", center)
                ws.write(r, 6, row.get("date_done_display") or "", center)
                ws.write(r, 7, row.get("state_label") or "", done_f if is_done else center)
                ws.write(r, 8, int(row.get("duration_minutes") or 0), center)
                ws.write(r, 9, float(row.get("duration_hours") or 0), num2)
                ws.write(r, 10, "%s%%" % int(row.get("progress") or 0), center)
                ql = row.get("manager_eval_percent")
                ws.write(r, 11, "%s%%" % ql if ql is not None else "", center)
                ws.write(r, 12, row["late_days"], center)
                kind = row["late_kind"]
                ws.write(r, 13, row.get("overdue_label") or "",
                         late_active if kind == "active" else late_done if kind == "done_late" else center)
                ws.write(r, 14, row.get("note") or "", cell)

        wb.close()
        return {
            "file_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
            "filename": "Bao_cao_CV_theo_hang_muc_Thang_%s_%s.xlsx" % (month, year),
        }
