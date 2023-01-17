
/*
patch the history object to fire an event every time the location changes
*/
if (location) {
    window.daedalus_location = location.pathname + location.search + location.hash
}

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

history._pushState = history.pushState;
history.pushState = (state, title, path) => {
    history._pushState(state, title, path)
    _sendEvent(path)
}
window.addEventListener('popstate', (event) => {
    _sendEvent(location.pathname + location.search + location.hash)
});


