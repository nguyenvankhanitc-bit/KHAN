# -*- coding: utf-8 -*-
"""Checklist công việc ASM: giống hệt Checklist công việc CHT (kế thừa store.cht.*), khác ở:
- danh mục công việc / nhóm nghiệp vụ riêng (store.asm.task / store.asm.task.group);
- người tick check list là ASM (cấp 3), người đánh giá là RSM trở lên (cấp >= 4) hoặc chức danh văn phòng;
- quyền theo mục "Checklist NVBH › Checklist CV ASM" và "Danh sách công việc ASM".
"""
from odoo import api, fields, models

from .store_cht import CHT_WEEKDAYS

ASM_GROUPS = [
    '01 – Nhân sự và đào tạo',
    '02 – Vận hành cửa hàng',
    '03 – Tài sản, thiết bị và CCDC',
    '04 – Marketing',
    '05 – Hàng hóa và tồn kho',
    '06 – POSM',
    '07 – Tài chính và doanh thu',
    '08 – Chi phí',
]

# 30 công việc ASM mặc định: (nội dung, số nhóm 1..8). Tần suất mặc định hằng ngày T2 - CN, chỉnh lại trong danh mục.
ASM_DEFAULT_TASKS = [
    ('Đánh giá, sàng lọc nhân sự có khả năng thăng tiến để đào tạo đội ngũ kế thừa; tuyển dụng nhân sự thay thế', 1),
    ('Theo dõi chi phí quầy, số lượng vật tư sử dụng tại cửa hàng/trung tâm; theo dõi chỉ số điện, nước', 8),
    ('Kiểm tra thực hiện chương trình khuyến mãi thúc đẩy target các cửa hàng/trung tâm', 4),
    ('Kiểm tra và hướng dẫn trưng bày, sắp xếp, bảo quản, vệ sinh bảng sale, hàng hóa, tem giá theo guideline', 6),
    ('Kiểm soát chi phí theo doanh thu/target cửa hàng và nhân viên', 8),
    ('Cập nhật thông tin đối thủ cạnh tranh theo ngành hàng: hình ảnh, hàng hóa, giá cả, khu vực trưng bày, thời gian chạy, '
     'địa điểm, tính năng sản phẩm, doanh thu', 4),
    ('Kiểm soát lưu trữ sổ sách, giấy tờ, chứng từ, giấy phép kinh doanh và giấy phép PCCC', 2),
    ('Kiểm tra ca làm việc, tác phong nhân viên', 1),
    ('Sắp lịch ca, phân bổ nhân sự theo từng khu vực', 1),
    ('Xử lý khiếu nại, đổi trả sản phẩm', 2),
    ('Vệ sinh cửa hàng: quét nhà, lau sàn, cửa kính', 2),
    ('Vệ sinh hàng hóa', 5),
    ('Vệ sinh CCDC, quầy kệ', 3),
    ('Vệ sinh, sắp xếp kho', 5),
    ('Kiểm tra tắt thiết bị khi về, khóa/niêm phong cửa hàng', 2),
    ('Kiểm tra số lượng thực tế và dữ liệu trên Drive', 5),
    ('Kiểm tra thẻ kho, sổ theo dõi nhập xuất tồn trên Drive', 5),
    ('Kiểm tra bàn giao ca trên sổ theo khu vực', 2),
    ('Kiểm tra báo cáo thiết bị/tài sản hư hỏng, mất', 3),
    ('Kiểm tra trưng bày, sắp xếp, bảng sale, hàng hóa, tem giá', 6),
    ('Kiểm tra báo cáo doanh thu, sổ sách, bill BLK, tem tag, chứng từ', 7),
    ('Kiểm tra email, phản hồi thông tin đúng thời gian', 2),
    ('Kiểm tra đăng bài Facebook/Google Business', 4),
    ('Kiểm tra báo cáo hình ảnh trưng bày chương trình khuyến mãi, bảng sale', 6),
    ('Đối chiếu công nợ và chứng từ gửi về công ty', 7),
    ('Kiểm tra báo cáo số lượng, hình ảnh, tình trạng hàng hóa hư hỏng', 5),
    ('Kiểm tra đối chiếu, giải trình số lượng tồn kho', 5),
    ('Kiểm tra mặt hàng/châm hàng/CCDC', 5),
    ('Kiểm tra đặt văn phòng phẩm/đồng phục', 8),
    ('Kiểm tra ký biên bản tự kiểm tra PCCC cửa hàng', 2),
]


class StoreAsmTaskGroup(models.Model):
    _name = 'store.asm.task.group'
    _inherit = 'store.cht.task.group'
    _description = 'Nhóm công việc ASM'

    _perm_menu = 'asm_task'
    _form_view_xmlid = 'store_checklist.view_store_asm_task_group_form'
    _default_group_labels = ASM_GROUPS


class StoreAsmTask(models.Model):
    _name = 'store.asm.task'
    _inherit = 'store.cht.task'
    _description = 'Công việc checklist ASM'

    _perm_menu = 'asm_task'
    _group_model = 'store.asm.task.group'
    _popup_title = 'Công việc ASM'
    _list_label = 'Danh sách công việc ASM'
    _xls_file = 'Cong_viec_ASM'

    group_id = fields.Many2one('store.asm.task.group', string='Nhóm công việc', ondelete='restrict', index=True)
    executor = fields.Char(string='Người thực hiện', default='ASM')
    controller = fields.Char(string='Người kiểm soát', default='RSM')
    admin_user_ids = fields.Many2many('res.users', 'store_asm_task_admin_user_rel', 'task_id', 'user_id', string='Admin',
                                      help='Các user Admin phúc tra cuối công việc này')
    related_user_ids = fields.Many2many('res.users', 'store_asm_task_related_user_rel', 'task_id', 'user_id', string='BP liên quan',
                                        help='Các user thuộc bộ phận liên quan đến công việc này')

    @api.model
    def _seed_default_tasks(self):
        """Tạo danh mục 30 công việc ASM mặc định (chỉ khi danh mục đang trống)."""
        if self.sudo().with_context(active_test=False).search_count([]):
            return
        Group = self.env[self._group_model].sudo()
        Group._ensure_default_groups()
        groups = {g.name: g.id for g in Group.search([])}
        vals_list = []
        for i, (name, gno) in enumerate(ASM_DEFAULT_TASKS, 1):
            vals = {'sequence': i, 'name': name, 'group_id': groups.get(ASM_GROUPS[gno - 1]), 'frequency': 'day',
                    'executor': 'ASM', 'controller': 'RSM', 'score': 2}
            vals.update({f: True for f, _l, _i in CHT_WEEKDAYS})
            vals_list.append(vals)
        self.sudo().create(vals_list)

    # các bước chuyển dữ liệu cũ chỉ dành cho danh mục CHT
    @api.model
    def _apply_cht_groups(self):
        return

    @api.model
    def _sync_group_ids(self):
        return

    @api.model
    def _fill_default_groups(self):
        return


class StoreAsmCheck(models.Model):
    _name = 'store.asm.check'
    _inherit = 'store.cht.check'
    _description = 'Phiếu checklist công việc ASM'

    _task_model = 'store.asm.task'
    _line_model = 'store.asm.check.line'
    _rights_key = 'nvbh_asmcv'
    _tick_level = 3        # ASM tick check list
    _eval_min_level = 4    # RSM trở lên đánh giá
    _prefix = 'ASM'
    _menu_label = 'Checklist CV ASM'

    line_ids = fields.One2many('store.asm.check.line', 'check_id', string='Công việc')


class StoreAsmCheckLine(models.Model):
    _name = 'store.asm.check.line'
    _inherit = 'store.cht.check.line'
    _description = 'Dòng checklist công việc ASM'

    check_id = fields.Many2one('store.asm.check', required=True, ondelete='cascade', index=True)
    task_id = fields.Many2one('store.asm.task', string='Công việc', ondelete='set null', index=True)
    group_id = fields.Many2one('store.asm.task.group', string='Nhóm công việc', ondelete='set null')
