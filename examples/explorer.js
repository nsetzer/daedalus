
import daedalus with {
    StyleSheet, DomElement,
    TextElement, ListItemElement, ListElement,
    HeaderElement, ButtonElement, LinkElement
}

function api_files_list(path) {
    const url = "/api/files/list/" + path
    return fetch(url).then((response) => {return response.json()})
}

const style = {
    item_hover: StyleSheet({background: '#0000CC22'}),
    item: StyleSheet({}),
    item_file: StyleSheet({color: "blue", cursor: 'pointer'})
}

class ListItemElement2 extends ListItemElement {

    onMouseOver() {
        this.updateProps({className: style.item_hover})
    }

    onMouseOut() {
        this.updateProps({className: style.item})
    }
}

class FileElement extends DomElement {

    constructor(name, url) {
        super("div", {className: style.item_file}, [new TextElement(name)])

        this.updateState({url: url})
    }

    onClick() {
        console.log(this.state.url)
        const url = "/api/files/list" + this.state.url
        daedalus.downloadFile(url, {}, {},
            (data)=> {console.log(data)},
            (data)=> {console.error(data)})
    }
}

export class Explorer extends DomElement {
    constructor() {
        super("div", {'style': 'display: block;'}, [])

        this.header = this.appendChild(new HeaderElement())

        this.btn1 = this.appendChild(new ButtonElement("refresh",
            () => {this.loadData()}))

        this.btn2 = this.appendChild(new ButtonElement("upload",
            this.handleUploadFile.bind(this)))

        this.appendChild(new DomElement("hr"))
        this.lst = this.appendChild(new ListElement())
        this.appendChild(new DomElement("hr"))

        //this.connect(history.locationChanged, this.loadData.bind(this))

        this.first = true
    }

    elementMounted() {
        //console.log("!!MOUNTED!!")
        //if (this.first) {
        //    this.loadData()
        //    this.first = false
        //}
    }

    elementUnmounted() {
        //console.log("!!UNMOUNTED!!")
    }

    loadData(path) {
        const url = path !== undefined ? path : this.state.match.path;
        api_files_list(url)
            .then((content) => {this.handleLoadData(content)})
            .catch((err) => {console.log(err)})
    }

    elementUpdateState(oldState, newState) {
        const oldPath = oldState.match && oldState.match.path;
        if (newState.match && oldPath != newState.match.path) {
            this.loadData(newState.match.path)
        }
        return true
    }

    handleLoadData(payload) {

        this.header.setText("Directory listing for " + (payload.path || "/"))
        this.lst.removeChildren()
        let parent_url = "/explorer" + payload.parent + "/"
        if (payload.path) {
            this.lst.appendChild(new ListItemElement2(new LinkElement("..", parent_url)))
        }
        payload.files.forEach(item => {
            if (item.mode == 2) {
                // Directory
                const url = "/explorer" + payload.path + "/" + item.name
                this.lst.appendChild(new ListItemElement2(new LinkElement(item.name + "/", url)))
            } else {
                // file
                const url = payload.path + "/" + item.name
                this.lst.appendChild(new ListItemElement2(new FileElement(item.name, url)))
            }
        })
    }

    handleUploadFile() {
        const url = "/api/files/" + this.state.match.path.replace(/^\/+/g,'')

        daedalus.uploadFile(url, {}, {},
            (obj) => {console.log("success", obj); this.loadData()},
            (obj) => {console.log("failure", obj); this.loadData()},
            (obj) => {console.log("progress", obj)})
    }
}
