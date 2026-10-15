/** @odoo-module **/
import { Component, onWillStart, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { loadBundle } from "@web/core/assets";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { useSetupAction } from "@web/search/action_hook";
import { localization } from "@web/core/l10n/localization";
import { _t } from "@web/core/l10n/translation";

const { DateTime } = luxon;
const PALETTE = ["#7954b3", "#32a89a", "#e5a044", "#5692d2", "#c97b9f"];

class DashboardChart extends Component {
    static template = "fitzone.ManagementChart";
    static props = { title: String, config: Object, empty: Boolean };
    setup() {
        this.canvas = useRef("canvas");
        this.chart = null;
        useEffect(() => {
            this.destroy();
            if (!this.props.empty && this.canvas.el) {
                const color = getComputedStyle(this.canvas.el).getPropertyValue("color");
                const config = this.props.config;
                this.chart = new Chart(this.canvas.el, {
                    ...config,
                    options: {
                        responsive: true, maintainAspectRatio: false,
                        ...config.options,
                        animation: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : undefined,
                        ...(config.type !== "doughnut" ? { scales: {
                            x: { ticks: { color }, grid: { color: "rgba(125,118,139,.12)" } },
                            y: { beginAtZero: true, ticks: { color }, grid: { color: "rgba(125,118,139,.12)" } },
                        } } : {}),
                        plugins: { ...config.options?.plugins, legend: { position: "bottom", labels: { color, usePointStyle: true, padding: 18 }, ...config.options?.plugins?.legend } },
                    },
                });
            }
            return () => this.destroy();
        }, () => [this.props.config, this.props.empty]);
        onWillUnmount(() => this.destroy());
    }
    destroy() {
        if (this.chart) { this.chart.destroy(); this.chart = null; }
    }
}

export class ManagementDashboard extends Component {
    performanceLabel(d) {
        if (d.trend.length > 45) {
            return _t("Daily performance");
        }
        return d.date_to > d.date_from
            ? _t("Performance over the selected period")
            : _t("Today's performance");
    }

    static template = "fitzone.ManagementDashboard";
    static components = { DashboardChart };
    static props = { ...standardActionServiceProps };
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        const today = DateTime.local();
        this.state = useState({ loading: true, error: null, data: null, preset: "month",
            dateFrom: today.startOf("month").toISODate(), dateTo: today.toISODate(), department: "", sources: false, ...this.props.state?.filters });
        useSetupAction({ getLocalState: () => ({ filters: { preset: this.state.preset, dateFrom: this.state.dateFrom, dateTo: this.state.dateTo, department: this.state.department } }) });
        this.request = 0;
        this.alive = true;
        onWillStart(async () => {
            try { await loadBundle("web.chartjs_lib"); await this.reload(); }
            catch (error) { this.state.error = error.message; this.state.loading = false; }
        });
        onWillUnmount(() => { this.alive = false; this.request++; });
    }
    async reload() {
        const request = ++this.request;
        this.state.loading = true;
        this.state.error = null;
        this.state.sources = false;
        try {
            // Retry bundle loading as well as RPC after an initial asset/network failure.
            await loadBundle("web.chartjs_lib");
            const data = await this.orm.call("fitzone.management.dashboard", "get_dashboard_data", [], {
                date_from: this.state.dateFrom, date_to: this.state.dateTo, department: this.state.department || null,
            });
            if (this.alive && request === this.request) { this.state.data = data; }
        } catch (error) {
            if (this.alive && request === this.request) { this.state.error = error.data?.message || error.message; }
        } finally {
            if (this.alive && request === this.request) { this.state.loading = false; }
        }
    }
    changePreset(event) {
        const preset = event.target.value;
        this.state.preset = preset;
        if (preset === "custom") { return; }
        const now = DateTime.local();
        const units = { today: "day", week: "week", month: "month", quarter: "quarter", year: "year" };
        this.state.dateFrom = now.startOf(units[preset]).toISODate();
        this.state.dateTo = now.toISODate();
        this.reload();
    }
    changeDate(key, event) {
        this.state[key] = event.target.value;
        if (this.state.dateFrom && this.state.dateTo) { this.reload(); }
    }
    get departments() { return this.state.data?.department_options || []; }
    changeDepartment(event) { this.state.department = event.target.value; this.reload(); }
    number(value, type = "number") {
        const options = type === "money" ? { style: "currency", currency: this.state.data.currency,
            minimumFractionDigits: this.state.data.currency_digits, maximumFractionDigits: this.state.data.currency_digits } :
            { minimumFractionDigits: type === "percent" ? 1 : 0, maximumFractionDigits: type === "percent" ? 1 : 0 };
        return new Intl.NumberFormat((localization.code || navigator.language).replaceAll("_", "-"), options).format(value || 0) + (type === "percent" ? "%" : "");
    }
    get refreshed() {
        const data = this.state.data;
        return data ? DateTime.fromSQL(data.refreshed_at, { zone: "utc" }).toLocal().toLocaleString(DateTime.TIME_WITH_SECONDS) : "—";
    }
    get cards() {

        const definitions = [
            ["total_revenue", _t("Total revenue"), "money", "fa-line-chart", false],
            ["total_expenses", _t("Total expenses"), "money", "fa-credit-card", true],
            ["net_revenue", _t("Net revenue"), "money", "fa-balance-scale", false],
            ["net_margin_percent", _t("Net margin"), "percent", "fa-pie-chart", false],
            ["active_memberships", _t("Active memberships"), "number", "fa-id-card-o", false],
            ["new_members", _t("New members"), "number", "fa-user-plus", false],
            ["overall_occupancy_percent", _t("Overall occupancy"), "percent", "fa-building-o", false],
            ["overdue_installments_amount", _t("Overdue installments"), "money", "fa-clock-o", true],
        ];

        return definitions.map(([key, label, type, icon, inverse]) => {
            const trend = this.state.data.trends[key];
            return { key, label, icon, value: this.number(this.state.data.kpis[key], type), trend,
                trendLabel: trend === null ? "New activity" : `${trend > 0 ? "+" : ""}${this.number(trend, "percent")}`,
                good: trend === null || (inverse ? trend <= 0 : trend >= 0),
            };
        });
    }
    drill(key, filters = {}) { return this.openSource(key, filters); }
    async openSource(key, filters = {}) {
        const action = await this.orm.call("fitzone.management.dashboard", "get_dashboard_action", [], {
            metric: key, date_from: this.state.dateFrom, date_to: this.state.dateTo,
            department: this.state.department || null, ...filters,
        });
        return this.action.doAction(action);
    }
    openInstallment(id) { return this.drill("overdue_installments_amount", { installment: id }); }
    rowKey(event, key, filters) {
        if (["Enter", " "].includes(event.key)) { event.preventDefault(); this.drill(key, filters); }
    }
    width(value) { return `width: ${Math.max(0, Math.min(100, value || 0))}%`; }
    occupancyClass(value) { return value < 40 ? "fz-low" : value < 80 ? "fz-ok" : "fz-high"; }
    matrixCount(source, target) {
        return this.state.data.conversion_matrix.find(r => r.source === source && r.target === target)?.count || 0;
    }
    chart(type, labels, datasets, options = {}) { return { type, data: { labels, datasets }, options }; }
    get charts() {
        const d = this.state.data;
        const bars = (label, data, color) => ({ label, data, backgroundColor: color, borderColor: color, borderRadius: 5 });
        const doughnut = (rows, key) => this.chart("doughnut", rows.map(r => r.name), [{ data: rows.map(r => r[key]), backgroundColor: rows.map((_, i) => PALETTE[i % PALETTE.length]), borderWidth: 0 }], { cutout: "72%" });
        const charts = {
            finances: this.chart("bar", d.departments.map(r => r.name), [bars(_t("Revenue"), d.departments.map(r => r.revenue), PALETTE[0]), bars(_t("Manual expenses"), d.departments.map(r => r.manual_expenses), PALETTE[2]), bars(_t("Purchase expenses"), d.departments.map(r => r.purchase_expenses), PALETTE[3])]),
            share: doughnut(d.departments.map(r => ({ ...r, revenue: Math.max(0,r.revenue) })), "revenue"),
            trend: this.chart("line", d.trend.map(r => r.day), [
                { label: _t("Revenue"), data: d.trend.map(r => r.revenue), borderColor: PALETTE[0], backgroundColor: PALETTE[0], tension: 0.3, pointRadius: 2 },
                { label: _t("Expenses"), data: d.trend.map(r => r.expenses), borderColor: PALETTE[2], backgroundColor: PALETTE[2], tension: 0.3, pointRadius: 2 },
            ]),
            workload: this.chart("bar", d.workload.map(r => r.name), [bars(_t("Sessions"), d.workload.map(r => r.sessions), PALETTE[0]), bars(_t("Quota"), d.workload.map(r => r.quota), PALETTE[1])], { indexAxis: "y" }),
            causes: this.chart("bar", d.injuries_by_cause.map(r => r.name), [bars(_t("Injuries"), d.injuries_by_cause.map(r => r.count), PALETTE[0])], { indexAxis: "y" }),
            sports: doughnut(d.injuries_by_sport, "count"),
            memberships: doughnut([{ name: _t("Active"), count: d.memberships.active }, { name: _t("Expired"), count: d.memberships.expired }], "count"),
        };
        const wire = (name, select, legend = select) => {
            charts[name].options.onClick = (_event, elements) => {
                if (elements.length) { select(elements[0].index, elements[0].datasetIndex); }
            };
            charts[name].options.plugins = { legend: { onClick: (_event, item) => legend(item.index, item.datasetIndex) } };
        };
        const financeKeys = ["total_revenue", "manual_expenses", "purchase_expenses"];
        wire("finances", (i, series) => this.drill(financeKeys[series], { department: d.departments[i].key }),
            (_i, series) => this.drill(financeKeys[series]));
        wire("share", i => this.drill("total_revenue", { department: d.departments[i].key }));
        wire("trend", (i, series) => {
            const start = DateTime.fromISO(d.trend[i].day);
            const end = d.trend.length > 1 && DateTime.fromISO(d.trend[1].day).diff(DateTime.fromISO(d.trend[0].day), "days").days === 7 ? start.plus({ days: 6 }) : start;
            this.drill(series === 0 ? "total_revenue" : "total_expenses", {
                date_from: start.toISODate() < d.date_from ? d.date_from : start.toISODate(),
                date_to: end.toISODate() > d.date_to ? d.date_to : end.toISODate(),
            });
        }, (_i, series) => this.drill(series === 0 ? "total_revenue" : "total_expenses"));
        wire("workload", i => this.drill("workload", { trainer: d.workload[i].id }), () => this.drill("workload"));
        wire("causes", i => this.drill("injuries_count", { cause: d.injuries_by_cause[i].id || 0 }), () => this.drill("injuries_count"));
        wire("sports", i => this.drill("injuries_sport", { sport: d.injuries_by_sport[i].name }));
        wire("memberships", i => this.drill(i === 0 ? "active_memberships" : "expired_memberships"));
        return charts;
    }
    get hasFinance() { return this.state.data.departments.some(r => r.revenue || r.expenses); }
    get hasRevenue() { return this.state.data.departments.some(r => r.revenue > 0); }
    get hasOccupancy() { return this.state.data.halls.some(r => r.offered_seats); }
}
registry.category("actions").add("fitzone_management_dashboard", ManagementDashboard);
