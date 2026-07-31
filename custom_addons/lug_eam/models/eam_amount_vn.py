# -*- coding: utf-8 -*-
"""Chuyển số tiền sang chữ (tiếng Việt) — dùng cho phiếu nhập mua."""


_DIGITS = (
    "không",
    "một",
    "hai",
    "ba",
    "bốn",
    "năm",
    "sáu",
    "bảy",
    "tám",
    "chín",
)


def _three_digits(n, full=False):
    """Đọc số 0–999."""
    tr = n // 100
    ch = (n % 100) // 10
    dv = n % 10
    parts = []
    if tr or full:
        if tr:
            parts.append(_DIGITS[tr])
            parts.append("trăm")
        elif full:
            parts.append("không trăm")
    if ch > 1:
        parts.append(_DIGITS[ch])
        parts.append("mươi")
        if dv == 1:
            parts.append("mốt")
        elif dv == 5:
            parts.append("lăm")
        elif dv:
            parts.append(_DIGITS[dv])
    elif ch == 1:
        parts.append("mười")
        if dv == 1:
            parts.append("một")
        elif dv == 5:
            parts.append("lăm")
        elif dv:
            parts.append(_DIGITS[dv])
    elif ch == 0 and dv:
        if tr or full:
            parts.append("lẻ")
        if dv == 5 and (tr or full):
            parts.append("năm")
        else:
            parts.append(_DIGITS[dv])
    elif not parts:
        parts.append(_DIGITS[0])
    return " ".join(parts)


def amount_to_vietnamese(amount):
    """Ví dụ: 410000 → 'Bốn trăm mười nghìn đồng chẵn.'"""
    try:
        n = int(round(float(amount or 0)))
    except (TypeError, ValueError):
        n = 0
    if n < 0:
        return "Âm " + amount_to_vietnamese(-n)
    if n == 0:
        return "Không đồng chẵn."

    units = [
        ("tỷ", 1_000_000_000),
        ("triệu", 1_000_000),
        ("nghìn", 1_000),
        ("", 1),
    ]
    parts = []
    remain = n
    started = False
    for label, base in units:
        chunk = remain // base
        remain %= base
        if chunk:
            parts.append(_three_digits(chunk, full=started))
            if label:
                parts.append(label)
            started = True
        elif started and remain and label:
            # giữ chỗ nếu cần (bỏ qua để ngắn gọn)
            pass

    text = " ".join(p for p in parts if p).strip()
    if text:
        text = text[0].upper() + text[1:]
    return f"{text} đồng chẵn."
