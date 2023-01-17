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

class Button extends DomElement {
    constructor() {
        super("input", {"type": "button", "value":"Click Me"})

        console.log("construct")
    }

    elementMounted() {
        console.log("mount")
        window.channel.objects.core1.pyCallMe.connect((arg)=>{
            let obj = JSON.parse(arg)
            console.log(arg)
            this.props.value = obj.text
            this.update()
            window.channel.objects.core1.jsCallMe(2)
        })
    }

    onClick() {
        let x = window.channel.objects.core1.jsCallMe(1)
        console.log(x)



    }
}

export class App extends DomElement {

    constructor() {
        super("div", {className: style.main})

        const body = document.getElementsByTagName("BODY")[0];
        body.className = style.body

        this.appendChild(new Button())

    }
}
