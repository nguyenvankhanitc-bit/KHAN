# -*- coding: utf-8 -*-
"""Báo cáo tổng hợp theo user (mục BÁO CÁO).

Bảng hạng mục lấy từ danh sách công việc cá nhân của user (cùng nguồn Báo cáo cá nhân / theo hạng mục).
Phần Đánh giá chung: Kết quả nổi bật · Tồn tại (tự liệt kê việc chưa hoàn thành) + Nguyên nhân (user tự
đánh giá từng việc) · Đề xuất / giải pháp khắc phục — lưu theo user × tháng.
"""

import base64
import io
import json
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class DailyTaskUserSummary(models.Model):
    _name = "daily.task.user.summary"
    _description = "Báo cáo tổng hợp theo user (đánh giá tháng)"
    _order = "year desc, month desc, user_id"

    user_id = fields.Many2one("res.users", string="User", required=True, index=True, ondelete="cascade")
    year = fields.Integer(required=True)
    month = fields.Integer(required=True)
    highlights = fields.Text(string="Kết quả nổi bật")
    solutions = fields.Text(string="Đề xuất / giải pháp khắc phục")
    cat_notes = fields.Text(string="Nhận xét QL theo hạng mục (JSON)")

    _user_month_uniq = models.Constraint(
        "UNIQUE(user_id, year, month)",
        "Mỗi user chỉ có 1 báo cáo tổng hợp cho 1 tháng.",
    )


class DailyTask(models.Model):
    _inherit = "daily.task"

    overdue_cause = fields.Text(
        string="Nguyên nhân (user tự đánh giá)",
        help="Nguyên nhân việc chưa hoàn thành / quá hạn — người phụ trách tự nhập ở Báo cáo tổng hợp theo user.",
    )

    # ------------------------------------------------------------------
    @api.model
    def _summary_target(self, employee_id=None):
        """(hr.employee, res.users) của báo cáo đang xem."""
        Emp = self.env["hr.employee"].sudo()
        emp = Emp.browse(int(employee_id)).exists() if employee_id else Emp.browse()
        if not emp:
            emp = Emp.search([("user_id", "=", self.env.uid)], limit=1)
        return emp, emp.user_id

    @api.model
    def _summary_can_manage(self, target_user):
        """Quản lý module, hoặc User quản lý team có user đó."""
        if self.env.su or self.env["daily.task.assign.access"]._is_manager():
            return True
        if not target_user:
            return False
        return bool(self.env["daily.task.team"].sudo().search_count([
            ("active", "=", True), ("manager_ids", "in", self.env.uid),
            "|", ("member_ids", "in", target_user.id), ("manager_ids", "in", target_user.id),
        ]))

    @api.model
    def get_user_summary(self, year=None, month=None, employee_id=None):
        filters = {"employee_id": int(employee_id)} if employee_id else {}
        data = self.get_category_report(year=year, month=month, filters=filters)
        if data.get("message"):
            return data
        Tier = self.env["daily.task.rating.tier"]
        emp, target_user = self._summary_target(data.get("selected_employee_id") or employee_id)
        summary = self.env["daily.task.user.summary"].sudo().search([
            ("user_id", "=", target_user.id or 0), ("year", "=", data["year"]), ("month", "=", data["month"]),
        ], limit=1)
        try:
            cat_notes = json.loads(summary.cat_notes or "{}")
        except ValueError:
            cat_notes = {}

        rows = []
        for g in data.get("cat_groups") or []:
            items = g["rows"]
            n = len(items) or 1
            not_started = sum(1 for r in items if r.get("state") not in ("done", "in_progress"))
            rows.append({
                "key": str(g["key"]),
                "code": g["code"],
                "label": g["label"],
                "total": g["count"],
                "done": g["done"],
                "doing": sum(1 for r in items if r.get("state") == "in_progress"),
                "not_started": not_started,
                "overdue": g["overdue"],
                "done_pct": round(100.0 * g["done"] / n, 1),
                "hours": round(g["minutes"] / 60.0, 1),
                "progress": float(g["progress"]),
                "efficiency": float(g["ql"]),
                "rating": g["rating"],
                "note": cat_notes.get(str(g["key"]), ""),
            })
        kpi = data.get("kpi") or {}
        total = {
            "total": kpi.get("total", 0), "done": kpi.get("done", 0), "doing": kpi.get("in_progress", 0),
            "not_started": sum(r["not_started"] for r in rows), "overdue": kpi.get("overdue", 0),
            "done_pct": kpi.get("done_pct", 0), "hours": kpi.get("duration_hours", 0),
            "progress": kpi.get("avg_progress", 0), "efficiency": kpi.get("efficiency", 0),
        }
        total["rating"] = Tier.rate(total["efficiency"])

        # Tồn tại: mọi việc có trạng thái khác Hoàn thành
        pending = []
        for g in data.get("cat_groups") or []:
            for r in g["rows"]:
                if r.get("state") == "done":
                    continue
                pending.append({
                    "id": r["id"],
                    "category": g["label"],
                    "name": r.get("name") or "",
                    "deadline": r.get("deadline_display") or "",
                    "state_label": r.get("state_label") or "",
                    "overdue_label": r.get("overdue_label") or "",
                    "is_overdue": bool(r.get("is_active_overdue")),
                })
        causes = {t.id: t.overdue_cause or "" for t in self.sudo().browse([p["id"] for p in pending])}
        for p in pending:
            p["cause"] = causes.get(p["id"], "")

        is_self = bool(target_user) and target_user == self.env.user
        data.update({
            "summary_rows": rows,
            "summary_total": total,
            "pending": pending,
            "highlights": summary.highlights or "",
            "solutions": summary.solutions or "",
            "can_edit_self": is_self or self._summary_can_manage(target_user),
            "can_edit_manager": self._summary_can_manage(target_user),
            "report_date": fields.Date.context_today(self).strftime("%d/%m/%Y"),
        })
        return data

    @api.model
    def save_user_summary(self, year, month, employee_id=None, vals=None):
        vals = vals or {}
        emp, target_user = self._summary_target(employee_id)
        if not target_user:
            raise ValidationError("Nhân viên chưa gắn user — không lưu được báo cáo.")
        is_self = target_user == self.env.user
        can_manage = self._summary_can_manage(target_user)
        if not (is_self or can_manage):
            raise AccessError("Bạn chỉ sửa được báo cáo tổng hợp của chính mình.")
        Summary = self.env["daily.task.user.summary"].sudo()
        rec = Summary.search([("user_id", "=", target_user.id), ("year", "=", int(year)), ("month", "=", int(month))], limit=1)
        if not rec:
            rec = Summary.create({"user_id": target_user.id, "year": int(year), "month": int(month)})
        write = {}
        if "highlights" in vals:
            write["highlights"] = vals.get("highlights") or ""
        if "solutions" in vals:
            write["solutions"] = vals.get("solutions") or ""
        if "cat_notes" in vals:
            if not can_manage:
                raise AccessError("Chỉ quản lý được nhập Ghi chú / Nhận xét QL.")
            write["cat_notes"] = json.dumps(vals.get("cat_notes") or {}, ensure_ascii=False)
        if write:
            rec.write(write)
        # Nguyên nhân từng việc (chỉ việc của chính user đó)
        for task_id, cause in (vals.get("causes") or {}).items():
            task = self.sudo().browse(int(task_id)).exists()
            if task and task.assignee_user_id == target_user:
                task.write({"overdue_cause": cause or False})
        return True

    @api.model
    def export_user_summary_excel(self, year=None, month=None, employee_id=None):
        try:
            import xlsxwriter
        except ImportError as exc:
            raise ValidationError("Thiếu thư viện xlsxwriter. Cài đặt: pip install xlsxwriter") from exc
        data = self.get_user_summary(year=year, month=month, employee_id=employee_id)
        if data.get("message"):
            raise ValidationError(data["message"])
        profile = data.get("profile") or {}
        year, month = data["year"], data["month"]

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        ws = wb.add_worksheet("Tong_hop_theo_user")
        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 0)
        ws.hide_gridlines(2)
        F = "Times New Roman"
        base = {"font_name": F, "font_size": 11, "border": 1, "valign": "vcenter", "border_color": "#a6a6a6"}

        def fmt(**kw):
            return wb.add_format({**base, **kw})

        title = wb.add_format({"font_name": F, "bold": True, "font_size": 18, "align": "center", "font_color": "#e00000"})
        sub = wb.add_format({"font_name": F, "bold": True, "font_size": 12, "align": "center"})
        note = wb.add_format({"font_name": F, "italic": True, "font_size": 10, "align": "center", "font_color": "#555555"})
        head = fmt(bold=True, align="center", text_wrap=True, bg_color="#fce4d6")
        c = fmt(align="center")
        left = fmt()
        bold_l = fmt(bold=True)
        pct = fmt(align="center", num_format='0.0"%"')
        num1 = fmt(align="center", num_format="0.0")
        red = fmt(align="center", bold=True, font_color="#c00000")
        tot = {"bold": True, "bg_color": "#ffff00", "align": "center"}
        tot_f = fmt(**tot)
        tot_pct = fmt(**tot, num_format='0.0"%"')
        tot_n1 = fmt(**tot, num_format="0.0")
        sec = wb.add_format({"font_name": F, "bold": True, "font_size": 12, "bg_color": "#d9e1f2", "border": 1})
        lbl = wb.add_format({"font_name": F, "bold": True, "font_size": 11})
        box = fmt(text_wrap=True, valign="top", bg_color="#fff2cc")
        rating_fmt = {
            "Xuất sắc": fmt(align="center", bold=True, font_color="#006100", bg_color="#c6efce"),
            "Tốt": fmt(align="center", bold=True, font_color="#1f4e79", bg_color="#ddebf7"),
            "Đạt": fmt(align="center", bold=True, font_color="#9c5700", bg_color="#ffeb9c"),
        }
        weak = fmt(align="center", bold=True, font_color="#9c0006", bg_color="#ffc7ce")

        widths = [6, 32, 9, 10, 10, 10, 9, 11, 10, 10, 10, 15, 30]
        for i, w in enumerate(widths):
            ws.set_column(i, i, w)
        last = len(widths) - 1
        ws.merge_range(0, 0, 0, last, "BÁO CÁO CÔNG VIỆC TỔNG HỢP THEO USER", title)
        ws.merge_range(1, 0, 1, last, "Họ và tên: %s · %s" % (profile.get("name") or "", profile.get("department") or ""), sub)
        ws.merge_range(2, 0, 2, last, "Tháng %s Năm %s" % (month, year), sub)
        ws.merge_range(3, 0, 3, last, "Số liệu chốt đến ngày %s · Nguồn: danh sách công việc cá nhân" % data["report_date"], note)

        heads = ["STT", "Hạng mục", "Tổng CV", "Hoàn thành", "Đang xử lý", "Chưa bắt đầu", "Quá hạn",
                 "% HT (số lượng)", "Giờ thực hiện", "Tiến độ TB", "Hiệu suất", "Xếp loại", "Ghi chú / Nhận xét QL"]
        r = 5
        ws.set_row(r, 32)
        for i, h in enumerate(heads):
            ws.write(r, i, h, head)
        for row in data["summary_rows"]:
            r += 1
            ws.write(r, 0, row["code"], c)
            ws.write(r, 1, row["label"], bold_l)
            ws.write(r, 2, row["total"], c)
            ws.write(r, 3, row["done"], c)
            ws.write(r, 4, row["doing"], c)
            ws.write(r, 5, row["not_started"], c)
            ws.write(r, 6, row["overdue"], red if row["overdue"] else c)
            ws.write(r, 7, row["done_pct"], pct)
            ws.write(r, 8, row["hours"], num1)
            ws.write(r, 9, row["progress"], pct)
            ws.write(r, 10, row["efficiency"], pct)
            ws.write(r, 11, row["rating"], rating_fmt.get(row["rating"], weak))
            ws.write(r, 12, row["note"], left)
        t = data["summary_total"]
        r += 1
        ws.merge_range(r, 0, r, 1, "TỔNG CỘNG", tot_f)
        for i, k in enumerate(("total", "done", "doing", "not_started", "overdue"), start=2):
            ws.write(r, i, t[k], tot_f)
        ws.write(r, 7, t["done_pct"], tot_pct)
        ws.write(r, 8, t["hours"], tot_n1)
        ws.write(r, 9, t["progress"], tot_pct)
        ws.write(r, 10, t["efficiency"], tot_pct)
        ws.write(r, 11, t["rating"], tot_f)
        ws.write(r, 12, "", tot_f)

        r += 2
        ws.merge_range(r, 0, r, last, "III. ĐÁNH GIÁ CHUNG & KIẾN NGHỊ", sec)
        r += 1
        ws.write(r, 0, "Kết quả nổi bật:", lbl)
        r += 1
        ws.merge_range(r, 0, r + 2, last, data["highlights"], box)
        r += 4
        ws.write(r, 0, "Tồn tại / nguyên nhân:", lbl)
        r += 1
        ws.write(r, 0, "STT", head)
        ws.merge_range(r, 1, r, 6, "Tồn tại (công việc chưa hoàn thành)", head)
        ws.merge_range(r, 7, r, last, "Nguyên nhân (user tự đánh giá)", head)
        for i, p in enumerate(data["pending"], start=1):
            r += 1
            text = "%s — %s (Deadline %s · %s%s)" % (
                p["category"], p["name"], p["deadline"] or "—", p["state_label"],
                (" · " + p["overdue_label"]) if p["overdue_label"] else "")
            ws.set_row(r, 30)
            ws.write(r, 0, i, c)
            ws.merge_range(r, 1, r, 6, text, fmt(text_wrap=True))
            ws.merge_range(r, 7, r, last, p["cause"], box)
        if not data["pending"]:
            r += 1
            ws.merge_range(r, 0, r, last, "Không có công việc tồn đọng.", c)
        r += 2
        ws.write(r, 0, "Đề xuất / giải pháp khắc phục:", lbl)
        r += 1
        ws.merge_range(r, 0, r + 2, last, data["solutions"], box)
        r += 5
        today = date.today()
        ws.merge_range(r, 9, r, last, "TP.HCM, ngày %s tháng %s năm %s" % (today.day, today.month, today.year), note)
        r += 1
        sign = wb.add_format({"font_name": F, "bold": True, "align": "center"})
        sign_n = wb.add_format({"font_name": F, "italic": True, "font_size": 9, "align": "center", "font_color": "#555555"})
        for col0, col1, label in ((0, 2, "Người lập"), (4, 7, "Trưởng phòng HCNS"), (9, last, "Ban Giám đốc")):
            ws.merge_range(r, col0, r, col1, label, sign)
            ws.merge_range(r + 1, col0, r + 1, col1, "(Ký, ghi rõ họ tên)", sign_n)
        wb.close()
        return {
            "file_base64": base64.b64encode(buf.getvalue()).decode("ascii"),
            "filename": "Bao_cao_tong_hop_%s_Thang_%s_%s.xlsx" % (
                (profile.get("name") or "user").replace(" ", "_"), month, year),
        }
