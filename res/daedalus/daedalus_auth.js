
import './daedalus_element.js'
import './daedalus_util.js'

// an element which is only displayed if an authentication callback
// returns true indicating the current user is authorized to view
// the given element
//
// the auth_callback logic can be inverted, in which case success
// and failure callbacks are invoked for "no auth", and "has auth"
export class AuthenticateElement extends DomElement {
    constructor(element, auth_callback, success, failure) {
        super("div", {}, [])

        this.attrs = {
            element,
            auth_callback,
            success,
            failure,
        }
    }

    handleAuth(status) {
        if (!!status) {

            // once authenticated, resolve the default element if required
            if (util.isFunction(this.element)) {
                // directly modify the state since a re-render is not required
                this.attrs.element = this.attrs.element();
            }

            // show the element if not already
            if (this.children.length == 0) {
                this.appendChild(this.attrs.element)
            }

            // call the success callback if one was provided
            if (this.attrs.success) {
                this.attrs.success()
            }
        } else {

            // remove the element from view
            if (this.children.length > 0) {
                this.removeChildren()
            }

            // call the failure callback if one was provided
            if (this.attrs.failure) {
                this.attrs.failure()
            }

        }
    }

    elementMounted() {
        // on first mount validate authentication
        if (this.children.length===0) {
            this.attrs.auth_callback()
                .then((status)=>{this.handleAuth(status)})
                .catch((error)=>{console.error(error); this.handleAuth(false);})
        }
    }

    // forward props to the child element
    elementUpdateProps(oldProps, newProps) {
        //this.attrs.element.updateProps(newProps);
        return false;
    }

    // forward state to the child element
    elementUpdateState(oldState, newState) {
        if (this.attrs.element.props.id === this.props.id) {
            throw "error"
        }
        this.attrs.element.updateState(newState);
        return false;
    }
}