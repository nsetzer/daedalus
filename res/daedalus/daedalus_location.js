
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

history._pushState = history.pushState;
history.pushState = (state, title, path) => {
    history._pushState(state, title, path)
    _sendEvent()
}
window.addEventListener('popstate', (event) => {
    _sendEvent()
});


