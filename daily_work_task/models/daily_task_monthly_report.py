# -*- coding: utf-8 -*-
"""Báo cáo công việc tháng — theo mẫu Excel "BÁO CÁO CÔNG VIỆC THÁNG" của công ty.

Mỗi hạng mục (I, II, III…) là một nhóm; mỗi công việc (gộp các lần cùng tên trong tháng) là một dòng:
Deadlines (chu kỳ) · Tần suất thực hiện · Ngày/Tuần/Tháng · TG thực hiện (phút/lần) ·
Định biên (giờ, %) · Thực hiện (giờ, mức độ hoàn thành) · Diễn giải · Quản lý đánh giá · Ghi chú.
Việc không thuộc hạng mục → "NHÓM CÔNG VIỆC KHÁC (NẾU CÓ)".
Dữ liệu + phân quyền lấy từ Báo cáo cá nhân (daily.task.get_report_overview).
"""

import base64
import io
import re
from datetime import date

from odoo import api, models
from odoo.exceptions import ValidationError

_ROMAN = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def _roman(n):
    out = ""
    for value, sym in _ROMAN:
        while n >= value:
            out += sym
            n -= value
    return out


def _norm(text):
    return " ".join((text or "").split()).casefold()


class DailyTaskMonthlyReport(models.AbstractModel):
    _name = "daily.task.monthly.report"
    _description = "Báo cáo công việc tháng"

    # Theo mẫu BÁO CÁO CÔNG VIỆC THÁNG:
    #   Định biên (giờ) = (TG thực hiện phút / 60) × 26   (26 ngày công chuẩn)
    #   %               = Định biên (giờ) / 208           (26 ngày × 8 giờ)
    #   Thực hiện (giờ) = (TG thực hiện phút / 60) × SỐ NGÀY (số ngày đã thực hiện)
    _STANDARD_DAYS = 26
    _STANDARD_HOURS = 208.0

    # Chu kỳ → (chữ cột Deadlines, cột đánh X)
    _PERIOD = {
        "daily": ("Mỗi ngày", "day"),
        "weekly": ("Mỗi tuần", "week"),
        "monthly": ("Tháng/lần", "month"),
        "yearly": ("Năm/lần", "month"),
    }

    @api.model
    def get_report(self, year=None, month=None, employee_id=None):
        Task = self.env["daily.task"]
        if not employee_id:
            # Báo cáo tháng luôn là của user đang đăng nhập (không còn ô chọn nhân viên)
            employee_id = Task._my_hr_employee().id or False
        filters = {"employee_id": int(employee_id)} if employee_id else {}
        data = Task.get_report_overview(year=year, month=month, filters=filters)
        if data.get("message"):
            return {
                "year": data.get("year"),
                "month": data.get("month"),
                "message": data["message"],
                "groups": [],
                "other": None,
                "employees": [],
            }
        profile = data.get("profile") or {}
        rows = data.get("rows") or []
        tasks = Task.sudo().browse([r["id"] for r in rows if r.get("id")]).exists()
        # % Hoàn thành CV đúng như cột trên Báo cáo cá nhân
        row_pct = {r["id"]: int(r.get("completion_percent") or 0) for r in rows if r.get("id")}
        WG = self.env["daily.task.work.group"].sudo()

        # Thứ tự hạng mục giống Bảng hạng mục
        cat_order = {}
        for dept in WG.get_category_board_data().get("departments") or []:
            for team in dept.get("teams") or []:
                for cat in team.get("categories") or []:
                    cat_order.setdefault(_norm(WG._norm_category_name(cat.get("name"))), len(cat_order))

        buckets = {}
        for task in tasks:
            wg = task.work_group_id
            cat = WG._norm_category_name(wg.name) if wg else ""
            gkey = _norm(cat) if cat else ""
            group = buckets.setdefault(gkey, {"name": cat, "items": {}})
            item = group["items"].setdefault(_norm(task.name), {
                "name": (task.name or "").strip(),
                "tasks": self.env["daily.task"],
            })
            item["tasks"] |= task

        def build_row(item, other=False):
            recs = item["tasks"]
            tpl = recs.mapped("recurring_id")[:1]
            # Tần suất thực hiện = số NGÀY làm trong tháng (1 ngày làm nhiều lần tính 1)
            work_days = {t.assign_date or t.deadline for t in recs if (t.assign_date or t.deadline)}
            count = len(work_days) or len(recs)
            minutes = [int(t.duration_minutes or 0) for t in recs]
            # TG thực hiện (phút) = cột "Phút" của Báo cáo cá nhân, chỉ cộng các việc ĐÃ HOÀN THÀNH
            done_min = sum(int(t.duration_minutes or 0) for t in recs if t.state == "done")
            # TG thực hiện (phút/lần) = phút của Báo cáo cá nhân, trung bình các lần ĐÃ HOÀN THÀNH;
            # chưa có lần hoàn thành → phút của mẫu lặp → trung bình các lần đã nhập
            done_each = [int(t.duration_minutes or 0) for t in recs if t.state == "done" and t.duration_minutes]
            per_time = round(sum(done_each) / len(done_each)) if done_each else 0
            if not per_time and tpl:
                per_time = int(tpl.duration_minutes or 0)
            if not per_time:
                nonzero = [m for m in minutes if m]
                per_time = round(sum(nonzero) / len(nonzero)) if nonzero else 0
            freq = next((k for k in (l._frequency_key() for l in recs.mapped("assign_line_id")) if k), False)
            if freq:
                # Tần suất tích trên Thêm phân công công việc (Ngày / Tuần / Tháng)
                label, col = {"day": ("Mỗi ngày", "day"), "week": ("Mỗi tuần", "week"),
                              "month": ("Tháng/lần", "month")}[freq]
            elif tpl:
                label, col = self._PERIOD.get(tpl.recurrence_type or "daily", ("Mỗi ngày", "day"))
            else:
                # Tự nhận diện theo ngày làm thực tế trong tháng:
                # làm ≥ 15 ngày khác nhau → hằng ngày; có mặt ở ≥ 3 tuần khác nhau → hằng tuần; còn lại → tháng
                weeks = {d.isocalendar()[:2] for d in work_days}
                if len(work_days) >= 15:
                    label, col = "Mỗi ngày", "day"
                elif len(weeks) >= 3:
                    label, col = "Mỗi tuần", "week"
                elif other:
                    label, col = "Phát sinh", "month"
                else:
                    label, col = ("%s ngày/tháng" % count if count > 1 else "Tháng/lần"), "month"
            # Mức độ hoàn thành = cột "% Hoàn thành CV" của Báo cáo cá nhân (trung bình các lần)
            pct = [row_pct.get(t.id, int(t.completion_percent or 0)) for t in recs]
            notes = [n for n in dict.fromkeys((t.note or "").strip() for t in recs) if n]
            plan_h = round(per_time / 60.0 * self._STANDARD_DAYS, 1)
            # SỐ NGÀY = số ngày nhập trên Thêm phân công công việc; để trống → số ngày đã hoàn thành
            done_days = len({t.assign_date or t.deadline for t in recs
                             if t.state == "done" and (t.assign_date or t.deadline)})
            set_days = max([int(l.freq_days or 0) for l in recs.mapped("assign_line_id")] or [0])
            so_ngay = set_days or done_days
            actual_h = round(so_ngay * per_time / 60.0, 1)
            return {
                "name": item["name"],
                "deadline": label,
                "freq": so_ngay,
                "day": "X" if col == "day" else "",
                "week": "X" if col == "week" else "",
                "month": "X" if col == "month" else "",
                "minutes": per_time,
                "plan_hours": plan_h,
                "actual_hours": actual_h,
                "done_days": done_days,
                "progress": round(sum(pct) / len(pct)) if pct else 0,
                "_pct_sum": sum(pct),
                # QUẢN LÝ ĐÁNH GIÁ = % Hoàn thành / Ghi chú quản lý nhập trên Kiểm tra CV (trung bình các lần)
                "mgr_pct": round(sum(int(t.manager_eval_percent or 0) for t in recs) / len(recs)) if recs else 0,
                "_mgr_ok": sum(int(t.manager_eval_percent or 0) for t in recs) / 100.0,
                "mgr_note": "; ".join(n for n in dict.fromkeys(
                    (t.manager_eval_note or "").strip() for t in recs) if n),
                "_pct_n": len(pct),
                "note": "; ".join(notes),
                "first": min((t.assign_date or t.deadline) for t in recs if (t.assign_date or t.deadline))
                if any(t.assign_date or t.deadline for t in recs) else False,
            }

        groups, other = [], None
        for gkey, group in buckets.items():
            is_other = not gkey
            lines = [build_row(it, other=is_other) for it in group["items"].values()]
            lines.sort(key=lambda r: (r["first"] or date.max, r["name"].casefold()))
            for idx, line in enumerate(lines, start=1):
                line["stt"] = idx
                line.pop("first", None)
            block = {
                "name": group["name"].upper() if group["name"] else "",
                "lines": lines,
                "plan_hours": round(sum(r["plan_hours"] for r in lines), 1),
                "progress": round(sum(r["_pct_sum"] for r in lines) / sum(r["_pct_n"] for r in lines))
                if sum(r["_pct_n"] for r in lines) else 0,
                "actual_hours": round(sum(r["actual_hours"] for r in lines), 1),
                "mgr_pct": round(100.0 * sum(r["_mgr_ok"] for r in lines) / sum(r["_pct_n"] for r in lines))
                if sum(r["_pct_n"] for r in lines) else 0,
                "_sort": cat_order.get(gkey, 10**6),
            }
            if is_other:
                other = block
            else:
                groups.append(block)
        groups.sort(key=lambda g: (g.pop("_sort"), g["name"]))
        if other:
            other.pop("_sort", None)
        for idx, g in enumerate(groups, start=1):
            g["code"] = _roman(idx)

        total_plan = sum(g["plan_hours"] for g in groups) + (other["plan_hours"] if other else 0)
        std = self._STANDARD_HOURS
        for block in groups + ([other] if other else []):
            block["plan_pct"] = round(100.0 * block["plan_hours"] / std, 1)
            for r in block["lines"]:
                r["plan_pct"] = round(100.0 * r["plan_hours"] / std, 1)
        total_actual = round(sum(g["actual_hours"] for g in groups) + (other["actual_hours"] if other else 0), 1)
        all_lines = [r for b in groups + ([other] if other else []) for r in b["lines"]]
        n_tasks = sum(r["_pct_n"] for r in all_lines)
        done_pct = round(sum(r["_pct_sum"] for r in all_lines) / n_tasks, 1) if n_tasks else 0
        mgr_pct = round(100.0 * sum(r["_mgr_ok"] for r in all_lines) / n_tasks, 1) if n_tasks else 0
        for r in all_lines:
            r.pop("_mgr_ok", None)
            r.pop("_pct_sum", None)
            r.pop("_pct_n", None)

        filt = data.get("filters") or {}
        charts = data.get("charts") or {}
        # Dashboard: số việc / biểu đồ giống Báo cáo cá nhân; riêng "Tổng thời gian" lấy đúng
        # tổng THỰC HIỆN của bảng (chỉ ngày đã hoàn thành) để 2 nơi khớp nhau
        # HIỆU SUẤT / Đánh giá hiệu suất tháng = đúng dòng tổng «QUẢN LÝ ĐÁNH GIÁ – % HOÀN THÀNH» của bảng
        kpi = dict(data.get("kpi") or {}, duration_hours=total_actual, efficiency=mgr_pct)
        rating = "Tốt" if mgr_pct >= 85 else "Khá" if mgr_pct >= 70 else "Cần cải thiện" if mgr_pct < 50 else "Trung bình"
        evaluation = dict(
            data.get("evaluation") or {},
            hours=total_actual,
            score=mgr_pct,
            rating=rating,
            stars=min(5.0, round((mgr_pct / 20.0) * 2) / 2.0) if mgr_pct else 0.0,
        )
        return {
            "kpi": kpi,
            "charts": {"by_state": charts.get("by_state") or {}, "weekly": charts.get("weekly") or {}},
            "evaluation": evaluation,
            "year": data["year"],
            "month": data["month"],
            "employee": {
                "id": profile.get("id") or profile.get("employee_id") or (int(employee_id) if employee_id else False),
                "name": profile.get("name") or "",
                "department": profile.get("department") or profile.get("department_name") or "",
                "job_title": profile.get("job_title") or "",
                "avatar_url": profile.get("avatar_url") or "",
            },
            "groups": groups,
            "other": other,
            "total_plan_hours": round(total_plan, 1),
            "total_actual_hours": total_actual,
            "total_progress": done_pct,
            "total_mgr_pct": mgr_pct,
            "can_pick_employee": bool(data.get("can_pick_employee")),
            "employees": filt.get("employees") or [],
        }

    # ------------------------------------------------------------------ Excel
    @api.model
    def export_excel(self, year=None, month=None, employee_id=None):
        try:
            import xlsxwriter
        except ImportError as exc:
            raise ValidationError("Thiếu thư viện xlsxwriter. Cài đặt: pip install xlsxwriter") from exc
        data = self.get_report(year=year, month=month, employee_id=employee_id)
        if data.get("message"):
            raise ValidationError(data["message"])

        buf = io.BytesIO()
        wb = xlsxwriter.Workbook(buf, {"in_memory": True})
        ws = wb.add_worksheet("Bao_cao_thang")
        ws.set_landscape()
        ws.set_paper(9)
        ws.fit_to_pages(1, 0)
        ws.set_margins(left=0.3, right=0.3, top=0.4, bottom=0.4)
        FONT = "Times New Roman"

        def f(**kw):
            base = {"font_name": FONT, "font_size": 11, "valign": "vcenter", "text_wrap": True}
            base.update(kw)
            return wb.add_format(base)

        bold = f(bold=True)
        title = f(bold=True, font_size=20, font_color="#FF0000", align="center")
        head = f(bold=True, border=1, align="center")
        head_green = f(bold=True, border=1, align="center", bg_color="#C6E0B4")
        band = f(bold=True, border=1, bg_color="#D9E1F2")
        grp = f(bold=True, border=1, bg_color="#FFFF00")
        grp_c = f(bold=True, border=1, bg_color="#FFFF00", align="center")
        cell = f(border=1)
        cell_c = f(border=1, align="center")
        pct_c = f(border=1, align="center", num_format="0.0%")
        dotted = f(bottom=3)

        widths = [6, 46, 13, 10, 7, 7, 8, 10, 11, 9, 11, 11, 13, 9, 34]
        for i, w in enumerate(widths):
            ws.set_column(i, i, w)

        emp = data["employee"]
        # Tiêu đề: BÁO CÁO CÔNG VIỆC (giữa) · Tháng … Năm … (giữa) · Họ và tên · Phòng ban
        ws.set_row(0, 34)
        ws.merge_range(0, 0, 0, 14, "BÁO CÁO CÔNG VIỆC", title)
        ws.merge_range(1, 0, 1, 14, "Tháng %s Năm %s" % (data["month"], data["year"]),
                       f(bold=True, font_size=13, align="center"))
        ws.merge_range(2, 0, 2, 14, "Họ và tên nhân viên: %s" % (emp["name"] or ""), bold)
        ws.merge_range(3, 0, 3, 14, "Phòng ban: %s" % (emp["department"] or ""), bold)

        # Tiêu đề bảng 2 dòng
        r = 5
        ws.set_row(r + 1, 48)
        for c, text in ((0, "STT"), (1, "NỘI DUNG CÔNG VIỆC"), (2, "DEADLINES"), (3, "SỐ NGÀY"),
                        (7, "TG THỰC HIỆN (ĐVT: PHÚT)"), (12, "GHI CHÚ")):
            ws.merge_range(r, c, r + 1, c, text, head)
        ws.merge_range(r, 4, r, 6, "TẦN SUẤT THỰC HIỆN", head)
        for c, text in ((4, "NGÀY"), (5, "TUẦN"), (6, "THÁNG")):
            ws.write(r + 1, c, text, head)
        ws.merge_range(r, 8, r, 9, "ĐỊNH BIÊN", head_green)
        ws.merge_range(r, 10, r, 11, "THỰC HIỆN", head_green)
        ws.merge_range(r, 13, r, 14, "QUẢN LÝ ĐÁNH GIÁ", head)
        for c, text in ((8, "THỜI GIAN (THEO GIỜ)"), (9, "%"), (10, "THỜI GIAN (THEO GIỜ)"),
                        (11, "MỨC ĐỘ HOÀN THÀNH"), (13, "% HOÀN THÀNH"), (14, "GHI CHÚ")):
            ws.write(r + 1, c, text, head)
        r += 2

        def write_line(r, line):
            vals = [line["stt"], line["name"], line["deadline"], line["freq"], line["day"], line["week"],
                    line["month"], line["minutes"] or "", line["plan_hours"], "%s%%" % line["plan_pct"],
                    line["actual_hours"], "%s%%" % line["progress"], line["note"], "%s%%" % line["mgr_pct"], line["mgr_note"]]
            for c, v in enumerate(vals):
                ws.write(r, c, v, cell if c in (1, 12, 14) else cell_c)
            # Định biên THỜI GIAN (giờ) = (TG thực hiện phút / 60) × SỐ NGÀY — ghi công thức như mẫu
            ws.write_formula(r, 8, "=ROUND((H%d/60)*%d,1)" % (r + 1, self._STANDARD_DAYS), cell_c, line["plan_hours"])
            # Thực hiện THỜI GIAN (giờ) = (TG thực hiện phút / 60) × số ngày đã thực hiện
            ws.write_formula(r, 10, "=ROUND((H%d/60)*D%d,1)" % (r + 1, r + 1), cell_c, line["actual_hours"])
            # % = Thời gian định biên (giờ) / 208 (quỹ giờ chuẩn tháng)
            ws.write_formula(r, 9, "=I%d/%d" % (r + 1, int(self._STANDARD_HOURS)), pct_c, line["plan_pct"] / 100.0)

        ws.merge_range(r, 0, r, 14, "NHÓM CÔNG VIỆC THEO MTCV CHI TIẾT", band)
        r += 1
        for g in data["groups"]:
            ws.write(r, 0, g["code"], grp_c)
            ws.write(r, 1, g["name"], grp)
            for c in range(2, 15):
                ws.write(r, c, "", grp_c)
            ws.write(r, 8, g["plan_hours"], grp_c)
            ws.write(r, 9, "%s%%" % g["plan_pct"], grp_c)
            ws.write(r, 10, g["actual_hours"], grp_c)
            ws.write(r, 11, "%s%%" % g["progress"], grp_c)
            ws.write(r, 13, "%s%%" % g["mgr_pct"], grp_c)
            r += 1
            for line in g["lines"]:
                write_line(r, line)
                r += 1
        ws.merge_range(r, 0, r, 14, "NHÓM CÔNG VIỆC KHÁC (NẾU CÓ)", band)
        r += 1
        other = data.get("other")
        if other:
            for line in other["lines"]:
                write_line(r, line)
                r += 1
            ws.merge_range(r, 0, r, 7, "TỔNG THỜI GIAN (THEO H)", grp_c)
            for c in range(8, 15):
                ws.write(r, c, "", grp_c)
            ws.write(r, 10, other["actual_hours"], grp_c)
            r += 1
        ws.merge_range(r, 0, r, 7, "TỔNG THỜI GIAN THỰC HIỆN TRONG THÁNG (THEO H)", grp_c)
        for c in range(8, 15):
            ws.write(r, c, "", grp_c)
        ws.write(r, 8, data["total_plan_hours"], grp_c)
        ws.write(r, 10, data["total_actual_hours"], grp_c)
        ws.write(r, 11, "%s%%" % data["total_progress"], grp_c)
        ws.write(r, 13, "%s%%" % data["total_mgr_pct"], grp_c)
        r += 2

        ws.write(r, 1, "Đánh giá của cấp quản lý/ trưởng bộ phận:", bold)
        for k in range(1, 4):
            for c in range(1, 15):
                ws.write(r + k, c, "", dotted)
        r += 5
        ws.write(r, 1, "Ngày............................")
        r += 1
        ws.write(r, 1, "Người lập", bold)
        ws.merge_range(r, 6, r, 9, "Trưởng bộ phận", f(bold=True, align="center"))
        ws.merge_range(r, 11, r, 14, "Ban Giám đốc", f(bold=True, align="center"))
        r += 5
        ws.write(r, 1, emp["name"] or "", bold)

        wb.close()
        name = re.sub(r"\W+", "_", emp["name"] or "nhan_vien").strip("_")
        return {
            "file_base64": base64.b64encode(buf.getvalue()).decode("ascii"),
            "filename": "Bao_cao_cong_viec_thang_%02d_%s_%s.xlsx" % (data["month"], data["year"], name),
        }
