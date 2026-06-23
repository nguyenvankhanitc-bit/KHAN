import json
import os

SRC = r"d:\Lap_odoo\odoo\addons\spreadsheet_dashboard_hr_timesheet\data\files\tasks_dashboard.json"
DEST = r"d:\Lap_odoo\odoo_time_off_custom\custom_addons\hr_leave_analytics\data\files\leave_dashboard.json"

F_DATE = "a1111111-1111-4111-8111-111111111101"
F_MIEN = "a1111111-1111-4111-8111-111111111102"
F_DEPT = "a1111111-1111-4111-8111-111111111103"
F_STORE = "a1111111-1111-4111-8111-111111111104"
F_BLOCK = "a1111111-1111-4111-8111-111111111105"

OLD_TO_NEW = {
    "83b5c62c-1c67-4477-a057-c0ec29edd595": F_DATE,
    "fb7f6ae2-e19c-40d5-9976-7a05b1f18c2d": F_DEPT,
    "3fc9b370-1aae-436e-b77e-6bbc5f10f56c": F_STORE,
    "cfccbf2c-c86e-4915-a73d-c1e8ae69abe9": F_BLOCK,
    "9c9461c3-974d-41c1-8cbd-2fa8e89de148": F_MIEN,
}

FIELD_MATCHING = {
    F_DATE: {"chain": "request_date_from", "type": "date", "offset": 0},
    F_MIEN: {"chain": "employee_mien", "type": "char"},
    F_DEPT: {"chain": "department_id", "type": "many2one"},
    F_STORE: {"chain": "store_id", "type": "many2one"},
    F_BLOCK: {"chain": "workforce_block", "type": "char"},
}


def replace_str(value: str) -> str:
    for old, new in OLD_TO_NEW.items():
        value = value.replace(old, new)
    replacements = [
        ("report.project.task.user", "hr.leave.analytics.report"),
        ("effective_hours", "number_of_days"),
        ("create_date", "request_date_from"),
        ("date_assign", "request_date_from"),
        ("user_ids", "employee_id"),
        ("project_id", "store_id"),
        ("tag_ids", "workforce_block"),
        ("partner_id", "employee_mien"),
        ("stage_id", "department_id"),
        ("Tasks by Stage", "Nghỉ phép theo phòng ban"),
        ("Tasks by State", "Nghỉ phép theo loại"),
        ("Top Assignees", "Top nhân viên nghỉ nhiều"),
        ("Top Projects", "Top cửa hàng nghỉ nhiều"),
        ("Top Tags", "Top miền"),
        ("Top Customers", "Theo miền"),
        ("Assignee", "Nhân viên"),
        ("Hours Logged", "Số ngày nghỉ"),
        ("Hours logged", "Số ngày nghỉ"),
        ("Days to assign", "Chờ duyệt"),
        ("Days to close", "Tỷ lệ nghỉ"),
        ('"nbr"', '"__count"'),
        ("working_days_open", "number_of_days"),
        ("working_days_close", "number_of_days"),
    ]
    for old, new in replacements:
        value = value.replace(old, new)
  # scorecard titles
    value = value.replace('"Tasks"', '"Nghỉ phép"')
    value = value.replace("Tasks Analysis", "Phân tích nghỉ phép")
    return value


def walk(obj):
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            new_key = OLD_TO_NEW.get(key, key)
            out[new_key] = walk(value)
        return out
    if isinstance(obj, list):
        return [walk(item) for item in obj]
    if isinstance(obj, str):
        return replace_str(obj)
    return obj


def main():
    with open(SRC, encoding="utf-8") as handle:
        data = json.load(handle)

    out = walk(data)
    out["globalFilters"] = [
        {"id": F_DATE, "type": "date", "label": "Kỳ báo cáo", "defaultValue": "last_30_days"},
        {"id": F_MIEN, "type": "text", "label": "Miền", "defaultValue": ""},
        {
            "id": F_DEPT,
            "type": "relation",
            "label": "Phòng ban",
            "modelName": "hr.department",
            "defaultValueDisplayNames": [],
        },
        {
            "id": F_STORE,
            "type": "relation",
            "label": "Cửa hàng",
            "modelName": "hr.store",
            "defaultValueDisplayNames": [],
        },
        {"id": F_BLOCK, "type": "text", "label": "Khối (VP/CH)", "defaultValue": ""},
    ]

    for pivot in out.get("pivots", {}).values():
        pivot["model"] = "hr.leave.analytics.report"
        domain = list(pivot.get("domain") or [])
        if ["state", "=", "validate"] not in domain:
            domain.append(["state", "=", "validate"])
        pivot["domain"] = domain
        pivot["fieldMatching"] = FIELD_MATCHING
        pivot["measures"] = [
            {"id": "number_of_days", "fieldName": "number_of_days"},
            {"id": "__count", "fieldName": "__count"},
        ]
        if pivot.get("sortedColumn", {}).get("measure") == "nbr":
            pivot["sortedColumn"]["measure"] = "number_of_days"

    for sheet in out.get("sheets", []):
        for figure in sheet.get("figures", []):
            payload = figure.get("data", {})
            if "fieldMatching" in payload:
                payload["fieldMatching"] = FIELD_MATCHING
            meta = payload.get("metaData")
            if meta:
                meta["resModel"] = "hr.leave.analytics.report"
                if meta.get("measure") in ("nbr", "__count"):
                    meta["measure"] = "number_of_days"
            search_params = payload.get("searchParams")
            if search_params is not None:
                search_params["domain"] = [["state", "=", "validate"]]

    out["chartOdooMenusReferences"] = {
        key: "hr_holidays.menu_hr_holidays_report"
        for key in (out.get("chartOdooMenusReferences") or {})
    }

    os.makedirs(os.path.dirname(DEST), exist_ok=True)
    with open(DEST, "w", encoding="utf-8") as handle:
        json.dump(out, handle, ensure_ascii=False, indent=2)
    print(DEST)


if __name__ == "__main__":
    main()
