# Kế hoạch Triển khai: Đồng bộ 1 chiều từ Dự án (lug_project) sang Công việc hàng ngày (daily_work_task)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Khi tạo hoặc cập nhật công việc trong dự án (`lug_project`), bắt buộc chọn Người phụ trách và đồng bộ 1 chiều tự động tạo/cập nhật `daily.task` cho **tất cả** người phụ trách trong phân hệ "Công việc hàng ngày" (`daily_work_task`).

**Architecture:**
- **Chiều đồng bộ:** 1 chiều duy nhất (`lug_project` -> `daily_work_task`). Thay đổi từ `daily.task` không ghi ngược về dự án.
- **`project.stage.task`:**
  - Bắt buộc `user_ids` (ràng buộc validation Python + UI XML `required="1"`).
  - Khai báo trường liên kết `daily_task_ids = fields.One2many("daily.task", "lug_origin_stage_task_id")`.
  - Triển khai hàm `_lug_sync_to_daily()`: Duyệt qua từng user trong `user_ids`, tạo/cập nhật `daily.task` tương ứng với tiêu đề `[Tên dự án] Tên công việc`, ngày giao `execution_date`, deadline, trạng thái, người giao PM.
  - Xóa/hủy `daily.task` tương ứng nếu user bị gỡ khỏi `user_ids` hoặc khi task giai đoạn bị xóa.
- **`project.task`:**
  - Bắt buộc có người phụ trách (`lug_pic_id` hoặc `user_ids`).
  - Nâng cấp `_lug_sync_to_todo_and_daily()`: Đồng bộ `daily.task` cho toàn bộ user trong `user_ids` (thay vì chỉ 1 user), đồng thời truyền `assign_date = lug_execution_date`.
- **`daily.task` (`lug_project/models/daily_task.py`):**
  - Khai báo `lug_origin_stage_task_id = fields.Many2one("project.stage.task", ondelete="set null", copy=False, index=True)`.
  - Đảm bảo `write` trên `daily.task` KHÔNG ghi ngược về `project.stage.task` (tuân thủ nguyên tắc 1 chiều).

**Tech Stack:** Odoo 19, Python ORM, XML Views.

---

## Global Constraints
- Đồng bộ 1 chiều nghiêm ngặt: Dự án ➔ Công việc hàng ngày.
- Bắt buộc phải có Người phụ trách khi tạo/lưu công việc dự án.
- Gán đúng `daily.task` riêng biệt cho từng người trong danh sách người phụ trách (`user_ids`).
- Sử dụng `execution_date` / `lug_execution_date` làm `assign_date` (ngày thực hiện) trên `daily.task`.

---

### Task 1: Bổ sung liên kết và đồng bộ 1 chiều trên `project.stage.task`

**Files:**
- Modify: `lug_project/models/project_stage_task.py`
- Modify: `lug_project/models/daily_task.py`
- Modify: `lug_project/views/project_stage_line_views.xml`

- [ ] **Step 1: Khai báo `lug_origin_stage_task_id` trong `lug_project/models/daily_task.py`**
  Thêm trường `lug_origin_stage_task_id = fields.Many2one("project.stage.task", string="Công việc giai đoạn gốc", ondelete="set null", copy=False, index=True)`.
- [ ] **Step 2: Cập nhật `project.stage.task` với validation bắt buộc và hàm đồng bộ**
  - Thêm `daily_task_ids = fields.One2many("daily.task", "lug_origin_stage_task_id", string="Công việc hàng ngày liên kết")`.
  - Thêm constraint `@api.constrains("user_ids")`: Yêu cầu ít nhất 1 người phụ trách.
  - Viết `_lug_get_or_create_daily_employee(user)` và `_lug_sync_to_daily()`.
  - Override `create`, `write`, `unlink` để kích hoạt `_lug_sync_to_daily()`.
- [ ] **Step 3: Cập nhật XML views cho `project.stage.task`**
  - Gắn `required="1"` cho `user_ids` trong popup `view_project_stage_task_popup_form`.
  - Gắn `required="1"` cho `user_ids` trong list `view_project_stage_task_list` và `view_project_stage_line_form`.
- [ ] **Step 4: Kiểm tra cú pháp Python và XML**
  Run:
  ```bash
  python3 -m py_compile lug_project/models/project_stage_task.py lug_project/models/daily_task.py
  python3 -c "import xml.etree.ElementTree as ET; ET.parse('lug_project/views/project_stage_line_views.xml')"
  ```
  Expected: PASS không có lỗi.

---

### Task 2: Cập nhật validation và đồng bộ đa user trên `project.task`

**Files:**
- Modify: `lug_project/models/project_task.py`
- Modify: `lug_project/views/project_stage_views.xml`

- [ ] **Step 1: Cập nhật validation và đồng bộ `project.task`**
  - Thêm constraint `@api.constrains("lug_pic_id", "user_ids")`: Nếu công việc thuộc dự án thì bắt buộc có người phụ trách.
  - Cập nhật `_lug_sync_to_todo_and_daily()`: Duyệt qua tất cả user trong `task.user_ids` (hoặc `task.lug_pic_id`) để tạo/cập nhật `daily.task` cho từng người.
  - Cập nhật `assign_date = task.lug_execution_date or fields.Date.context_today(task)`.
  - Thêm `lug_execution_date` vào `sync_fields` trong `write()`.
- [ ] **Step 2: Cập nhật XML views cho `project.task`**
  - Đặt `required="1"` cho trường phụ trách trong `view_lug_stage_task_form` và `view_lug_project_stage_form`.
- [ ] **Step 3: Kiểm tra cú pháp Python và XML**
  Run:
  ```bash
  python3 -m py_compile lug_project/models/project_task.py
  python3 -c "import xml.etree.ElementTree as ET; ET.parse('lug_project/views/project_stage_views.xml')"
  ```
  Expected: PASS không có lỗi.

---

### Task 3: Viết Unit Tests & Xác minh Toàn diện

**Files:**
- Modify/Create: `tests/test_sync_duan_to_daily.py`

- [ ] **Step 1: Viết unit tests kiểm tra đồng bộ 1 chiều từ dự án sang công việc hàng ngày**
  - Test validation bắt buộc `user_ids`.
  - Test tạo `project.stage.task` với 2 users -> sinh ra 2 `daily.task` cho 2 users.
  - Test mapping `execution_date` -> `assign_date`, `deadline` -> `deadline`.
  - Test 1-way: cập nhật `daily.task` không thay đổi `project.stage.task`.
  - Test unlink `project.stage.task` dọn dẹp các `daily.task`.
- [ ] **Step 2: Chạy toàn bộ test suite**
  Run:
  ```bash
  python3 -m unittest discover tests
  ```
  Expected: All tests PASS.
- [ ] **Step 3: Kiểm tra toàn bộ mã nguồn Python trong `lug_project`**
  Run:
  ```bash
  python3 -m py_compile lug_project/**/*.py
  ```
  Expected: PASS không có lỗi.
