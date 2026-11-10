/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { viewService } from "@web/views/view_service";

/**
 * Cấu trúc giao diện (get_views) được trình duyệt lưu trên đĩa, và cờ create / edit / delete đã được
 * "ghi cứng" vào cấu trúc theo quyền tại lúc tải. Khi quyền của người dùng thay đổi (thêm vào nhóm,
 * đồng bộ LUG Permission...), bản lưu cũ làm nút "Thêm mới" biến mất cho đến khi tải lại 2 lần.
 * Với model của Checklist Audit (store.*), bỏ qua bộ nhớ đệm đĩa: luôn lấy giao diện mới từ server.
 */
patch(viewService, {
    start(env, dependencies) {
        const { loadViews: originalLoadViews } = super.start(env, dependencies);
        const { orm } = dependencies;

        async function loadViews(params, options = {}) {
            const { context, resModel, views } = params;
            if (!resModel || !resModel.startsWith("store.")) {
                return originalLoadViews(params, options);
            }

            const loadViewsOptions = {
                action_id: options.actionId || false,
                embedded_action_id: options.embeddedActionId || false,
                embedded_parent_res_id: options.embeddedParentResId || false,
                load_filters: options.loadIrFilters || false,
                toolbar: (!context?.disable_toolbar && options.loadActionMenus) || false,
            };
            for (const key in options) {
                if (
                    ![
                        "actionId",
                        "embeddedActionId",
                        "embeddedParentResId",
                        "loadIrFilters",
                        "loadActionMenus",
                    ].includes(key)
                ) {
                    loadViewsOptions[key] = options[key];
                }
            }
            if (env.isSmall) {
                loadViewsOptions.mobile = true;
            }
            if (env.debug) {
                loadViewsOptions.debug = true;
            }
            const filteredContext = Object.fromEntries(
                Object.entries(context || {}).filter(
                    ([k]) => k === "lang" || k.endsWith("_view_ref")
                )
            );

            // không dùng orm.cache({ type: "disk" }): luôn hỏi server
            const result = await orm.call(resModel, "get_views", [], {
                context: filteredContext,
                views,
                options: loadViewsOptions,
            });
            const viewDescriptions = {
                fields: result.models[resModel].fields,
                relatedModels: result.models,
                views: {},
            };
            for (const viewType in result.views) {
                const { arch, toolbar, id, filters, custom_view_id } = result.views[viewType];
                const viewDescription = { arch, id, custom_view_id };
                if (toolbar) {
                    viewDescription.actionMenus = toolbar;
                }
                if (filters) {
                    viewDescription.irFilters = filters;
                }
                viewDescriptions.views[viewType] = viewDescription;
            }
            return viewDescriptions;
        }

        return { loadViews };
    },
});
