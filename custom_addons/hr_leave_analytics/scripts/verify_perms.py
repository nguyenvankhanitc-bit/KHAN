with open(r"d:\Lap_odoo\odoo_time_off_custom\scripts\verify_perms_out.txt", "w", encoding="utf-8") as f:
    for login in ["anh.trinh@sangtam.com", "admin.lug@sangtam.com"]:
        u = env["res.users"].sudo().search([("login", "=", login)], limit=1)
        xmlids = [env["ir.model.data"].search([("model", "=", "res.groups"), ("res_id", "=", g.id)], limit=1).complete_name for g in u.group_ids if "leave_analytics" in (env["ir.model.data"].search([("model", "=", "res.groups"), ("res_id", "=", g.id)], limit=1).module or "")]
        hr_groups = []
        for g in u.group_ids:
            data = env["ir.model.data"].search([("model", "=", "res.groups"), ("res_id", "=", g.id)], limit=1)
            if data.module == "hr_leave_analytics":
                hr_groups.append(data.name)
        f.write("%s miens=%s hr_groups=%s\n" % (login, u._hr_leave_analytics_allowed_miens_list(), hr_groups))
