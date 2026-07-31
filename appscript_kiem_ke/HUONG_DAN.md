# Hướng dẫn gắn form Kiểm kê CCDC

## 1. Copy file vào Apps Script

Trong project **Kiểm kê vật tư**, thay nội dung:

| File Apps Script | File trong thư mục này |
|------------------|------------------------|
| `Code.gs`        | `Code.gs`              |
| `Index.html`     | `Index.html`           |
| `Style.html`     | `Style.html`           |
| `JavaScript.html`| `JavaScript.html`      |

## 2. Cấu hình bắt buộc

Trong `Code.gs`:

1. `SHEET_DATA: 'TỔNG'` — đã set sẵn.
2. `DRIVE_FOLDER_ID` — thay `THAY_FOLDER_ID_CUA_BAN` bằng ID thư mục Drive.
   - Mở thư mục Drive → URL dạng `https://drive.google.com/drive/folders/XXXX`
   - `XXXX` chính là ID.

## 3. Phân quyền

- Chạy thử hàm `getVatTuList` một lần → cấp quyền Spreadsheet + Drive.
- Deploy: **Triển khai → Ứng dụng web mới**
  - Thực thi với tư cách: **Tôi**
  - Người có quyền truy cập: theo nhu cầu (chỉ bạn / bất kỳ ai trong tổ chức)

## 4. Cách dùng

1. Mở URL Web App.
2. Chọn **mã vật tư** (lấy từ sheet `TỔNG`).
3. Điền thông tin + chọn/chụp ảnh.
4. Bấm **Lưu kiểm kê** → cập nhật đúng dòng, ảnh vào cột **I (Hình ảnh)** dạng ảnh trong ô.

## 5. Lưu ý

- Chỉ **cập nhật dòng đã có mã**, không thêm dòng mới.
- Nếu chưa chọn ảnh, vẫn lưu các cột text; cột ảnh giữ nguyên.
- Ảnh được upload Drive (chia sẻ link xem) rồi gắn vào ô bằng `CellImage`.
