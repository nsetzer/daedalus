
import './daedalus_util.js'
import './daedalus_element.js'
import './daedalus_location.js'
import './daedalus_router.js'
import './daedalus_auth.js'
import './daedalus_fileapi.js'
import './daedalus_platform.js'

let workstack = [];
let deletions = [];
let updatequeue = [];
let wipRoot = null;
let currentRoot = null;

export function render(container, element) {
    wipRoot = {
        type: "ROOT",
        dom: container,
        props: {},
        children: [element],
        _fibers: [],
        alternate: currentRoot
    }
    workstack.push(wipRoot)
}

export function render_update(element) {
    if (!element.dirty) {
        element.dirty = true
        const fiber = {
            effect: 'UPDATE',
            children: [element],
            _fibers: [],
            alternate: null,
            partial: true // indicates this is a psuedo fiber
        }
        updatequeue.push(fiber)
    }
}

DomElement.prototype._update = render_update

function workLoop(deadline) {
    //let t0 = performance.now();
    let debug = workstack.length > 1 || updatequeue.length > 1

    let shouldYield = false;

    const initialWorkLength = workstack.length;
    const initialUpdateLength = updatequeue.length;

    while (!shouldYield) {
        while (workstack.length > 0 && !shouldYield) {
            let unit = workstack.pop();
            performUnitOfWork(unit);
            shouldYield = deadline.timeRemaining() < 1;
        }

        if (workstack.length == 0 && wipRoot) {
            commitRoot();
        }


        if (workstack.length == 0 && updatequeue.length > 0 && !wipRoot) {

            wipRoot = updatequeue[0];
            workstack.push(wipRoot);
            updatequeue.shift();
        }
        shouldYield = deadline.timeRemaining() < 1;
    }

    debug = workstack.length > 1 || updatequeue.length > 1
    if (debug) {
        console.warn("workloop failed to finish",
            initialWorkLength, '->', workstack.length,
            initialUpdateLength, '->', updatequeue.length)
    }

    requestIdleCallback(workLoop);
    //let t1 = performance.now();
    //let elapsed = t1 - t0
    //if (elapsed > 0) {
    //    console.log("timeit", deadline, t1 - t0)
    //}
}
requestIdleCallback(workLoop);

// TODO: performUnitOfWork and reconcileChildren should be merged and renamed
function performUnitOfWork(fiber) {
    if (!fiber.dom && fiber.effect == 'CREATE') {
        fiber.dom = createDomNode(fiber);
    }
    reconcileChildren(fiber);
}

function reconcileChildren(parentFiber) {

    // tag old fibers to be deleted
    const oldParentFiber = parentFiber.alternate;

    // mark each child fiber for deletion, if it is processed below
    // unset this field

    if (oldParentFiber) {
        oldParentFiber.children.forEach(child => {
            child._delete = true;
        })
    }

    // get the last fiber in the current work chain
    // if a parent has multiple children, prev.next may
    // already be populated. overwriting prev.next with
    // a new value would prevent the element from being rendered
    let prev = parentFiber;
    while (prev.next) {
        prev = prev.next;
    }
    parentFiber.children.forEach(
        (element, index) => {
            if (!element || !element.type) {
                console.error(`${parentFiber.element.props.id}: undefined child element at index ${index} `);
                return;
            }
            const oldFiber = element._fiber;

            // unset the delete flag for this child fiber
            //#if (oldFiber) {
            //#    oldFiber._delete = false;
            //#}
            element._delete = false;

            const oldIndex = oldFiber ? oldFiber.index : index;

            // check if the parent is a psuedo fiber
            if (parentFiber.partial) {
                index = oldIndex;
            }

            let effect;

            if (oldFiber) {
                if (oldIndex == index && element.dirty === false) {
                    effect = 'NONE';
                } else {
                    effect = 'UPDATE';
                }
            } else {
                effect = 'CREATE';
            }

            // mark as clean, work to update DOM is done later.
            element.dirty = false;

            const newFiber = {
                type: element.type,
                effect: effect,
                props: {...element.props},
                children: element.children.slice(),
                _fibers: [],
                parent: parentFiber.partial? element._fiber.parent :parentFiber,
                alternate: oldFiber,
                dom: oldFiber ? oldFiber.dom : null,
                signals: element.signals,
                element: element,
                index: index,
                oldIndex: oldIndex
            };

            if (!newFiber.parent.dom) {
                console.error("dom error", newFiber.parent)
            }

            if (newFiber.props.style) {
                console.warn("unsafe use of inline style: ", newFiber.type, element.props.id, newFiber.props.style)
            }

            if (typeof(newFiber.props.style)==='object') {
                newFiber.props.style = util.object2style(newFiber.props.style)
            }

            if (Array.isArray(newFiber.props.className)) {
                newFiber.props.className = newFiber.props.className.join(' ')
            }

            element._fiber = newFiber
            parentFiber._fibers.push(newFiber)

            prev.next = newFiber;
            prev = newFiber;
            workstack.push(newFiber);

        }
    )

    // now that all children have been processed, mark fibers for deletion

    if (oldParentFiber) {
        oldParentFiber.children.forEach(child => {
            if (child._delete) {
                deletions.push(child._fiber);
            }
        })
    }
}

function commitRoot() {

    deletions.forEach(removeDomNode)

    // consider moving this function into `workLoop`
    // is there anything to be gained by being able to pause
    // this whil loop and return to it?
    let unit = wipRoot.next
    let next;
    while (unit) {
        commitWork(unit)
        next = unit.next
        unit.next = null
        unit = next
    }

    currentRoot = wipRoot
    wipRoot = null
    deletions = []
}

function commitWork(fiber) {

    const parentDom = fiber.parent.dom;

    if (fiber.effect === 'CREATE') {

        // the fibers are created in the same order as the children
        // in the array. appending will work for the initial creation
        // of the parent, or if appendChild is used later on. if
        // insertChild is used after initial construction, insert the
        // child dom before the correct element
        const length = parentDom.children.length;
        const position = fiber.index;

        if (length == position) {
            parentDom.appendChild(fiber.dom);
        } else {
            parentDom.insertBefore(fiber.dom,
                parentDom.children[position]);
        }

        if (fiber.element.elementMounted) {
            requestIdleCallback(fiber.element.elementMounted.bind(fiber.element))
        }

    } else if (fiber.effect === 'UPDATE') {
        fiber.alternate.alternate = null // prevent memory leak
        updateDomNode(fiber)
    } else if (fiber.effect === 'DELETE') {
        fiber.alternate.alternate = null // prevent memory leak
        removeDomNode(fiber)
    }
}

const isEvent = key => key.startsWith("on")
const isProp = key => !isEvent(key)
const isCreate = (prev, next) => key => (key in next && !(key in prev))
const isUpdate = (prev, next) => key => (key in prev && key in next && prev[key] !== next[key])
const isDelete = (prev, next) => key => !(key in next)

function createDomNode(fiber) {

    const dom = fiber.type == "TEXT_ELEMENT"
        ? document.createTextNode("")
        : document.createElement(fiber.type)

    Object.keys(fiber.props)
        .filter(isEvent)
        .forEach(key => {
            //console.log("create-event: " + key)
            const event = key.toLowerCase().substring(2)
            dom.addEventListener(event, fiber.props[key])
        })

    Object.keys(fiber.props)
        .filter(isProp)
        .forEach(key => {
            //console.log("create-prop: " + key + " = " + fiber.props[key])
            dom[key] = fiber.props[key];
        })

    return dom
}

function updateDomNode(fiber) {

    const dom = fiber.dom
    const parentDom = fiber.parent.dom
    const oldProps = fiber.alternate.props
    const newProps = fiber.props

    if (!dom) {
        console.log("fiber does not contain a dom")
        return
    }

    if (fiber.oldIndex != fiber.index && parentDom) {
        // TODO: this will fail if there is a move and a delete or insert
        // in the same set of actions to be updated
        //console.log(fiber.index, fiber.oldIndex)

        // a simple swap will require only a single move
        // check if this item is already in the correct position before moving
        if (parentDom.children[fiber.index] !== dom) {
            parentDom.removeChild(fiber.dom);
            parentDom.insertBefore(fiber.dom,
                parentDom.children[fiber.index]);
        }
    }

    // remove old or modified event listeners
    Object.keys(oldProps)
        .filter(isEvent)
        .filter(key => isUpdate(oldProps, newProps)(key) || isDelete(oldProps, newProps)(key))
        .forEach(key => {
            //console.log("delete-event: " + key)
            const event = key.toLowerCase().substring(2)
            dom.removeEventListener(event, oldProps[key])
        })

    // add new or updated event listeners
    Object.keys(newProps)
        .filter(isEvent)
        .filter(key => isCreate(oldProps, newProps)(key) || isUpdate(oldProps, newProps)(key))
        .forEach(key => {
            //console.log("update-event: " + key)
            const event = key.toLowerCase().substring(2)
            dom.addEventListener(event, newProps[key])
        })

    // remove old properties
    Object.keys(oldProps)
        .filter(isProp)
        .filter(isDelete(oldProps, newProps))
        .forEach(key => {
            //console.log("delete-prop: " + key)
            dom[key] = ""
        })

    // add or update properties
    Object.keys(newProps)
        .filter(isProp)
        .filter(key => isCreate(oldProps, newProps)(key) || isUpdate(oldProps, newProps)(key))
        .forEach(key => {
            //console.log("update-prop: "  + key + ": " + oldProps[key] + " => " + newProps[key])
            dom[key] = newProps[key]
        })
}

// remove all traces of a fiber from the elements
// in case the user wants to add this element later
function _removeDomNode_elementFixUp(element) {
    element.children.forEach(child => {
        child._fiber = null;
        _removeDomNode_elementFixUp(child);
    })
}

function removeDomNode(fiber) {

    //if (fiber.effect === 'CREATE') {
    //    console.error("remove node that was never placed", fiber)
    //    return
    //}
    //
    if (fiber.element.elementUnmounted) {
        requestIdleCallback(fiber.element.elementUnmounted.bind(fiber.element))
    }


    if (fiber.dom) {
        //if (fiber.parent.dom) {
        //    fiber.parent.dom.removeChild(fiber.dom);
        //} else {
        //    fiber.dom.parentNode.removeChild(fiber.dom);
        //}
        // if the parent is a psuedo fiber then there is
        // no parent dom, fortunately we can ask the node
        // for it parent in order to remove
        if (fiber.dom.parentNode) {
            fiber.dom.parentNode.removeChild(fiber.dom);
        }

        //console.log('DELETE: ', fiber.element.type);

    } else {

        console.error("failed to delete", fiber.element.type)
    }

    fiber.dom = null
    fiber.element._fiber = null
    fiber.alternate = null
    _removeDomNode_elementFixUp(fiber.element)
    // TODO: check for connected signals/slots and disconnect
    // if we can add/remove dom nodes in this way then
    // removeing a dom node and adding it again means
    // manually reconnecting signals...
    // and removing it means it can't receive signals...
}




