import json
import os


def migrate(cr, version):
    if not version:
        return
    from odoo import api, SUPERUSER_ID

    env = api.Environment(cr, SUPERUSER_ID, {})
    dashboard = env.ref("hr_leave_analytics.spreadsheet_dashboard_leave", raise_if_not_found=False)
    if not dashboard:
        return

    module_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = os.path.join(module_path, "data", "files", "leave_dashboard.json")
    with open(json_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    dashboard.write({"spreadsheet_data": json.dumps(payload)})
