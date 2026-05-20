# -*- coding: utf-8 -*-
{
    'name': 'Employee Checklist',
    'version': '19.0.2.0.0',
    'category': 'Human Resources',
    'summary': 'Monthly employee inspection checklist with daily pass/fail tracking',
    'depends': ['base', 'mail', 'hr'],
    'data': [
        'security/hr_employee_checklist_security.xml',
        'security/ir.model.access.csv',
        'views/checklist_menu_views.xml',
        'views/checklist_stage_views.xml',
        'views/checklist_tag_views.xml',
        'views/checklist_line_views.xml',
        'views/checklist_employee_entry_views.xml',
        'views/checklist_schedule_line_views.xml',
        'views/checklist_checklist_views.xml',
    ],
    'license': 'LGPL-3',
    'author': 'Custom',
    'installable': True,
    'application': True,
    'auto_install': False,
}
