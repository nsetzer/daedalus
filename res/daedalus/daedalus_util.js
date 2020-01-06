

function array_move(arr, p1, p2) {

    let s1 = p1
    let s2 = p2
    if (p1 < 0) {p1 = 0}
    if (p2 < 0) {p2 = 0}
    if (p1 > arr.length) {p1 = arr.length}
    if (p2 > arr.length) {p2 = arr.length}
    if (p1 == p2) {
        return
    }

    let item = arr[p1]
    //console.log(s1, s2, "|", p1, "+>", p2, "+>", arr.indexOf(item))
    arr.splice(p2, 0, arr.splice(p1, 1)[0]);
}

function randomFloat(min, max) {
    return Math.random() * (max - min) + min;
}

/**
 * Returns a random integer between min (inclusive) and max (inclusive).
 * The value is no lower than min (or the next integer greater than min
 * if min isn't an integer) and no greater than max (or the next integer
 * lower than max if max isn't an integer).
 * Using Math.round() will give you a non-uniform distribution!
 */
function randomInt(min, max) {
    min = Math.ceil(min);
    max = Math.floor(max);
    return Math.floor(Math.random() * (max - min + 1)) + min;
}

function object2style_helper(prefix, obj) {
    const items = Object.keys(obj).map(key => {
        const type = typeof(obj[key])
        if (type === "object") {
          return object2style_helper(prefix + key + "-", obj[key])
        } else {
            return [prefix + key + ": " + obj[key]]
        }
    })
    return [].concat.apply([], items)
}

// convert a property object into an inline CSS style string
// i.e. {padding: {top: 4}, color: 'red'}
//       'padding-top: 4; color: red'
function object2style(obj) {
    const arr = object2style_helper("", obj)
    return [].concat.apply([], arr).join(';')
}


function serializeParameters(obj) {
    if (Object.keys(obj).length == 0) {
        return "";
    }

    const strings = Object.keys(obj).reduce(function(a,k) {
        if (Array.isArray(obj[k])) {
            for (let i=0; i < obj[k].length; i++) {
                a.push(encodeURIComponent(k) + '=' + encodeURIComponent(obj[k][i]));
            }
        } else {
            a.push(encodeURIComponent(k) + '=' + encodeURIComponent(obj[k]));
        }
        return a
    }, [])

    return '?' + strings.join('&')
}



function isFunction(x) {
    return (x instanceof Function);
}

function joinpath(...parts) {
    let str = "";
    for (let i=0; i < parts.length; i++) {
        if (!str.endsWith("/") && !parts[i].startsWith("/")) {
            str += "/";
        }
        str += parts[i];
    }
    return str;
}

let css_sheet = null;
let selector_names = {};

function generateStyleSheetName(element, psuedoclass) {
    const chars = 'abcdefghijklmnopqrstuvwxyz';

    let name;
    do {
        name = "css-";
        for (let i=0; i < 6; i++) {
            let c = chars[randomInt(0, chars.length - 1)];
            name += c;
        }
    } while (selector_names[name]!==undefined);



    return name
}

/**
this function has two forms based on the number of arguments
the style is always the final parameter

The single argument form builds a new style sheet and automatically
generates a class name.

StyleSheet(style)
StyleSheet(selector, style)

The two argument form builds a style sheet but allows the user to specifiy
the selector. Use to apply psuedo class selectors to existing styles.

usage:
    This example sets the color of an element to red, and changes the
    color to blue when the element is hovered over

    style1 = StyleSheet({color: red})
    style1_hover = StyleSheet(`.${style1}:hover`, {color: blue})
    element.updateProps({'className': style1})

*/
export function StyleSheet(...args) {

    let name;
    let element;
    let style;
    let psuedoclass;
    let selector;
    if (args.length === 1) {
        name = generateStyleSheetName(element, psuedoclass)
        selector = "." + name
        style = args[0]
    } else if (args.length === 2) {
        selector = args[0]
        style = args[1]
    }

    //https://stackoverflow.com/questions/1720320/how-to-dynamically-create-css-class-in-javascript-and-apply
    if (css_sheet === null) {
        css_sheet = document.createElement('style');
        css_sheet.type = 'text/css';
        document.head.appendChild(css_sheet);
    }
    const text = object2style(style)

    if (element) {
        name = element + "." + name
    }

    if (psuedoclass) {
        name = name + ":" + psuedoclass
    }

    selector_names[name] = style


    if(!(css_sheet.sheet||{}).insertRule){
        (css_sheet.styleSheet || css_sheet.sheet).addRule(selector, text);
    } else {
        css_sheet.sheet.insertRule(selector+"{"+text+"}", css_sheet.sheet.rules.length);
    }
    return name;
}

export function getStyleSheet(name) {
    return selector_names[name]
}


export const util = {
    array_move,
    randomInt,
    randomFloat,
    object2style,
    serializeParameters,
    isFunction,
    joinpath,
}
