
include './daedalus_util.js'

let sigal_counter = 0
export function Signal(element, name) {
    const event_name = "onSignal_" + (sigal_counter++) + "_" + name

    const signal = {}
    signal._event_name = event_name
    signal._slots = []
    signal.emit = (obj=null) => {
        signal._slots.map(
            item => {requestIdleCallback(() => {item.callback(obj)})}
        )
    }

    console.log("signal create:" + event_name)

    if (!!element) {
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
    constructor(type="div", props=undefined, children=undefined) {
        if (type===undefined) {
            // this would otherwise cause a bizarre rendering error
            throw `DomElement type is undefined. super called with ${arguments.length} arguments`
        }
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
            throw "invalid child";
        }

        if (typeof this.children === "string") {
            this.children = [this.children, ]
        } else if (typeof this.children === "undefined") {
            this.children = []
        }

        this.children.push(childElement)
        this.update()

        return childElement
    }

    insertChild(index, childElement) {
        if (!childElement || !childElement.type) {
            throw "invalid child";
        }


        if (index < 0) {
            // -1 is append at end
            // -2 is append just before last
            index += this.children.length + 1;
        }

        if (index < 0 || index > this.children.length) {
            console.error("invalid index: " + index);
            return
        }

        if (typeof this.children === "string") {
            this.children = [this.children, ]
        } else if (typeof this.children === "undefined") {
            this.children = []
        }

        this.children.splice(index, 0, childElement);
        this.update();

        return childElement
    }

    removeChild(childElement) {
        if (!childElement || !childElement.type) {
            throw "invalid child";
        }
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

    addClassName(cls) {
        let props;

        //assign the class
        if (!this.props.className) {
            props = {className: cls};
        }
        // append the class to the list
        else if (Array.isArray(this.props.className)) {
            props = {className: [cls, ...this.props.className]};
        // convert the class to a class list
        } else {
            props = {className: [cls, this.props.className]};
        }
        this.updateProps(props)
    }

    removeClassName(cls) {
        let props;
        if (Array.isArray(this.props.className)) {
            props = {className: this.props.className.filter(x=>x!==cls)}
            // the filter function did not remove anything
            if (props.className.length === this.props.className.length) {
                return;
            }
            this.updateProps(props)
        } else if (this.props.className === cls) {
            props = {className: null}
            this.updateProps(props)
        }
    }

    hasClassName(cls) {
        let props;
        if (Array.isArray(this.props.className)) {
            return this.props.className.filter(x=>x===cls).length === 1;
        }
        return this.props.className === cls;
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

    getDomNode() {
        return this._fiber && this._fiber.dom
    }

    isMounted() {
        return this._fiber !== null
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

export class LinkElement extends DomElement {

    constructor(text, url) {
        super("div", {className: LinkElement.style.link, title:url}, [new TextElement(text)])

        this.state = {
            url
        }
    }

    onClick() {
        if (this.state.url.startsWith('http')) {
            window.open(this.state.url, '_blank');
        } else {
            history.pushState({}, "", this.state.url)
        }
    }
}
LinkElement.style = {link: StyleSheet({cursor: 'pointer', color: 'blue'})}

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
    }

    setText(text) {
        this.children[0].setText(text);
    }

    getText() {
        return this.children[0].props.nodeValue;
    }
}

export class TextInputElement extends DomElement {

    // second positional parameter reserved for future use
    // TODO: eliminate use of signal here
    constructor(text, _, submit_callback) {
        super("input", {value: text, type:"text"}, []);

        //this.textChanged = Signal(this, 'textChanged');

        this.attrs = {
            submit_callback,
        }
    }

    setText(text) {
        //this.updateProps({value: text})

        this.getDomNode().value = text

        //this.textChanged.emit(this.props)
        //this.update()
    }

    getText() {
        return this.getDomNode().value;
    }

    onChange(event) {
        //this.updateProps({value: event.target.value}, false)
        //this.textChanged.emit(this.props)
    }

    onPaste(event) {
        //this.updateProps({value: event.target.value}, false)
        //this.textChanged.emit(this.props)
    }

    // onKeyDown
    // onKeyPress

    onKeyUp(event) {
        //this.updateProps({value: event.target.value}, false)
        //this.textChanged.emit(this.props)


        if (event.key == "Enter") {
            if (this.attrs.submit_callback) {
                console.log("enter: " + this.getText())
                this.attrs.submit_callback(this.getText())
            }
        }
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


// Swap two nodes
function swap(nodeA, nodeB) {
    if (!nodeA || !nodeB) {
        return
    }
    const parentA = nodeA.parentNode;
    const siblingA = nodeA.nextSibling === nodeB ? nodeA : nodeA.nextSibling;

    // Move `nodeA` to before the `nodeB`
    nodeB.parentNode.insertBefore(nodeA, nodeB);

    // Move `nodeB` to before the sibling of `nodeA`
    parentA.insertBefore(nodeB, siblingA);
};

// Check if `nodeA` is above `nodeB`
function isAbove(nodeA, nodeB) {
    if (!nodeA || !nodeB) {
        return false
    }
    // Get the bounding rectangle of nodes
    const rectA = nodeA.getBoundingClientRect();
    const rectB = nodeB.getBoundingClientRect();

    const a = rectA.top + rectA.height / 2;
    const b = rectB.top + rectB.height / 2;

    return a < b;
};

function childIndex(node) {
    if (node===null) {
        return 0
    }
    let count = 0;
    while( (node = node.previousSibling) != null ) {
      count++;
    }
    return count
}


const placeholder = StyleSheet({
    background-color: "#edf2f7",
    border: "2px dashed #cbd5e0",
    width: '100%',
    height: '100%',
})

/**
 * Reference implementation for a Draggable Item
 */
export class DraggableListItem extends DomElement {

    constructor() {
        super("div", {}, []);
    }

    onTouchStart(event) {
        this.attrs.parent.handleChildDragBegin(this, event)
    }

    onTouchMove(event) {
        this.attrs.parent.handleChildDragMove(this, event)
    }

    onTouchEnd(event) {
        this.attrs.parent.handleChildDragEnd(this, {target: this.getDomNode()})
    }

    onTouchCancel(event) {
        this.attrs.parent.handleChildDragEnd(this, {target: this.getDomNode()})
    }

    onMouseDown(event) {
        this.attrs.parent.handleChildDragBegin(this, event)
    }

    onMouseMove(event) {
        this.attrs.parent.handleChildDragMove(this, event)
    }

    onMouseLeave(event) {
        this.attrs.parent.handleChildDragEnd(this, event)
    }

    onMouseUp(event) {
        this.attrs.parent.handleChildDragEnd(this, event)
    }
}

/**
 * A div where child elements can be dragged with a mouse or touch event
 *
 */
export class DraggableList extends DomElement {

    constructor() {
        super("div", {}, [])


        this.attrs = {
            x: null,
            y: null,
            placeholder: null,
            placeholderClassName: placeholder,
            draggingEle: null,
            isDraggingStarted: false,
            indexStart: -1,
            lockX: true, // prevent moving in the x direction
            swipeScrollTimer: null
        }
    }

    setPlaceholderClassName(className) {
        this.attrs.placeholderClassName = className
    }

    /**
     * child: a DomElement that is a child of this element
     * event: a mouse or touch event
     */
    handleChildDragBegin(child, event) {

        //event.preventDefault()

        if (!!this.attrs.draggingEle) {
            // previous drag did not complete. cancel that drag and ignore
            // this event
            console.error("running drag cancel because previous did not finish")
            this.handleChildDragCancel();

            //return;
        }

        let evt = (event?.touches || event?.originalEvent?.touches)
        if (evt) {
            event = evt[0]
        }

        // TODO: function which uses getDomNode() and reproduces the following
        //       allow for a button within the element to begin the drag

        this.attrs.draggingEle = child.getDomNode();
        this.attrs.draggingChild = child
        this.attrs.indexStart = childIndex(this.attrs.draggingEle)

        if (this.attrs.indexStart < 0) {
            console.error("drag begin failed for child")
            this.attrs.draggingEle = null
            this.attrs.indexStart = -1
            return
        }

        // Calculate the mouse position
        const rect = this.attrs.draggingEle.getBoundingClientRect();
        this.attrs.x = event.clientX - rect.left;
        //this.attrs.y = event.clientY - rect.top;
        this.attrs.y = event.pageY - rect.top;
        this.attrs.eventSource = child
        console.log("set event source")

        //event.stopPropagation()
    }

    handleChildDragMoveImpl(pageX, pageY) {
        const draggingRect = this.attrs.draggingEle.getBoundingClientRect();

        if (this.attrs.indexStart < 0) {
            console.error("drag move failed for child")
            return
        }

        if (!this.attrs.isDraggingStarted) {
            this.attrs.isDraggingStarted = true;

            // Let the placeholder take the height of dragging element
            // So the next element won't move up
            this.attrs.placeholder = document.createElement('div');
            this.attrs.placeholder.classList.add(this.attrs.placeholderClassName);
            this.attrs.draggingEle.parentNode.insertBefore(this.attrs.placeholder, this.attrs.draggingEle.nextSibling);
            //this.attrs.placeholder.style.height = `${draggingRect.height}px`;
            this.attrs.placeholder.style.height = `${this.attrs.draggingEle.clientHeight}px`;
        }

        this.attrs.draggingEle.style.position = 'absolute';

        //let rect = this.getDomNode().getBoundingClientRect()
        //let top = rect.top
        //let bot = rect.bottom
        // Set position for dragging element
        //the original equation, which does not support scrolling is
        //  let ypos = event.pageY - this.attrs.y
        // this fixed version may not allways work
        //let ypos = pageY - this.attrs.y + window.scrollY
        let ypos = pageY - (this.attrs.draggingEle.clientHeight/2)
        //if (ypos > top && ypos < bot) {}
        this.attrs.draggingEle.style.top = `${ypos}px`;


        if (!this.attrs.lockX) {
            this.attrs.draggingEle.style.left = `${pageX - this.attrs.x}px`;
        }

        // The current order
        // prevEle
        // draggingEle
        // placeholder
        // nextEle
        const prevEle = this.attrs.draggingEle.previousElementSibling;
        const nextEle = this.attrs.placeholder.nextElementSibling;

        // The dragging element is above the previous element
        // User moves the dragging element to the top
        if (prevEle && isAbove(this.attrs.draggingEle, prevEle)) {
            // The current order    -> The new order
            // prevEle              -> placeholder
            // draggingEle          -> draggingEle
            // placeholder          -> prevEle

            swap(this.attrs.placeholder, this.attrs.draggingEle);
            swap(this.attrs.placeholder, prevEle);

            const a = childIndex(prevEle) - 1
            const b = childIndex(this.attrs.draggingEle)
            prevEle._fiber.element.setIndex(a)
            this.attrs.draggingEle._fiber.element.setIndex(b)
        }

        // The dragging element is below the next element
        // User moves the dragging element to the bottom
        else if (nextEle && isAbove(nextEle, this.attrs.draggingEle)) {
            // The current order    -> The new order
            // draggingEle          -> nextEle
            // placeholder          -> placeholder
            // nextEle              -> draggingEle

            swap(nextEle, this.attrs.placeholder);
            swap(nextEle, this.attrs.draggingEle);

            const a = childIndex(nextEle)
            const b = childIndex(this.attrs.draggingEle)
            nextEle._fiber.element.setIndex(a)
            this.attrs.draggingEle._fiber.element.setIndex(b)
        }
    }

    _handleAutoScroll(dy) {

        const rate = 15

        const step = dy = rate * dy

        let _y = window.pageYOffset;
        window.scrollBy(0, step);

        if (_y != window.pageYOffset) {

            let total_step = window.pageYOffset - _y

            this.attrs.y += total_step
            this.attrs.autoScrollY += total_step

            this.handleChildDragMoveImpl(
                this.attrs.autoScrollX,
                this.attrs.autoScrollY);
        }
    }

    _handleChildDragAutoScroll(evt) {
        let node = this.getDomNode()
        let top = Math.floor(window.pageYOffset) //+ node.offsetTop
        let bot = Math.floor(top + window.innerHeight - node.offsetTop)
        let y = Math.floor(evt.pageY - node.offsetTop)
        let h = this.attrs.draggingEle.clientHeight

        if (y < top + h*2) {
            this.attrs.autoScrollX = Math.floor(evt.pageX)
            this.attrs.autoScrollY = Math.floor(evt.pageY)
            if (this.attrs.swipeScrollTimer === null) {
                this.attrs.swipeScrollTimer = setInterval(()=>{
                    this._handleAutoScroll(-1)}, 33)
            }

        } else if (y > bot - h*2) {
            this.attrs.autoScrollX = Math.floor(evt.pageX)
            this.attrs.autoScrollY = Math.floor(evt.pageY)
            if (this.attrs.swipeScrollTimer === null) {
                this.attrs.swipeScrollTimer = setInterval(()=>{
                    this._handleAutoScroll(1)}, 33)
            }
        } else if (this.attrs.swipeScrollTimer !== null) {
            clearInterval(this.attrs.swipeScrollTimer)
            this.attrs.swipeScrollTimer = null
        }
    }


    handleChildDragMove(child, event) {
        if (!this.attrs.draggingEle || this.attrs.draggingEle!==child.getDomNode()) {
            return;
        }

        event.preventDefault()

        let evt = (event?.touches || event?.originalEvent?.touches)
        if (evt) {
            event = evt[0]
        }

        this._handleChildDragAutoScroll(event)

        let x = Math.floor(event.pageX)
        let y = Math.floor(event.pageY)

        if (this.attrs._px !== x || this.attrs._py !== y) {
            this.attrs._px = x
            this.attrs._py = y
            return this.handleChildDragMoveImpl(x, y)
        }
    }

    handleChildDragEnd(child, event) {
        //if (this.attrs.draggingEle && this.attrs.draggingEle===child.getDomNode()) {
        //    // todo: update the model
        //    // the children will need to be updated to reflect reality
        //}

        this.handleChildDragCancel();
    }

    handleChildDragCancel(doUpdate=true) {
        // Remove the placeholder
        this.attrs.placeholder && this.attrs.placeholder.parentNode.removeChild(this.attrs.placeholder);

        const indexEnd = childIndex(this.attrs.draggingEle)
        if (this.attrs.indexStart >= 0 && this.attrs.indexStart !== indexEnd) {
            this.updateModel(this.attrs.indexStart, indexEnd)
        }

        if (this.attrs.draggingEle) {
            this.attrs.draggingEle.style.removeProperty('top');
            this.attrs.draggingEle.style.removeProperty('left');
            this.attrs.draggingEle.style.removeProperty('position');
        }

        if (this.attrs.swipeScrollTimer !== null){
            clearInterval(this.attrs.swipeScrollTimer)
            this.attrs.swipeScrollTimer = null
        }

        this.attrs.x = null;
        this.attrs.y = null;
        this.attrs.draggingEle = null;
        this.attrs.isDraggingStarted = false;
        this.attrs.placeholder = null;
        this.attrs.indexStart = -1;
        console.error("cancel")
    }

    updateModel(indexStart, indexEnd) {
        // no reason to call update() since the DOM is already correct
        // it is the virtual DOM that is out of date
        this.children.splice(indexEnd, 0, this.children.splice(indexStart, 1)[0]);
        //console.log(this.children.map(child => child.children[1].getText()))
    }

    debugString() {

        let str = ""

        if (this.attrs.isDraggingStarted) {
            str += " dragging"
        } else {
            str += " not dragging"
        }

        if (this.attrs.draggingEle) {
            str += 'elem'
        }

        if (this.attrs.x || this.attrs.y) {
            str += ` x:${this.attrs.x}, y:${this.attrs.y}`
        }

        return str

    }
}