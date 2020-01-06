

// import daedalus

// export Test
// export assertEqual
// export UnitTestRoot

const unit_tests = {}

function Test(name, callback) {
    unit_tests[name] = callback;
}


function assertEqual(lhs, rhs, message) {
    if (lhs !== rhs) {
        throw {lhs, rhs, message: (message || "not equal")};
    }
}


class UnitTestRoot extends daedalus.DomElement{

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