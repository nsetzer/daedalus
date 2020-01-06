
import daedalus with {
    StyleSheet, DomElement, Signal, TextInputElement,
    TextElement, ListItemElement, ListElement,
    HeaderElement, ButtonElement, NumberInputElement
}

function api_list_get() {
    const url = "/api/todo"
    return fetch(url).then((response) => {return response.json()})
}

function api_list_set(todolist) {
    const url = "/api/todo"
    return fetch(url, {
        method: "POST",
        headers: {'Content-Type': "application/json"},
        body: JSON.stringify(todolist),
    }).then((response) => {return response.json()})
}

style = {
    show: StyleSheet({display: 'inline'}),
    hide: StyleSheet({display: 'none'}),
}

class TodoItem extends DomElement {

    constructor(text) {
        super("li", {}, [])
        const child = new DomElement("div", {}, [
            new ButtonElement("up", this.handleMoveUp.bind(this)),
            new ButtonElement("down", this.handleMoveDown.bind(this)),

        ])
        this.child = this.appendChild(child)


        this.moveUp = Signal(this, "moveUp")
        this.moveDown = Signal(this, "moveDown")

        this.updateState({text: text})

        this.btn_edit = new ButtonElement("edit", this.handleEdit.bind(this));
        this.child.appendChild(this.btn_edit);

        this.wtext = new TextElement(text);
        this.wtext_container = this.child.appendChild(new DomElement("div", {}, [this.wtext]))
        this.wtext_container.updateProps({className: style.show});
        this.wedit = this.child.appendChild(new TextInputElement(text));
        this.wedit.updateProps({className: style.hide});
    }

    handleMoveUp() {
        this.moveUp.emit()
    }

    handleMoveDown() {
        this.moveDown.emit()
    }

    handleEdit() {

        if (this.btn_edit.getText()==='edit') {
            this.btn_edit.setText('save')

            this.wedit.updateProps({className: style.show})
            this.wtext_container.updateProps({className: style.hide})
        } else {
            this.btn_edit.setText('edit')
            const newValue = this.wedit.props.value;
            this.updateState({text: newValue});
            this.wtext.setText(newValue)

            this.wedit.updateProps({className: style.hide})
            this.wtext_container.updateProps({className: style.show})
        }
    }
}

export class TodoList extends ListElement {
    constructor() {
        super()

        this.header = this.appendChild(new HeaderElement("Todo List"))

        this.btn1 = this.appendChild(new ButtonElement("save", this.handleSave.bind(this)))

        this.div_lst = this.appendChild(new DomElement("div", {}, []))

    }

    elementMounted() {
        this.loadData()
    }

    moveUp(child) {
        let p1 = this.div_lst.children.indexOf(child)
        daedalus.util.array_move(this.div_lst.children, p1, p1 - 1)
        this.update()
        //console.log(this.children.indexOf(child))
    }

    moveDown(child) {
        let p1 = this.div_lst.children.indexOf(child)
        daedalus.util.array_move(this.div_lst.children, p1, p1 + 1)
        this.update()
    }

    loadData() {
        api_list_get()
            .then(data => this.handleLoad(data))
            .catch(error => console.error(error));
    }

    handleLoad(data) {
        console.log(data)
        let items = data.result;
        this.div_lst.removeChildren();
        items.forEach(item => {
            let child = this.div_lst.appendChild(new TodoItem(item))
            this.connect(child.moveUp, ()=>{this.moveUp(child)})
            this.connect(child.moveDown, ()=>{this.moveDown(child)})
        })
    }

    handleSave() {
        const lst = this.div_lst.children.map(child => child.state.text)
        api_list_set(lst)
    }
}
