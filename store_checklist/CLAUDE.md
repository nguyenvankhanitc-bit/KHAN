# store_checklist — Checklist Đánh Giá Cửa Hàng (Odoo 19)

Người dùng nói tiếng Việt → trả lời tiếng Việt. Đọc thêm `STATUS.md` (trạng thái việc đang làm).

## Môi trường
- Odoo 19 Community, module `store_checklist` (depends: `mail`, `lug_phan_he`). Repo GitHub `nguyenvankhanitc-bit/KHAN`, nhánh `main`.
- Local: `d:\Lap_odoo` (venv, `odoo/odoo-bin`, `odoo.conf`), DB `lap_odoo19`, http://localhost:8069.
  PostgreSQL portable hay bị tắt: `C:\PostgreSQL16\bin\pg_ctl.exe -D C:\PostgreSQL16\data -l C:\PostgreSQL16\pg.log start`.
- Production: workspace.lug.info.vn (docker `odoo-odoo19-1`, DB `master`). KHÔNG có SSH — user tự chạy lệnh PuTTY (pull → rsync → `-u store_checklist` → restart).

## Quy trình mỗi lần sửa
1. Tăng `version` trong `__manifest__.py` (19.0.2.NNN.0).
2. Nâng cấp local (dùng `--logfile` vì odoo.conf ghi log ra odoo.log):
   `cd /d/Lap_odoo && PYTHONUTF8=1 venv/Scripts/python.exe odoo/odoo-bin -c odoo.conf --logfile=/d/Lap_odoo/_upg.log -u store_checklist -d lap_odoo19 --stop-after-init --no-http`
   (ERROR "lug_task_assignment not loaded" là lỗi cũ, bỏ qua.)
3. Test bằng `odoo-bin shell -c odoo.conf --logfile= -d lap_odoo19 --no-http < script.py`; cuối script `env.cr.rollback()`. Hàm RPC test qua `odoo.service.model.call_kw` (context đặt trong kwargs).
4. Commit: `git -c safe.directory=* -c user.name=Khan -c user.email=<email user> commit` — message `vNNN: mô tả không dấu`, rồi push. Nhắc user chạy PuTTY + Ctrl+F5.
- Patch dài: viết file .py vào scratchpad rồi chạy (heredoc bash dài hay lỗi).
- Có thể có phiên Claude khác sửa song song cùng file → `git status` trước khi commit, báo user nếu commit lẫn thay đổi của phiên khác.
- Không sửa dữ liệu đánh giá cũ khi chưa được user đồng ý.

## Vai trò & cấp bậc (`models/store_role.py`, `ROLE_LEVEL_MAP`)
| Cấp | Mã chức vụ | Ghi chú |
|---|---|---|
| 1 | NVBH, NV, NT, NTTT, PT | nhân viên cửa hàng |
| 2 | CHT, CHTTT, ASMTT | cửa hàng trưởng (ASMTT cùng cấp CHT) |
| 3 | ASM | quản lý khu vực |
| 4 | RSM | quản lý vùng |
| 5 | GS, GSTT | giám sát |
| 6 | QLBH | quản lý bán hàng |
- Mã lấy từ dòng Lịch xếp ca mới nhất, không có thì suy từ Chức danh (`role_code_from_title`). Admin / `group_store_manager` / `lug_data_scope='company'`: không giới hạn. Tài khoản chung `CH_...`: thấy mọi NV của cửa hàng mình.
- Hiển thị dữ liệu (`_user_person_domain`, `_search`): cấp 1 chỉ thấy của mình; CHT thấy mình + NV cấp 1 tại cửa hàng; ASM trở lên theo phạm vi cửa hàng (`store.audit._user_store_scope`). Nếu có `store.staff.view.rule` (Phân quyền xem nhân sự theo Miền/Cửa hàng) thì rule thay cho phạm vi mặc định.
- Quyền menu: `store.perm.rule` + `MENUS`/`FOLDERS` trong `models/store_menu_perm.py`.

## Luồng đánh giá checklist (`store.nvbh.check`, kind nvbh/cht/asm)
- `_approval_chain`: đi ngược Sơ đồ tổ chức (parent_id), mỗi cấp cao hơn là một bước (STEP_CODES 2=CHT, 3=ASM, 4=RSM; tối đa 4 bước, bước cuối có thể Admin).
  NVBH → CHT → ASM chốt; CHT → ASM chốt; ASM → RSM → Admin/Admin tổng (nếu có).
- state: draft → pending_review (step_done) → approved. `save_step_evaluation`, `_finish_step`, `STEP_PREFIX=['','asm_','rsm_','adm_']`.
- Hạn: NV 4 ngày (`staff_window_days`), mỗi cấp 4 ngày (`review_window_days`); bước ASM của cht/nvbh: hạn ≥ thứ Hai + 13. ASM được sửa lại đến 23h55 (`_reedit_until`).

## Model chính
- `store.audit` (+ `.line`: note, error_count, actual_score, is_scored, result) — Phiếu đánh giá cửa hàng, PDF `report/store_audit_report.xml` (cache attachment `Bien-ban-vNN-...`: đổi cách hiển thị thì tăng NN).
- `store.audit.level` — bảng Mức Đánh giá CHUNG cho mọi phiếu (`common_levels()`, domain `audit_type != 'gs'`); `level_for(pct, audit_type, errors)`; `no_error` = mức chỉ đạt khi Lỗi = 0 (vd. Tốt).
- Tiêu chí có "Chi tiết lỗi": hiển thị Điểm đánh giá = −điểm chuẩn (đỏ), actual_score lưu 0.
- `store.nvbh.check` / `.line` / `.step`, `store.nvbh.schedule(.line)` (lịch ca), `store.nvbh.task`, `store.nvbh.rating`, `store.nvbh.kpi.input`, `store.nvbh.revenue`, `store.nvbh.target`.
- `store.cht.task(.group)`, `store.cht.check(.line)`, `store.cht.visit` (+ `store.cht.visit.row`) — đánh giá tuần CHT / toàn cửa hàng (Tuần 1–4): `get_cht_week`, `save_cht_week`, `get_store_week`, `save_store_week` (`models/store_week_review.py`), nhận xét theo nhóm + tổng thể, KPI khớp Bảng checklist Tổng.
- `store.asm.task(.group)`, `store.asm.check(.line)` — checklist ASM.
- `store.asm.audit` (+ `.group`, `.crit` 30 tiêu chí, `.line`, `.remark`, `.plan`) — Phiếu Audit cửa hàng (ASM).
- `store.audit.action` — xử lý sai phạm. GPS / bản đồ nhân viên nằm ở module khác: `../hr_employee_location`.

## Quy ước code / UI
- Giao diện chính là OWL client action "shell": `static/src/shell/store_shell.js|.xml|.scss` (state, nav items, các trang), view backend trong `views/store_shell_views.xml`.
- Hàm Python gọi từ JS phải có `@api.model` (chèn helper cẩn thận, đừng làm mất decorator của hàm kế bên).
- Template OWL: không dùng regex literal hay `Math` trong biểu thức → viết getter trong JS. `t-foreach` có `x_first`, `x_index`.
- Thêm field vào view nào thì phải đúng model của view đó (lỗi upgrade exit≠0 thường do vậy).
- `<function>` khởi tạo một lần: đặt trong data file KHÔNG noupdate, có cờ ICP để chạy 1 lần.
- Layout: user chủ yếu dùng máy tính (desktop), có thêm giao diện điện thoại (responsive trong scss). Làm theo đúng mẫu/ảnh user gửi; sửa JS/XML xong user phải restart server + Ctrl+F5 mới thấy.
- Nhãn/chú thích bằng tiếng Việt có dấu; commit message không dấu.
