# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    "name": "Business Discuss Bots",
    "version": "19.0.1.0.3",
    "category": "Productivity",
    "summary": "Business-specific Discuss bots for workflow notifications",
    "depends": ["mail_bot"],
    "post_init_hook": "post_init_hook",
    "data": [
        "data/discuss_bot_users.xml",
        "data/ir_cron_data.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "business_discuss_bots/static/src/css/discuss_table.css",
            "business_discuss_bots/static/src/js/thread_model_patch.js",
        ],
    },
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
