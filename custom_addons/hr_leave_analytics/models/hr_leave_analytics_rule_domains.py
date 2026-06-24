# Part of Odoo. See LICENSE file for full copyright and licensing details.

"""domain_force for analytics SQL views filtered by allowed miền."""


def hr_leave_analytics_mien_rule_domain():
  return (
      "[(1, '=', 1)] if user.hr_leave_analytics_allowed_miens is None "
      "else [('employee_mien', 'in', user.hr_leave_analytics_allowed_miens or [''])]"
  )


HR_LEAVE_ANALYTICS_MIEN_RULE_DOMAIN = hr_leave_analytics_mien_rule_domain()
