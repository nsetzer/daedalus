
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
 * A class which controls the child element of another DomElement using
 * the current location.
 *
 * This class is designed to be embeddable. The method handleLocationChanged
 * should be called by the user whenever the location has been changed.
 * This class can be used independently of the window location, provided
 * the user can provide an alternative location.
 */
export class Router {

    /**
     * container: a DomElement
     * default_callback: function(setElementCallback)
     */
    constructor(container, default_callback) {
        this.container = container
        this.default_callback = default_callback
        this.routes = [] // list of {pattern, callback, auth, noauth, fallback, re}
        this.current_index = -1
        this.current_location = null
    }

    handleLocationChanged(location) {

        // find the first matching route and displat that child
        let index=0;
        while (index < this.routes.length) {
            const item = this.routes[index]
            const match = locationMatch(item.re, location)
            if (match !== null) {

                // if the location results in a new child to be diplayed
                // then display that child. otherwise there is no need
                // to update the child

                let fn = (element) => this.setElement(index, location, match, element)
                if (this.doRoute(item, fn, match)) {
                    return
                }
            }
            index += 1;
        }

        // no route, display the default element
        let fn = (element) => this.setElement(-1, location, null, element)
        this.default_callback(fn)
        return
    }

    /**
     * item: the route object
     * fn: a callback function which will set the element in the container
     * match: the location match result
     *
     * When a location matches a known route this function is called
     * the route object contains a callback which should be called
     * In which case this method returns true. If this route should not
     * be followed return false
     *
     */
    doRoute(item, fn, match) {
        item.callback(fn, match)
        return true
    }

    setElement(index, location, match, element) {
        if (!!element) {
            console.log(element)
            if (index != this.current_index) {
                this.container.children = [element]
                this.container.update()
            }

            if (this.current_location !== location) {
                element.updateState({match: match})
            }

            this.current_index = index
        } else {
            this.container.children = []
            this.current_index = -1
            this.container.update()
        }

        this.current_location = location
    }

    addRoute(pattern, callback) {
        const re = patternToRegexp(pattern);
        this.routes.push({pattern, callback, re})
    }

    /**
     * set the callback to use for the default route, when no
     * other defined route matches the current location.
     *
     * callback :: function(setElementCallback)
     *   the callback should be a function which accepts asingle arugment,
     *   a function that will be used to set an element as a child of the
     *   container
     */
    setDefaultRoute(callback) {
        this.default_callback = callback
    }
}

export class AuthenticatedRouter extends Router {

    constructor(container, route_list, default_callback) {
        super(container, route_list, default_callback)
        this.authenticated = false;
    }

    /**
     *
     */
    doRoute(item, fn, match) {

        let has_auth = this.isAuthenticated()

        if (item.auth===true && item.noauth === undefined) {

            if (!!has_auth) {
                item.callback(fn, match)
                return true
            } else if (item.fallback !== undefined) {
                history.pushState({}, "", item.fallback)
                return true
            }
        }

        if (item.auth===undefined && item.noauth === true) {
            console.log(item, has_auth)
            if (!has_auth) {
                item.callback(fn, match)
                return true
            } else if (item.fallback !== undefined) {
                history.pushState({}, "", item.fallback)
                return true
            }
        }

        if (item.auth===undefined && item.noauth === undefined) {
            item.callback(fn, match)
            return true
        }

        return false

    }

    isAuthenticated() {
        return this.authenticated;
    }

    setAuthenticated(value) {
        this.authenticated = !!value;
    }

    addAuthRoute(pattern, callback, fallback) {
        const re = patternToRegexp(pattern);
        this.routes.push({pattern, callback, auth:true, fallback, re})
    }

    addNoAuthRoute(pattern, callback, fallback) {
        const re = patternToRegexp(pattern);
        this.routes.push({pattern, callback, noauth:true, fallback, re})
    }
}