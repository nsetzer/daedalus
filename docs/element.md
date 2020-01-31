

# Element

An element (`daedalus.DomElement(type, props, children)`) represents a single DOM element
in the Virtual DOM managed by Daedalus. Daedalus uses a Diff-And-Patch strategy to
make sure that the Virtual DOM matches the actual DOM displayed in the browser.
Whenever an element is modified in a way that will require an update to the DOM
the `update()` method for that element must be called. Using the methods
defined for an Element to mutate the state and props will ensure update()
is called automatically.

## Element Base Class

construct a new element with:
```javascript
const elem = new daedalus.DomElement("div", {}, [])
```

A minimally complete Element is defined as:

```javascript
element = {
    type: "div",
    props: {},
    state: {},
    children: []
}
```

## Element type

The element type can be any valid html tag

## Element children

Every element has a list of children, which contains other elements. The children
of an element are rendered in the order of the list.

- `appendChild(elem)` - Append a new child to this element
- `removeChild(elem)` - remove the child from this element
- `replaceChild(elem1, elem2)` - replace a child element with another element
- `removeChildren()` - remove all children from this element

> Warning: An element with multiple parents has undefined behavior

> Warning: Directly modifying the children array requires calling `elem.update()`

## Element state

The state property holds user defined data representing the state of an element.
The current state of an element can be accessed with the `state` attribute

- `updateState(newState, update)`
Mutate the state of this element and then update
the value of `update` can be one of `true|false|undefined`

> Warning: Directly modifying the state requires calling `elem.update()`

## Element props

The Properties of an element are assigned to the DOM node. The Properties must be
valid HTML properties, such as `id`, `style`, etc. the property `className` is
used to modify the `class` of the element, which is used for applying styles.

The current properties of an element can be accessed with the `prop` attribute

- `updateProps(newProps, update)`
Mutate the props of this element and then update
the value of `update` can be one of `true|false|undefined`

> Warning: Directly modifying the props requires calling `elem.update()`

## Element Event Handlers

Properties that start with the string 'on' will be registered as event
handlers. Furthermore, class methods that start with the prefix 'on'
will automatically be registerd as an event handler

The following examples are equivalent

```javascript
class MyElement extends daedalus.DomElement {
    constructor() {
        super("div", {onClick: (event)=>{}}, [])
    }
}
```

```javascript
class MyElement extends daedalus.DomElement {

    onClick(event) {

    }
}
```

## Element Lifecycle

Lifecycle methods are optional methods which can be defined for an element

- `elementMounted` - element is added to the DOM
- `elementUnmounted` - element is removed from the DOM
- `elementUpdateState(oldState, newState)` -
Called when the state is about to be changed. the old state will be overwritten
with the new state. This method can return false to disable updating. A return
value of true or undefined will cause the widget to be updated.
- `elementUpdateProps(oldProps, newProps)` -
Called when the state is about to be changed. the old state will be overwritten
with the new state. This method can return false to disable updating. A return
value of true or undefined will cause the widget to be updated.

## Styles

Use Style Sheets to style elements. Create a style sheet by calling `StyleSheet`
then apply this style to an element by setting the `className` prop.

```javascript
myStyle = daedalus.StyleSheet({display: 'block', background: {color: 'red'});
elem.updateProps({className: myStyle})
````

The `className` prop can be a string or a list of strings in order to assign multiple classes

For an easier time manipulating the class names of an element, use the provided helper functions.

The method *addClassName* will add a named class while checking to prevent duplicates.
The *className* property will be promoted from a string to a list of strings if the element
has more than one class.

```javascript
elem.addClassName(name)
```

The method *removeClassName* will remove a named class if it exists.

```javascript
elem.removeClassName(name)
```

## Inline Styles

> inline styles are a security risk and should not be used

the style prop for an element can either be a string or object. These are equivalent:

```javascript

elem.updateProps({style: "display: block; background-color: red"})
elem.updateProps({style: {display: 'block', background: {color: 'red'}})
````

