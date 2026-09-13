# lug_app_center

Odoo 19 module — Enterprise Application Center (cổng truy cập ứng dụng).

## Yêu cầu

- Odoo 19
- Module phụ thuộc: `web`, `mail`, `lug_permission`

## Cài đặt

1. Clone repo vào thư mục addons (hoặc thêm parent path vào `addons_path`):

```text
addons_path = ...,D:\KHAN
```

2. Restart Odoo và cài / nâng cấp module **LUG Enterprise Application Center**.

## Tính năng chính

- Header thương hiệu + tìm kiếm ứng dụng
- Sidebar điều hướng + branding
- Lưới ứng dụng theo menu quyền người dùng
- Redirect `/odoo` về App Center khi không có app trong URL
