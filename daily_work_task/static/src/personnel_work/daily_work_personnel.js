/** @odoo-module **/
/* personnel-work: 19.0.1.39.45-assigned-region */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { _t } from "@web/core/l10n/translation";
import { DailyWorkAppShell } from "@daily_work_task/shell/daily_work_app_shell";

export class DailyWorkPersonnel extends Component {
    static template = "daily_work_task.DailyWorkPersonnel";
    static components = { DailyWorkAppShell };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            search: "",
            departmentId: "",
            teamId: "",
            userId: "",
            categoryId: "",
            region: "",
            role: "",
            people: [],
            filters: {
                departments: [],
                teams: [],
                users: [],
                categories: [],
                regions: [],
                roles: [],
            },
            openPeople: {},
            openCats: {},
        });
        onWillStart(() => this.load());
    }

    get shellActiveNav() {
        return "personnel_work";
    }

    get visiblePeople() {
        const q = (this.state.search || "").trim().toLowerCase();
        const out = [];
        for (const person of this.state.people || []) {
            const personHit = q && (person.name || "").toLowerCase().includes(q);
            const categories = [];
            for (const cat of person.categories || []) {
                const lines = (cat.lines || []).filter((line) => this._lineVisible(line, person, personHit, q));
                if (!lines.length) {
                    continue;
                }
                categories.push({ ...cat, lines, count: lines.length });
            }
            if (!categories.length) {
                continue;
            }
            const count = categories.reduce((n, cat) => n + cat.lines.length, 0);
            out.push({
                ...person,
                categories,
                count,
                open: Boolean(this.state.openPeople[person.id]),
            });
        }
        return out;
    }

    _lineVisible(line, person, personHit, q) {
        if (this.state.departmentId && String(line.department_id) !== String(this.state.departmentId)) {
            return false;
        }
        if (this.state.teamId && String(line.team_id) !== String(this.state.teamId)) {
            return false;
        }
        if (this.state.userId && String(person.id) !== String(this.state.userId)) {
            return false;
        }
        if (this.state.categoryId && String(line.category_id) !== String(this.state.categoryId)) {
            return false;
        }
        if (this.state.region && (line.region || "") !== this.state.region) {
            return false;
        }
        if (this.state.role && line.role_key !== this.state.role) {
            return false;
        }
        if (!q || personHit) {
            return true;
        }
        const blob = [line.name, line.code, line.category, line.region, person.name]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();
        return blob.includes(q);
    }

    taskRows(cat) {
        const rows = [];
        const index = {};
        for (const line of cat.lines || []) {
            const key = line.assign_id || line.code;
            let row = index[key];
            if (!row) {
                row = {
                    key,
                    code: line.code,
                    name: line.name,
                    region: line.region || "",
                    assigneeName: "",
                    checkerName: "",
                };
                index[key] = row;
                rows.push(row);
            }
            if (!row.region && line.region) {
                row.region = line.region;
            }
            const userName = line.user_name || "";
            if (line.role_key === "assignee") {
                row.assigneeName = userName;
            } else if (line.role_key === "checker") {
                row.checkerName = userName;
            }
            if (!row.checkerName && line.task_checker_name) {
                row.checkerName = line.task_checker_name;
            }
        }
        return rows;
    }

    catOpen(personId, catId) {
        const key = `${personId}:${catId}`;
        if (this.state.openCats[key] === undefined) {
            return false;
        }
        return Boolean(this.state.openCats[key]);
    }

    togglePerson(personId) {
        const current = Boolean(this.state.openPeople[personId]);
        this.state.openPeople = { ...this.state.openPeople, [personId]: !current };
    }

    toggleCat(personId, catId) {
        const key = `${personId}:${catId}`;
        const current = this.catOpen(personId, catId);
        this.state.openCats = { ...this.state.openCats, [key]: !current };
    }

    onFilter(field, ev) {
        this.state[field] = ev.target.value || "";
    }

    onSearch(ev) {
        this.state.search = ev.target.value || "";
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "daily.task.assign",
                "get_personnel_work_data",
                []
            );
            const people = data.people || [];
            const openPeople = {};
            const openCats = {};
            for (const person of people) {
                openPeople[person.id] = false;
            }
            if (people.length) {
                openPeople[people[0].id] = true;
                const firstCat = (people[0].categories || [])[0];
                if (firstCat) {
                    openCats[`${people[0].id}:${firstCat.id}`] = true;
                }
            }
            this.state.people = people;
            this.state.filters = data.filters || this.state.filters;
            this.state.openPeople = openPeople;
            this.state.openCats = openCats;
        } catch (e) {
            this.state.people = [];
            this.notification.add(
                e?.data?.message || _t("Không tải được công việc theo nhân sự."),
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }
}

registry.category("actions").add("daily_work_personnel", DailyWorkPersonnel);
