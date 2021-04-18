

import module daedalus

const unit_tests = []

const style = {
    pass: StyleSheet({
        background: "rgba(0, 200, 0, .3)",
        margin: {top: '.25em'}
    }),
    skip: StyleSheet({
        background: "rgba(200, 200, 0, .3)",
        margin: {top: '.25em'}
    }),
    fail: StyleSheet({
        background: "rgba(200, 0, 0, .3)",
        margin: {top: '.25em'}
    }),
    output: StyleSheet({
        background: "rgb(192, 192, 192)",
    }),
}

export function Test(name, callback) {
    unit_tests.push({name, callback});
}

export const assert = {
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
            throw {message: (message || `is not nullish: (${value})`)};
        }
    },
    isNotNone: function(value, message) {
        if (value === null || value === undefined) {
            throw {message: (message || `is nullish: (${value})`)};
        }
    },
    fail: function(message) {
        throw {message: message};
    },
    skip: function(message) {
        throw {message: message, skip: true};
    },
    flt: {
        equal: function(lhs, rhs, message, eps=.00001) {
            if (Math.abs(lhs - rhs) > eps) {
                throw {message: `not equal: (${lhs} !== ${rhs}). ${message}`};
            }
        }
    }
}

export class UnitTestRoot extends daedalus.DomElement {

    constructor() {
        super("div", {}, [])

    }

    elementMounted() {

        unit_tests.forEach(test => {
            const callback = unit_tests[name];

            let pass = true;
            let text = test.name;
            let nodes = []
            let ctxt = {
                write: function(...args) {
                    nodes.push("> " + args.join(" "))
                }
            }

            let className = style.fail
            try {
                console.log("----- " + test.name + " -----")

                test.callback(ctxt)
                className = style.pass
                text += ": pass"
                pass = true
            } catch(err) {

                if (err.skip !== undefined) {
                    className = style.skip
                    text += ": skip"
                    text += ": " + err.message
                } else if (err.message !== undefined) {
                    text += ": fail"
                    text += ": " + err.message
                } else {
                    text += ": fail"
                    text += ": " + JSON.stringify(err)
                }
            }

            this.appendChild(new daedalus.DomElement("div", {className: className},
                [new daedalus.TextElement(text)]))

            if (nodes.length > 0) {
                const pre = this.appendChild(new daedalus.DomElement("pre", {className: style.output}, []))
                nodes.forEach(node => {
                    pre.appendChild(new daedalus.TextElement(node))
                    pre.appendChild(new daedalus.DomElement("br", {}, []))

                })
            }
        })
    }
}