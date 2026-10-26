---
title: Project Contract Files - Plan
type: feat
date: 2026-10-26
topic: duan-contract-file
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-brainstorm
execution: code
---

# Project Contract Files - Plan

## Goal Capsule

- **Objective:** Quản lý dự án có thể đính kèm nhiều tệp hợp đồng và phụ lục (PDF, Word, Excel...) ngay khi khởi tạo hoặc cập nhật Dự án trong module `lug_project`, đồng thời xem và tải nhanh các tệp này trực tiếp từ cột "File hợp đồng" trên danh sách Dự án.
- **Means:** Thêm trường Many2many `lug_contract_attachment_ids` vào `project.project`, tích hợp widget tải nhiều file vào form tạo mới và render cột link/icon tải nhanh trong giao diện danh sách OWL Shell và Odoo chuẩn (KTD1, KTD2).
- **Product authority:** Phân hệ Dự án (`lug_project`).
- **Open blockers:** Không có.

---

## Product Contract

*Product Contract unchanged.*

### Summary

Bổ sung trường lưu trữ đa tệp "File hợp đồng" vào biểu mẫu khởi tạo và chi tiết Dự án trong `lug_project`, đồng thời hiển thị cột "File hợp đồng" trên danh sách Dự án với các thẻ liên kết/icon tệp bấm tải trực tiếp.

### Problem Frame

Khi tạo mới Dự án, người dùng cần lưu trữ hợp đồng nguyên tắc, bảng báo giá hoặc phụ lục thỏa thuận liên quan đến dự án. Hiện tại, biểu mẫu khởi tạo chỉ có trường "File đính kèm" chung và màn hình danh sách Dự án hoàn toàn không có cột hiển thị hợp đồng. Người dùng phải mở từng dự án để kiểm tra tệp hoặc lục tìm lẫn lộn giữa các tài liệu dự án khác, làm chậm quy trình tra cứu và nghiệm thu hồ sơ pháp lý.

### Key Decisions

- **Lưu trữ đa tệp bằng quan hệ `ir.attachment` riêng biệt** (session-settled: user-directed — chosen over single binary contract file: cho phép đính kèm nhiều tệp như hợp đồng gốc, phụ lục kỹ thuật, biên bản thanh lý trên cùng một dự án). Governs R1, R2, R3.
- **Hiển thị trực tiếp các liên kết/icon tệp trong ô danh sách** (session-settled: user-directed — chosen over count badge / modal popover: giúp người xem bấm một chạm để tải về hoặc xem ngay mà không cần mở popup trung gian). Governs R5, R7.
- **Không bắt buộc đính kèm khi khởi tạo** (session-settled: user-approved — chosen over required validation: cho phép tạo trước mã và thông tin dự án khi hợp đồng còn đang thương thảo hoặc bổ sung sau). Governs R2.

<!-- ce-section: work-relationships -->
### How This Work Fits Together

Kế hoạch này tập trung độc lập vào tính năng quản lý và hiển thị File hợp đồng của Dự án.

- **Area 1: File hợp đồng Dự án (Phạm vi tài liệu này)**
  - Cung cấp trường dữ liệu và giao diện upload, hiển thị tệp hợp đồng trên biểu mẫu và danh sách.
- **Area 2: Điều chỉnh tiến độ Gantt Chart theo "Ngày thực hiện" và "Ngày hết hạn"**
  - Relationship: Can proceed independently of Area 1.
  - Phụ trách sửa đổi thuật toán tính toán thanh tiến độ task (`_lug_gantt_data`) và căn chỉnh trục thời gian theo Start Date / Deadline của Dự án trong `project_dashboard.py` và template Gantt OWL.

### Requirements

**Data Model & Storage**
- R1. Khai báo trường quan hệ đa tệp `lug_contract_attachment_ids` (Many2many tới `ir.attachment`) trên model `project.project` độc lập với trường `lug_attachment_ids` hiện có.
- R2. Chấp nhận các định dạng tệp thông dụng bao gồm `.pdf`, `.doc`, `.docx`, `.xls`, `.xlsx`, và giữ trường ở trạng thái không bắt buộc (optional).

**Biểu mẫu Khởi tạo & Chi tiết Dự án**
- R3. Tích hợp trường "File hợp đồng" sử dụng widget `many2many_binary` vào biểu mẫu nhập nhanh dự án mới (`view_project_intake_form`), đặt cạnh trường tệp đính kèm trong nhóm thông tin chung.
- R4. Hiển thị trường "File hợp đồng" trên form dự án rút gọn và đầy đủ (`project_project_view_form_simplified_lug`, `edit_project_lug`) để người dùng có thể tải thêm hoặc xóa tệp sau khi tạo.

**Giao diện Danh sách Dự án (OWL Shell & Odoo List)**
- R5. Thêm cột "File hợp đồng" vào bảng danh sách dự án của OWL Shell (`LugProjectList`), hiển thị danh sách các thẻ icon/tên tệp kèm đường dẫn tải trực tiếp (`/web/content/<id>?download=true`).
- R6. Hiển thị ký tự `—` khi dự án chưa có tệp hợp đồng nào được đính kèm.
- R7. Thêm cột "File hợp đồng" vào view danh sách chuẩn Odoo (`view_project_project_list_lug`).

**Tuần tự hóa Dữ liệu & Xuất Báo cáo**
- R8. Cập nhật phương thức `_lug_serialize_project_row` trong `project_dashboard.py` để đóng gói mảng danh sách tệp hợp đồng (gồm `id`, `name`, `mimetype`) gửi về cho giao diện web client.
- R9. Cập nhật phương thức xuất Excel `export_lug_project_list_xlsx` để bổ sung cột "File hợp đồng", điền tên các tệp đính kèm cách nhau bởi dấu phẩy.

### Key Flows

- F1. Khởi tạo Dự án kèm tệp hợp đồng
  - **Trigger:** Người dùng bấm "+ Tạo mới" trên giao diện danh sách dự án.
  - **Actors:** Quản lý dự án, Quản trị viên.
  - **Steps:** Form nhập dự án hiển thị; người dùng điền thông tin chung và tải lên một hoặc nhiều tệp hợp đồng (.pdf, .docx, .xlsx); bấm "Lưu".
  - **Outcome:** Dự án được lưu và các tệp hợp đồng được liên kết chính xác vào `lug_contract_attachment_ids`.
  - **Governs:** R1, R2, R3

- F2. Tra cứu và tải tệp hợp đồng từ danh sách
  - **Trigger:** Người dùng mở danh sách Dự án trên hệ thống.
  - **Actors:** Người dùng có quyền xem dự án.
  - **Steps:** Người dùng duyệt cột "File hợp đồng" trên từng dòng dự án, click trực tiếp vào icon hoặc tên tệp cần mở.
  - **Outcome:** Tệp được tải xuống hoặc mở trên trình duyệt lập tức mà không cần mở form chi tiết dự án.
  - **Governs:** R5, R6, R7, R8

### Acceptance Examples

- AE1. Tạo dự án kèm nhiều tệp hợp đồng
  - **Covers R1, R2, R3, R5.**
  - **Given:** Người dùng đang mở popup "Nhập dự án".
  - **When:** Người dùng chọn tải lên 2 tệp `Hop_dong_kinh_te.pdf` và `Phu_luc_01.docx`, sau đó bấm "Lưu".
  - **Then:** Dự án lưu thành công; trên danh sách xuất hiện 2 thẻ tệp `[📄 Hop_dong_kinh_te.pdf]` và `[📝 Phu_luc_01.docx]` có thể bấm tải.

- AE2. Tạo dự án không có hợp đồng
  - **Covers R2, R6.**
  - **Given:** Người dùng tạo mới dự án nhưng hợp đồng chưa hoàn tất.
  - **When:** Người dùng để trống trường "File hợp đồng" và bấm "Lưu".
  - **Then:** Dự án lưu bình thường không bị chặn bởi validation; cột "File hợp đồng" hiển thị `—`.

- AE3. Xuất danh sách Dự án ra Excel
  - **Covers R9.**
  - **Given:** Dự án có 2 tệp hợp đồng là `HD_NguyenTac.pdf` và `BangGia.xlsx`.
  - **When:** Người dùng bấm nút "Xuất Excel" trên danh sách dự án.
  - **Then:** File Excel tải về có cột "File hợp đồng" ghi giá trị `HD_NguyenTac.pdf, BangGia.xlsx`.

### Scope Boundaries

- **Deferred for later:**
  - Tính năng 2: Căn chỉnh thanh tiến độ task trong Gantt Chart theo "Ngày thực hiện" và "Ngày hết hạn" khớp với thời hạn của Dự án.
  - Tính năng ký số, phê duyệt hợp đồng trực tuyến hoặc quản lý trạng thái hiệu lực hợp đồng.
  - Tự động trích xuất nội dung số tiền/ngày ký từ file hợp đồng bằng OCR.
- **Outside this product's identity:**
  - Hệ thống Quản trị Vòng đời Hợp đồng phức tạp (CLM) chuyên sâu dành cho phòng Pháp chế.

### Dependencies / Assumptions

- Odoo 19 ORM và module `ir.attachment` hoạt động ổn định trong workspace.
- Người dùng có quyền truy cập bản ghi `project.project` được kế thừa quyền đọc/tải các tệp hợp đồng đính kèm tương ứng.

### Outstanding Questions

- **Deferred to Planning:** Xử lý rút gọn nhãn hiển thị khi tên tệp quá dài trên giao diện bảng (ví dụ: giới hạn số ký tự kèm tooltip tên đầy đủ để bảo đảm độ rộng cột tối ưu).
- **Deferred to Planning:** Xác định quy tắc phân quyền chi tiết giữa quyền chỉ đọc và quyền xóa/sửa tệp hợp đồng đối với từng nhóm người dùng.

### Sources / Research

- `lug_project/models/project_project.py`: Khai báo model và quan hệ `lug_attachment_ids`.
- `lug_project/views/project_project_views.xml`: Cấu trúc form nhập dự án `view_project_intake_form` và list view `view_project_project_list_lug`.
- `lug_project/static/src/list/lug_project_list.xml` & `lug_project_list.js`: Giao diện danh sách dự án dạng OWL Component trong Shell.
- `lug_project/models/project_dashboard.py`: Xử lý serialization dữ liệu dòng dự án và xuất Excel.

---

## Planning Contract

### Key Technical Decisions

- KTD1. **Khai báo bảng quan hệ trung gian riêng `lug_project_contract_ir_attachment_rel`**: Tránh trùng lặp hoặc xung đột với `lug_project_ir_attachment_rel` của `lug_attachment_ids`, đảm bảo tệp hợp đồng được phân loại độc lập hoàn toàn với tệp đính kèm dự án thông thường. Governs R1, R2.
- KTD2. **Sử dụng widget `many2many_binary` với thuộc tính lọc đuôi mở rộng file**: Cấu hình `options="{'accepted_file_extensions': '.pdf,.doc,.docx,.xls,.xlsx'}"` trên view XML để giới hạn định dạng thân thiện ngay tại hộp thoại chọn file của hệ điều hành. Governs R2, R3, R4.
- KTD3. **Payload serialization hợp đồng dạng mảng đối tượng gọn**: Trả về `contract_files: [{id, name, mimetype, download_url}]` trong `_lug_serialize_project_row`, trong đó `download_url = f"/web/content/{att.id}?download=true"`, kèm icon đại diện theo `mimetype` hoặc phần mở rộng tệp. Governs R5, R8.
- KTD4. **Render giao diện thẻ chip tệp responsive**: Thiết kế thẻ chip nhỏ gọn với tooltip chứa đầy đủ tên file, giới hạn hiển thị tối đa 20 ký tự để không làm tràn chiều cao hàng danh sách. Governs R5, R6.

### High-Level Technical Design

```
+---------------------------------------------------------------------------------+
|                                 WEB BROWSER                                     |
|                                                                                 |
|  [ Popup: Nhập dự án ]                  [ Danh sách Dự án (OWL Shell) ]         |
|  - Tên dự án, Mã, Khách hàng...         - STT | Mã DA | Cửa hàng | ...          |
|  - File hợp đồng (many2many_binary)     - Cột "File hợp đồng":                   |
|    [+ Upload] -> HopDong.pdf, PL.xlsx     [📄 HopDong.pdf] [📊 PL.xlsx]          |
|                                                  |                              |
+--------------------------------------------------+------------------------------+
                         |                         | Click tải file trực tiếp
                         v                         v
+---------------------------------------------------------------------------------+
|                                ODOO SERVER / ORM                                |
|                                                                                 |
|  Model: project.project                                                         |
|  - lug_contract_attachment_ids = fields.Many2many("ir.attachment", ...)         |
|                                                                                 |
|  Method: _lug_serialize_project_row()                                           |
|  -> contract_files: [{id: 12, name: "HD.pdf", icon: "fa-file-pdf-o"}, ...]     |
|                                                                                 |
|  Method: export_lug_project_list_xlsx()                                         |
|  -> Cột "File hợp đồng": "HopDong.pdf, PL.xlsx"                                 |
+---------------------------------------------------------------------------------+
                         |
                         v
+---------------------------------------------------------------------------------+
|                              POSTGRESQL DATABASE                                |
|                                                                                 |
|  - Table: ir_attachment (Lưu metadata và binary file)                           |
|  - Relation Table: lug_project_contract_ir_attachment_rel (project_id, att_id)  |
+---------------------------------------------------------------------------------+
```

### Assumptions & Constraints

- Khả năng tương thích ngược: Bổ sung trường mới không ảnh hưởng đến bất kỳ dữ liệu `lug_attachment_ids` cũ nào.
- Hiển thị rỗng: Nếu dự án không có hợp đồng đính kèm, `contract_files` là mảng rỗng `[]`, giao diện hiển thị `—`.
- Quyền truy cập: Người dùng có quyền truy cập vào dự án sẽ tự động có quyền tải các tệp hợp đồng thuộc dự án đó.

### Sequencing & Dependencies

- Bước 1 (U1): Mở rộng model `project.project` trong `lug_project/models/project_project.py`.
- Bước 2 (U2): Cập nhật XML views cho biểu mẫu nhập dự án và form chi tiết.
- Bước 3 (U3): Nâng cấp backend serialization `project_dashboard.py` và frontend template `LugProjectList` trong OWL Shell.
- Bước 4 (U4): Cập nhật list view chuẩn Odoo và hàm xuất Excel.
- Bước 5 (U5): Viết test case và chạy kiểm thử tự động toàn diện.

---

## Implementation Units

### U1. Database Schema & Model Definition

- **Goal:** Khai báo trường Many2many `lug_contract_attachment_ids` trên `project.project`.
- **Requirements:** Covers R1, R2.
- **Files:**
  - Modify: `lug_project/models/project_project.py`
- **Approach:**
  - Thêm trường `lug_contract_attachment_ids = fields.Many2many("ir.attachment", "lug_project_contract_ir_attachment_rel", "project_id", "attachment_id", string="File hợp đồng")`.
  - Không gán `required=True` để đáp ứng tính năng tùy chọn.
- **Test Scenarios:**
  - Tạo record `project.project` kèm 2 attachments gắn vào `lug_contract_attachment_ids`.
  - Tạo record `project.project` không có `lug_contract_attachment_ids` (lưu thành công).
- **Verification:**
  - Chạy `python3 -m py_compile lug_project/models/project_project.py`.

### U2. Project Intake & Form Views

- **Goal:** Bổ sung trường "File hợp đồng" lên form nhập nhanh và form dự án chi tiết.
- **Requirements:** Covers R3, R4.
- **Files:**
  - Modify: `lug_project/views/project_project_views.xml`
- **Approach:**
  - Trong `view_project_intake_form`, thêm khối trường "File hợp đồng" ngay trước khối "File đính kèm":
    ```xml
    <div class="o_lug_kv o_lug_kv_file">
        <span class="o_lug_k">File hợp đồng</span>
        <field name="lug_contract_attachment_ids" widget="many2many_binary" nolabel="1"
               options="{'accepted_file_extensions': '.pdf,.doc,.docx,.xls,.xlsx'}"/>
    </div>
    ```
  - Trong `project_project_view_form_simplified_lug`, tab `E. Tài liệu`, thêm field `lug_contract_attachment_ids` với nhãn "Hợp đồng & Phụ lục".
- **Test Scenarios:**
  - Parse XML hợp lệ, không có lỗi cấu trúc cú pháp.
- **Verification:**
  - Chạy `python3 -c "import xml.etree.ElementTree as ET; ET.parse('lug_project/views/project_project_views.xml')"`.

### U3. Custom Shell List View Component & Row Serialization

- **Goal:** Nâng cấp serialization dữ liệu dự án và render cột "File hợp đồng" trên `LugProjectList`.
- **Requirements:** Covers R5, R6, R8.
- **Files:**
  - Modify: `lug_project/models/project_dashboard.py`
  - Modify: `lug_project/static/src/list/lug_project_list.xml`
  - Modify: `lug_project/static/src/list/lug_project_list.scss`
- **Approach:**
  - Trong `_lug_serialize_project_row(project, today)`: Đọc `project.lug_contract_attachment_ids`, trích xuất `id`, `name`, `mimetype`, `icon` (nhận diện pdf, doc/docx, xls/xlsx, hoặc mặc định `fa-file-o`), trả về danh sách `contract_files`.
  - Trong `lug_project_list.xml`: Bổ sung hiển thị `contract_files` trên thẻ dự án hoặc thanh thông tin nhanh.
  - Thêm CSS styling cho chip tệp hợp đồng (`.o_lug_contract_chip`): nền xám nhẹ, border radius, icon màu trực quan, hover hiệu ứng bấm tải.
- **Test Scenarios:**
  - Dự án có 2 file -> trả về 2 phần tử mảng có đầy đủ id, name, icon, url.
  - Dự án không có file -> trả về mảng rỗng `[]`.
- **Verification:**
  - Chạy `python3 -m py_compile lug_project/models/project_dashboard.py`.
  - Kiểm tra tính hợp lệ XML template.

### U4. Standard Odoo List View & Excel Export

- **Goal:** Thêm cột "File hợp đồng" vào list view chuẩn và file Excel xuất ra.
- **Requirements:** Covers R7, R9.
- **Files:**
  - Modify: `lug_project/views/project_project_views.xml`
  - Modify: `lug_project/models/project_dashboard.py`
- **Approach:**
  - Trong `view_project_project_list_lug`, thêm cột `<field name="lug_contract_attachment_ids" widget="many2many_binary" string="File hợp đồng" optional="show"/>`.
  - Trong `export_lug_project_list_xlsx`: Thêm tiêu đề cột "File hợp đồng" vào `headers`, lấy danh sách tên tệp `", ".join(...)` ghi vào ô tương ứng của mỗi dòng dự án.
- **Test Scenarios:**
  - Gọi hàm `export_lug_project_list_xlsx` trên tập dữ liệu dự án mẫu, kiểm tra file sinh ra chứa cột "File hợp đồng".
- **Verification:**
  - Chạy `python3 -m py_compile lug_project/models/project_dashboard.py`.

### U5. Automated Test Suite

- **Goal:** Viết bộ test tự động kiểm thử toàn bộ logic và tính năng mới.
- **Requirements:** Covers R1-R9, AE1-AE3.
- **Files:**
  - Create: `tests/test_project_contract_files.py`
- **Approach:**
  - Kiểm thử model `project.project`: định nghĩa trường, quan hệ Many2many, lưu tệp thành công.
  - Kiểm thử hàm `_lug_serialize_project_row`: trả về đầy đủ metadata hợp đồng.
  - Kiểm thử hàm xuất Excel: kiểm tra dữ liệu cột hợp đồng.
- **Test Scenarios:**
  - `test_contract_files_field_definition`: Xác nhận trường `lug_contract_attachment_ids` có kiểu Many2many tới `ir.attachment`.
  - `test_contract_files_serialization`: Xác nhận format output của `contract_files`.
  - `test_excel_export_contract_files`: Xác nhận xuất Excel gồm cột hợp đồng.
- **Verification:**
  - Chạy `pytest tests/test_project_contract_files.py` hoặc `python3 -m unittest tests/test_project_contract_files.py`.

---

## Verification Contract

- **Cú pháp Python:** `python3 -m py_compile lug_project/models/project_project.py lug_project/models/project_dashboard.py`
- **Cú pháp XML Views & Templates:**
  - `python3 -c "import xml.etree.ElementTree as ET; ET.parse('lug_project/views/project_project_views.xml'); ET.parse('lug_project/static/src/list/lug_project_list.xml')"`
- **Kiểm thử tự động:**
  - `python3 -m unittest tests/test_project_contract_files.py`

---

## Definition of Done

- [ ] Model `project.project` có trường `lug_contract_attachment_ids` (Many2many tới `ir.attachment`).
- [ ] View `view_project_intake_form` có trường "File hợp đồng" cho phép upload file docx, pdf, excel...
- [ ] View `project_project_view_form_simplified_lug` hiển thị trường "File hợp đồng".
- [ ] List view `view_project_project_list_lug` có cột "File hợp đồng".
- [ ] Phương thức `_lug_serialize_project_row` trả về danh sách `contract_files` cho frontend.
- [ ] Giao diện `LugProjectList` hiển thị thẻ chip liên kết tải nhanh file hợp đồng.
- [ ] Phương thức `export_lug_project_list_xlsx` xuất được cột "File hợp đồng" ra Excel.
- [ ] Bộ kiểm thử tự động `tests/test_project_contract_files.py` vượt qua 100% không có lỗi.
