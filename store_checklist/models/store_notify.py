"""Thông báo OdooBot (Discuss) cho Checklist Audit: mẫu giống tin "Công việc đã hoàn thành" của module giao việc."""
import logging

from markupsafe import Markup, escape

from odoo import fields

_logger = logging.getLogger(__name__)

SHELL_URL = '/odoo/action-store_checklist.action_store_shell'


def card(title, rows, label='Xem chi tiết'):
    """Thẻ tin nhắn: tiêu đề đậm, các dòng "Nhãn: giá trị" và nút Xem chi tiết (dẫn tới ứng dụng Checklist Audit)."""
    body = Markup('<b>%s</b><br/>') % title
    for key, value in rows:
        body += Markup('%s: <b>%s</b><br/>') % (key, value or '—')
    return body + Markup(
        '<a href="%s" target="_self" style="display:inline-block;margin-top:10px;padding:8px 18px;'
        'background-color:#714B67;cursor:pointer;color:#ffffff;border-radius:6px;text-decoration:none;'
        'font-weight:600;font-size:14px;line-height:1.2;">%s</a>') % (SHELL_URL, label)


def bot_send(env, users, body):
    """Gửi tin Discuss từ OdooBot tới từng user (lỗi gửi không làm hỏng thao tác lưu)."""
    bot = env.ref('base.user_root', raise_if_not_found=False)
    if not bot or not bot.partner_id:
        return
    for user in users:
        if not user.active or user.share or not user.partner_id:
            continue
        try:
            with env.cr.savepoint():
                chat = env['discuss.channel'].sudo().with_user(user)._get_or_create_chat([bot.partner_id.id], pin=True)
                member = chat.sudo().channel_member_ids.filtered(lambda m: m.partner_id == user.partner_id)[:1]
                if member:
                    member.write({'unpin_dt': False, 'last_interest_dt': fields.Datetime.now()})
                chat.with_user(bot).sudo().message_post(
                    body=body, message_type='comment', subtype_xmlid='mail.mt_comment', author_id=bot.partner_id.id)
                chat.sudo()._broadcast(user.partner_id.ids)
        except Exception:
            _logger.exception('store_checklist: gửi thông báo OdooBot cho user %s thất bại', user.id)
