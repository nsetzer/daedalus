
/*
patch the history object to fire a signal every time the location changes
*/

import './daedalus_element.js'

history.locationChanged = Signal(null, "locationChanged")
history._pushState = history.pushState;
history.pushState = (state, title, path) => {
    history._pushState(state, title, path)
    history.locationChanged.emit({path: location.pathname})
}
window.addEventListener('popstate', (event) => {
  history.locationChanged.emit({path: location.pathname})
});
