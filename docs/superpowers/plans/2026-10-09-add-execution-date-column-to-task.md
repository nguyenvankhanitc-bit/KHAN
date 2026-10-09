# Kế hoạch Triển khai: Bổ sung cột "Ngày thực hiện" cho Task trong lug_project

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm cột "Ngày thực hiện" (kiểu Date) khi tạo mới hoặc quản lý công việc trong `lug_project`, áp dụng cho cả bảng công việc theo thẻ giai đoạn (`project.stage.task`) và danh sách công việc dự án chuẩn (`project.task`).

**Architecture:**
- Mở rộng model `project.stage.task`: Bổ sung trường `execution_date` (fields.Date), hiển thị trên popup tạo mới công việc, bảng danh sách công việc của thẻ giai đoạn (OWL component `LugStageCardsField`), view list và view form.
- Mở rộng model `project.task`: Bổ sung trường `lug_execution_date` (fields.Date), hiển thị trên form chi tiết công việc của giai đoạn, bảng công việc trên form giai đoạn và bảng kế hoạch dự án.

**Tech Stack:** Odoo 19, Python ORM, XML Views, OWL 2 Components.

---

## Global Constraints
- Tuân thủ quy tắc đặt tên trường của module:
  - Trên model kế thừa `project.task`: dùng tiền tố `lug_execution_date`.
  - Trên model riêng `project.stage.task`: dùng `execution_date`.
- Kiểu dữ liệu là `fields.Date` (định dạng ngày, đồng bộ với `deadline` / `date_deadline`).
- Giữ nguyên cấu trúc giao diện responsive và styling SCSS hiện tại của bảng thẻ giai đoạn (`LugStageCardsField`).
- Đảm bảo kiểm tra cú pháp Python (`py_compile`) và XML (`xml.etree.ElementTree`) trước khi hoàn tất.

---

### Task 1: Bổ sung trường `execution_date` và cập nhật Views cho `project.stage.task`

**Files:**
- Modify: `lug_project/models/project_stage_task.py`
- Modify: `lug_project/views/project_stage_line_views.xml`
- Modify: `lug_project/views/project_project_views.xml`

- [ ] **Step 1: Thêm field `execution_date` vào `project.stage.task`**
  Trong `lug_project/models/project_stage_task.py`, khai báo:
  ```python
  execution_date = fields.Date(string="Ngày thực hiện")
  ```
- [ ] **Step 2: Cập nhật popup "Thêm công việc" và danh sách trong `project_stage_line_views.xml`**
  - Trong `view_project_stage_task_list`: Thêm `<field name="execution_date" string="Ngày thực hiện"/>` trước `<field name="deadline"/>`.
  - Trong `view_project_stage_task_popup_form`: Thêm `<field name="execution_date"/>` vào group cùng với `deadline`.
  - Trong `view_project_stage_line_form`: Thêm `<field name="execution_date" string="Ngày thực hiện"/>` vào `<list>` của `task_ids`.
- [ ] **Step 3: Cập nhật `view_project_intake_form` trong `project_project_views.xml`**
  Trong list `task_ids` của form popup giai đoạn, thêm `<field name="execution_date" string="Ngày thực hiện"/>`.
- [ ] **Step 4: Kiểm tra cú pháp Python và XML**
  Run:
  ```bash
  python3 -m py_compile lug_project/models/project_stage_task.py
  python3 -c "import xml.etree.ElementTree as ET; ET.parse('lug_project/views/project_stage_line_views.xml'); ET.parse('lug_project/views/project_project_views.xml')"
  ```
  Expected: PASS không có lỗi.

---

### Task 2: Cập nhật giao diện Thẻ giai đoạn OWL (`LugStageCardsField`)

**Files:**
- Modify: `lug_project/static/src/stages/lug_stage_cards.js`
- Modify: `lug_project/static/src/stages/lug_stage_cards.xml`

- [ ] **Step 1: Cập nhật JS đọc và định dạng `execution_date`**
  Trong `lug_project/static/src/stages/lug_stage_cards.js`:
  - Trong `get cards()`: thêm `executionDateLabel: formatDate(task.execution_date)`.
  - Trong `_refreshTasks()`: thêm `"execution_date"` vào mảng field gọi `orm.searchRead`.
- [ ] **Step 2: Cập nhật XML hiển thị cột "Ngày thực hiện"**
  Trong `lug_project/static/src/stages/lug_stage_cards.xml`:
  - Trong `<thead>`: thêm `<th class="is-execution-date">Ngày thực hiện</th>` trước cột `<th class="is-deadline">Deadline</th>`.
  - Trong `<tbody>`: thêm `<td class="is-execution-date" t-esc="task.executionDateLabel"/>`.
  - Cập nhật `colspan` ở dòng rỗng `!card.tasks.length` từ `10 : 9` thành `11 : 10`.
  - Cập nhật `colspan` ở footer tổng từ `8` thành `9`.
- [ ] **Step 3: Kiểm tra tính hợp lệ XML template**
  Run:
  ```bash
  python3 -c "import xml.etree.ElementTree as ET; ET.parse('lug_project/static/src/stages/lug_stage_cards.xml')"
  ```
  Expected: PASS không có lỗi.

---

### Task 3: Bổ sung trường `lug_execution_date` và cập nhật Views cho `project.task`

**Files:**
- Modify: `lug_project/models/project_task.py`
- Modify: `lug_project/views/project_stage_views.xml`
- Modify: `lug_project/views/project_project_views.xml`

- [ ] **Step 1: Thêm field `lug_execution_date` vào `project.task`**
  Trong `lug_project/models/project_task.py`, khai báo:
  ```python
  lug_execution_date = fields.Date(string="Ngày thực hiện", copy=False)
  ```
- [ ] **Step 2: Cập nhật `view_lug_stage_task_form` và `view_lug_project_stage_form`**
  Trong `lug_project/views/project_stage_views.xml`:
  - Trong `view_lug_stage_task_form`: thêm `<field name="lug_execution_date"/>` trước `<field name="date_deadline"/>`.
  - Trong `view_lug_project_stage_form` (editable list `task_ids`): thêm `<field name="lug_execution_date" string="NGÀY THỰC HIỆN"/>` trước `<field name="date_deadline"/>`.
- [ ] **Step 3: Cập nhật `project_project_view_form_simplified_lug`**
  Trong `lug_project/views/project_project_views.xml`:
  - Trong tab "D. Kế hoạch" (`task_ids`), thêm `<field name="lug_execution_date" string="Ngày thực hiện"/>` trước `<field name="date_deadline"/>`.
- [ ] **Step 4: Kiểm tra cú pháp Python và XML**
  Run:
  ```bash
  python3 -m py_compile lug_project/models/project_task.py
  python3 -c "import xml.etree.ElementTree as ET; ET.parse('lug_project/views/project_stage_views.xml'); ET.parse('lug_project/views/project_project_views.xml')"
  ```
  Expected: PASS không có lỗi.

---

### Task 4: Kiểm thử và Xác minh Toàn diện

**Files:**
- Create: `tests/test_task_execution_date.py`

- [ ] **Step 1: Viết standalone unit test kiểm tra thuộc tính và logic các model**
  Tạo `tests/test_task_execution_date.py` kiểm tra:
  - Model `project.stage.task` có trường `execution_date` kiểu Date.
  - Model `project.task` có trường `lug_execution_date` kiểu Date.
  - Test tương thích dữ liệu và không làm ảnh hưởng luồng sync hiện có.
- [ ] **Step 2: Chạy toàn bộ test suites**
  Run:
  ```bash
  python3 -m unittest tests/test_task_execution_date.py
  python3 -m unittest tests/test_sync_logic.py
  ```
  Expected: Tất cả tests PASS.
- [ ] **Step 3: Kiểm tra toàn bộ codebase Python của `lug_project`**
  Run:
  ```bash
  python3 -m py_compile lug_project/**/*.py
  ```
  Expected: PASS không có lỗi.
