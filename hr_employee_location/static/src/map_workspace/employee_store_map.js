/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

export class EmployeeStoreMap extends Component {
    static template = "hr_employee_location.EmployeeStoreMap";
    static props = { ...standardActionServiceProps, "*": true };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.mapContainer = useRef("mapContainer");

        this.map = null;
        this.storeLayerGroup = null;
        this.employeeLayerGroup = null;
        this.networkLayerGroup = null;

        this.state = useState({
            employees: [],
            stores: [],
            storesById: {},
            selectedEmployeeId: null,
            searchQuery: "",
            filterStatus: "all", // all, active, stale, none
            isLoading: true,
            stats: {
                totalEmployees: 0,
                activeGpsCount: 0,
                totalStores: 0,
            },
        });

        onMounted(async () => {
            this.initMap();
            await this.loadData();
        });

        onWillUnmount(() => {
            if (this.map) {
                this.map.remove();
                this.map = null;
            }
        });
    }

    initMap() {
        if (!window.L) {
            console.error("Leaflet library (L) is not loaded");
            return;
        }

        const el = this.mapContainer.el;
        // Tọa độ mặc định trung tâm (Việt Nam / TP.HCM)
        this.map = window.L.map(el, {
            zoomControl: true,
            attributionControl: true,
        }).setView([10.7769, 106.7009], 12);

        // Tile layer OpenStreetMap chuẩn
        window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors',
        }).addTo(this.map);

        // Khởi tạo các nhóm layer để dễ xóa/vẽ lại
        this.storeLayerGroup = window.L.layerGroup().addTo(this.map);
        this.networkLayerGroup = window.L.layerGroup().addTo(this.map);
        this.employeeLayerGroup = window.L.layerGroup().addTo(this.map);

        setTimeout(() => {
            if (this.map) {
                this.map.invalidateSize();
            }
        }, 200);
    }

    async loadData() {
        this.state.isLoading = true;
        try {
            const [employees, stores] = await Promise.all([
                this.orm.searchRead(
                    "hr.employee",
                    [["active", "=", true]],
                    [
                        "id",
                        "name",
                        "job_title",
                        "work_email",
                        "last_latitude",
                        "last_longitude",
                        "last_location_time",
                        "gps_status",
                        "store_ids",
                    ],
                    { order: "name asc" }
                ),
                this.orm.searchRead(
                    "hr.store",
                    [],
                    ["id", "name", "code", "address", "latitude", "longitude", "geocode_status"],
                    { order: "name asc" }
                ),
            ]);

            const storesMap = {};
            stores.forEach((st) => {
                storesMap[st.id] = st;
            });

            this.state.employees = employees;
            this.state.stores = stores;
            this.state.storesById = storesMap;

            // Thống kê
            this.state.stats.totalEmployees = employees.length;
            this.state.stats.activeGpsCount = employees.filter((e) => e.gps_status === "active").length;
            this.state.stats.totalStores = stores.length;

            this.renderStoreMarkers();
        } catch (error) {
            this.notification.add("Lỗi khi tải dữ liệu nhân viên và cửa hàng: " + error.message, {
                type: "danger",
            });
        } finally {
            this.state.isLoading = false;
        }
    }

    createStoreIcon(storeName) {
        return window.L.divIcon({
            className: "o_leaflet_store_marker",
            html: `
                <div class="o_store_pin_wrapper">
                    <div class="o_store_pin_badge">
                        <i class="fa fa-shopping-bag"></i>
                    </div>
                    <div class="o_store_pin_label">${storeName}</div>
                </div>
            `,
            iconSize: [120, 40],
            iconAnchor: [60, 36],
        });
    }

    createEmployeeIcon(empName) {
        return window.L.divIcon({
            className: "o_leaflet_emp_marker",
            html: `
                <div class="o_emp_pin_wrapper">
                    <div class="o_emp_pin_pulse"></div>
                    <div class="o_emp_pin_badge">
                        <i class="fa fa-user"></i>
                    </div>
                    <div class="o_emp_pin_label">${empName}</div>
                </div>
            `,
            iconSize: [120, 44],
            iconAnchor: [60, 40],
        });
    }

    renderStoreMarkers() {
        if (!this.map || !this.storeLayerGroup) return;
        this.storeLayerGroup.clearLayers();

        const markers = [];
        this.state.stores.forEach((store) => {
            if (store.latitude && store.longitude) {
                const marker = window.L.marker([store.latitude, store.longitude], {
                    icon: this.createStoreIcon(store.name),
                });
                marker.bindPopup(`
                    <div class="o_store_popup">
                        <h6 class="mb-1 text-primary"><i class="fa fa-store me-1"></i>${store.name}</h6>
                        <div class="text-muted small mb-1">Mã CH: <b>${store.code || ""}</b></div>
                        <div class="small">${store.address || "Chưa có địa chỉ"}</div>
                        <div class="mt-2 text-muted small">Tọa độ: ${store.latitude.toFixed(5)}, ${store.longitude.toFixed(5)}</div>
                    </div>
                `);
                this.storeLayerGroup.addLayer(marker);
                markers.push(marker);
            }
        });

        if (markers.length > 0 && !this.state.selectedEmployeeId) {
            const group = window.L.featureGroup(markers);
            this.map.fitBounds(group.getBounds().pad(0.15));
        }
    }

    // Công thức Haversine tính khoảng cách theo km giữa 2 tọa độ
    calculateHaversineKm(lat1, lon1, lat2, lon2) {
        const R = 6371; // Bán kính Trái Đất (km)
        const dLat = ((lat2 - lat1) * Math.PI) / 180;
        const dLon = ((lon2 - lon1) * Math.PI) / 180;
        const a =
            Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos((lat1 * Math.PI) / 180) *
                Math.cos((lat2 * Math.PI) / 180) *
                Math.sin(dLon / 2) *
                Math.sin(dLon / 2);
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;
    }

    selectEmployee(employee) {
        this.state.selectedEmployeeId = employee.id;
        if (!this.map) return;

        this.employeeLayerGroup.clearLayers();
        this.networkLayerGroup.clearLayers();

        const boundsPoints = [];

        // 1. Kiểm tra vị trí của nhân viên
        const hasEmpCoords = employee.last_latitude && employee.last_longitude;
        if (hasEmpCoords) {
            const empCoords = [employee.last_latitude, employee.last_longitude];
            const empMarker = window.L.marker(empCoords, {
                icon: this.createEmployeeIcon(employee.name),
                zIndexOffset: 1000,
            });
            empMarker.bindPopup(`
                <div class="o_emp_popup">
                    <h6 class="mb-1 text-success"><i class="fa fa-user-circle me-1"></i>${employee.name}</h6>
                    <div class="text-muted small">${employee.job_title || "Nhân viên"}</div>
                    <div class="small mt-1">Cập nhật lúc: <b>${employee.last_location_time || "Chưa rõ"}</b></div>
                    <div class="mt-1 text-muted small">Tọa độ: ${employee.last_latitude.toFixed(5)}, ${employee.last_longitude.toFixed(5)}</div>
                </div>
            `);
            this.employeeLayerGroup.addLayer(empMarker);
            boundsPoints.push(empCoords);
        } else {
            this.notification.add(
                `Nhân viên ${employee.name} chưa ghi nhận tọa độ GPS gần đây. Bản đồ hiển thị các cửa hàng trực thuộc.`,
                { type: "warning" }
            );
        }

        // 2. Tìm tất cả cửa hàng trực thuộc nhân viên này
        const assignedStoreIds = employee.store_ids || [];
        assignedStoreIds.forEach((storeId) => {
            const store = this.state.storesById[storeId];
            if (store && store.latitude && store.longitude) {
                const storeCoords = [store.latitude, store.longitude];
                boundsPoints.push(storeCoords);

                // Nếu có vị trí nhân viên -> vẽ tia mạng lưới (network ray polyline)
                if (hasEmpCoords) {
                    const distKm = this.calculateHaversineKm(
                        employee.last_latitude,
                        employee.last_longitude,
                        store.latitude,
                        store.longitude
                    );

                    const polyline = window.L.polyline(
                        [
                            [employee.last_latitude, employee.last_longitude],
                            [store.latitude, store.longitude],
                        ],
                        {
                            color: "#0d6efd",
                            weight: 3.5,
                            opacity: 0.85,
                            dashArray: "8, 8",
                            lineCap: "round",
                        }
                    );

                    polyline.bindTooltip(
                        `<div class="o_distance_tooltip">
                            <b>${store.name}</b><br/>
                            Khoảng cách: <span class="badge bg-primary text-white">${distKm.toFixed(2)} km</span>
                        </div>`,
                        {
                            permanent: false,
                            sticky: true,
                            direction: "top",
                        }
                    );

                    this.networkLayerGroup.addLayer(polyline);
                }
            }
        });

        // 3. Tự động điều chỉnh góc nhìn (fitBounds)
        if (boundsPoints.length > 1) {
            this.map.fitBounds(window.L.latLngBounds(boundsPoints).pad(0.2), {
                maxZoom: 15,
                animate: true,
            });
        } else if (boundsPoints.length === 1) {
            this.map.setView(boundsPoints[0], 14, { animate: true });
        }
    }

    resetView() {
        this.state.selectedEmployeeId = null;
        this.employeeLayerGroup.clearLayers();
        this.networkLayerGroup.clearLayers();
        this.renderStoreMarkers();
    }

    get filteredEmployees() {
        const query = (this.state.searchQuery || "").trim().toLowerCase();
        const status = this.state.filterStatus;

        return this.state.employees.filter((emp) => {
            const matchesQuery =
                !query ||
                (emp.name && emp.name.toLowerCase().includes(query)) ||
                (emp.job_title && emp.job_title.toLowerCase().includes(query));

            const matchesStatus =
                status === "all" ||
                (status === "active" && emp.gps_status === "active") ||
                (status === "stale" && emp.gps_status === "stale") ||
                (status === "none" && emp.gps_status === "none");

            return matchesQuery && matchesStatus;
        });
    }
}

registry.category("actions").add("hr_employee_location.map_workspace", EmployeeStoreMap);
