# -*- coding: utf-8 -*-
{
    "name": "Refuse Ticket Notifier",
    "version": "19.0.1.0.2",
    "category": "Human Resources",
    "summary": "Notify all approvers via OdooBot when time off requests are refused",
    "description": """
        When a time off request is refused, all approvers in the approval chain
        receive a Discuss DM from OdooBot with the refusal notification.
    """,
    "depends": [
        "hr_holidays",
    ],
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}
