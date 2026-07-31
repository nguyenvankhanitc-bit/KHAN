# -*- coding: utf-8 -*-
"""Import Excel theo dõi thanh toán Internet → lug_phan_he."""
from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

import openpyxl
import xmlrpc.client

EXCEL = Path(r"c:\Users\nguye\Downloads\theo dõi thanh toán internet.xlsx")
URL = "http://127.0.0.1:8069"
DB = "lap_odoo19"
USER = "admin"
PASSWORDS = ["admin", "1", "Admin@123", "LapMaster@2026"]


def to_date(val):
    if val is None or val == "":
        return False
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, date):
        return val.isoformat()
    s = str(val).strip()
    if not s:
        return False
    # range like 17/09/2025 - 16/11/2026 or 19/09/2025-18/10/2026
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", s)
    if m:
        try:
            return datetime.strptime(m.group(1), "%d/%m/%Y").date().isoformat()
        except ValueError:
            pass
    # T12-31/12/2026
    m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", s)
    if m:
        try:
            return datetime.strptime(m.group(1), "%d/%m/%Y").date().isoformat()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return False


def clean(s):
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip().strip("'\"")


def store_code(name: str) -> str:
    code = re.sub(r"[^A-Za-z0-9]+", "-", clean(name).upper()).strip("-")
    return (code or "CH")[:32]


def parse_payment_info(text: str):
    """Return dict: account_name, account_number, bank_name, raw."""
    raw = clean(text)
    if not raw:
        return {}
    account_number = ""
    bank_name = ""
    account_name = raw.split("-")[0].strip(" -:")[:200] if raw else ""

    m = re.search(r"STK\s*[:：]?\s*([0-9.\s]+)", raw, re.I)
    if m:
        account_number = re.sub(r"[.\s]", "", m.group(1))

    m = re.search(r"NG[AÂ]N\s*H[AÀ]NG\s*[:：]?\s*(.+?)(?:$|- Nội dung)", raw, re.I)
    if m:
        bank_name = clean(m.group(1))[:120]
    elif "ACB" in raw.upper():
        bank_name = "ACB"
    elif "VIETCOMBANK" in raw.upper() or "VCB" in raw.upper() or "NGOẠI THƯƠNG" in raw.upper():
        bank_name = "Vietcombank"
    elif "BIDV" in raw.upper():
        bank_name = "BIDV"
    elif "AGRIBANK" in raw.upper() or "NÔNG NGHIỆP" in raw.upper():
        bank_name = "Agribank"

    # Prefer explicit TÊN TK
    m = re.search(r"T[EÊ]N\s*TK\s*[:：]?\s*(.+?)(?:- STK|$)", raw, re.I)
    if m:
        account_name = clean(m.group(1))[:200]
    elif "FPT" in raw.upper():
        account_name = "FPT Telecom"
    elif "VNPT" in raw.upper():
        account_name = "VNPT"

    provider_name = "FPT Telecom" if "FPT" in raw.upper() else (
        "VNPT" if "VNPT" in raw.upper() else (
            "Viettel" if "VIETTEL" in raw.upper() or "QUÂN ĐỘI" in raw.upper() or "QUAN DOI" in raw.upper()
            else (account_name or "Nhà cung cấp khác")
        )
    )
    return {
        "provider_name": provider_name[:120],
        "account_name": (account_name or provider_name)[:120],
        "account_number": account_number or "UNKNOWN",
        "bank_name": bank_name or "Khác",
        "raw": raw,
    }


def guess_mien(address: str, name: str):
    text = f"{address} {name}".upper()
    if any(k in text for k in ("HÀ NỘI", "HA NOI", "HẢI PHÒNG", "HAI PHONG", "BẮC", "BAC NINH")):
        return "BAC"
    if any(k in text for k in ("ĐÀ NẴNG", "DA NANG", "HUẾ", "HUE", "QUẢNG")):
        return "DTT"
    if any(k in text for k in ("CẦN THƠ", "CAN THO", "BÌNH DƯƠNG", "BINH DUONG", "HỒ CHÍ MINH", "HO CHI MINH", "TP.HCM", "TPHCM", "HCM", "BÀ RỊA", "BA RIA", "LONG AN")):
        return "NAM"
    return "NAM"


def connect():
    common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", allow_none=True)
    uid = None
    password = None
    for pwd in PASSWORDS:
        try:
            uid = common.authenticate(DB, USER, pwd, {})
            if uid:
                password = pwd
                break
        except Exception:
            continue
    if not uid:
        raise SystemExit("Không đăng nhập được Odoo admin")
    models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)
    return uid, password, models


def execute(models, uid, password, model, method, *args, **kwargs):
    return models.execute_kw(DB, uid, password, model, method, list(args), kwargs or {})


def get_or_create(models, uid, pwd, model, domain, vals):
    ids = execute(models, uid, pwd, model, "search", domain, limit=1)
    if ids:
        execute(models, uid, pwd, model, "write", ids, vals)
        return ids[0], False
    return execute(models, uid, pwd, model, "create", vals), True


def main():
    uid, pwd, models = connect()
    print(f"Auth OK uid={uid}")

    # refs
    type_ids = execute(models, uid, pwd, "phan.he.service.type", "search", [("code", "=", "internet")], limit=1)
    if not type_ids:
        raise SystemExit("Thiếu loại dịch vụ INTERNET — kiểm tra module lug_phan_he")
    type_id = type_ids[0]

    mien_map = {}
    for rec in execute(models, uid, pwd, "phan.he.mien", "search_read", [], fields=["id", "code"]):
        mien_map[rec["code"]] = rec["id"]

    wb = openpyxl.load_workbook(EXCEL, data_only=True)
    ws = wb["INTERNET"]

    stats = {
        "rows": 0, "stores": 0, "services": 0, "payments": 0,
        "invoices": 0, "providers": 0, "banks": 0, "skip": 0, "errors": [],
    }
    provider_cache = {}
    bank_cache = {}

    for row in ws.iter_rows(min_row=4, values_only=True):
        store_name = clean(row[2]) if len(row) > 2 else ""
        if not store_name:
            continue
        # skip title-ish
        if store_name.upper().startswith("THEO DÕI"):
            continue
        stats["rows"] += 1

        try:
            customer_raw = clean(row[3]) if len(row) > 3 else ""
            customer_code = customer_raw.split(" ")[0].split("\n")[0].strip() if customer_raw else ""
            date_start = to_date(row[4] if len(row) > 4 else None)
            date_end = to_date(row[5] if len(row) > 5 else None)
            content = clean(row[6]) if len(row) > 6 else ""
            amount = row[7] if len(row) > 7 else None
            try:
                amount = float(amount) if amount not in (None, "") else 0.0
            except (TypeError, ValueError):
                amount = 0.0
            status_txt = clean(row[9]) if len(row) > 9 else ""
            address = clean(row[11]) if len(row) > 11 else ""
            pay_info = parse_payment_info(row[12] if len(row) > 12 else "")
            invoice_no = clean(row[14]) if len(row) > 14 else ""
            pay_amount = row[15] if len(row) > 15 else None
            try:
                pay_amount = float(pay_amount) if pay_amount not in (None, "") else amount
            except (TypeError, ValueError):
                pay_amount = amount
            date_due_raw = row[16] if len(row) > 16 else None
            date_due = to_date(date_due_raw)
            period = clean(date_due_raw) if isinstance(date_due_raw, str) else ""

            # state
            low = f"{status_txt} {address}".lower()
            if "thanh lý" in low or "thanh ly" in low:
                state = "expired"
                store_state = "inactive"
            elif date_end and date_end < date.today().isoformat():
                state = "expired"
                store_state = "active"
            else:
                state = "active"
                store_state = "active"

            mien_code = guess_mien(address, store_name)
            mien_id = mien_map.get(mien_code) or False

            # Store
            code = store_code(store_name)
            store_vals = {
                "code": code,
                "name": store_name,
                "address": address or False,
                "state": store_state,
                "mien_id": mien_id,
                "note": status_txt or False,
            }
            store_id, created = get_or_create(
                models, uid, pwd, "phan.he.store",
                ["|", ("code", "=", code), ("name", "=", store_name)],
                store_vals,
            )
            if created:
                stats["stores"] += 1

            # Provider + bank
            provider_id = False
            bank_id = False
            if pay_info:
                pname = pay_info["provider_name"]
                if pname not in provider_cache:
                    pid, pnew = get_or_create(
                        models, uid, pwd, "phan.he.provider",
                        [("name", "=", pname)],
                        {"name": pname, "transfer_content_template": False},
                    )
                    provider_cache[pname] = pid
                    if pnew:
                        stats["providers"] += 1
                provider_id = provider_cache[pname]

                bkey = (provider_id, pay_info["account_number"])
                if bkey not in bank_cache:
                    bid, bnew = get_or_create(
                        models, uid, pwd, "phan.he.bank.account",
                        [("provider_id", "=", provider_id), ("account_number", "=", pay_info["account_number"])],
                        {
                            "provider_id": provider_id,
                            "account_name": pay_info["account_name"],
                            "account_number": pay_info["account_number"],
                            "bank_name": pay_info["bank_name"],
                            "is_default": True,
                            "transfer_content_template": f"TT Internet {store_name} {customer_code}".strip(),
                            "note": pay_info.get("raw") or False,
                        },
                    )
                    bank_cache[bkey] = bid
                    if bnew:
                        stats["banks"] += 1
                bank_id = bank_cache[bkey]

            # Service / contract
            svc_domain = [
                ("store_id", "=", store_id),
                ("service_type_id", "=", type_id),
            ]
            if customer_code:
                svc_domain.append(("customer_code", "=", customer_code))
            svc_vals = {
                "store_id": store_id,
                "service_type_id": type_id,
                "customer_code": customer_code or False,
                "package_name": content or False,
                "service_content": content or False,
                "usage_address": address or False,
                "date_start": date_start,
                "date_end": date_end,
                "contract_amount": amount,
                "provider_id": provider_id or False,
                "state": state,
                "note": status_txt or False,
            }
            # keep existing code if update
            existing = execute(models, uid, pwd, "phan.he.service", "search", svc_domain, limit=1)
            if existing:
                execute(models, uid, pwd, "phan.he.service", "write", existing, svc_vals)
                service_id = existing[0]
            else:
                svc_vals["code"] = f"NET-{code}"[:32]
                # unique code fallback
                clash = execute(models, uid, pwd, "phan.he.service", "search", [("code", "=", svc_vals["code"])], limit=1)
                if clash:
                    svc_vals["code"] = f"NET-{code}-{stats['rows']}"[:32]
                service_id = execute(models, uid, pwd, "phan.he.service", "create", svc_vals)
                stats["services"] += 1

            # Payment + invoice
            if invoice_no or pay_amount or date_due:
                pay_vals = {
                    "service_id": service_id,
                    "provider_id": provider_id or False,
                    "bank_account_id": bank_id or False,
                    "period": period or "HĐ 001",
                    "invoice_number": invoice_no or False,
                    "amount": pay_amount or amount or 0.0,
                    "date_due": date_due,
                    "payment_state": "pending" if state == "active" else ("paid" if state == "expired" and "thanh lý" in low else "pending"),
                    "payment_content": pay_info.get("raw") or False,
                }
                if invoice_no:
                    p_existing = execute(
                        models, uid, pwd, "phan.he.payment", "search",
                        [("service_id", "=", service_id), ("invoice_number", "=", invoice_no)],
                        limit=1,
                    )
                else:
                    p_existing = execute(
                        models, uid, pwd, "phan.he.payment", "search",
                        [("service_id", "=", service_id), ("period", "=", pay_vals["period"])],
                        limit=1,
                    )
                if p_existing:
                    execute(models, uid, pwd, "phan.he.payment", "write", p_existing, pay_vals)
                    payment_id = p_existing[0]
                else:
                    payment_id = execute(models, uid, pwd, "phan.he.payment", "create", pay_vals)
                    stats["payments"] += 1

                if invoice_no:
                    inv_vals = {
                        "invoice_number": invoice_no,
                        "payment_id": payment_id,
                        "service_id": service_id,
                        "amount": pay_amount or amount or 0.0,
                        "invoice_date": date_start or date_due or False,
                        "reconcile_state": "draft",
                    }
                    inv_existing = execute(
                        models, uid, pwd, "phan.he.invoice", "search",
                        [("invoice_number", "=", invoice_no), ("service_id", "=", service_id)],
                        limit=1,
                    )
                    if inv_existing:
                        execute(models, uid, pwd, "phan.he.invoice", "write", inv_existing, inv_vals)
                    else:
                        execute(models, uid, pwd, "phan.he.invoice", "create", inv_vals)
                        stats["invoices"] += 1

            print(f"OK  {store_name} | KH={customer_code} | HĐ={invoice_no or '-'}")
        except Exception as e:
            stats["skip"] += 1
            stats["errors"].append(f"{store_name}: {e}")
            print(f"ERR {store_name}: {e}")

    print("\n=== SUMMARY ===")
    for k, v in stats.items():
        if k != "errors":
            print(f"{k}: {v}")
    if stats["errors"]:
        print("errors:")
        for e in stats["errors"][:20]:
            print(" -", e)


if __name__ == "__main__":
    main()
