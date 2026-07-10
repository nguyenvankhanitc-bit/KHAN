# -*- coding: utf-8 -*-

import re
import unicodedata

from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError

_REQUIRED_LEAVE_FORM_BASENAME = "don xin nghi phep"


def _normalize_attachment_basename(name):
    base = (name or "").strip()
    if "." in base:
        base = base.rsplit(".", 1)[0]
    normalized = base.casefold()
    normalized = "".join(
        ch for ch in unicodedata.normalize("NFKD", normalized) if not unicodedata.combining(ch)
    )
    return re.sub(r"\s+", " ", normalized).strip()


class HrLeave(models.Model):
    _inherit = "hr.leave"

    employee_id_hrm = fields.Char(
        string="ID HRM",
        compute="_compute_employee_hrm_display",
        readonly=True,
    )
    employee_ma_bo_phan = fields.Char(
        string="Mã bộ phận",
        compute="_compute_employee_hrm_display",
        readonly=True,
    )

    @api.depends("employee_id")
    def _compute_employee_hrm_display(self):
        for leave in self:
            employee = leave.employee_id.sudo()
            id_hrm = (getattr(employee, "id_hrm", None) or "").strip()
            leave.employee_id_hrm = f"ID {id_hrm}" if id_hrm else ""
            leave.employee_ma_bo_phan = (getattr(employee, "ma_bo_phan", None) or "").strip()

    def _leave_reason_from_vals(self, vals):
        return (vals.get("name") or vals.get("private_name") or "").strip()

    def _leave_reason_text(self, vals=None):
        self.ensure_one()
        if vals:
            reason = self._leave_reason_from_vals(vals)
            if reason:
                return reason
        reason = (self.sudo().private_name or "").strip()
        if not reason:
            reason = (self.name or "").strip()
        return reason

    def _can_persist_leave_reason(self):
        self.ensure_one()
        is_officer = self.env.user.has_group("hr_holidays.group_hr_holidays_user")
        employee_user = self.employee_id.user_id
        return bool(
            is_officer
            or self.user_id == self.env.user
            or employee_user == self.env.user
            or self.employee_id.leave_manager_id == self.env.user
        )

    def _inverse_description(self):
        for leave in self:
            if not leave._can_persist_leave_reason():
                continue
            reason = (leave.name or "").strip()
            if reason:
                leave.sudo().private_name = reason

    def _ensure_leave_reason_persisted(self, vals_list=None):
        for idx, leave in enumerate(self):
            vals = vals_list[idx] if vals_list and idx < len(vals_list) else {}
            reason = leave._leave_reason_text(vals)
            if not reason or not leave._can_persist_leave_reason():
                continue
            if reason != (leave.sudo().private_name or "").strip():
                leave.sudo().private_name = reason

    def _validate_leave_reason_required(self, vals_list=None):
        for idx, leave in enumerate(self):
            if leave.state != "confirm":
                continue
            vals = vals_list[idx] if vals_list and idx < len(vals_list) else {}
            if not leave._leave_reason_text(vals):
                raise ValidationError(_("Vui lòng nhập lý do nghỉ phép trước khi gửi đơn."))

    def _attachment_ids_from_vals(self, vals):
        attachment_ids = []
        for field_name in ("supported_attachment_ids", "attachment_ids"):
            commands = vals.get(field_name) or []
            for command in commands:
                if not isinstance(command, (list, tuple)) or not command:
                    continue
                if command[0] == Command.SET:
                    attachment_ids.extend(command[2])
                elif command[0] == Command.LINK:
                    attachment_ids.append(command[1])
        return attachment_ids

    def _leave_form_attachment_basenames(self, vals=None):
        self.ensure_one()
        names = []
        seen = set()
        if vals:
            for field_name in ("supported_attachment_ids", "attachment_ids"):
                for command in vals.get(field_name) or []:
                    if (
                        isinstance(command, (list, tuple))
                        and len(command) > 2
                        and command[0] == Command.CREATE
                        and isinstance(command[2], dict)
                        and command[2].get("name")
                    ):
                        normalized = _normalize_attachment_basename(command[2]["name"])
                        if normalized and normalized not in seen:
                            seen.add(normalized)
                            names.append(normalized)
            pending_ids = self._attachment_ids_from_vals(vals)
            if pending_ids:
                for attachment_name in self.env["ir.attachment"].browse(pending_ids).mapped("name"):
                    normalized = _normalize_attachment_basename(attachment_name)
                    if normalized and normalized not in seen:
                        seen.add(normalized)
                        names.append(normalized)
        for attachment_name in self.attachment_ids.mapped("name"):
            normalized = _normalize_attachment_basename(attachment_name)
            if normalized and normalized not in seen:
                seen.add(normalized)
                names.append(normalized)
        return names

    def _validate_leave_form_attachment_required(self, vals_list=None):
        required = _REQUIRED_LEAVE_FORM_BASENAME
        for idx, leave in enumerate(self):
            if leave.state != "confirm":
                continue
            vals = vals_list[idx] if vals_list and idx < len(vals_list) else {}
            basenames = leave._leave_form_attachment_basenames(vals)
            if not basenames:
                raise ValidationError(
                    _("Vui lòng đính kèm file Đơn xin nghỉ phép trước khi gửi đơn.")
                )
            if required not in basenames:
                raise ValidationError(
                    _(
                        'Tệp đính kèm bắt buộc phải có tên "Đơn xin nghỉ phép" '
                        "(ví dụ: Đơn xin nghỉ phép.docx)."
                    )
                )

    def _validate_leave_submit_requirements(self, vals_list=None):
        self._validate_leave_reason_required(vals_list)
        self._validate_leave_form_attachment_required(vals_list)

    def _leave_form_attachment_block_preview(self, res_id=False, vals=None):
        """Return a user-facing error message when attachment rules fail."""
        vals = vals or {}
        if self.env.context.get("import_file"):
            return False
        state = vals.get("state")
        if res_id:
            leave = self.browse(res_id)
            state = state or leave.state
        else:
            leave = self.new(vals)
            state = state or leave.state
        if state != "confirm":
            return False
        try:
            leave._validate_leave_form_attachment_required([vals])
        except ValidationError as exc:
            return exc.args[0] if exc.args else str(exc)
        return False

    @api.model
    def check_leave_form_save_confirmations(self, res_id=False, vals=None):
        result = super().check_leave_form_save_confirmations(res_id=res_id, vals=vals)
        if result.get("blocked"):
            return result
        message = self._leave_form_attachment_block_preview(res_id=res_id, vals=vals)
        if message:
            return {
                "blocked": True,
                "needs_confirmation": False,
                "set_emergency_confirmed": False,
                "set_con_lai_zero_confirmed": False,
                "title": _("Thiếu file đính kèm"),
                "message": message,
            }
        return result

    def _should_check_leave_reason(self, vals):
        if not vals:
            return False
        # Public-holiday create/write re-evaluates overlapping hr.leave rows via
        # sudo().write({'state': 'confirm'}) — not a user submit action.
        if self.env.su and set(vals.keys()) <= {"state"}:
            return False
        if self.env.context.get("skip_handover_constraints_on_leave_sync"):
            return False
        tracked = {
            "name",
            "private_name",
            "state",
            "holiday_status_id",
            "request_date_from",
            "request_date_to",
            "request_unit_half",
            "request_unit_hours",
            "handover_acceptance_ids",
            "skip_work_handover",
            "attachment_ids",
            "supported_attachment_ids",
        }
        return bool(tracked & set(vals))

    @api.constrains("state", "attachment_ids")
    def _check_leave_form_attachment_required(self):
        if (
            self.env.context.get("import_file")
            or self.env.context.get("skip_handover_constraints_on_leave_sync")
        ):
            return
        self._validate_leave_form_attachment_required()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self.env.context.get("import_file"):
            return records
        if not self.env.context.get("leave_fast_create"):
            records._ensure_leave_reason_persisted(vals_list)
            records._validate_leave_reason_required(vals_list)
        records._validate_leave_form_attachment_required(vals_list)
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self._should_check_leave_reason(vals):
            return res
        if self.env.context.get("import_file"):
            return res
        vals_list = [vals] * len(self)
        if not self.env.context.get("leave_fast_create"):
            self._ensure_leave_reason_persisted(vals_list)
            self._validate_leave_reason_required(vals_list)
        self._validate_leave_form_attachment_required(vals_list)
        return res
