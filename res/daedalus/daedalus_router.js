
import {} from './daedalus_element.js'
import {parseParameters, StyleSheet, getStyleSheet, util} from './daedalus_util.js'
import {} from './daedalus_location.js'

// pattern: a location string used to match URLs
// returns a function (map, map) => string
// which constructs a valid URL
// matching the given pattern using a dictionary argument to
// fill in named groups
export function patternCompile(pattern) {
    const arr = pattern.split('/')

    let tokens=[]

    // split the pattern on forward slashes
    // create an object out of each component
    // and indicate if the component should be substituted (param: true)
    // or taken literally (param: false)
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

    // return a function which takes a mapping of items to use
    // as substitutions in the url, and an optional mapping of query parameters
    return (items, query_items) => {
        let location = '';
        for (let i=0; i < tokens.length; i++) {
            location += '/'
            if (tokens[i].param) {
                location += items[tokens[i].name]
            } else {
                location += tokens[i].value
            }
        }
        if (!!query_items) {
            location += util.serializeParameters(query_items)
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
        if (!container) {
            throw 'invalid container';
        }
        this.container = container
        this.default_callback = default_callback
        this.routes = [] // list of {pattern, callback, auth, noauth, fallback, re}
        // -1 is used for default route,
        // -2 is used to  differentiate default and never set
        this.current_index = -2
        this.current_location = null
        this.match = null
    }

    handleLocationChanged(location) {
        // location should be everything after the host name in the url

        // find the first matching route and displat that child
        let auth = this.isAuthenticated()
        let index=0;
        while (index < this.routes.length) {
            const item = this.routes[index]
            if (!auth && item.auth) {
                index += 1;
                continue
            }

            const match = locationMatch(item.re, (new URL(window.location.protocol + "//" + window.location.hostname + location)).pathname)
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
            if (index != this.current_index) {
                this.container.children = [element]
                this.container.update()
            }

            if (this.current_location !== location) {
                this.setMatch(match)
                element.updateState({match: match}) // TODO: remove
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

    setMatch(match) {
        this.match = match;
    }

    clear() {
        this.container.children = []
        this.current_index = -1
        this.current_location = null
        this.container.update()
    }

    isAuthenticated() {
        return false
    }

}

Router.instance = null;

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
