# -*- coding: utf-8 -*-

from odoo import api, fields, models

from .monthly_matrix_schedule import _norm_code

SKIP_CODES = {"", "-", "OFF", "NGHI", "NGHỈ", "LE", "LỄ", "NVM"}
WD_VN = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")


def _float_to_hhmm(value):
    if value is None or value is False:
        return ""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return ""
    hours = int(num)
    minutes = int(round((num - hours) * 60))
    if minutes == 60:
        hours += 1
        minutes = 0
    return f"{hours:02d}:{minutes:02d}"


class LinkqTodayShift(models.TransientModel):
    _name = "linkq.today.shift"
    _description = "Lịch ca hôm nay"
    _order = "store_id, stt, id"

    stt = fields.Integer(string="STT")
    employee_name = fields.Char(string="HỌ VÀ TÊN")
    job_position = fields.Char(string="CHỨC VỤ")
    employee_code = fields.Char(string="MÃ ID")
    store_id = fields.Many2one("hr.store", string="CỬA HÀNG", ondelete="set null")
    shift_symbol = fields.Char(string="CA")
    shift_time = fields.Char(string="THỜI GIAN")

    @api.model
    def _shift_catalog(self):
        rows = self.env["linkq.shift.code"].sudo().search([])
        by_code = {}
        for rec in rows:
            code = _norm_code(rec.code)
            if code:
                by_code[code] = rec
        return by_code

    @api.model
    def _code_for_today(self, line, day_key):
        plan = line._code_map(line.plan_codes)
        actual = line._code_map(line.actual_codes)
        return plan.get(day_key) or actual.get(day_key) or ""

    @api.model
    def _time_range(self, code, catalog):
        rec = catalog.get(code)
        if rec and rec.shift_group == "OFF":
            return None
        if rec and (rec.time_in or rec.time_out):
            start = _float_to_hhmm(rec.time_in)
            end = _float_to_hhmm(rec.time_out)
            if start and end:
                return f"{start} - {end}"
        return "Theo ca"

    @api.model
    def sync_today_rows(self):
        today = fields.Date.context_today(self)
        day_key = str(today.day)
        self.search([]).unlink()
        rosters = self.env["linkq.monthly.roster"].search([
            ("year", "=", today.year),
            ("month", "=", str(today.month)),
        ])
        catalog = self._shift_catalog()
        vals_list = []
        seen = set()
        idx = 1
        for roster in rosters:
            store_id = roster.store_id.id if roster.store_id else False
            for line in roster.line_ids:
                code = _norm_code(self._code_for_today(line, day_key))
                if not code or code in SKIP_CODES:
                    continue
                symbol = catalog.get(code)
                if symbol and symbol.shift_group == "OFF":
                    continue
                time_range = self._time_range(code, catalog)
                if time_range is None:
                    continue
                emp_code = str(line.employee_code or "") if line.employee_code else ""
                name = (line.employee_name or "").strip().upper()
                key = (store_id, emp_code, name, code)
                if key in seen:
                    continue
                seen.add(key)
                vals_list.append({
                    "stt": idx,
                    "employee_name": name,
                    "job_position": line.job_title or "",
                    "employee_code": emp_code,
                    "store_id": store_id,
                    "shift_symbol": code,
                    "shift_time": time_range,
                })
                idx += 1
        if vals_list:
            self.create(vals_list)
        return today

    @api.model
    def action_open_today_shift(self):
        today = self.sync_today_rows()
        title = "Lịch ca hôm nay - %s, %s" % (
            WD_VN[today.weekday()],
            today.strftime("%d/%m/%Y"),
        )
        return {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": "linkq.today.shift",
            "view_mode": "list",
            "views": [(False, "list")],
            "target": "current",
            "context": {"search_default_group_store": 0},
        }
