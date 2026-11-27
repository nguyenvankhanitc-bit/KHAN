# STATUS — cập nhật 2026-11-26

## Đang làm
- Doanh thu NVBH (Checklist NVBH › Doanh thu), 4 tab: Doanh thu theo ngày · Doanh Thu Tháng · Phân Bổ Target · Theo Dõi Target
  (`models/store_nvbh_revenue.py`, `models/store_nvbh_target.py`, phần `rev` trong `static/src/shell/store_shell.*`).
- Bản mới nhất: v2.156 (đã push). Theo Dõi Target: 4 khối (chỉ tiêu CH, tiến độ NV, tuần 1-4, từng ngày) + Excel 2 sheet.

## Đã chốt (chạy ổn, không sửa lại)
- Luồng duyệt: NVBH → CHT chốt; CHT làm xong → chờ ASM (quản lý trực tiếp) đánh giá, ASM chấm từng phiếu hoặc theo tuần (v2.157, KHÔNG có bước CHT tự đánh giá); ASM → RSM → Admin.
- Đánh giá tuần toàn cửa hàng (CHT + từng NVBH), KPI khớp Bảng Tổng. Phiếu Audit ASM (30 tiêu chí).
- Bảng Mức Đánh giá chung; Tốt yêu cầu Lỗi = 0; tiêu chí có Chi tiết lỗi hiện −điểm chuẩn.
- Phân Bổ Target: cột ID HRM / Mã chức vụ, Import Excel, dòng TỔNG HỆ THỐNG ẩn với cấp 1-5 (NV, CHT, ASM, RSM, GS).
- Thuật ngữ Target: Target Tháng / Target Ngày / Phân bổ target (%) / Doanh thu đã đạt / % Đạt được / Còn lại phải đạt / % Còn lại.

## Còn dang dở / chờ user
- Ô "Tổng Target" ở Phân Bổ Target có ẩn với cấp 1-5 không? (chưa trả lời)
- Local thiếu 1.077 file ảnh đại diện (res.partner / hr.employee) — chờ đồng ý xóa liên kết hỏng trên local.
- Ghép nhóm công việc CHT ↔ NVBH; bảng đánh giá tuần dạng thẻ trên điện thoại (`store_week_review.py`, `store_shell.*`).
