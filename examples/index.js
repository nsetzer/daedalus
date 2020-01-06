
import daedalus with {DomElement, TextElement, ButtonElement, Router}
import './todolist.js'
import './explorer.js'
import './minesweeper.js'

class Home extends DomElement {
    constructor() {
        super("div", {}, [])

        this.appendChild(new TextElement("Welcome to Daedalus!"))
    }
}

export class Root extends DomElement {
    constructor() {
        super("div", {}, [])
        console.log(DomElement)
        console.log(ButtonElement)
        this.btn0 = this.appendChild(new ButtonElement("home",
            ()=>{history.pushState({}, "", "/")}))
        this.btn1 = this.appendChild(new ButtonElement("todo",
            ()=>{history.pushState({}, "", "/todolist")}))
        this.btn2 = this.appendChild(new ButtonElement("explorer",
            ()=>{history.pushState({}, "", "/explorer")}))
        this.btn2 = this.appendChild(new ButtonElement("minesweeper",
            ()=>{history.pushState({}, "", "/minesweeper")}))

        // delay construction of the individual pages until the path
        // actually matches
        this.appendChild(new Router([
            {pattern: "/todolist",        element: ()=>{return new todolist.TodoList()}},
            {pattern: "/explorer/:path*", element: ()=>{return new explorer.Explorer()}},
            {pattern: "/minesweeper",     element: ()=>{return new minesweeper.Game()}},
        ], ()=>{return new Home()}))

    }


}