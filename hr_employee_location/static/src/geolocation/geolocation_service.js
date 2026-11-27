/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { user } from "@web/core/user";

// Xóa device_id tự sinh cũ trong localStorage nếu có
try {
    localStorage.removeItem("odoo_device_id");
} catch (_e) {}

function getDeviceInfo() {
    const ua = typeof navigator !== "undefined" ? navigator.userAgent || "" : "";
    let deviceType = "computer";
    let osName = "Windows";
    let browserName = "Trình duyệt";

    // 1. Phân loại OS & Device Type
    if (/android/i.test(ua)) {
        osName = "Android";
        deviceType = /mobile/i.test(ua) ? "mobile" : "tablet";
    } else if (/iphone/i.test(ua)) {
        osName = "iPhone";
        deviceType = "mobile";
    } else if (/ipad/i.test(ua) || (/macintosh/i.test(ua) && typeof navigator !== "undefined" && navigator.maxTouchPoints > 1)) {
        osName = "iPad";
        deviceType = "tablet";
    } else if (/win/i.test(ua)) {
        osName = "Windows";
        deviceType = "computer";
    } else if (/mac/i.test(ua)) {
        osName = "macOS";
        deviceType = "computer";
    } else if (/linux/i.test(ua)) {
        osName = "Linux";
        deviceType = "computer";
    }

    // 2. Phân loại Browser
    if (/edg/i.test(ua)) {
        browserName = "Edge";
    } else if (/opr\//i.test(ua)) {
        browserName = "Opera";
    } else if (/chrome|crios/i.test(ua)) {
        browserName = "Chrome";
    } else if (/firefox|fxios/i.test(ua)) {
        browserName = "Firefox";
    } else if (/safari/i.test(ua)) {
        browserName = "Safari";
    }

    return {
        deviceName: `${osName} (${browserName})`,
        deviceType: deviceType,
    };
}

export const geolocationService = {
    start() {
        const STORAGE_KEY = "odoo_last_gps_sync";
        const SYNC_INTERVAL_MS = 5 * 60 * 1000; // 5 phút throttle

        const queryAndSyncLocation = () => {
            if (!user.userId) {
                return;
            }

            const lastSync = parseInt(sessionStorage.getItem(STORAGE_KEY) || "0", 10);
            const now = Date.now();
            if (now - lastSync < SYNC_INTERVAL_MS) {
                return; // Chưa đến chu kỳ 5 phút
            }

            const info = getDeviceInfo();

            const sendPayload = async (coords = null) => {
                try {
                    const payload = {
                        device_name: info.deviceName,
                        device_type: info.deviceType,
                    };
                    if (coords) {
                        payload.latitude = coords.latitude;
                        payload.longitude = coords.longitude;
                        payload.accuracy = coords.accuracy;
                    }
                    await rpc("/hr_employee_location/update_position", payload);
                    sessionStorage.setItem(STORAGE_KEY, String(Date.now()));
                } catch (err) {
                    console.warn("[GeolocationService] Background sync failed:", err);
                }
            };

            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    (position) => sendPayload(position.coords),
                    () => sendPayload(null), // Nếu từ chối cấp quyền GPS hoặc timeout, vẫn đồng bộ thông tin thiết bị
                    {
                        enableHighAccuracy: false,
                        timeout: 5000,
                        maximumAge: 300000,
                    }
                );
            } else {
                sendPayload(null);
            }
        };

        // Kích hoạt khi tải trang và sau khi login
        setTimeout(queryAndSyncLocation, 2000);

        return {
            syncNow: queryAndSyncLocation,
            getDeviceInfo,
        };
    },
};

registry.category("services").add("hr_employee_geolocation", geolocationService);
