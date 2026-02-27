/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

const TIMEOUT_MS = 15 * 60 * 1000; // 15 minutes

const sessionTimeoutService = {
    dependencies: [],
    start() {
        let timer = null;

        function resetTimer() {
            if (timer) browser.clearTimeout(timer);
            timer = browser.setTimeout(() => {
                browser.location.href = "/web/session/logout";
            }, TIMEOUT_MS);
        }

        const events = ["mousemove", "mousedown", "keydown", "scroll", "touchstart"];
        for (const event of events) {
            browser.addEventListener(event, resetTimer, { passive: true });
        }

        resetTimer();
    },
};

registry.category("services").add("session_timeout", sessionTimeoutService);
