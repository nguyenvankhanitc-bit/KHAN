rows = env["hr.leave.analytics.employee.watch"].search([("employee_mien", "=", "Nam")])
all_rows = env["hr.leave.analytics.employee.watch"].search([])
with open(r"d:\Lap_odoo\odoo_time_off_custom\scripts\verify_mien_filter_out.txt", "w", encoding="utf-8") as f:
    f.write("all=%s nam=%s\n" % (len(all_rows), len(rows)))
    for r in all_rows:
        f.write("%s mien=%s\n" % (r.employee_name, r.employee_mien))
