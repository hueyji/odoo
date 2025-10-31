/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

class BatchAgingBoard extends Component {
    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.state = useState({ metrics: [], updated: null });

        onWillStart(async () => {
            await this.loadMetrics();
        });
    }

    async loadMetrics() {
        try {
            const data = await this.orm.call("store.inventory.batch", "action_get_aging_metrics", [], {});
            this.state.metrics = data.metrics || [];
            this.state.updated = data.generated_at;
        } catch (error) {
            this.notification.add(_t("无法加载陈化数据，请稍后重试。"), {
                type: "danger",
            });
            throw error;
        }
    }

    openStage(stage) {
        const name = this.state.metrics.find((metric) => metric.stage === stage)?.label || _t("批次明细");
        this.actionService.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: "store.inventory.batch",
            view_mode: "tree,form",
            domain: [
                ["state", "in", ["in_stock", "transit"]],
                ["aging_stage", "=", stage],
            ],
        });
    }
}

BatchAgingBoard.template = "store_inventory.BatchAgingBoardTemplate";

registry.category("actions").add("store_inventory_batch_board", (env, action) => {
    return {
        Component: BatchAgingBoard,
        props: { action },
    };
});
