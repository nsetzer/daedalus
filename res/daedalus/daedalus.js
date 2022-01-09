
include './daedalus_util.js'
include './daedalus_element.js'
include './daedalus_location.js'
include './daedalus_router.js'
include './daedalus_fileapi.js'
include './daedalus_platform.js'

//---safarai
if (window.requestIdleCallback===undefined) {
    window.requestIdleCallback = (callback, options) => {
        //options.timeout : timeout in milliseconds
        // the maximum amount of time to delay before calling callback
        setTimeout(()=>{callback()}, 0);
    }
}
//---

let workstack = [];
let deletions = [];
let deletions_removed = new Set();
let updatequeue = [];
let wipRoot = null;
let currentRoot = null;

let workLoopActive = false;

let workCounter = 0;

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

    if (!workLoopActive) {
        workLoopActive = true
        setTimeout(workLoop, 0)
    }
}

export function render_update(element) {
    // update the element if it is not already dirty
    // (an update has already been queued)
    // do not update the element if it does not have a fiber
    // (it has not been mounted and there is nothing to update)
    if (!element._$dirty && element._$fiber !== null) {
        element._$dirty = true
        const fiber = {
            effect: 'UPDATE',
            children: [element],
            _fibers: [],
            alternate: null,
            partial: true // indicates this is a psuedo fiber
        }
        updatequeue.push(fiber)
    }

    if (!workLoopActive) {
        workLoopActive = true
        setTimeout(workLoop, 0)
    }
}

DomElement.prototype._update = render_update

function workLoop(deadline=null) {

    //let tstart = new Date().getTime();

    let shouldYield = false;

    const initialWorkLength = workstack.length;
    const initialUpdateLength = updatequeue.length;

    /*
    friendly: when set to true, obey the deadline timer
    battery powered devices are frequently given < 1 second to
    perform all updates, which are measured to take < 50 ms
    in the worst case.
    */

    let friendly = deadline != null;
    let initial_delay = 0

    try {
        if (!!friendly) {

            initial_delay = deadline.timeRemaining()

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
        } else {
            while (1) {
                while (workstack.length > 0) {
                    let unit = workstack.pop();
                    performUnitOfWork(unit);
                }

                if (wipRoot) {
                    commitRoot();
                }

                if (updatequeue.length > 0 && !wipRoot) {


                    wipRoot = updatequeue[0];
                    workstack.push(wipRoot);
                    updatequeue.shift();
                } else {
                    break;
                }
            }
        }
    } catch (e) {
        console.error("unhandled workloop exception: " + e.message)
    }

    //-------------



    let debug = workstack.length > 1 || updatequeue.length > 1
    if (!!debug) {
        console.warn("workloop failed to finish", initial_delay, ":"
            initialWorkLength, '->', workstack.length,
            initialUpdateLength, '->', updatequeue.length)

        if (!friendly) {
            setTimeout(workLoop, 50);
        } else {
            requestIdleCallback(workLoop);
        }
    } else {
        workLoopActive = false
    }

    //let tend = new Date().getTime();
    //console.error("workLoop: " + Math.floor(tend - tstart));
}

//requestIdleCallback(workLoop);
//setTimeout(workLoop, 50)

// TODO: performUnitOfWork and reconcileChildren should be merged and renamed
function performUnitOfWork(fiber) {
    if (!fiber.dom && fiber.effect == 'CREATE') {
        fiber.dom = createDomNode(fiber);
    }
    reconcileChildren(fiber);
}

function reconcileChildren(parentFiber) {
    workCounter += 1
    // tag old fibers to be deleted
    const oldParentFiber = parentFiber.alternate;

    // mark each child fiber for deletion, if it is processed below
    // unset this field

    if (!!oldParentFiber) {
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
            const oldFiber = element._$fiber;

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

            if (!!oldFiber) {
                if (oldIndex == index && element._$dirty === false) {
                    // effect = 'NONE';
                    // Experiment: with nothing to do exit early
                    // Require any children to have called update()
                    return;
                } else {
                    effect = 'UPDATE';
                }
            } else {
                effect = 'CREATE';
            }

            // mark as clean, work to update DOM is done later.
            element._$dirty = false;

            const newFiber = {
                type: element.type,
                effect: effect,
                props: {...element.props},
                children: element.children.slice(),
                _fibers: [],
                parent: (parentFiber.partial && oldFiber)? oldFiber.parent : parentFiber,
                alternate: oldFiber,
                dom: oldFiber ? oldFiber.dom : null,
                element: element,
                index: index,
                oldIndex: oldIndex
            };

            if (!newFiber.parent.dom) {
                console.error(`element parent is not mounted id: ${element.props.id} effect: ${effect}`);
                return;
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

            element._$fiber = newFiber
            parentFiber._fibers.push(newFiber)

            prev.next = newFiber;
            prev = newFiber;


            workstack.push(newFiber);


        }
    )

    // now that all children have been processed, mark fibers for deletion

    if (!!oldParentFiber) {
        oldParentFiber.children.forEach(child => {
            if (child._delete) {
                deletions.push(child._$fiber);
            }
        })
    }
}

function commitRoot() {

    deletions_removed = new Set();
    deletions.forEach(removeDomNode)

    // unique elements which were removed by this action should
    // have their unmounted callback called.
    if(deletions_removed.size > 0) {
        deletions_removed.forEach(elem => {
            requestIdleCallback(elem.elementUnmounted.bind(elem))
        })
    }

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

    if (!parentDom) {
        console.warn(`element has no parent. effect: ${fiber.effect}`)
        return
    }

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
            //if (key !== "id" && key !== "nodeValue") {
            //    console.log("create-prop: " + key + " = " + fiber.props[key])
            //}
            const propValue = fiber.props[key];
            if (propValue===null) {
                delete dom[key];
            } else {
                dom[key] = propValue;
            }

        })

    dom._$fiber = fiber // allow access to the virtual dom element
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

    dom._$fiber = fiber // allow access to the virtual dom element

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

    if (element.elementUnmounted) {
        deletions_removed.add(element)
    }

    element.children.forEach(child => {
        child._$fiber = null;
        _removeDomNode_elementFixUp(child);

    })
}

function removeDomNode(fiber) {

    //if (fiber.effect === 'CREATE') {
    //    console.error("remove node that was never placed", fiber)
    //    return
    //}
    //

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
    fiber.element._$fiber = null
    fiber.alternate = null
    _removeDomNode_elementFixUp(fiber.element)
}




