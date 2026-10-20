# -*- coding: utf-8 -*-
"""QL đánh giá tổng — % hiệu suất quản lý chốt cho từng nhân viên theo tháng.

Nhập ở Báo cáo hiệu suất → «Hiệu suất nhân sự» (cột QL đánh giá tổng). Khi có giá trị, đây là
kết quả cuối cùng cho «QL đánh giá» của nhân viên đó trên Báo cáo CV NV Kho; chưa nhập → giữ
giá trị tính tự động (TB % Hoàn thành QL chấm trên Kiểm tra CV).
"""

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError


class DailyTaskManagerPerf(models.Model):
    _name = "daily.task.manager.perf"
    _description = "QL đánh giá tổng (hiệu suất tháng của nhân viên)"
    _order = "year desc, month desc, employee_id"

    employee_id = fields.Many2one("hr.employee", string="Nhân viên", required=True, index=True, ondelete="cascade")
    user_id = fields.Many2one(related="employee_id.user_id", store=True, index=True)
    year = fields.Integer(required=True, index=True)
    month = fields.Integer(required=True, index=True)
    percent = fields.Float(string="QL đánh giá tổng (%)", digits=(5, 1), required=True)
    set_by_id = fields.Many2one("res.users", string="Người chốt", readonly=True)
    set_date = fields.Datetime(string="Ngày chốt", readonly=True)

    _uniq_emp_month = models.Constraint(
        "unique(employee_id, year, month)",
        "Mỗi nhân viên chỉ có một QL đánh giá tổng trong tháng.",
    )

    # ------------------------------------------------------------------ quyền
    @api.model
    def _can_rate(self, employee):
        """Quản trị / quản lý công việc, quản lý trực tiếp (HR) hoặc quản lý Team của nhân viên."""
        if self.env.su or self.env["daily.task"]._is_manager():
            return True
        uid = self.env.uid
        emp = employee.sudo()
        if emp.user_id and emp.user_id.id == uid:
            return False  # không tự chốt cho mình
        if emp.parent_id and emp.parent_id.user_id.id == uid:
            return True
        if emp.user_id:
            teams = self.env["daily.task.team"].sudo().search([
                "|", ("member_ids", "in", emp.user_id.ids), ("manager_ids", "in", emp.user_id.ids),
            ])
            if any(uid in t.manager_ids.ids for t in teams):
                return True
        return False

    # ------------------------------------------------------------------ đọc / ghi
    @api.model
    def get_map(self, year, month, employee_ids=None, user_ids=None):
        """{employee_id: percent} hoặc theo user khi truyền user_ids → {user_id: percent}."""
        domain = [("year", "=", int(year)), ("month", "=", int(month))]
        if employee_ids is not None:
            domain.append(("employee_id", "in", list(employee_ids)))
        if user_ids is not None:
            domain.append(("user_id", "in", list(user_ids)))
            return {r.user_id.id: r.percent for r in self.sudo().search(domain) if r.user_id}
        return {r.employee_id.id: r.percent for r in self.sudo().search(domain)}

    @api.model
    def set_manager_perf(self, employee_id, year, month, percent=None):
        """Lưu QL đánh giá tổng; percent rỗng → xoá (quay về giá trị tính tự động)."""
        emp = self.env["hr.employee"].sudo().browse(int(employee_id or 0)).exists()
        if not emp:
            raise ValidationError("Không tìm thấy nhân viên.")
        if not self._can_rate(emp):
            raise AccessError("Bạn không có quyền chốt QL đánh giá tổng cho «%s»." % emp.name)
        year, month = int(year), int(month)
        rec = self.sudo().search([("employee_id", "=", emp.id), ("year", "=", year), ("month", "=", month)], limit=1)
        if percent in (None, False, ""):
            rec.unlink()
            return {"employee_id": emp.id, "percent": None}
        try:
            value = round(float(str(percent).replace(",", ".")), 1)
        except (TypeError, ValueError):
            raise ValidationError("% QL đánh giá tổng không hợp lệ.")
        if value < 0 or value > 100:
            raise ValidationError("% QL đánh giá tổng phải từ 0 đến 100.")
        vals = {"percent": value, "set_by_id": self.env.uid, "set_date": fields.Datetime.now()}
        if rec:
            rec.write(vals)
        else:
            self.sudo().create(dict(vals, employee_id=emp.id, year=year, month=month))
        return {"employee_id": emp.id, "percent": value}
