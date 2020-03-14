
include './daedalus_element.js'
include './daedalus_location.js'

// pattern: a location string used to match URLs
// returns a function (map) => string
// which constructs a valid URL
// matching the given pattern using a dictionary argument to
// fill in named groups
export function patternCompile(pattern) {
    const arr = pattern.split('/')

    let tokens=[]

    for (let i=1; i < arr.length; i++) {

        let part = arr[i]

        if (part.startsWith(':')) {
            if (part.endsWith('?')) {
                tokens.push({param: true, name: part.substr(1, part.length-2)})
            } else if (part.endsWith('+')) {
                tokens.push({param: true, name: part.substr(1, part.length-2)})
            } else if (part.endsWith('*')) {
                tokens.push({param: true, name: part.substr(1, part.length-2)})
            } else {
                tokens.push({param: true, name: part.substr(1)})
            }
        } else {
            tokens.push({param: false, value: part})
        }

    }

    return items => {
        let location = '';
        for (let i=0; i < tokens.length; i++) {
            location += '/'
            if (tokens[i].param) {
                location += items[tokens[i].name]
            } else {
                location += tokens[i].value
            }
        }
        return location;
    }
}

// pattern: a location string used to match URLs
// returns an object which can be used for matching strings
// exact match :  /abc
// named group :  /:name
// zero or one :  /:name?
// one or more :  /:name+
// zero or more:  /:name*

export function patternToRegexp(pattern, exact=true) {

    const arr = pattern.split('/')

    let re = "^"

    let tokens=[]

    for (let i=exact?1:0; i < arr.length; i++) {
        let part = arr[i]

        if (i==0 && exact === false) {
            ;
        } else {
            re += "\\/";
        }

        if (part.startsWith(':')) {

            if (part.endsWith('?')) {
                // zero or one
                tokens.push(part.substr(1, part.length-2))
                re += "([^\\/]*)"
            } else if (part.endsWith('+')) {
                // one or more
                tokens.push(part.substr(1, part.length-2))
                re += "?(.+)"
            } else if (part.endsWith('*')) {
                // zero or more
                tokens.push(part.substr(1, part.length-2))
                re += "?(.*)"
            } else {
                // exactly one
                tokens.push(part.substr(1))
                re += "([^\\/]+)"
            }

        } else {
            re += part
        }

    }

    if (re !== "^\\/") {
        re += "\\/?"
    }

    re += "$"

    return {re: new RegExp(re, "i"), text:re, tokens}
}

export function locationMatch(obj, location) {

    // reset this regex object if it has
    // been used before
    obj.re.lastIndex = 0

    let arr = location.match(obj.re)

    if (arr == null) {
        return null;
    }

    let result = {}
    for (let i=1; i < arr.length; i++) {
        result[obj.tokens[i-1]] = arr[i]
    }

    return result;
}

function patternMatch(pattern, location) {
    //
    return locationMatch(patternToRegexp(pattern), location)
}

/**
@class Router

*/
export class Router extends DomElement {
    constructor(route_list, default_element) {
        super("div", {}, [])

        this.default_element = default_element
        this.routes = route_list.map(item => {
            const re = patternToRegexp(item.pattern);
            return {re, pattern:item.pattern, element: item.element};
        })
        this.current_index = -1
        this.current_location = null

        this.connect(history.locationChanged, this.doRoute.bind(this))

    }

    elementMounted() {
        this.doRoute()
    }

    doRoute() {

        // find the first matching route and displat that child
        let i=0;
        while (i < this.routes.length) {
            const item = this.routes[i]
            const match = locationMatch(item.re, window.location.pathname)
            if (match !== null) {

                // if the location results in a new child to be diplayed
                // then display that child. otherwise there is no need
                // to update the child
                if (this.current_index !== i) {
                    // replace a callable with an element when it
                    // finally routes
                    if (util.isFunction(item.element)) {
                        item.element = item.element()
                    }
                    this.children = [item.element]
                    this.update()
                }

                // Note: order matters
                // updateState after this.update()
                // otherwise partial parentFiber update effect has no parent dom

                // if the location has changed, update the match for the child
                if (this.current_location !== window.location.pathname) {
                    item.element.updateState({match: match})
                }

                this.current_index = i;
                this.current_location = window.location.pathname;


                return;
            }
            i += 1;
        }

        if (util.isFunction(this.default_element)) {
            this.default_element = this.default_element()
        }

        this.current_index = -1;
        // no route, display the default element
        if (this.default_element) {
            this.children = [this.default_element]
            this.update()
        } else {
            this.children = []
            this.update()
        }
    }
}