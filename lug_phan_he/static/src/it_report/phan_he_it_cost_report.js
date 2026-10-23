/** @odoo-module **/

import { loadBundle } from "@web/core/assets";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, onWillUpdateProps, useEffect, useRef, useState } from "@odoo/owl";

const PIE_COLORS = [
    "#2ecc71",
    "#f1c40f",
    "#e74c3c",
    "#95a5a6",
    "#3498db",
    "#9b59b6",
    "#e67e22",
    "#1abc9c",
    "#34495e",
    "#fd79a8",
];

const SLICE_FIELDS = {
    month: "Tên thiết bị",
    asset: "Tên thiết bị",
    quarter: "Tháng",
    year: "Tháng",
    provider: "Nhà cung cấp",
};

function formatMoney(value) {
    return new Intl.NumberFormat("vi-VN").format(Math.round(Number(value || 0)));
}

export class PhanHeItCostReport extends Component {
    static template = "lug_phan_he.PhanHeItCostReport";
    static props = {
        reportKey: String,
        reloadToken: { type: Number, optional: true },
        onOpenCost: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.pieRef = useRef("pie");
        this.chart = null;
        this.state = useState({
            loading: true,
            exporting: false,
            sliceField: "Tên thiết bị",
            title: "",
            dimension: "",
            period: "",
            total: 0,
            count: 0,
            slices: [],
            rows: [],
        });
        onWillStart(async () => {
            await this.ensureChartLib();
            await this.load(this.props.reportKey);
        });
        onWillUpdateProps(async (next) => {
            if (next.reportKey !== this.props.reportKey || next.reloadToken !== this.props.reloadToken) {
                await this.load(next.reportKey);
            }
        });
        useEffect(
            () => {
                this.renderChart();
                return () => this.destroyChart();
            },
            () => [this.state.loading, this.state.slices.map((slice) => `${slice.label}:${slice.amount}`).join("|")]
        );
        onWillUnmount(() => this.destroyChart());
    }

    async ensureChartLib() {
        if (typeof Chart !== "undefined") {
            return;
        }
        try {
            await loadBundle("web.chartjs_lib");
        } catch (error) {
            console.warn("it cost pie chart", error);
        }
    }

    async load(reportKey) {
        const key = reportKey || this.props.reportKey;
        this.state.loading = true;
        this.destroyChart();
        try {
            const data = await this.orm.call("phan.he.it.cost", "get_it_cost_pie_report", [key]);
            this.state.title = data?.title || "";
            this.state.dimension = data?.dimension || "";
            this.state.period = data?.period || "";
            this.state.total = data?.total || 0;
            this.state.count = data?.count || 0;
            this.state.sliceField = SLICE_FIELDS[key] || "Nội dung";
            this.state.slices = (data?.slices || []).map((slice, index) => ({
                ...slice,
                color: PIE_COLORS[index % PIE_COLORS.length],
            }));
            this.state.rows = data?.rows || [];
        } catch (error) {
            console.error(error);
            this.state.slices = [];
            this.state.rows = [];
            this.notification.add(
                error?.data?.message || error?.message || "Không tải được báo cáo.",
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    destroyChart() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }

    renderChart() {
        this.destroyChart();
        const canvas = this.pieRef.el;
        if (this.state.loading || !canvas || typeof Chart === "undefined" || !this.state.slices.length) {
            return;
        }
        const slices = this.state.slices;
        const total = Number(this.state.total || 0);
        const centerPlugin = {
            id: "itCostDonutCenter",
            afterDraw: (chart) => {
                const meta = chart.getDatasetMeta(0);
                if (!meta?.data?.length) {
                    return;
                }
                const { x, y } = meta.data[0];
                const ctx = chart.ctx;
                ctx.save();
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillStyle = "#1e293b";
                ctx.font = "700 28px Inter, system-ui, sans-serif";
                ctx.fillText(formatMoney(total), x, y - 10);
                ctx.fillStyle = "#94a3b8";
                ctx.font = "500 13px Inter, system-ui, sans-serif";
                ctx.fillText("Tổng chi phí", x, y + 16);
                ctx.restore();
            },
        };
        this.chart = new Chart(canvas, {
            type: "doughnut",
            data: {
                labels: slices.map((slice) => slice.label),
                datasets: [
                    {
                        data: slices.map((slice) => Number(slice.amount || 0)),
                        backgroundColor: slices.map((slice) => slice.color),
                        borderColor: "#ffffff",
                        borderWidth: 4,
                        hoverOffset: 4,
                        spacing: 2,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "68%",
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (item) => {
                                const slice = slices[item.dataIndex];
                                return ` ${this.state.sliceField} - ${slice.label}: ${formatMoney(slice.amount)} đ (${slice.percent}%)`;
                            },
                        },
                    },
                },
            },
            plugins: [centerPlugin],
        });
    }

    formatMoney(value) {
        return formatMoney(value);
    }

    openRow(row) {
        if (row?.id && this.props.onOpenCost) {
            this.props.onOpenCost(row.id);
        }
    }

    async exportExcel() {
        if (this.state.exporting) {
            return;
        }
        this.state.exporting = true;
        try {
            const result = await this.orm.call("phan.he.it.cost", "export_it_cost_pie_excel", [
                this.props.reportKey,
            ]);
            if (!result?.file_base64) {
                throw new Error("Không nhận được file Excel.");
            }
            const binary = atob(result.file_base64);
            const bytes = new Uint8Array(binary.length);
            for (let index = 0; index < binary.length; index++) {
                bytes[index] = binary.charCodeAt(index);
            }
            const blob = new Blob([bytes], {
                type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = result.filename || "Bao_cao_may_chu.xlsx";
            link.click();
            URL.revokeObjectURL(url);
            this.notification.add("Đã xuất file Excel.", { type: "success" });
        } catch (error) {
            console.error(error);
            this.notification.add(
                error?.data?.message || error?.message || "Không xuất được Excel.",
                { type: "danger" }
            );
        } finally {
            this.state.exporting = false;
        }
    }
}
