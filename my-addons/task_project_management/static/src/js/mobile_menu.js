/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { NavBar } from "@web/webclient/navbar/navbar";
import { onMounted, onWillUnmount } from "@odoo/owl";

patch(NavBar.prototype, {
    setup() {
        super.setup(...arguments);

        this._mobileOnResize = () => {
            if (window.innerWidth >= 768) {
                const navbar = this.root.el;
                if (!navbar) return;
                const sections = navbar.querySelector(".o_menu_sections");
                if (sections) sections.classList.remove("o_mobile_show");
            }
        };

        onMounted(() => {
            this._addMobileHamburger();
            window.addEventListener("resize", this._mobileOnResize);
        });

        onWillUnmount(() => {
            window.removeEventListener("resize", this._mobileOnResize);
        });
    },

    _addMobileHamburger() {
        if (window.innerWidth >= 768) return;

        const navbar = this.root.el;
        if (!navbar || navbar.querySelector(".o_mobile_hamburger")) return;

        const btn = document.createElement("button");
        btn.className = "o_mobile_hamburger";
        btn.type = "button";
        btn.innerHTML = "&#9776;";
        btn.addEventListener("click", () => {
            const sections = navbar.querySelector(".o_menu_sections");
            if (sections) sections.classList.toggle("o_mobile_show");
        });

        // Insert at the beginning of navbar
        navbar.prepend(btn);
    },
});
