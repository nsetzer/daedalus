from module daedalus import {DomElement, TextElement, StyleSheet}

const style = {
    body: StyleSheet({
        margin:0,
        padding:0,
    }),
    main: StyleSheet({
        width: "100%",
        "text-align": "center",
    })
}

export class App extends DomElement {

    constructor() {
        super("div", {className: style.main})

        const body = document.getElementsByTagName("BODY")[0];
        body.className = style.body

        this.appendChild(new TextElement("Hello World"))
    }
}
