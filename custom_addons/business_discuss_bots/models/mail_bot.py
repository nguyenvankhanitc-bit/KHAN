import re
import unicodedata
import logging

from markupsafe import Markup

from odoo import models, _
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)


class MailBot(models.AbstractModel):
    _inherit = "mail.bot"

    _BUSINESS_BOT_PARTNER_XMLID_TO_SKILL = {
        "business_discuss_bots.partner_bot_approval": "approval",
        "business_discuss_bots.partner_bot_handover": "handover",
        "business_discuss_bots.partner_bot_gate_ticket": "gate_ticket",
    }
    _APPROVAL_SUPPORTED_INTENTS = {"approval_status", "approval_who", "pending_approval_detail", "help"}
    _HANDOVER_SUPPORTED_INTENTS = {
        "handover_status",
        "handover_accepted",
        "handover_pending",
        "handover_refused",
        "help",
    }
    _GATE_TICKET_SUPPORTED_INTENTS = {"approval_status", "approval_who", "help"}

    def _get_answer(self, channel, body, values, command=False):
        answer = self._business_bot_route(channel, body, values, command)
        if answer:
            return answer
        return super()._get_answer(channel, body, values, command=command)

    def _apply_logic(self, channel, values, command=None):
        """Post answers as the correct bot identity in DM channels."""
        channel.ensure_one()
        if self.env.context.get("business_bot_skip_apply_logic"):
            return
        default_author_id = self.env["ir.model.data"]._xmlid_to_res_id("base.partner_root")
        if values.get("author_id") in self._business_bot_author_ids() | {default_author_id} or (
            values.get("message_type") != "comment" and not command
        ):
            return
        raw_body = values.get("body", "")
        body = html2plaintext(raw_body or "").replace("\xa0", " ").strip().lower().strip(".!")
        _logger.info(
            "business_discuss_bots: _apply_logic channel_id=%s author_id=%s message_type=%s body=%r command=%s",
            channel.id,
            values.get("author_id"),
            values.get("message_type"),
            body[:200],
            command,
        )
        answer = self._get_answer(channel, body, values, command)
        if not answer:
            _logger.info("business_discuss_bots: no answer for channel_id=%s body=%r", channel.id, body[:200])
            return
        author_id = self._business_bot_author_id(channel) or default_author_id
        answers = answer if isinstance(answer, list) else [answer]
        _logger.info(
            "business_discuss_bots: posting %s answer(s) channel_id=%s author_id=%s",
            len(answers),
            channel.id,
            author_id,
        )
        for ans in answers:
            channel.with_context(business_bot_skip_apply_logic=True).sudo().message_post(
                author_id=author_id,
                body=Markup(ans) if not isinstance(ans, Markup) else ans,
                message_type="comment",
                silent=True,
                subtype_xmlid="mail.mt_comment",
            )

    def _business_bot_route(self, channel, body, values, command=False):
        if command or channel.channel_type != "chat":
            _logger.info(
                "business_discuss_bots: route skipped channel_id=%s command=%s channel_type=%s",
                channel.id,
                command,
                channel.channel_type,
            )
            return False
        skill_key = self._business_bot_skill_key(channel)
        if not skill_key:
            _logger.info("business_discuss_bots: no skill key for channel_id=%s", channel.id)
            return False
        if "hr.leave" not in self.env:
            return _("Bot chưa truy cập được dữ liệu Time Off trên hệ thống hiện tại.")
        intent = self._classify_intent(body)
        if intent in ("daily_tasks", "pending_approval_detail"):
            if intent == "daily_tasks":
                return self._run_secretary_daily_tasks_skill()
            return self._run_pending_approval_detail_skill()
        if skill_key == "main":
            _logger.info("business_discuss_bots: route channel_id=%s skill=main", channel.id)
            return self._run_main_router_skill(body)
        _logger.info("business_discuss_bots: route channel_id=%s skill=%s intent=%s", channel.id, skill_key, intent)
        if skill_key == "approval":
            if intent not in self._APPROVAL_SUPPORTED_INTENTS:
                return self._redirect_to_main_bot_message(_("duyệt đơn nghỉ phép"))
            return self._run_approval_skill(intent)
        if skill_key == "handover":
            if intent not in self._HANDOVER_SUPPORTED_INTENTS:
                return self._redirect_to_main_bot_message(_("bàn giao công việc"))
            return self._run_handover_skill(intent)
        if skill_key == "gate_ticket":
            if intent not in self._GATE_TICKET_SUPPORTED_INTENTS:
                return self._redirect_to_main_bot_message(_("duyệt đơn ra cổng"))
            return self._run_gate_ticket_skill(intent, body)
        return False

    def _business_bot_skill_key(self, channel):
        partners = channel.sudo().channel_member_ids.partner_id
        main_bot_partner = self.env.ref("base.partner_root", raise_if_not_found=False)
        if main_bot_partner and main_bot_partner in partners:
            return "main"
        for xmlid, skill_key in self._BUSINESS_BOT_PARTNER_XMLID_TO_SKILL.items():
            partner = self.env.ref(xmlid, raise_if_not_found=False)
            if partner and partner in partners:
                return skill_key
        return False

    _SECRETARY_CLEAN_INTENTS = frozenset({"daily_tasks", "pending_approval_detail"})
    _HANDOVER_INTENTS = frozenset({
        "handover_status",
        "handover_accepted",
        "handover_pending",
        "handover_refused",
    })

    def _run_main_router_skill(self, body):
        normalized = self._normalize_text(body)
        if not normalized:
            return False
        intent = self._classify_intent(body)
        if intent in self._SECRETARY_CLEAN_INTENTS:
            if intent == "daily_tasks":
                return self._run_secretary_daily_tasks_skill()
            return self._run_pending_approval_detail_skill()
        hr_tokens = (
            "time off",
            "xin nghi",
            "xin phep",
            "nghi phep",
            "don nghi",
            "duyet",
            "ban giao",
            "handover",
            "leave",
            "vacation",
            "pto",
        )
        hr_related = intent in {
            "approval_status",
            "approval_who",
            "pending_approval_detail",
            "latest_leave",
            "handover_status",
            "handover_accepted",
            "handover_pending",
            "handover_refused",
        } or (intent == "help" and any(token in normalized for token in hr_tokens)) or any(
            token in normalized for token in hr_tokens
        )
        if not hr_related:
            return False

        odoobot_state = self.env.user.odoobot_state
        in_onboarding = bool(odoobot_state and odoobot_state not in ("idle", "not_initialized", False))
        onboarding_note = ""
        if in_onboarding:
            onboarding_note = _(
                "<i>(Bạn đang trong tour OdooBot; mình vẫn trả lời phần Time Off bên dưới. "
                "Để hỏi chi tiết bước duyệt, hãy mở chat OdooBot Duyệt đơn.)</i><br/><br/>"
            )

        core = False
        if intent in self._HANDOVER_INTENTS:
            if "ban giao" in normalized or "handover" in normalized:
                core = self._run_handover_skill(intent)
            elif self._is_pending_approval_detail_intent(normalized):
                return self._run_pending_approval_detail_skill()
            else:
                return False
        elif intent in ("latest_leave", "approval_who", "approval_status"):
            core = self.with_context(business_discuss_leave_on_main_bot=True)._run_approval_skill(intent)
        elif intent == "help" and self._is_pending_approval_detail_intent(normalized):
            return self._run_pending_approval_detail_skill()
        elif intent == "help" and any(t in normalized for t in hr_tokens):
            core = self._run_main_help_with_leave_summary()
        elif any(t in normalized for t in hr_tokens):
            if self._is_pending_approval_detail_intent(normalized):
                return self._run_pending_approval_detail_skill()
            core = self._run_approval_skill("latest_leave")
        else:
            core = self._run_main_help_with_leave_summary()

        if not core:
            core = self._run_main_help_with_leave_summary()

        guidance = _(
            "<br/><br/><b>Hỏi chi tiết hơn</b> (chat trực tiếp từng bot):<br/>"
            "• <b>OdooBot Duyệt đơn</b>: đang ở bước duyệt nào, ai đang duyệt<br/>"
            "• <b>OdooBot Bàn giao việc</b>: ai đã chấp nhận / đang chờ / đã từ chối bàn giao"
        )
        return Markup(onboarding_note) + Markup(core) + Markup(guidance)

    def _run_secretary_daily_tasks_skill(self):
        approval_count = self._count_pending_approval_leaves_for_user()
        handover_count = self._count_pending_handover_leaves_for_user()
        if not approval_count and not handover_count:
            return _(
                "Hôm nay bạn không có việc nào đang chờ xử lý.<br/>"
                "Chúc bạn một ngày làm việc hiệu quả!"
            )
        lines = [_("Hôm nay bạn có những việc sau đây đang chờ. Cụ thể là:")]
        if approval_count:
            lines.append(
                _("_ %(count)s đơn nghỉ phép đang cần bạn duyệt")
                % {"count": approval_count}
            )
        if handover_count:
            lines.append(
                _("_ %(count)s đơn bàn giao việc cần bạn xử lý")
                % {"count": handover_count}
            )
        return "<br/>".join(lines)

    def _search_pending_approval_leaves_for_user(self, user=None):
        user = user or self.env.user
        Leave = self.env["hr.leave"].sudo()
        if "approval_actionable_user_ids" not in Leave._fields:
            return Leave.browse()
        return Leave.search(
            [
                ("state", "in", ("confirm", "validate1")),
                ("approval_actionable_user_ids", "in", user.id),
            ],
            order="request_date_from asc, create_date asc, id asc",
        )

    def _count_pending_approval_leaves_for_user(self, user=None):
        return len(self._search_pending_approval_leaves_for_user(user=user))

    def _employee_display_id(self, employee):
        id_hrm = (getattr(employee, "id_hrm", None) or "").strip()
        if id_hrm:
            return id_hrm
        barcode = (employee.barcode or "").strip()
        if barcode:
            return barcode
        return str(employee.id)

    def _leave_date_range_text(self, leave):
        date_from = leave.request_date_from or (leave.date_from and leave.date_from.date())
        date_to = leave.request_date_to or (leave.date_to and leave.date_to.date()) or date_from
        if not date_from:
            return leave.display_name or ""
        from_str = date_from.strftime("%d/%m/%Y")
        if not date_to or date_to == date_from:
            return _("ngày %(date)s") % {"date": from_str}
        return _("ngày %(date_from)s đến ngày %(date_to)s") % {
            "date_from": from_str,
            "date_to": date_to.strftime("%d/%m/%Y"),
        }

    def _format_pending_approval_detail_line(self, leave):
        employee = leave.employee_id
        name = employee.name if employee else _("Không rõ")
        emp_id = self._employee_display_id(employee) if employee else "—"
        title = (employee.job_title or "").strip() if employee else ""
        title = title or _("không rõ")
        date_range = self._leave_date_range_text(leave)
        return _(
            "_ đơn nghỉ phép của <b>%(name)s</b> (ID nhân viên: %(emp_id)s) "
            "với chức danh là %(title)s, xin nghỉ %(date_range)s"
        ) % {
            "name": name,
            "emp_id": emp_id,
            "title": title,
            "date_range": date_range,
        }

    def _run_pending_approval_detail_skill(self):
        leaves = self._search_pending_approval_leaves_for_user()
        if not leaves:
            return _("Hiện bạn không có đơn nghỉ phép nào đang chờ duyệt.")
        count = len(leaves)
        if count == 1:
            header = _("1 đơn nghỉ phép đang chờ bạn duyệt:")
        else:
            header = _("%(count)s đơn nghỉ phép đó lần lượt là:") % {"count": count}
        lines = [header]
        lines.extend(self._format_pending_approval_detail_line(leave) for leave in leaves)
        return "<br/>".join(lines)

    def _count_pending_handover_leaves_for_user(self, user=None):
        user = user or self.env.user
        employee = user.sudo().employee_id
        if not employee:
            return 0
        if "hr.leave.handover.acceptance" not in self.env:
            return 0
        Acceptance = self.env["hr.leave.handover.acceptance"].sudo()
        Leave = self.env["hr.leave"]
        leave_ids = set()
        pending_lines = Acceptance.search(
            [
                ("employee_id", "=", employee.id),
                ("state", "=", "pending"),
                ("leave_id.state", "in", ("confirm",)),
            ]
        )
        for line in pending_lines:
            leave = line.leave_id
            if employee in leave.handover_employee_ids:
                leave_ids.add(leave.id)
        if "handover_escalated" in Leave._fields:
            escalation_leaves = Leave.with_user(user).search(
                [
                    ("state", "in", ("confirm", "validate1")),
                    ("handover_escalated", "=", True),
                    ("handover_escalation_user_id", "=", user.id),
                ]
            )
            for leave in escalation_leaves:
                if leave.handover_escalation_pick_prompt:
                    leave_ids.add(leave.id)
        return len(leave_ids)

    def _run_main_help_with_leave_summary(self):
        employee = self.env.user.employee_id
        if not employee:
            return _("Mình chưa thấy hồ sơ nhân sự gắn với tài khoản của bạn.<br/>")
        leaves = self.env["hr.leave"].sudo().search(
            [("employee_id", "=", employee.id)],
            order="request_date_from desc, create_date desc, id desc",
            limit=5,
        )
        if not leaves:
            return _("Chưa có đơn Time Off nào trên hệ thống cho bạn.<br/>")
        latest = leaves[:1]
        pending = leaves.filtered(lambda l: l.state in ("confirm", "validate1"))[:1]
        lines = [
            _("<b>Tóm tắt Time Off của bạn</b><br/>"),
            self._format_latest_leave_answer(latest),
        ]
        if pending and pending.id != latest.id:
            st = dict(pending._fields["state"].selection).get(pending.state, pending.state)
            lines.append(
                _("<br/>Đơn đang chờ xử lý gần nhất: ngày %(date)s — %(state)s.") % {
                    "date": self._leave_date_text(pending),
                    "state": st,
                }
            )
        lines.append(
            _("<br/><br/>Bạn có thể hỏi mình: đơn nghỉ gần nhất ngày nào, tình trạng đơn, "
              "hoặc mở chat bot chuyên trách như trên.")
        )
        return "<br/>".join(lines)

    def _business_bot_author_id(self, channel):
        partners = channel.channel_member_ids.partner_id
        for xmlid in self._BUSINESS_BOT_PARTNER_XMLID_TO_SKILL:
            partner = self.env.ref(xmlid, raise_if_not_found=False)
            if partner and partner in partners:
                return partner.id
        return False

    def _business_bot_author_ids(self):
        author_ids = set()
        for xmlid in self._BUSINESS_BOT_PARTNER_XMLID_TO_SKILL:
            partner = self.env.ref(xmlid, raise_if_not_found=False)
            if partner:
                author_ids.add(partner.id)
        return author_ids

    def _is_daily_tasks_intent(self, text):
        """Detect secretary-style questions about pending work (flexible Vietnamese/English)."""
        if not text:
            return False
        strong_phrases = (
            "hom nay co viec",
            "hom nay co gi can lam",
            "hom nay co gi can xu ly",
            "hom nay lam gi",
            "hom nay can lam gi",
            "hom nay can xu ly gi",
            "hom nay can duyet gi",
            "co viec gi can lam",
            "co viec gi can xu ly",
            "viec gi can lam",
            "viec gi can xu ly",
            "co gi can lam",
            "co gi can xu ly",
            "nhung viec can lam",
            "nhung viec can xu ly",
            "viec can lam hom nay",
            "viec can xu ly hom nay",
            "cong viec can lam",
            "cong viec can xu ly",
            "can lam gi hom nay",
            "con viec gi can lam",
            "con viec gi can xu ly",
            "viec dang cho",
            "nhung viec dang cho",
            "dang cho toi duyet",
            "dang cho toi xu ly",
            "co don nao can duyet",
            "co don nao can xu ly",
            "bao nhieu don can duyet",
            "bao nhieu don can xu ly",
            "tom tat viec",
            "nhac viec hom nay",
            "what do i need to do",
            "what should i do today",
            "tasks today",
            "pending tasks",
            "to do today",
            "my pending work",
        )
        if any(phrase in text for phrase in strong_phrases):
            return True

        time_words = ("hom nay", "today", "bay gio", "luc nay", "ngay hom nay")
        action_words = (
            "can lam",
            "can xu ly",
            "can duyet",
            "lam gi",
            "xu ly gi",
            "duyet gi",
            "lam gi khong",
            "viec gi",
        )
        has_time = any(word in text for word in time_words)
        has_action = any(word in text for word in action_words)
        if has_time and has_action:
            return True
        if has_time and "co gi" in text and any(
            word in text for word in ("lam", "xu ly", "duyet", "viec", "don")
        ):
            return True
        if ("viec" in text or "cong viec" in text or "don" in text) and has_action:
            return True
        if text.startswith("hom nay") and any(
            word in text for word in ("viec", "lam", "xu ly", "duyet", "don", "gi")
        ):
            return True
        return False

    def _mentions_leave_request(self, text):
        return any(
            token in text
            for token in (
                "don nghi",
                "nghi phep",
                "don xin nghi",
                "xin nghi phep",
                "xin nghi",
                "time off",
                "leave",
            )
        )

    def _is_leave_detail_followup_intent(self, text):
        if not text:
            return False
        if any(marker in text for marker in ("cua toi", "cua minh", "don cua toi", "don cua minh")):
            return False
        if "ban giao" in text or "handover" in text:
            return False
        asks_detail = any(
            word in text
            for word in ("chi tiet", "liet ke", "danh sach", "noi ro", "noi chi tiet", "ke chi tiet")
        )
        return asks_detail and self._mentions_leave_request(text)

    def _is_pending_approval_detail_intent(self, text):
        """Approver asks who submitted leave requests waiting for their approval."""
        if not text:
            return False
        if any(marker in text for marker in ("cua toi", "cua minh", "don cua toi", "don cua minh")):
            return False
        strong_phrases = (
            "don nghi phep can duyet la cua ai",
            "don nghi can duyet la cua ai",
            "don can duyet la cua ai",
            "can duyet la cua ai",
            "ai xin nghi can duyet",
            "ai xin nghi can toi duyet",
            "ai xin nghi cho toi duyet",
            "danh sach don can duyet",
            "danh sach don nghi can duyet",
            "liet ke don can duyet",
            "liet ke don nghi can duyet",
            "chi tiet don can duyet",
            "chi tiet don nghi can duyet",
            "chi tiet don nghi phep",
            "chi tiet don nghi",
            "noi chi tiet don nghi",
            "noi chi tiet don nghi phep",
            "ke chi tiet don nghi",
            "noi ro don nghi",
            "don nao can toi duyet",
            "nhung don can duyet",
            "nhung don nghi can duyet",
            "don nghi phep can duyet la ai",
            "don nghi phep nao can duyet",
            "whose leave needs approval",
            "list pending leave approvals",
        )
        if any(phrase in text for phrase in strong_phrases):
            return True
        if self._is_leave_detail_followup_intent(text):
            return True
        has_leave = self._mentions_leave_request(text)
        needs_approval = any(
            word in text
            for word in ("can duyet", "can toi duyet", "cho duyet", "cho toi duyet", "dang cho duyet")
        )
        asks_detail = any(
            word in text
            for word in (
                "cua ai",
                "la ai",
                "danh sach",
                "chi tiet",
                "liet ke",
                "nhung don",
                "don nao",
                "noi chi tiet",
                "noi ro",
                "ke chi tiet",
            )
        )
        if has_leave and asks_detail and not needs_approval:
            if any(
                phrase in text
                for phrase in (
                    "chi tiet don nghi",
                    "chi tiet don nghi phep",
                    "liet ke don nghi",
                    "danh sach don nghi",
                )
            ):
                return True
        return has_leave and needs_approval and asks_detail

    def _is_handover_pending_intent(self, text):
        if not text:
            return False
        if any(token in text for token in ("pending", "chua phan hoi", "dang doi")):
            return "ban giao" in text or "handover" in text
        return any(
            phrase in text
            for phrase in (
                "dang cho ban giao",
                "dang cho phan hoi ban giao",
                "cho phan hoi ban giao",
                "ban giao dang cho",
                "ban giao chua phan hoi",
            )
        )

    def _classify_intent(self, body):
        text = self._normalize_text(body)
        if not text:
            return "help"
        if self._is_daily_tasks_intent(text):
            return "daily_tasks"
        if self._is_pending_approval_detail_intent(text):
            return "pending_approval_detail"
        if any(token in text for token in ("menu", "help", "giup", "tro giup", "huong dan")):
            return "help"
        if any(token in text for token in ("gan nhat", "ngay nao", "khi nao")):
            return "latest_leave"
        if any(token in text for token in ("ai duyet", "nguoi duyet", "chuc vu")):
            return "approval_who"
        if any(token in text for token in ("accepted", "chap nhan", "dong y")):
            return "handover_accepted"
        if self._is_handover_pending_intent(text):
            return "handover_pending"
        if any(token in text for token in ("refused", "tu choi", "khong nhan")):
            return "handover_refused"
        if any(token in text for token in ("ban giao", "handover")):
            return "handover_status"
        if any(
            token in text
            for token in (
                "step",
                "buoc",
                "trang thai",
                "tinh trang",
                "ket qua",
                "duyet",
                "time off",
                "xin nghi",
                "don",
            )
        ):
            return "approval_status"
        return "help"

    def _run_approval_skill(self, intent):
        employee = self.env.user.employee_id
        if not employee:
            return _("Mình chưa thấy hồ sơ nhân sự gắn với tài khoản của bạn nên chưa kiểm tra được đơn Time Off.")

        leaves = self.env["hr.leave"].sudo().search(
            [("employee_id", "=", employee.id)],
            order="request_date_from desc, create_date desc, id desc",
            limit=10,
        )
        if not leaves:
            return _("Hiện tại mình chưa thấy đơn Time Off nào của bạn.")
        latest = leaves[:1]
        if intent == "help":
            return self._approval_help_message()
        if intent == "pending_approval_detail":
            return self._run_pending_approval_detail_skill()
        if intent == "latest_leave":
            return self._format_latest_leave_answer(latest)

        leave = leaves.filtered(lambda l: l.state in ("confirm", "validate1"))[:1]
        if not leave:
            if self.env.context.get("business_discuss_leave_on_main_bot"):
                latest = leaves[:1]
                state_label = dict(latest._fields["state"].selection).get(latest.state, latest.state)
                return _(
                    "Đơn gần nhất của bạn: ngày %(date)s — trạng thái: %(state)s.<br/>"
                    "Hiện không còn đơn nào đang chờ duyệt (confirm/validate1)."
                ) % {
                    "date": self._leave_date_text(latest),
                    "state": state_label,
                }
            return _(
                "Đơn của bạn hiện không còn ở trạng thái chờ duyệt tại bot này.<br/>"
                "Bạn vui lòng nhắn OdooBot chính để tra cứu kết quả đơn đã duyệt xong "
                "(Approved/Refused/Cancelled)."
            )

        step_label, approver_lines = self._approval_step_and_approvers(leave)
        leave_date = self._leave_date_text(leave)
        if intent == "approval_who":
            if approver_lines:
                return _("Đơn ngày %(date)s đang chờ: %(approvers)s.") % {
                    "date": leave_date,
                    "approvers": ", ".join(approver_lines),
                }
            return _("Đơn ngày %(date)s đang chờ duyệt nhưng chưa xác định được người duyệt hiện tại.") % {
                "date": leave_date
            }
        response_lines = [
            _("Đơn Time Off ngày %(date)s của bạn hiện đang ở: %(step)s.") % {
                "date": leave_date,
                "step": step_label,
            }
        ]
        if approver_lines:
            response_lines.append(_("Người đang duyệt: %(approvers)s.") % {"approvers": ", ".join(approver_lines)})
        return "<br/>".join(response_lines)

    def _run_handover_skill(self, intent):
        employee = self.env.user.employee_id
        if not employee:
            return _("Mình chưa thấy hồ sơ nhân sự gắn với tài khoản của bạn nên chưa kiểm tra được bàn giao công việc.")
        if intent == "help":
            return self._handover_help_message()
        leave = self.env["hr.leave"].sudo().search(
            [
                ("employee_id", "=", employee.id),
                ("handover_employee_ids", "!=", False),
            ],
            order="request_date_from desc, create_date desc, id desc",
            limit=1,
        )
        if not leave:
            return _("Hiện tại bạn chưa có đơn Time Off nào có bàn giao công việc.")
        accepted, pending, refused = self._handover_groups(leave)
        date_text = self._leave_date_text(leave)
        if intent == "handover_accepted":
            return _("Đơn ngày %(date)s, đã chấp nhận bàn giao: %(names)s.") % {
                "date": date_text,
                "names": self._join_or_none(accepted),
            }
        if intent == "handover_pending":
            return _("Đơn ngày %(date)s, đang chờ phản hồi bàn giao: %(names)s.") % {
                "date": date_text,
                "names": self._join_or_none(pending),
            }
        if intent == "handover_refused":
            return _("Đơn ngày %(date)s, đã từ chối bàn giao: %(names)s.") % {
                "date": date_text,
                "names": self._join_or_none(refused),
            }
        return _(
            "Trạng thái bàn giao của đơn ngày %(date)s:<br/>"
            "Đã chấp nhận: %(accepted)s<br/>"
            "Đang chờ: %(pending)s<br/>"
            "Đã từ chối: %(refused)s"
        ) % {
            "date": date_text,
            "accepted": self._join_or_none(accepted),
            "pending": self._join_or_none(pending),
            "refused": self._join_or_none(refused),
        }

    def _run_gate_ticket_skill(self, intent, body):
        employee = self.env.user.employee_id
        if not employee:
            return _("Mình chưa thấy hồ sơ nhân sự gắn với tài khoản của bạn nên chưa kiểm tra được đơn ra cổng.")
        if "hr.employee.gate.ticket" not in self.env:
            return _("Chưa tìm thấy dữ liệu đơn ra cổng trên hệ thống hiện tại.")

        gate_ticket_model = self.env["hr.employee.gate.ticket"].sudo()
        ticket_code = self._extract_gate_ticket_code(body)
        ticket = False
        if ticket_code:
            ticket = gate_ticket_model.search(
                [("employee_id", "=", employee.id), ("name", "=", ticket_code)],
                limit=1,
            )
            if not ticket:
                return _("Mình không tìm thấy đơn ra cổng mã %(ticket)s của bạn.") % {"ticket": ticket_code}
        else:
            ticket = gate_ticket_model.search(
                [("employee_id", "=", employee.id)],
                order="check_in desc, create_date desc, id desc",
                limit=1,
            )
            if not ticket:
                return _("Hiện tại bạn chưa có đơn ra cổng nào.")

        state_labels = dict(ticket._fields["state"].selection)
        state_label = state_labels.get(ticket.state, ticket.state)
        approver = self._gate_ticket_current_approver(ticket)
        ticket_date = ticket.check_in and ticket.check_in.strftime("%d/%m/%Y %H:%M") or "-"
        ticket_link = "/web#id=%s&model=hr.employee.gate.ticket&view_type=form" % ticket.id

        if intent == "approval_who":
            if approver:
                return _(
                    "Đơn ra cổng <b>%(ticket)s</b> đang chờ: <b>%(approver)s</b>.<br/>"
                    "Mở đơn: <a href='%(url)s'>%(url)s</a>"
                ) % {
                    "ticket": ticket.name,
                    "approver": approver.name,
                    "url": ticket_link,
                }
            return _(
                "Đơn ra cổng <b>%(ticket)s</b> hiện ở trạng thái <b>%(state)s</b> (không còn người duyệt hiện tại).<br/>"
                "Mở đơn: <a href='%(url)s'>%(url)s</a>"
            ) % {
                "ticket": ticket.name,
                "state": state_label,
                "url": ticket_link,
            }

        result = _(
            "Đơn ra cổng <b>%(ticket)s</b> (%(date)s) hiện ở trạng thái: <b>%(state)s</b>."
        ) % {
            "ticket": ticket.name,
            "date": ticket_date,
            "state": state_label,
        }
        if approver:
            result += _("<br/>Người đang duyệt: <b>%(approver)s</b>.") % {"approver": approver.name}
        result += _("<br/>Mở đơn: <a href='%(url)s'>%(url)s</a>") % {"url": ticket_link}
        return result

    def _approval_step_and_approvers(self, leave):
        if hasattr(leave, "_bot_status_current_step_details"):
            return leave._bot_status_current_step_details()
        step_label = leave.approval_current_step_label or _("Đang chờ duyệt")
        return step_label, []

    def _handover_groups(self, leave):
        active_recipients = leave.handover_employee_ids
        accepted = []
        pending = []
        refused = []
        for recipient in active_recipients:
            line = leave.handover_acceptance_ids.filtered(lambda l: l.employee_id == recipient)[:1]
            label = self._employee_with_title(recipient)
            if not line or line.state == "pending":
                pending.append(label)
            elif line.state == "accepted":
                accepted.append(label)
            elif line.state == "refused":
                refused.append(label)
        return accepted, pending, refused

    def _employee_with_title(self, employee):
        title = (employee.job_title or "").strip()
        if title:
            return "%s (%s)" % (employee.name, title)
        return employee.name

    def _format_latest_leave_answer(self, leave):
        state_label = dict(leave._fields["state"].selection).get(leave.state, leave.state)
        return _("Đơn Time Off gần nhất của bạn là ngày %(date)s (trạng thái: %(state)s).") % {
            "date": self._leave_date_text(leave),
            "state": state_label,
        }

    def _leave_date_text(self, leave):
        leave_date = leave.request_date_from or (leave.date_from and leave.date_from.date())
        return leave_date.strftime("%d/%m/%Y") if leave_date else (leave.display_name or "")

    def _join_or_none(self, values):
        return ", ".join(values) if values else _("Không có")

    def _approval_help_message(self):
        return _(
            "Bạn có thể hỏi mình:<br/>"
            "1) Đơn đang ở bước nào<br/>"
            "2) Ai đang duyệt đơn<br/>"
            "3) Đơn nghỉ phép cần duyệt là của ai (chi tiết từng đơn)"
        )

    def _handover_help_message(self):
        return _(
            "Bạn có thể hỏi mình:<br/>"
            "1) Ai đã chấp nhận bàn giao<br/>"
            "2) Ai đang chờ phản hồi bàn giao<br/>"
            "3) Ai đã từ chối bàn giao<br/>"
            "4) Trạng thái bàn giao hiện tại"
        )

    def _redirect_to_main_bot_message(self, task_name):
        return _(
            "Mình chỉ hỗ trợ tác vụ %(task)s.<br/>"
            "Câu hỏi này chưa thuộc phạm vi của mình, bạn vui lòng nhắn qua OdooBot chính để được hỗ trợ thêm."
        ) % {"task": task_name}

    def _normalize_text(self, text):
        normalized = (text or "").strip().lower()
        normalized = normalized.replace("đ", "d").replace("Đ", "d")
        normalized = unicodedata.normalize("NFKD", normalized)
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized

    def _extract_gate_ticket_code(self, body):
        match = re.search(r"\bGT\d+\b", (body or "").upper())
        return match.group(0) if match else False

    def _gate_ticket_current_approver(self, ticket):
        if ticket.state == "confirm":
            return ticket.approver_id
        if ticket.state == "second_approve":
            return ticket.second_approver_id
        if ticket.state == "third_approve":
            return ticket.third_approver_id
        return False
