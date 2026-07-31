# -*- coding: utf-8 -*-

from odoo import api, models


class LugAppCenter(models.AbstractModel):
    _name = "lug.app.center"
    _description = "Enterprise Application Center"

    @api.model
    def get_portal_data(self):
        """User/company header data. App list comes from the web menu service."""
        user = self.env.user
        company = self.env.company
        partner = user.partner_id

        first_name = "bạn"
        if user.name:
            first_name = user.name.split()[-1]

        avatar_url = False
        if partner and partner.image_128:
            avatar_url = f"/web/image/res.partner/{partner.id}/image_128"

        return {
            "company_name": "CÔNG TY TNHH SÁNG TÂM",
            "company_slogan": "Bền vững hôm nay - Thịnh vượng ngày mai",
            "company_website": "www.sangtam.com.vn",
            "company_address": self._format_company_address(company),
            "company_logo_url": (
                f"/web/image/res.company/{company.id}/logo"
                if company.logo
                else "/lug_app_center/static/src/img/sataco_logo.png"
            ),
            "user_name": user.name,
            "user_first_name": first_name,
            "user_login": user.login or "",
            "user_email": user.email or partner.email or "",
            "user_phone": user.phone or partner.phone or "",
            "user_role": (
                "Quản trị hệ thống"
                if user.has_group("base.group_system")
                else "Người dùng"
            ),
            "user_initial": (user.name or "U")[:1].upper(),
            "avatar_url": avatar_url,
            "welcome": "Chào mừng bạn đến với hệ thống quản trị doanh nghiệp",
        }

    @api.model
    def _format_company_address(self, company):
        parts = [
            company.street,
            company.street2,
            company.city,
            company.state_id.name if company.state_id else False,
            company.country_id.name if company.country_id else False,
        ]
        return ", ".join(part for part in parts if part) or (
            "30-34 Đường 74, Phường Bình Phú, TP. Hồ Chí Minh"
        )
