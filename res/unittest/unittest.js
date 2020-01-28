

import daedalus

const unit_tests = {}

export function Test(name, callback) {
    unit_tests[name] = callback;
}

export assert = {
    equal: function(lhs, rhs, message) {
        if (lhs !== rhs) {
            throw {message: (message || `not equal: (${lhs} !== ${rhs})`)};
        }
    },
    notEqual: function(lhs, rhs, message) {
        if (lhs === rhs) {
            throw {message: (message || `equal: (${lhs} === ${rhs})`)};
        }
    },
    isNone: function(value, message) {
        if (value !== null && value !== undefined) {
            throw {message: (message || `equal: (${lhs} === ${rhs})`)};
        }
    }
}

export class UnitTestRoot extends daedalus.DomElement {

    constructor() {
        super("div", {}, [])

    }

    elementMounted() {

        Object.keys(unit_tests).forEach(name => {
            const callback = unit_tests[name];

            let pass = true;
            let text = name;

            try {

                callback()

                text += ": pass"
                pass = true
            } catch(err) {
                text += ": fail"
                if (err.message !== undefined) {
                    text += ": " + err.message
                } else {
                    text += ": " + JSON.stringify(err)
                }
            }

            this.appendChild(new daedalus.DomElement("br", {}, []))
            this.appendChild(new daedalus.TextElement(text))
        })
    }
}