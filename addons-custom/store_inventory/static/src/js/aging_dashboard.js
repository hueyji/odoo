/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

class AgingDashboard extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            summary: [],
            top_batches: {},
            total_qty: 0,
            total_batches: 0,
            generated_on: null,
        });
        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.rpc("/store_inventory/aging_dashboard/data", {});
            this.state.summary = data.summary || [];
            this.state.top_batches = data.top_batches || {};
            this.state.total_qty = data.total_qty || 0;
            this.state.total_batches = data.total_batches || 0;
            this.state.generated_on = data.generated_on || null;
            this.state.bucket_defs = data.bucket_defs || [];
        } catch (error) {
            console.error("Failed to load aging dashboard data", error);
            this.notification.add(_t("加载陈化看板数据失败，请稍后重试。"), { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    bucketColor(key) {
        const mapping = {
            "0_30": "bg-success",
            "31_90": "bg-info",
            "91_180": "bg-warning",
            "181_365": "bg-primary",
            "gt_365": "bg-danger",
        };
        return mapping[key] || "bg-secondary";
    }

    topBatches(key) {
        return this.state.top_batches?.[key] || [];
    }

    formatNumber(value) {
        if (value === undefined || value === null) {
            return "0";
        }
        return Number(value).toLocaleString();
    }

    exportReport() {
        window.open("/store_inventory/aging_dashboard/export", "_blank");
    }

    async refresh() {
        await this.loadData();
    }
}

AgingDashboard.template = "store_inventory.AgingDashboard";

registry.category("actions").add("store_inventory_aging_dashboard", AgingDashboard);

export default AgingDashboard;
