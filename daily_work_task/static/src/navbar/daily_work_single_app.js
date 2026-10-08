/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";
import { NavBar } from "@web/webclient/navbar/navbar";
import { menuService } from "@web/webclient/menus/menu_service";

const DAILY_WORK_APP = "daily_work_task.menu_daily_work_root";

function isSingleAppUser() {
    return Boolean(session.daily_work_single_app);
}

if (isSingleAppUser()) {
    document.documentElement.classList.add("o_dw_single_app");
}

const _menuStart = menuService.start;
menuService.start = async function (env, deps) {
    const service = await _menuStart.call(this, env, deps);
    const getApps = service.getApps.bind(service);
    service.getApps = function () {
        const apps = getApps();
        if (!isSingleAppUser()) {
            return apps;
        }
        const only = apps.filter((app) => app.xmlid === DAILY_WORK_APP);
        return only.length ? only : apps;
    };
    const selectMenu = service.selectMenu.bind(service);
    service.selectMenu = async function (menu) {
        if (isSingleAppUser()) {
            const item = typeof menu === "number" ? service.getMenu(menu) : menu;
            const app = item && service.getMenu(item.appID);
            if (app && app.xmlid && app.xmlid !== DAILY_WORK_APP) {
                const home = service.getApps()[0];
                if (home) {
                    return selectMenu(home);
                }
                return;
            }
        }
        return selectMenu(menu);
    };
    return service;
};

patch(NavBar.prototype, {
    get dailyWorkSingleApp() {
        return isSingleAppUser();
    },

    /**
     * Cho mở sidebar để xem menu nội bộ (CÔNG VIỆC / BÁO CÁO),
     * nhưng không chuyển sang chế độ «Tất cả ứng dụng».
     */
    _openAppMenuSidebar() {
        if (this.dailyWorkSingleApp) {
            this.state.isAllAppsMenuOpened = false;
        }
        return super._openAppMenuSidebar(...arguments);
    },

    onAllAppsBtnClick() {
        if (this.dailyWorkSingleApp) {
            this.state.isAllAppsMenuOpened = false;
            return;
        }
        return super.onAllAppsBtnClick(...arguments);
    },
});
