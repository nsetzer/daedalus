

function array_move(arr, p1, p2) {

    //let s1 = p1
    //let s2 = p2
    if (p1 < 0) {p1 = 0}
    if (p2 < 0) {p2 = 0}
    if (p1 > arr.length) {p1 = arr.length}
    if (p2 > arr.length) {p2 = arr.length}
    if (p1 == p2) {
        return
    }

    //let item = arr[p1]
    //console.log(s1, s2, "|", p1, "+>", p2, "+>", arr.indexOf(item))
    arr.splice(p2, 0, arr.splice(p1, 1)[0]);
    return;
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
    let _rnd = Math.random()
    let _min = Math.ceil(min);
    let _max = Math.floor(max);
    return Math.floor(_rnd * (_max - _min + 1)) + _min;
}

function object2style_helper(prefix, obj) {

    const items = Object.keys(obj).map(key => {
        const val = obj[key];
        const type = typeof(val)
        if (type === "object") {
            return object2style_helper(prefix + key + "-", val)
        } else {
            return [prefix + key + ": " + val]
        }
    })
    let out = []
    for (let i=0; i< items.length; i++) {
        out.concat(items[i])
    }
    return out
}

// convert a property object into an inline CSS style string
// i.e. {padding: {top: 4}, color: 'red'}
//       'padding-top: 4; color: red'
function object2style(obj) {
    const arr = object2style_helper("", obj)
    return [].concat(arr).join(';')
}


function serializeParameters(obj) {
    if (Object.keys(obj).length == 0) {
        return "";
    }

    const strings = Object.keys(obj).reduce((a,k) => {
        if (obj[k] === null || obj[k] === undefined) {
            ; // nothing to do
        } else if (Array.isArray(obj[k])) {
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

/**
 * Parse URL Parameters from a string or the current window location
 *
 * return an object mapping of string to list of strings
 */
export function parseParameters(text=undefined) {
    let match;
    let search = /([^&=]+)=?([^&]*)/g
    let decode = s => decodeURIComponent(s.replace(/\+/g, " "))
    //let search_term = window.location.search;
    let search_term = (new URL(window.location.protocol + "//" + window.location.hostname + window.daedalus_location)).search
    let query  = (text===undefined)?search_term.substring(1):text;

    let urlParams = {};
    while (match = search.exec(query)) {
        let value = decode(match[2])
        let key = decode(match[1])
        if (urlParams[key]===undefined) {
            urlParams[key] = [value]
        } else {
            urlParams[key].push(value)
        }
    }
   return urlParams
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

function splitpath(path) {
    const parts = path.split('/');
    if (parts.length > 0 && parts[parts.length-1].length === 0) {
        parts.pop()
    }
    return parts;
}

// return the directory name containing the given path
// assumes unix style paths
function dirname(path) {
    const parts = path.split('/');
    while (parts.length > 0 && parts[parts.length-1].length === 0) {
        parts.pop()
    }
    return joinpath(...parts.slice(0, -1))
}

// foo.txt -> ['foo', '.txt']
// .config -> ['.config', '']
// path/to/.config -> ['path/to/.config', '']
// path/to/foo.txt -> ['path/to/foo', '.txt']
function splitext(name) {
    const index = name.lastIndexOf('.');
    if (index <= 0 || name[index-1] == '/') {
        return [name, '']
    }
    else {
        return [name.slice(0,index), name.slice(index)]
    }
}

let css_sheet = null;
let selector_names = {};

function generateStyleSheetName() {
    const chars = 'abcdefghijklmnopqrstuvwxyz';

    let name;
    do {
        name = "css-";
        for (let i=0; i < 6; i++) {
            let c = chars[randomInt(0, chars.length - 1)];
            name += c;
        }
    } while (name in selector_names);
    //} while (selector_names[name]!==undefined);

    return name
}

// inplace fisher-yates
function shuffle(array) {
  let currentIndex = array.length, temporaryValue, randomIndex;

  while (0 !== currentIndex) {

    randomIndex = Math.floor(Math.random() * currentIndex);
    currentIndex -= 1;

    temporaryValue = array[currentIndex];
    array[currentIndex] = array[randomIndex];
    array[randomIndex] = temporaryValue;
  }

  return array;
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
    let style;
    let selector;
    if (args.length === 1) {
        name = generateStyleSheetName()
        selector = "." + name
        style = args[0]
    } else if (args.length === 2) {
        selector = args[0]
        style = args[1]
        name = selector
    }

    if (args.length >= 3) {
        // format args as a csv string
        let str = ""
        for (let i=0; i < args.length; i++) {
            if (i > 0) {
                str += ", "
            }
            // if the argument is an object, JSONify it
            if (typeof(args[i]) === "object") {
                str += JSON.stringify(args[i])
            } else {
                str += args[i]
            }
        }
        console.error(`Invalid Style Sheet StyleSheet(${str})`)
        return
    }
    if (style === undefined) {
        console.log(`$nargs=${args.length}`)
        console.log(`${args[0]}, ${args[1]}, ${args[2]}`)
        console.log(`StyleSheet(name=${name}, selector=${selector}, style=${style})`)
        throw new Error("style must be defined")
    }
    //https://stackoverflow.com/questions/1720320/how-to-dynamically-create-css-class-in-javascript-and-apply
    if (css_sheet === null) {
        css_sheet = document.createElement('style');
        css_sheet.type = 'text/css';
        document.head.appendChild(css_sheet);
    }
    const text = object2style(style)

    selector_names[name] = style

    css_sheet.sheet.insertRule(selector+" {"+text+"}", css_sheet.sheet.rules.length);
    return name;
}

export function getStyleSheet(name) {
    return selector_names[name]
}

function perf_timer() {
    return performance.now();
}

export const util = {
    array_move,
    randomInt,
    randomFloat,
    object2style,
    serializeParameters,
    parseParameters,
    isFunction,
    joinpath,
    splitpath,
    dirname,
    splitext,
    shuffle,
    perf_timer,
}

