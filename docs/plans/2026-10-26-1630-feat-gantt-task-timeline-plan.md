---
title: Gantt Chart Task Timeline Matching - Implementation Plan & Report
type: feat
date: 2026-10-26
topic: duan-gantt-task-timeline
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-brainstorm
execution: code
---

# Gantt Chart Task Timeline Matching - Implementation Plan & Report

## Goal Capsule

- **Objective:** Trong biểu đồ Gantt của Dự án (`lug_project`), điều chỉnh thanh tiến độ (progress bar) của mỗi công việc của từng Dự án phải khớp với Deadline và Start Date của Dự án, vẽ thanh tiến độ dựa trên "Ngày thực hiện" và "Ngày hết hạn".
- **Means:** 
  1. Hỗ trợ đầy đủ model công việc giai đoạn `project.stage.task` (WBS chuẩn của `lug_project`) và fallback `project.task` trong phương thức tính toán Gantt `_lug_gantt_data`.
  2. Xác định mốc thời gian vẽ thanh tiến độ:
     - `t_start`: Ưu tiên "Ngày thực hiện" (`execution_date` / `lug_execution_date`), fallback về Start Date của Dự án (`project.date_start`), sau đó đến ngày tạo hoặc ngày hiện tại.
     - `t_end`: Ưu tiên "Ngày hết hạn" (`deadline` / `date_deadline`), fallback về Deadline của Dự án (`project.lug_deadline` / `project.date`), sau đó đến `t_start`.
     - Ràng buộc: Luôn đảm bảo `t_end >= t_start`.
  3. Cập nhật nhãn trạng thái (`task_label`) bao gồm các trạng thái `draft` ("Chưa bắt đầu"), `in_progress` ("Đang làm"), `done` ("Hoàn thành").
  4. Cập nhật popup thêm công việc `action_add_task_popup` và logic sinh công việc mẫu để tự động gán mặc định "Ngày thực hiện" và "Ngày hết hạn" từ Start Date & Deadline của Dự án.
  5. Hỗ trợ click mở popup chi tiết công việc giai đoạn (`project.stage.task`) hoặc nhiệm vụ Odoo (`project.task`) từ thanh tiến độ Gantt trong `LugProjectShell`.
- **Product authority:** Phân hệ Dự án (`lug_project`).
- **Status:** Hoàn thành 100% & đã kiểm chứng tự động (41/41 tests passing).

---

## Key Technical Changes

### 1. Backend Gantt Calculation (`lug_project/models/project_dashboard.py`)
- Phương thức `_lug_gantt_data`:
  - Trước đây chỉ tìm kiếm `project.task` và hoàn toàn bỏ qua `project.stage.task`, dẫn đến các dự án tạo qua form chuẩn bị thiếu toàn bộ công việc trên biểu đồ Gantt.
  - Sửa đổi: Tìm kiếm và gom nhóm cả `project.stage.task` và `project.task` theo `picked_ids`.
  - Ưu tiên `project.stage.task`:
    - `t_start = _lug_as_date(stask.execution_date) or proj_start or _lug_as_date(stask.create_date) or today`
    - `t_end = _lug_as_date(stask.deadline) or proj_end or t_start`
  - Fallback sang `project.task`:
    - `t_start = _lug_as_date(task.lug_execution_date) or _lug_as_date(task.date_assign) or proj_start or _lug_as_date(task.create_date) or today`
    - `t_end = _lug_as_date(task.date_deadline) or _lug_as_date(task.date_end) or proj_end or t_start`
  - Bổ sung trường `model` ("project.stage.task" / "project.task") trong từ điển dòng task để frontend xử lý tương tác chính xác.
  - Mở rộng giới hạn hiển thị công việc khi xem chi tiết 1 dự án (tối đa 80 công việc thay vì 20).
  - Tối ưu hóa tính toán cửa sổ hiển thị (`win_start`, `win_end`) khi xem đơn dự án để bao quát trọn vẹn mọi mốc ngày của công việc.

### 2. Form Context & Default Dates (`lug_project/models/project_stage_line.py` & `project_project.py`)
- Trong `action_add_task_popup`:
  - Thêm `default_execution_date`: `self.project_id.date_start or fields.Date.context_today(self)`
  - Thêm `default_deadline`: `self.project_id.lug_deadline or self.project_id.date or False`
- Trong `_lug_ensure_stage_lines`:
  - Thiết lập mặc định `execution_date` và `deadline` khớp với thời gian dự án khi khởi tạo công việc mẫu.

### 3. Frontend OWL Shell Interaction (`lug_project/static/src/shell/lug_project_shell.js`)
- Cập nhật `onGanttRowClick(row)` truyền `row.model` vào `this.openTask(row.res_id, row.model)`.
- Cập nhật `openTask`:
  - Nếu `model === "project.stage.task"`, gọi `action_open_popup` mở popup chỉnh sửa công việc giai đoạn dạng modal, tự động tải lại dữ liệu Gantt khi đóng popup.
  - Nếu `model === "project.task"`, mở view form tiêu chuẩn.

---

## Verification & Automated Test Suite

- **Test Suite:** `tests/test_gantt_timeline.py`
  - `test_gantt_clip_calculation`: Kiểm tra tính toán tọa độ `left` và chiều dài `span` của thanh tiến độ.
  - `test_gantt_stage_task_timeline_matching`: Kiểm tra khớp tiến độ công việc giai đoạn theo "Ngày thực hiện" & "Ngày hết hạn", fallback Start Date & Deadline của Dự án.
  - `test_gantt_native_task_timeline_matching`: Kiểm tra khớp tiến độ nhiệm vụ Odoo theo `lug_execution_date` & `date_deadline`.
  - `test_stage_line_action_add_task_popup_defaults`: Kiểm tra tự động điền sẵn ngày thực hiện và deadline khi mở popup thêm công việc.
- **Kết quả kiểm thử toàn workspace:**
  - 41/41 unit tests chạy thành công không có lỗi (0 failures, 0 errors).
