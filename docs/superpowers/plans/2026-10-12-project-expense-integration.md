# Implementation Plan: Tích hợp "Chi phí" (hr_expense) vào Dự án (lug_project)

## 1. Mục tiêu
Thêm cột "Chi phí" vào dự án (`project.project`), lấy dữ liệu tổng hợp từ phân hệ Chi phí (`hr_expense`) chuẩn của Odoo:
- Tính tổng chi phí của các phiếu có trạng thái hợp lệ: `approved`, `posted`, `in_payment`, `paid`.
- Thêm trường `project_id` trên `hr.expense` để liên kết chi phí trực tiếp với dự án.
- Hiển thị cột "Chi phí" trên danh sách dự án (tree/list view), smart button trên form dự án, và tích hợp vào dashboard/xuất Excel.

---

## 2. Các bước thực hiện

### Task 1: Khai báo phụ thuộc và mở rộng `hr.expense`
- [ ] Thêm `"hr_expense"` vào `depends` trong `lug_project/__manifest__.py`.
- [ ] Tạo file `lug_project/models/hr_expense.py`:
  - Kế thừa `hr.expense`.
  - Bổ sung trường `project_id = fields.Many2one("project.project", string="Dự án", index=True, tracking=True)`.
  - Tự động gán `analytic_distribution` theo `project_id.account_id` nếu có.
- [ ] Import `hr_expense` trong `lug_project/models/__init__.py`.
- [ ] Tạo file `lug_project/views/hr_expense_views.xml`:
  - Kế thừa `hr_expense.hr_expense_view_form` để thêm trường `project_id`.
  - Thêm `views/hr_expense_views.xml` vào `data` trong `lug_project/__manifest__.py`.

### Task 2: Mở rộng `project.project` tính toán "Chi phí"
- [ ] Trong `lug_project/models/project_project.py`:
  - Khai báo quan hệ `lug_expense_ids = fields.One2many("hr.expense", "project_id", string="Chi phí liên quan")`.
  - Khai báo trường tính toán `lug_total_expense = fields.Monetary(string="Chi phí", currency_field="currency_id", compute="_compute_lug_total_expense", store=True)`.
  - Khai báo trường `lug_expense_count = fields.Integer(string="Số phiếu chi phí", compute="_compute_lug_total_expense")`.
  - Viết logic `_compute_lug_total_expense`: lọc chi phí có `state in ('approved', 'posted', 'in_payment', 'paid')` và cộng `total_amount`.
  - Viết method `action_view_lug_expenses`: mở danh sách chi phí của dự án.

### Task 3: Cập nhật giao diện (Views) & Xuất Excel
- [ ] Trong `lug_project/views/project_project_views.xml`:
  - Thêm cột `<field name="lug_total_expense" string="Chi phí" widget="monetary" optional="show"/>` vào danh sách dự án `view_project_lug`.
  - Thêm Smart Button trong `div.oe_button_box` trên form `view_project_intake_form`.
- [ ] Trong `lug_project/models/project_dashboard.py`:
  - Cập nhật `_lug_serialize_project_row` để trả về `total_expense`.
  - Cập nhật `export_lug_project_list_xlsx` thêm cột "Chi phí".

### Task 4: Viết Unit Tests & Xác minh
- [ ] Tạo file test `tests/test_project_expense.py`:
  - Kiểm tra tính toán `lug_total_expense` chỉ tính các trạng thái `approved`, `posted`, `in_payment`, `paid`.
  - Kiểm tra bỏ qua `draft`, `refused`.
  - Kiểm tra `action_view_lug_expenses`.
- [ ] Chạy `python3 -m unittest discover tests`.
- [ ] Kiểm tra cú pháp Python (`py_compile`) và XML toàn bộ module.
