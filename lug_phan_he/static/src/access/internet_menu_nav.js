/** @odoo-module **/

export const INTERNET_NAV_TO_CODE = {
    overview: "overview_dashboard",
    manage: "group_manage_internet",
    list_all: "internet_active",
    list_active: "internet_active",
    list_suspend: "internet_suspend",
    list_liquidated: "internet_liquidation",
    store_declare: "internet_entry",
    payment: "group_cost_payment",
    payment_schedule: "payment_schedule",
    payment_confirm: "payment_confirm",
    payment_overdue: "payment_overdue",
    payment_forecast: "payment_forecast",
    // Legacy aliases (menu cũ)
    payment_track: "payment_confirm",
    payment_tracking: "payment_confirm",
    alert_due_soon: "payment_schedule",
    alert_overdue: "payment_overdue",
    expire_soon: "payment_schedule",
    expired: "payment_overdue",
    alerts: "group_cost_payment",
    group_alerts: "group_cost_payment",
    reports: "group_reports",
    report_month: "report_month",
    report_quarter: "report_quarter",
    report_year: "report_year",
    settings: "group_settings",
    settings_store: "setting_store",
    settings_area: "setting_area",
    settings_region: "setting_region",
    settings_provider: "setting_provider",
    settings_bank: "setting_bank",
};

export function internetMenuCan(menus, code, op = "read") {
    if (!code) {
        return false;
    }
    const row = (menus || {})[code] || {};
    return Boolean(row[op]);
}

export function internetNavCan(menus, navId, op = "read") {
    const code = INTERNET_NAV_TO_CODE[navId] || navId;
    return internetMenuCan(menus, code, op);
}

export function filterInternetNavSections(sections, menus) {
    return (sections || [])
        .map((section) => {
            const children = (section.children || []).filter((child) =>
                internetNavCan(menus, child.id)
            );
            if (!children.length) {
                return null;
            }
            return { ...section, children };
        })
        .filter(Boolean);
}

export function firstAllowedInternetNav(sections) {
    for (const section of sections || []) {
        const child = (section.children || [])[0];
        if (child) {
            return child;
        }
    }
    return null;
}
