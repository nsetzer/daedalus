
import './daedalus_util.js'

let sigal_counter = 0
export function Signal(element, name) {
    const event_name = "onSignal_" + (sigal_counter++) + "_" + name

    const signal = () => {}
    signal._event_name = event_name
    signal._slots = []
    signal.emit = (obj=null) => {
        signal._slots.map(
            item => {requestIdleCallback(() => {item.callback(obj)})}
        )
    }

    console.log("signal create:" + event_name)

    if (element) {
        element.signals.push(signal)
    }

    return signal
}

let element_uid = 0
function generateElementId() {
    const chars = 'abcdefghijklmnopqrstuvwxyz';
    let name;
    name = "-";
    for (let i=0; i < 6; i++) {
        let c = chars[util.randomInt(0, chars.length - 1)];
        name += c;
    }
    return name + "-" + (element_uid++)
}

export class DomElement {
    constructor(type, props, children) {
        this.type = type;
        if (props===undefined) {
            this.props = {};
        } else {
            this.props = props;
        }
        if (this.props.id===undefined){
            this.props.id = this.constructor.name + generateElementId()
        }
        if (children===undefined) {
            this.children = []
        } else {
            this.children = children // optional , undefined
        }
        this.signals = []
        this.slots = []
        this.dirty = true // whether a change has been queued to re-render
        this.state = {} // element data that effects rendering
        this.attrs = {}  // like state, but does not effect rendering
        this._fiber = null

        Object.getOwnPropertyNames(this.__proto__)
            .filter(key => key.startsWith("on"))
            .forEach(key => {
                this.props[key] = this[key].bind(this)
            }
        )
    }

    _update(element) {} // implementation is patched in

    update() {
        this._update(this)
    }

    updateState(state, doUpdate) {
        const newState = {...this.state, ...state};
        // update this element if doUpdate is true, or not false and
        // this element defines the lifecycle method elementUpdateState
        // and that method returns true
        if (doUpdate!==false) {
            if ((doUpdate===true) ||
                (this.elementUpdateState===undefined) ||
                (this.elementUpdateState(this.state, newState) !== false)) {
                this.update();
            }
        }
        this.state = newState;
    }

    updateProps(props, doUpdate) {
        const newProps = {...this.props, ...props};
        // update this element if doUpdate is true, or not false and
        // this element defines the lifecycle method elementUpdateProps
        // and that method returns true
        if (doUpdate!==false) {
            if ((doUpdate===true) ||
                (this.elementUpdateProps===undefined) ||
                (this.elementUpdateProps(this.props, newProps) !== false)) {
                this.update();
            }
        }
        this.props = newProps;
    }

    appendChild(childElement) {

        if (!childElement || !childElement.type) {
            raise "invalid child";
        }

        if (typeof this.children === "string") {
            this.children = [this.children, ]
        } else if (typeof this.children === "undefined") {
            this.children = []
        }

        this.children.push(childElement)
        //this.children.splice(0, 0, childElement)  // nani?
        this.update()

        return childElement
    }

    removeChild(childElement) {
        const index = this.children.indexOf(childElement)
        if (index >= 0) {
            this.children.splice(index, 1)
            this.update()
        } else {
            console.error("child not in list")
        }
    }

    removeChildren() {
        this.children.splice(0, this.children.length)
        this.update()
    }

    replaceChild(childElement, newChildElement) {
        const index = this.children.indexOf(childElement)
        if (index >= 0) {
            this.children[index] = newChildElement
            this.update()
        }
    }

    connect(signal, callback) {
        console.log("signal connect:" + signal._event_name, callback)
        const ref = {element: this, signal: signal, callback: callback};
        signal._slots.push(ref)
        this.slots.push(ref)
    }

    disconnect(signal) {
        console.log("signal disconnect:" + signal._event_name)
    }
}

export class TextElement extends DomElement {
    constructor(text, props={}) {
        super("TEXT_ELEMENT", {'nodeValue': text, ...props}, [])
    }

    setText(text) {
        this.props = {'nodeValue': text}
        this.update()
    }

    getText() {
        return this.props.nodeValue;
    }
}

style_link = StyleSheet({cursor: 'pointer', color: 'blue'})
export class LinkElement extends DomElement {
    constructor(text, link) {
        super("div", {className: style_link, title:link}, [new TextElement(text)])

        this.link = link
    }

    onClick() {
        history.pushState({}, "", this.link)
    }
}

export class ListElement extends DomElement {
    constructor() {
        super("ul", {}, [])
    }
}

export class ListItemElement extends DomElement {
    constructor(item) {
        super("li", {}, [item])
    }
}

export class HeaderElement extends DomElement {
    constructor(text="") {
        super("h1", {}, [])
        this.node = this.appendChild(new TextElement(text))
    }

    setText(text) {
        this.node.setText(text)
    }
}

export class ButtonElement extends DomElement {
    constructor(text, onClick) {
        super("button", {'onClick': onClick}, [new TextElement(text)])
        console.log(this.type)
    }

    setText(text) {
        this.children[0].setText(text);
    }

    getText() {
        return this.children[0].props.nodeValue;
    }
}

export class TextInputElement extends DomElement {

    constructor(text) {
        super("input", {value: text}, []);

        this.textChanged = Signal(this, 'textChanged');
    }

    onChange(event) {
        this.updateProps({value: event.target.value}, false)
        this.textChanged.emit(this.props)
    }

    onPaste(event) {
        this.updateProps({value: event.target.value}, false)
        this.textChanged.emit(this.props)
    }

    // onKeyDown
    // onKeyPress

    onKeyUp(event) {
        this.updateProps({value: event.target.value}, false)
        this.textChanged.emit(this.props)
    }
}

export class NumberInputElement extends DomElement {

    constructor(value) {
        super("input", {value: value, type: "number"}, []);

        this.valueChanged = Signal(this, 'valueChanged');
    }

    onChange(event) {
        this.updateProps({value: parseInt(event.target.value, 10)}, false)
        this.valueChanged.emit(this.props)
    }

    onPaste(event) {
        this.updateProps({value: parseInt(event.target.value, 10)}, false)
        this.valueChanged.emit(this.props)
    }

    onKeyUp(event) {
        this.updateProps({value: parseInt(event.target.value, 10)}, false)
        this.valueChanged.emit(this.props)
    }

    onInput(event) {
        this.updateProps({value: parseInt(event.target.value, 10)}, false)
        this.valueChanged.emit(this.props)
    }
}