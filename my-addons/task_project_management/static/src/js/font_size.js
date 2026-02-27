/** @odoo-module **/

import { registry } from "@web/core/registry";
import { session } from "@web/session";

const FONT_SIZE_MAP = {
    small: "13px",
    medium: "15px",
    large: "17px",
    xlarge: "19px",
};

const fontSizeService = {
    dependencies: ["user", "rpc"],
    start(env, { user, rpc }) {
        function applyFontSize(size) {
            const px = FONT_SIZE_MAP[size] || FONT_SIZE_MAP.medium;
            document.documentElement.style.setProperty("--task-mgmt-font-size", px);
            document.body.classList.remove(
                "task-font-small", "task-font-medium",
                "task-font-large", "task-font-xlarge"
            );
            document.body.classList.add("task-font-" + (size || "medium"));
        }

        // Apply on startup from session
        const initialSize = (session.user_context || {}).task_font_size
            || session.task_font_size
            || "medium";
        applyFontSize(initialSize);

        // Fetch from user record to be sure
        rpc("/web/dataset/call_kw", {
            model: "res.users",
            method: "read",
            args: [[user.userId], ["task_font_size"]],
            kwargs: {},
        }).then((result) => {
            if (result && result.length) {
                applyFontSize(result[0].task_font_size || "medium");
            }
        });

        return {
            applyFontSize,
            getCurrentSize() {
                for (const cls of document.body.classList) {
                    if (cls.startsWith("task-font-")) {
                        return cls.replace("task-font-", "");
                    }
                }
                return "medium";
            },
        };
    },
};

registry.category("services").add("task_font_size", fontSizeService);
