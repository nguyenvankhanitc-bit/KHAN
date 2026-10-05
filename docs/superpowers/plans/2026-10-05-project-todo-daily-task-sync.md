# Hướng dẫn & Kế hoạch Triển khai Đồng bộ Dự án - Việc Cần Làm - Công Việc Hàng Ngày

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Triển khai cơ chế đồng bộ 2 chiều giữa phân hệ Dự án (`lug_project`), Việc cần làm (`project_todo`) và Công việc hàng ngày (`daily_work_task`) khi tạo mới dự án hoặc gán công việc trong dự án.

**Architecture:** Mở rộng `lug_project` (không sửa đổi `daily_work_task` để bảo đảm tính độc lập): `lug_project` kế thừa `project.task` để quản lý việc tạo & đồng bộ với To-Do (`project.task` không `project_id`), đồng thời kế thừa `daily.task` để quản lý việc tạo & đồng bộ với Công việc hàng ngày. Sử dụng context lock `lug_sync_lock` để ngăn chặn vòng lặp đệ quy 2 chiều.

**Tech Stack:** Odoo 19 (Python ORM, Postgres, XML)

---

## Global Constraints
- Không sửa mã nguồn trong `daily_work_task` (giữ module này độc lập theo thiết kế ban đầu). Mọi logic kế thừa `daily.task` phải đặt trong `lug_project`.
- Giữ vững quy tắc chống lặp vô hạn (infinite recursion guard) với `self.env.context.get("lug_sync_lock")`.
- Tất cả các trường liên kết phải có `ondelete="set null"` hoặc xử lý an toàn khi bản ghi gốc bị xóa.

---

### Task 1: Cập nhật phụ thuộc Manifest trong `lug_project`

**Files:**
- Modify: `lug_project/__manifest__.py`

- [ ] **Step 1: Thêm `project_todo` và `daily_work_task` vào `depends`**
  Cập nhật mảng `depends` trong `lug_project/__manifest__.py` thành:
  ```python
    "depends": [
        "project",
        "project_todo",
        "daily_work_task",
        "hr",
        "mail",
    ],
  ```
- [ ] **Step 2: Kiểm tra cú pháp manifest bằng `python3 -m py_compile`**
  Run: `python3 -m py_compile lug_project/__manifest__.py`
  Expected: PASS không có lỗi cú pháp.

---

### Task 2: Kế thừa `project.task` trong `lug_project` để đồng bộ To-Do và Daily Task

**Files:**
- Modify: `lug_project/models/project_task.py`

**Interfaces:**
- Fields:
  - `lug_todo_task_id = fields.Many2one("project.task", string="Việc cần làm liên kết", ondelete="set null", copy=False)`
  - `lug_daily_task_id = fields.Many2one("daily.task", string="Công việc hàng ngày liên kết", ondelete="set null", copy=False)`
  - `lug_origin_project_task_id = fields.Many2one("project.task", string="Công việc dự án gốc", ondelete="set null", copy=False)`
- Methods:
  - `_lug_get_or_create_daily_employee(user)`
  - `_lug_sync_to_todo_and_daily()`
  - `_lug_sync_from_todo_to_project()`

- [ ] **Step 1: Viết các trường liên kết và hàm trợ giúp tìm/tạo `daily.task.employee`**
  Viết method `_lug_get_or_create_daily_employee(self, user)`:
  - Tìm `hr.employee` có `user_id = user.id`. Nếu có: gọi `self.env['daily.task.employee'].get_or_create_from_hr(hr.id)`.
  - Nếu không có: tìm theo email hoặc tên, nếu chưa có tạo mới `daily.task.employee`.

- [ ] **Step 2: Viết logic `_lug_sync_to_todo_and_daily(self)`**
  Duyệt qua các tasks có `project_id`:
  - Lấy người phụ trách chính (`lug_pic_id` hoặc người đầu tiên trong `user_ids`).
  - Nếu có người phụ trách:
    - **Việc cần làm**: Nếu chưa có `lug_todo_task_id`, tạo mới `project.task` với `project_id=False`, `user_ids=[user.id]`, `name=f"[{project.name}] {task.name}"`, `date_deadline=task.date_deadline`, `lug_origin_project_task_id=task.id`. Nếu đã có: cập nhật tên, deadline, trạng thái, người phụ trách.
    - **Công việc hàng ngày**: Nếu chưa có `lug_daily_task_id`, tạo mới `daily.task` với `name=f"[{project.name}] {task.name}"`, `assignee_id=daily_emp.id`, `assigned_by_id=self.env.user.id`, `deadline=task.date_deadline or project.lug_deadline or today`, `state` tương ứng, `lug_origin_project_task_id=task.id`. Nếu đã có: cập nhật deadline, state, assignee.
  - Sử dụng `.with_context(lug_sync_lock=True)`.

- [ ] **Step 3: Viết logic đồng bộ ngược `_lug_sync_from_todo_to_project(self, vals)`**
  Khi bản ghi là việc cần làm (`not rec.project_id and rec.lug_origin_project_task_id`):
  - Khi cập nhật `state` ('1_done' -> `lug_status = 'done'`, '1_canceled' -> `lug_status = 'cancel'`, '01_in_progress' -> `lug_status = 'progress'`)
  - Khi cập nhật `date_deadline` -> cập nhật `date_deadline` trên `lug_origin_project_task_id`.
  - Gọi với `.with_context(lug_sync_lock=True)`.

- [ ] **Step 4: Tích hợp vào `create`, `write`, `unlink` của `project.task`**
  - Trong `create`: Sau khi `super().create()`, nếu không có `lug_sync_lock`, gọi `_lug_sync_to_todo_and_daily()`.
  - Trong `write`: Gọi `super().write()`. Sau đó nếu không có `lug_sync_lock`:
    - Nếu task là task dự án (`project_id`): gọi `_lug_sync_to_todo_and_daily()`.
    - Nếu task là todo task (`not project_id and lug_origin_project_task_id`): gọi `_lug_sync_from_todo_to_project(vals)`.
  - Trong `unlink`: xóa hoặc gỡ liên kết an toàn ở các bản ghi tương ứng.

- [ ] **Step 5: Kiểm tra cú pháp bằng `python3 -m py_compile`**
  Run: `python3 -m py_compile lug_project/models/project_task.py`
  Expected: PASS không có lỗi.

---

### Task 3: Kế thừa `daily.task` trong `lug_project` để đồng bộ ngược

**Files:**
- Create: `lug_project/models/daily_task.py`
- Modify: `lug_project/models/__init__.py`

- [ ] **Step 1: Tạo file `lug_project/models/daily_task.py`**
  - Khai báo model kế thừa:
    ```python
    class DailyTask(models.Model):
        _inherit = "daily.task"

        lug_origin_project_task_id = fields.Many2one(
            "project.task",
            string="Công việc dự án gốc",
            ondelete="set null",
            copy=False,
            index=True,
        )
    ```
  - Override hàm `write(self, vals)`:
    - Nếu trong `self.env.context.get("lug_sync_lock")`: return `super().write(vals)`.
    - Gọi `res = super().write(vals)`.
    - Duyệt qua các records có `lug_origin_project_task_id`:
      - Nếu `vals` có `state`:
        - `'done'` -> đồng bộ `lug_status = 'done'`, `lug_done_date = fields.Date.context_today(self)`.
        - `'in_progress'` -> đồng bộ `lug_status = 'progress'`.
        - `'not_started'` -> đồng bộ `lug_status = 'todo'`.
      - Nếu `vals` có `deadline`: đồng bộ `date_deadline = vals['deadline']`.
      - Gọi cập nhật `rec.lug_origin_project_task_id.with_context(lug_sync_lock=True).write(...)`.
    - Trả về `res`.

- [ ] **Step 2: Đăng ký import trong `lug_project/models/__init__.py`**
  Thêm `from . import daily_task` vào `lug_project/models/__init__.py`.

- [ ] **Step 3: Kiểm tra cú pháp bằng `python3 -m py_compile`**
  Run: `python3 -m py_compile lug_project/models/daily_task.py lug_project/models/__init__.py`
  Expected: PASS không có lỗi.

---

### Task 4: Kiểm thử toàn diện và Xác minh (Comprehensive Verification)

**Files:**
- Create: `tests/test_project_todo_daily_sync.py` hoặc chạy test kịch bản tự động

- [ ] **Step 1: Viết script kiểm tra logic ánh xạ và đồng bộ không xung đột**
- [ ] **Step 2: Kiểm tra import và toàn bộ module `lug_project`**
  Run: `python3 -m py_compile lug_project/**/*.py`
- [ ] **Step 3: Kiểm tra git status & diff**
