from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Bỏ các dòng khắc phục tự tạo cho tiêu chí không có lỗi ghi nhận (chỉ bị trừ điểm) và chưa ai nhập gì."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    stray = env['store.audit.action'].search([
        ('line_id.error_count', '=', 0), ('state', '=', 'todo'),
        ('action_plan', '=', False), ('root_cause', '=', False), ('date_done', '=', False),
        ('reviewer_id', '=', False), ('responsible_ids', '=', False), ('control_done', '=', False),
    ])
    stray.unlink()
