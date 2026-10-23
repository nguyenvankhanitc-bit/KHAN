# Kế hoạch triển khai — Máy chủ & Cloud

**Module:** `lug_phan_he` (Quản lý dịch vụ)  
**Phân hệ:** `service_type.code = server`  
**Ngày lập:** 2026-10-21  
**Phiên bản Odoo mục tiêu:** 19.0  

---

## 1. Kết quả khảo sát (Giai đoạn 1)

### 1.1. Stack kỹ thuật

| Thành phần | Hiện trạng |
|---|---|
| Odoo | **19.0** (`version_info = (19, 0, …)`) |
| Addon | `D:\Lap_odoo\KHAN\lug_phan_he` (addons_path ưu tiên `KHAN`) |
| Frontend | **OWL** client actions + SCSS; biểu đồ **Chart.js** (`web.chartjs_lib`) |
| Shell UI | `PhanHeInternetShell` dùng chung cho Internet / Server |
| Dashboard | `ir.actions.client` tag `phan_he_dashboard` + context `phan_he_service_type_code` |
| Backend API | ORM RPC (`orm.call`), hầu như không dùng HTTP controller nghiệp vụ |
| Migration | Thư mục `migrations/19.0.x.y.z/` (pre/post-migrate) |
| Phân quyền | `group_phan_he_*` + `security.internet.menu.permission` (Internet) + `phan.he.access.mixin` |

### 1.2. Module Dịch vụ Internet (chuẩn tham chiếu)

- **Model HĐ:** `phan.he.service` (store, provider, bandwidth, kỳ TT, ops_status…).
- **Thanh toán:** `phan.he.payment` gắn `service_id`; board OWL xác nhận TT / lịch TT.
- **Dashboard:** `phan.he.service.get_dashboard_data` + Chart.js overview; báo cáo tháng/quý/năm OWL.
- **Menu sidebar:** cấu hình trong `SERVER_NAV_SECTIONS` / `INTERNET_NAV_SECTIONS` (`phan_he_dashboard.js`).
- **ACL menu:** `internet_menu_permission` — chỉ Internet; Server chưa có ACL menu riêng.

### 1.3. Máy chủ & Cloud hiện có (đã làm / hạn chế)

**Đã có:**
- `service_type` code `server`.
- Client action dashboard + shell.
- Field server trên `phan.he.service` (hostname, IP, CPU/RAM, `server_kind_id`…).
- Model `phan.he.server.kind` (ban đầu: VPS/Cloud/Dedicated…); gần đây đã thêm field dạng tài sản (Mã/Tên/Model/Vị trí/Trạng thái) theo yêu cầu UI tạm thời.
- Nav sidebar Server đang mirror một phần Internet (list OWL / payment / báo cáo).

**Thiếu so với yêu cầu đầy đủ:**
- Model **tài sản IT** độc lập (không phải hợp đồng cửa hàng).
- Hạng mục chi phí / gia hạn nhiều kỳ / lịch sử không ghi đè.
- Bảo trì & sự cố.
- Dashboard KPI tài sản + danh sách việc cần xử lý.
- Cài đặt: chu kỳ gia hạn, cấu hình nhắc hạn, danh mục loại tài sản / hạng mục chi phí.
- Phân quyền vai trò IT / Finance riêng cho phân hệ Server.

### 1.4. Giả định quan trọng

1. **Không tách addon mới** — mở rộng trong `lug_phan_he` để giữ hub, shell, Chart.js, provider, miền/khu vực.
2. **`phan.he.service` (HĐ)** không thay thế danh sách tài sản: HĐ Internet bắt buộc `store_id`; tài sản IT cần model riêng.
3. **`phan.he.server.kind`** quay lại vai trò **danh mục loại/nhóm tài sản** (Vật lý / Ảo / Cloud / Mạng…); dữ liệu máy cụ thể (SRV-001…) chuyển sang `phan.he.it.asset`.
4. **Chi phí/gia hạn** ưu tiên model mới `phan.he.it.cost` + lịch sử `phan.he.it.cost.period`; có thể **liên kết tùy chọn** sang `phan.he.payment` khi cần xác nhận TT theo quy trình Internet (không bắt buộc accounting.account.move nếu chưa cài accounting).
5. **Không tạo dữ liệu giả** ngày hết hạn / SN / IP / giá; chỉ seed 4 tài sản tham chiếu (mã, tên, nhóm, hãng, model).
6. Bản copy `odoo_time_off_custom/custom_addons/lug_phan_he` **không** là nguồn chạy (Odoo resolve `KHAN\lug_phan_he`).

---

## 2. Kiến trúc đề xuất (ít ảnh hưởng nhất)

```
lug_phan_he
├── Hub (giữ nguyên)
├── Dịch vụ Internet (không đổi nghiệp vụ)
└── Máy chủ & Cloud (mở rộng)
    ├── OWL shell + nav mới (SERVER_NAV_SECTIONS)
    ├── Dashboard Chart.js (mở rộng get_dashboard_data / API mới)
    ├── phan.he.it.asset          ← danh sách tài sản
    ├── phan.he.it.asset.type     ← danh mục loại (thay/gắn server.kind)
    ├── phan.he.it.cost.category  ← hạng mục chi phí
    ├── phan.he.it.cost           ← khoản chi phí / hợp đồng dịch vụ
    ├── phan.he.it.cost.period    ← lịch sử từng kỳ gia hạn (không ghi đè)
    ├── phan.he.it.ticket         ← bảo trì / hỗ trợ / sự cố
    ├── phan.he.it.reminder.config
    └── Tái sử dụng: phan.he.provider, phan.he.mien, phan.he.store (vị trí), mail.activity
```

### Quan hệ dữ liệu

```
it.asset.type 1──* it.asset
it.asset      1──* it.cost
it.cost       1──* it.cost.period   (mỗi kỳ gia hạn = 1 dòng lịch sử)
it.cost.category *──* it.cost (Many2one)
it.asset      1──* it.ticket
provider      *──* cost / ticket
mien / store  (optional) trên asset để lọc khu vực
```

### Trạng thái (ràng buộc backend)

**Tài sản:** `draft` | `active` | `suspended` | `retired` (không xóa cứng nếu có cost/ticket).

**Gia hạn (`it.cost.renewal_state`):**  
`active` | `expiring` | `quote` | `approval` | `processing` | `renewed` | `overdue` | `cancel`  
— chuyển trạng thái qua method có kiểm tra điều kiện.

**Thanh toán (`it.cost.payment_state`):**  
`not_due` | `confirm` | `pending` | `paid` | `overdue` | `cancel`  
— đồng bộ từ kỳ hiện tại / payment liên kết.

---

## 3. Menu sidebar (chỉ mục có hành vi)

| Nhóm | Menu | Hành vi |
|---|---|---|
| Tổng quan | Tổng quan | Client dashboard |
| Quản lý tài sản | Danh sách máy chủ | List `it.asset` |
| | Máy chủ vật lý / ảo / Cloud / Mạng | Domain theo `asset_type` |
| | Thêm mới | Form tạo `it.asset` |
| Chi phí & gia hạn | Danh sách chi phí | List `it.cost` |
| | Chờ xác nhận TT / Quá hạn / Lịch gia hạn | Domain / board |
| | Dự toán chi phí | OWL board (reuse pattern Internet) |
| Bảo trì & hỗ trợ | Lịch sử bảo trì / Yêu cầu hỗ trợ / Nhật ký sự cố | Domain `it.ticket` theo loại |
| Báo cáo | Chi phí tháng / quý / năm | OWL boards (param `service_type`/`module=server`) |
| | Theo tài sản / NCC | List/pivot hoặc board |
| Cài đặt | Loại tài sản / Hạng mục CP / NCC / Chu kỳ / Nhắc hạn | Catalog + config |

Menu không có model/API → **không tạo**.

---

## 4. File cần tạo / sửa

### Tạo mới

| File | Mục đích |
|---|---|
| `models/phan_he_it_asset.py` | Tài sản + type |
| `models/phan_he_it_cost.py` | Cost, category, period |
| `models/phan_he_it_ticket.py` | Bảo trì / sự cố |
| `models/phan_he_it_reminder.py` | Cấu hình nhắc hạn + cron |
| `models/phan_he_it_dashboard.py` | API dashboard Server (KPI thực) |
| `views/phan_he_it_views.xml` | List/form/search/actions |
| `views/phan_he_it_menus.xml` hoặc patch `phan_he_menus.xml` | Menu Odoo (nếu cần) |
| `data/phan_he_it_asset_type_data.xml` | Loại tài sản |
| `data/phan_he_it_cost_category_data.xml` | Hạng mục CP |
| `data/phan_he_it_asset_seed.xml` | 4 tài sản tham chiếu (noupdate) |
| `data/phan_he_it_cron.xml` | Cron nhắc hạn |
| `security` entries trong CSV + groups IT/Finance (map vào group_phan_he_*) |
| `migrations/19.0.2.499.0/post-migrate.py` | Migrate kind→type; backfill status |
| `static/...` mở rộng nav + overview Server | Dashboard mới |

### Sửa có kiểm soát

| File | Thay đổi |
|---|---|
| `models/phan_he_server_kind.py` | Giữ catalog loại; field tài sản cụ thể deprecate / ẩn khỏi UI chính |
| `static/.../phan_he_dashboard.js` | `SERVER_NAV_SECTIONS` theo menu mới; load API IT dashboard |
| `static/.../phan_he_dashboard.xml` | Overview KPI tài sản (không copy chỉ số Internet) |
| `__manifest__.py` | data/assets mới, bump version |
| `models/__init__.py` | import model mới |

**Không đụng** nghiệp vụ Internet list/payment trừ khi truyền `service_type_code` đã có.

---

## 5. API / method bổ sung

| Method | Model | Mô tả |
|---|---|---|
| `get_it_dashboard_data(filters)` | `phan.he.it.dashboard` | KPI, charts, việc cần xử lý |
| `action_set_renewal_state(new_state)` | `phan.he.it.cost` | Đổi trạng thái có validate |
| `action_confirm_renewal(vals)` | `phan.he.it.cost` | Tạo `it.cost.period`, cập nhật hạn mới |
| `cron_it_reminder()` | `phan.he.it.reminder.config` | Activity/mail theo mốc 90/60/30/7/0 |
| `_compute_amount_tax_total` | `phan.he.it.cost` | trước thuế + VAT → tổng |
| `action_archive` / chặn `unlink` | `phan.he.it.asset` | Không xóa cứng khi có phát sinh |

---

## 6. Phân quyền

Map vào nhóm hiện có (ít group mới):

| Vai trò yêu cầu | Map đề xuất |
|---|---|
| Administrator | `group_phan_he_admin` |
| IT Manager | `group_phan_he_service_manager` (+ record rules khu vực nếu có mixin) |
| IT Employee | `group_phan_he_staff` |
| Finance | `group_phan_he_regional` hoặc group mới `group_phan_he_it_finance` (read cost + write payment fields) |

- ACL trên model mới trong `ir.model.access.csv`.
- Record rules: theo `mien_id` / `company_id` giống `phan.he.access.mixin` nếu áp dụng được.
- Menu ACL Server: mở rộng pattern `internet_menu_permission` → `server_menus` (giai đoạn sau, không chặn MVP).

---

## 7. Migration

1. Bump `19.0.2.499.0`.
2. Tạo bảng model mới.
3. Seed `it.asset.type` từ nhóm: physical / virtual / cloud / network / software.
4. Seed 4 asset (SRV-001, SRV-002, NET-001, NET-002) — **idempotent** theo `code`.
5. `server.kind`: giữ XML data VPS/Cloud…; UI “Danh mục loại tài sản” trỏ `it.asset.type`. Field thừa trên kind ẩn khỏi list chính (tránh nhầm với danh sách máy).
6. Không xóa `phan.he.service` server fields (tương thích HĐ cũ).

---

## 8. Rủi ro tương thích

| Rủi ro | Giảm thiểu |
|---|---|
| Nhầm `server.kind` với danh sách máy | Tách `it.asset`; đổi nhãn menu |
| Dashboard Server đang dùng API Internet | API riêng `get_it_dashboard_data`; không hardcode |
| OWL list Internet hardcode `internet` | Đã có `serviceTypeCode`; IT asset dùng act_window/OWL riêng |
| Upgrade asset cache | `-u lug_phan_he` + `--dev=assets` khi dev |
| Duplicate addon path | Chỉ sửa `KHAN\lug_phan_he` |
| Phá Internet | Không đổi domain/default Internet; regression test list Internet |

---

## 9. Kế hoạch kiểm thử

- [ ] Tạo/sửa/xem tài sản; archive khi có cost.
- [ ] Nhiều `it.cost` / 1 asset; nhiều `it.cost.period` không ghi đè.
- [ ] Công thức thuế + tổng; không cộng trùng kỳ.
- [ ] Cron/activity nhắc hạn theo config.
- [ ] Dashboard filter tháng/khu vực/loại/NCC đổi số liệu.
- [ ] Click việc cần xử lý → mở đúng record.
- [ ] Quyền staff vs manager vs finance.
- [ ] Internet dashboard/list/payment vẫn chạy.
- [ ] Responsive shell (desktop/mobile).
- [ ] Seed 4 asset không tạo trùng khi upgrade lại.

---

## 10. Lộ trình phát triển (Sprint)

### Sprint A — Nền tảng (làm ngay)
Model + security + views list/form + menu sidebar + seed 4 asset + cài đặt danh mục.

### Sprint B — Chi phí & gia hạn
`it.cost` + period + trạng thái + lịch gia hạn + chờ TT / quá hạn.

### Sprint C — Dashboard
KPI 4 thẻ + charts + bảng việc cần xử lý (dữ liệu thật).

### Sprint D — Bảo trì & báo cáo
`it.ticket` + báo cáo tháng/quý/năm/theo asset/NCC + dự toán.

### Sprint E — Nhắc hạn & ACL menu Server
Cron/activity + cấu hình mốc + menu permission.

---

## 11. Phương án đã chọn

**Mở rộng `lug_phan_he` + model IT asset mới** — ít ảnh hưởng Internet, tái sử dụng shell/Chart.js/provider/miền, migration rõ ràng.

**Không chọn:** addon riêng (mất hub/shell); nhồi hết vào `phan.he.service` (sai nghiệp vụ cửa hàng); dùng `server.kind` làm danh sách máy (đã thử, không khớp yêu cầu đầy đủ).

---

## 12. Trạng thái bàn giao tài liệu

- [x] Khảo sát source  
- [x] Kế hoạch này (`docs/server_cloud_implementation_plan.md`)  
- [x] Sprint A — model / menu / security / seed  
- [x] Sprint B — chi phí & gia hạn (form + trạng thái + lịch sử period)  
- [x] Sprint C — dashboard IT (`get_it_dashboard_data` + Chart.js KPI)  
- [x] Sprint D — ticket views + báo cáo act_window theo nhóm  
- [x] Sprint E — cron nhắc hạn + cấu hình mốc (ACL menu Server: giai đoạn sau)  
- [ ] Kiểm thử thực tế trên `lap_odoo19` (checklist mục 9)  

**Ghi chú:** Không tuyên bố hoàn thành toàn bộ yêu cầu §3–§11 cho đến khi các checklist kiểm thử tương ứng pass trên DB thật.
