/** @odoo-module **/

import { registry } from "@web/core/registry";

export const geolocationService = {
    dependencies: ["rpc", "user"],
    start(env, { rpc, user }) {
        const STORAGE_KEY = "odoo_last_gps_sync";
        const SYNC_INTERVAL_MS = 5 * 60 * 1000; // 5 phút throttle

        const queryAndSyncLocation = () => {
            if (!navigator.geolocation || !user.userId) {
                return;
            }

            const lastSync = parseInt(sessionStorage.getItem(STORAGE_KEY) || "0", 10);
            const now = Date.now();
            if (now - lastSync < SYNC_INTERVAL_MS) {
                return; // Chưa đến chu kỳ 5 phút
            }

            navigator.geolocation.getCurrentPosition(
                async (position) => {
                    const coords = position.coords;
                    try {
                        await rpc("/hr_employee_location/update_position", {
                            latitude: coords.latitude,
                            longitude: coords.longitude,
                            accuracy: coords.accuracy,
                        });
                        sessionStorage.setItem(STORAGE_KEY, String(Date.now()));
                    } catch (err) {
                        // Bỏ qua lỗi kết nối ngầm để không ảnh hưởng người dùng
                        console.warn("[GeolocationService] RPC sync failed:", err);
                    }
                },
                (error) => {
                    // Người dùng từ chối cấp quyền hoặc timeout -> im lặng bỏ qua
                    if (error.code !== error.PERMISSION_DENIED) {
                        console.debug("[GeolocationService] Position error:", error.message);
                    }
                },
                {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 60000,
                }
            );
        };

        // Kích hoạt khi tải trang và sau khi login
        setTimeout(queryAndSyncLocation, 2000);

        return {
            syncNow: queryAndSyncLocation,
        };
    },
};

registry.category("services").add("hr_employee_geolocation", geolocationService);
