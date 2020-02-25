
/*
patch the history object to fire a signal every time the location changes
*/

import './daedalus_element.js'

history.locationChanged = Signal(null, "locationChanged")
history.states = [{state: {}, title: null, path: window.location.href}];
history.forward_states = [];
history._pushState = history.pushState;
history.pushState = (state, title, path) => {
    history._pushState(state, title, path);
    history.locationChanged.emit({path: location.pathname});
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
    history.locationChanged.emit({path: location.pathname});

    return true;
}
window.addEventListener('popstate', (event) => {
  history.locationChanged.emit({path: location.pathname})
});
