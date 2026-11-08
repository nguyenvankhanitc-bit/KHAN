from odoo import api, models


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    @api.model
    def _build_wkhtmltopdf_args(self, *args, **kwargs):
        # wkhtmltopdf trên Windows đoán sai charset nên tiếng Việt trong PDF bị vỡ font
        return super()._build_wkhtmltopdf_args(*args, **kwargs) + ['--encoding', 'utf-8']
