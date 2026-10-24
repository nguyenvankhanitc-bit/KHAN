/** @odoo-module **/

const SERVER_NAV_TO_CODE = {
    overview: "overview_dashboard",
};

export function serverMenuCan(menus, code, op = "read") {
    if (!code) {
        return false;
    }
    const row = (menus || {})[code] || {};
    if (row.admin) {
        return true;
    }
    return Boolean(row[op]);
}

export function serverNavCan(menus, navId, op = "read") {
    const code = SERVER_NAV_TO_CODE[navId] || navId;
    return serverMenuCan(menus, code, op);
}

export function serverNavCreate(menus, navId) {
    if (serverNavCan(menus, navId, "create")) {
        return true;
    }
    const key = String(navId || "");
    if (key.startsWith("it_asset")) {
        return serverNavCan(menus, "it_asset_new", "create");
    }
    if (key.startsWith("it_cost")) {
        return serverNavCan(menus, "it_cost_new", "create");
    }
    return false;
}

export function filterServerNavSections(sections, menus) {
    return (sections || [])
        .map((section) => {
            const children = (section.children || []).filter((child) =>
                serverNavCan(menus, child.id)
            );
            if (!children.length) {
                return null;
            }
            return { ...section, children };
        })
        .filter(Boolean);
}

export function firstAllowedServerNav(sections) {
    for (const section of sections || []) {
        const child = (section.children || [])[0];
        if (child) {
            return child;
        }
    }
    return null;
}
