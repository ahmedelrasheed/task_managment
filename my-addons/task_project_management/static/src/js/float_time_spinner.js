/** @odoo-module **/

import { registry } from "@web/core/registry";
import { FloatTimeField, floatTimeField } from "@web/views/fields/float_time/float_time_field";
import { formatFloatTime } from "@web/views/fields/formatters";
import { Component, xml } from "@odoo/owl";

export class FloatTimeSpinnerField extends FloatTimeField {
    static template = xml`
        <span t-if="props.readonly" t-esc="formattedValue" />
        <div t-else="" class="o_float_time_spinner d-flex align-items-center">
            <button type="button" class="btn btn-sm btn-outline-secondary o_time_btn o_time_down"
                    t-on-click="onDecrement" tabindex="-1">
                <i class="fa fa-chevron-down"/>
            </button>
            <input t-att-id="props.id" type="text" t-ref="numpadDecimal"
                   t-att-placeholder="props.placeholder"
                   class="o_input text-center mx-1" autocomplete="off"
                   style="min-width: 70px; max-width: 90px;"/>
            <button type="button" class="btn btn-sm btn-outline-secondary o_time_btn o_time_up"
                    t-on-click="onIncrement" tabindex="-1">
                <i class="fa fa-chevron-up"/>
            </button>
        </div>
    `;

    get currentValue() {
        return this.props.record.data[this.props.name] || 0;
    }

    _step() {
        // Step by 30 minutes (0.5 hours)
        return 0.5;
    }

    onIncrement() {
        const newVal = Math.min(23.5, this.currentValue + this._step());
        this.props.record.update({ [this.props.name]: newVal });
    }

    onDecrement() {
        const newVal = Math.max(0, this.currentValue - this._step());
        this.props.record.update({ [this.props.name]: newVal });
    }
}

export const floatTimeSpinnerField = {
    ...floatTimeField,
    component: FloatTimeSpinnerField,
};

registry.category("fields").add("float_time_spinner", floatTimeSpinnerField);
