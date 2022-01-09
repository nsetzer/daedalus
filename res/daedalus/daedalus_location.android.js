
/*
patch the history object to fire an event every time the location changes
*/

include './daedalus_element.js'

function _sendEvent() {
    const myEvent = new CustomEvent('locationChangedEvent', {
      detail: {path: location.pathname},
      bubbles: true,
      cancelable: true,
      composed: false
    })
    window.dispatchEvent(myEvent)
}

history.states = [{state: {}, title: null, path: window.location.href}];
history.forward_states = [];
history._pushState = history.pushState;
history.pushState = (state, title, path) => {
    history._pushState(state, title, path);
    _sendEvent()
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
    history._pushState(new_state.state, new_state.title, new_state.path)
    _sendEvent()

    return true;
}
window.addEventListener('popstate', (event) => {
    _sendEvent()
});
