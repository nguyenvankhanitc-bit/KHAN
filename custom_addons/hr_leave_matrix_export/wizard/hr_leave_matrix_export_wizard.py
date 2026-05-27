# Part of Odoo. See LICENSE file for full copyright and licensing details.

import calendar
import json
import re
from collections import defaultdict
from datetime import date, timedelta
from io import BytesIO

import xlsxwriter

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Column layout (same order as the reference sheet)
COL_APPROVE = 0
COL_STATUS = 1
COL_ID_HRM = 2
COL_NAME = 3
COL_DAY_START = 4

STATUS_LABELS = {
    "active": "Chính thức",
    "probation": "Thử việc",
    "leave": "Nghỉ phép",
    "terminated": "Đã nghỉ việc",
}


class HrLeaveMatrixExportWizard(models.TransientModel):
    _name = "hr.leave.matrix.export.wizard"
    _inherit = ["hr.leave.store.export.mixin"]
    _description = "Export time off as day matrix (Excel)"

    year = fields.Integer(required=True, default=lambda self: fields.Date.context_today(self).year)
    month = fields.Integer(
        required=True,
        default=lambda self: fields.Date.context_today(self).month,
        help="Calendar month used for columns N1…N(last day).",
    )
    domain_json = fields.Text(
        string="Search domain (JSON)",
        help="Technical: current list filters from the Time Off list view.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        # Ignore stale client/registry payloads after export_kind was removed.
        for vals in vals_list:
            vals.pop("export_kind", None)
        return super().create(vals_list)

    def write(self, vals):
        vals.pop("export_kind", None)
        return super().write(vals)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        ctx = self.env.context
        raw = ctx.get("matrix_export_domain_json")
        if raw is not None and "domain_json" in fields_list:
            res["domain_json"] = raw if isinstance(raw, str) else json.dumps(raw)
        res.pop("export_kind", None)
        return res

    @api.constrains("month")
    def _check_month(self):
        for wiz in self:
            if wiz.month < 1 or wiz.month > 12:
                raise UserError(_("Month must be between 1 and 12."))

    def _parse_domain(self):
        self.ensure_one()
        raw = (self.domain_json or "").strip()
        if not raw:
            return []
        try:
            domain = json.loads(raw)
        except json.JSONDecodeError as e:
            raise UserError(_("Invalid search domain: %s") % e) from e
        if not isinstance(domain, list):
            raise UserError(_("Search domain must be a list."))
        return domain

    @staticmethod
    def _leave_type_cell_label(leave_type):
        """Mã ô Excel = phần trong ngoặc () của tên loại nghỉ, vd. 'Nghỉ Phép (P)' -> 'P'."""
        if not leave_type:
            return ""
        name = (leave_type.name or "").strip()
        if not name:
            return ""
        match = re.search(r"\(([^)]+)\)\s*$", name)
        if match:
            return match.group(1).strip()
        return ""

    @staticmethod
    def _weekend_kind(year, month, day):
        wd = date(year, month, day).weekday()
        if wd == 5:
            return "sat"
        if wd == 6:
            return "sun"
        return None

    def _employee_status_label(self, employee):
        if "trang_thai_nhan_vien" not in employee._fields:
            return ""
        status = employee.trang_thai_nhan_vien
        if status in STATUS_LABELS:
            return STATUS_LABELS[status]
        if status:
            selection = dict(
                employee._fields["trang_thai_nhan_vien"]._description_selection(self.env)
            )
            return selection.get(status, status)
        return ""

    def _employee_id_hrm(self, employee):
        return (getattr(employee, "id_hrm", None) or "").strip()

    def _employee_department_name(self, employee):
        if employee.department_id:
            return (employee.department_id.name or "").strip()
        ten_bo_phan = (getattr(employee, "ten_bo_phan", None) or "").strip()
        if ten_bo_phan:
            return ten_bo_phan
        return _("Other")

    def _build_matrix(self, year, month, base_domain):
        last_day = calendar.monthrange(year, month)[1]
        month_start = date(year, month, 1)
        month_end = date(year, month, last_day)
        overlap_domain = [
            ("request_date_from", "<=", month_end),
            ("request_date_to", ">=", month_start),
        ]
        domain = base_domain + overlap_domain if base_domain else overlap_domain
        leaves = self.env["hr.leave"].search(domain, order="employee_id, request_date_from, id")

        cells = defaultdict(lambda: defaultdict(list))
        employees = self.env["hr.employee"]
        for leave in leaves:
            if not leave.employee_id or not leave.request_date_from or not leave.request_date_to:
                continue
            if not self._leave_in_mien(leave, self.MIEN_VP_CODES):
                continue
            employees |= leave.employee_id
            label = self._leave_type_cell_label(leave.holiday_status_id)
            span_start = max(leave.request_date_from, month_start)
            span_end = min(leave.request_date_to, month_end)
            d = span_start
            while d <= span_end:
                bucket = cells[d.day][leave.employee_id.id]
                if label not in bucket:
                    bucket.append(label)
                d += timedelta(days=1)

        return employees, cells, last_day

    def _group_employees_by_department(self, employees):
        """Return [(department_name, employee_recordset), ...] sorted by department then name."""
        by_dept = defaultdict(lambda: self.env["hr.employee"])
        for emp in employees:
            dept_name = self._employee_department_name(emp)
            by_dept[dept_name] |= emp
        groups = []
        for dept_name in sorted(by_dept.keys(), key=lambda n: (n == _("Other"), str(n).upper())):
            emps = by_dept[dept_name].sorted(lambda e: (e.name or "").upper())
            groups.append((dept_name, emps))
        return groups

    def _workbook_formats(self, workbook):
        border = {"border": 1, "border_color": "#B4C6E7"}
        base = {**border, "valign": "vcenter"}
        return {
            "header": workbook.add_format(
                {
                    **base,
                    "bold": True,
                    "bg_color": "#BDD7EE",
                    "align": "center",
                    "text_wrap": True,
                }
            ),
            "header_sat": workbook.add_format(
                {
                    **base,
                    "bold": True,
                    "bg_color": "#F8CBAD",
                    "align": "center",
                }
            ),
            "header_sun": workbook.add_format(
                {
                    **base,
                    "bold": True,
                    "bg_color": "#D9D2E9",
                    "align": "center",
                }
            ),
            "dept": workbook.add_format(
                {
                    **base,
                    "bold": True,
                    "bg_color": "#FFFFFF",
                    "align": "left",
                }
            ),
            "cell": workbook.add_format({**base, "align": "center"}),
            "cell_stripe": workbook.add_format({**base, "bg_color": "#DDEBF7", "align": "center"}),
            "name": workbook.add_format({**base, "align": "left", "text_wrap": True}),
            "name_stripe": workbook.add_format(
                {**base, "bg_color": "#DDEBF7", "align": "left", "text_wrap": True}
            ),
            "cell_sat": workbook.add_format({**base, "bg_color": "#FCE4D6", "align": "center"}),
            "cell_sun": workbook.add_format({**base, "bg_color": "#E4DFEC", "align": "center"}),
            "cell_sat_stripe": workbook.add_format(
                {**base, "bg_color": "#F4D4C4", "align": "center"}
            ),
            "cell_sun_stripe": workbook.add_format(
                {**base, "bg_color": "#DAD4E4", "align": "center"}
            ),
        }

    def _day_cell_format(self, formats, year, month, day, stripe):
        kind = self._weekend_kind(year, month, day)
        if kind == "sat":
            return formats["cell_sat_stripe"] if stripe else formats["cell_sat"]
        if kind == "sun":
            return formats["cell_sun_stripe"] if stripe else formats["cell_sun"]
        return formats["cell_stripe"] if stripe else formats["cell"]

    def _header_format_for_day(self, formats, year, month, day):
        kind = self._weekend_kind(year, month, day)
        if kind == "sat":
            return formats["header_sat"]
        if kind == "sun":
            return formats["header_sun"]
        return formats["header"]

    def action_export_matrix_excel(self):
        self.ensure_one()
        if not self.env.user.has_group("base.group_allow_export"):
            raise UserError(_("You need export permissions to download this file."))

        year, month = int(self.year), int(self.month)
        base_domain = self._parse_domain()
        employees, cells, last_day = self._build_matrix(year, month, base_domain)
        dept_groups = self._group_employees_by_department(employees)

        buffer = BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
        sheet = workbook.add_worksheet(_("Time off"))
        formats = self._workbook_formats(workbook)
        last_col = COL_DAY_START + last_day - 1

        headers = [
            "Duyệt",
            "TRẠNG THÁI NHÂN VIÊN",
            "ID HRM",
            "HỌ VÀ TÊN (dấu)",
        ]
        for col, title in enumerate(headers):
            sheet.write(0, col, title, formats["header"])
        for day in range(1, last_day + 1):
            col = COL_DAY_START + day - 1
            sheet.write(
                0,
                col,
                f"N{day}",
                self._header_format_for_day(formats, year, month, day),
            )

        row = 1
        stripe_toggle = False
        for dept_name, dept_employees in dept_groups:
            sheet.write(row, COL_NAME, dept_name.upper(), formats["dept"])
            for col in (COL_APPROVE, COL_STATUS, COL_ID_HRM):
                sheet.write(row, col, "", formats["dept"])
            for day in range(1, last_day + 1):
                col = COL_DAY_START + day - 1
                sheet.write(row, col, "", formats["dept"])
            row += 1

            for emp in dept_employees:
                stripe = stripe_toggle
                stripe_toggle = not stripe_toggle
                name_fmt = formats["name_stripe"] if stripe else formats["name"]
                base_fmt = formats["cell_stripe"] if stripe else formats["cell"]

                sheet.write(row, COL_APPROVE, "", base_fmt)
                sheet.write(row, COL_STATUS, self._employee_status_label(emp), base_fmt)
                sheet.write(row, COL_ID_HRM, self._employee_id_hrm(emp), base_fmt)
                sheet.write(row, COL_NAME, emp.name or "", name_fmt)

                for day in range(1, last_day + 1):
                    col = COL_DAY_START + day - 1
                    labels = cells[day].get(emp.id) or []
                    value = ", ".join(labels) if labels else ""
                    sheet.write(
                        row,
                        col,
                        value,
                        self._day_cell_format(formats, year, month, day, stripe),
                    )
                row += 1

        if row == 1:
            sheet.write_row(1, 0, [""] * (last_col + 1), formats["cell"])
            row = 2

        sheet.freeze_panes(1, COL_NAME)

        sheet.set_column(COL_APPROVE, COL_APPROVE, 6)
        sheet.set_column(COL_STATUS, COL_STATUS, 18)
        sheet.set_column(COL_ID_HRM, COL_ID_HRM, 10)
        sheet.set_column(COL_NAME, COL_NAME, 32)
        if last_day >= 1:
            sheet.set_column(COL_DAY_START, last_col, 5.5)

        workbook.close()
        buffer.seek(0)
        data = buffer.read()
        filename = "time_off_matrix_%s-%02d.xlsx" % (year, month)

        attachment = self.env["ir.attachment"].create(
            {
                "name": filename,
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "raw": data,
                "res_model": self._name,
                "res_id": self.id,
            }
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }
