
/*
patch the history object to fire an event every time the location changes
*/

import {DomElement} from './daedalus_element.js'

window.daedalus_location = "/"
function _sendEvent(path) {
    const myEvent = new CustomEvent('locationChangedEvent', {
      detail: {path: path},
      bubbles: true,
      cancelable: true,
      composed: false
    })
    window.daedalus_location = path
    window.dispatchEvent(myEvent)
}
history.states = [{state: {}, title: null, path: window.daedalus_location}];
history.forward_states = [];
history._pushState = history.pushState;
history.pushState = (state, title, path) => {
    // history._pushState(state, title, path);
    _sendEvent(path)
    history.forward_states = [];
    history.states.push({state, title, path})
}
history.goBack = () => {
    if (history.states.length < 2) {
        return false;
    }
    const state = history.states.pop();
    history.forward_states.splice(0, 0, state);

    const new_state = history.states[history.states.length - 1]
    //history._pushState(new_state.state, new_state.title, new_state.path)
    _sendEvent(new_state.path)

    return true;
}
window.addEventListener('popstate', (event) => {
    history.goBack()
});