

import daedalus with {
    StyleSheet, DomElement,
    TextElement, ListItemElement, ListElement,
    HeaderElement, ButtonElement, NumberInputElement
}

const game_style = {
    row: StyleSheet({margin: 0, padding: 0, display: 'block'}),
    board: StyleSheet({margin: "0 auto", display: 'inline-block'}),
    cell: StyleSheet({
        border: {style: "outset"},
        background: "#AAAAAA",
        width: '1.5em',
        height: '1.5em',
        margin: 0,
        padding: 0,
        display: "inline-block",
        text: {align: 'center'},
        vertical: {align: 'middle'},
        font: {weight: 900}
    }),
    cell2: StyleSheet({
        border: {style: "inset"},
        background: "#CCCCCC",
        width: '1.5em',
        height: '1.5em',
        margin: 0,
        padding: 0,
        display: "inline-block",
        text: {align: 'center'},
        vertical: {align: 'middle'},
        font: {weight: 900}
    }),
    cellf: StyleSheet({border: {style: "outset"},
        background: "#003388",
        width: '1.5em',
        height: '1.5em',
        margin: 0,
        padding: 0,
        display: "inline-block",
        text: {align: 'center'},
        vertical: {align: 'middle'},
        font: {weight: 900}
    }),
    cellm: StyleSheet({border: {style: "inset"},
        background: "#880000",
        width: '1.5em',
        height: '1.5em',
        margin: 0,
        padding: 0,
        display: "inline-block",
        text: {align: 'center'},
        vertical: {align: 'middle'},
        font: {weight: 900}
    }),
    padding: StyleSheet({padding: {bottom: '1em'}}),
    center_block: StyleSheet({text: {align: 'center'}}),
    block: StyleSheet({display: "block"})
}

class GameCell extends DomElement {
    constructor(board, row, col) {
        super("div", {className: game_style.cell}, [])

        this.text = this.appendChild(new TextElement("0"))

        this.updateState({
            isRevealed: false,
            isFlagged: false,
            isMine: false,
            count: 0,
            board,
            row,
            col
        })
    }

    onClick() {
        this.state.board.handleLeftClick(this)
    }

    onContextMenu(event) {
        event.preventDefault();
        this.state.board.handleRightClick(this)
        return false;
    }

    elementUpdateProps(oldProps, newProps) {
        this.recomputeCellContent(this.state)

        return true;
    }

    elementUpdateState(oldState, newState) {
        this.recomputeCellContent(newState)
        return true;
    }

    recomputeCellContent(state) {

        if (state.isRevealed) {
            if (state.isMine) {
                this.text.setText("x")
            } else if (state.count > 0) {
                this.text.setText(state.count)
            } else {
                this.text.setText("")
            }
        } else {
            this.text.setText("")
        }
    }
}

class GameBoard extends DomElement {
    constructor(width, height, mineCount) {
        super("div", {className: game_style.board}, [])


        this.reset(width, height, mineCount)

    }

    reset(width, height, mineCount) {

        this.children = []

        this.updateState({width: width, height: height, mineCount: mineCount});

        let row = 0;
        while (row < height) {
            const row_elem = this.appendChild(new DomElement("div", {className: game_style.row}, []));
            let col = 0;
            while (col < width) {
                row_elem.appendChild(new GameCell(this, row, col));
                col ++;
            }
            row ++;
        }

        let placed = 0
        while (placed < this.state.mineCount) {

            let row = daedalus.util.randomInt(0, this.state.height-1);
            let col = daedalus.util.randomInt(0, this.state.width-1);
            const cell = this.children[row].children[col];
            if (!cell.state.isMine) {
                cell.updateState({isMine: true});
                placed++;
            }
        }
        this.computeCounts()
    }

    computeCounts() {
        for (let row=0; row < this.state.height; row++) {
            for (let col=0; col < this.state.width; col++) {
                if (this.indexIsMine(row, col)) {
                    this.incrementCount(row-1, col-1);
                    this.incrementCount(row-1, col);
                    this.incrementCount(row-1, col+1);

                    this.incrementCount(row, col-1);
                    this.incrementCount(row, col+1);

                    this.incrementCount(row+1, col-1);
                    this.incrementCount(row+1, col);
                    this.incrementCount(row+1, col+1);
                }
            }
        }

    }

    indexIsMine(row, col) {
        if (row >= 0 && row < this.state.height) {
            if (col >= 0 && col < this.state.width) {
                return this.children[row].children[col].state.isMine
            }
        }
        return false;
    }

    incrementCount(row, col) {
        if (row >= 0 && row < this.state.height) {
            if (col >= 0 && col < this.state.width) {
                const cell = this.children[row].children[col];
                cell.updateState({count: cell.state.count+1}, false)
            }
        }
    }

    handleLeftClick(cell) {
        this.revealCell(cell.state.row, cell.state.col)
    }

    handleRightClick(cell) {
        if (!cell.state.isRevealed) {

            cell.updateState({isFlagged: !cell.state.isFlagged})
            const cls = cell.state.isFlagged?game_style.cellf:game_style.cell
            cell.updateProps({className: cls})
        }
    }

    revealCell(row, col) {

        const queue = [[row,col]]
        const visited = {}

        const enqueue = (r,c) => {
            if (r >= 0 && r < this.state.height) {
                if (c >= 0 && c < this.state.width) {
                    const idx = r * this.state.width + c;
                    if (!visited[idx]) {
                        queue.push([r, c])
                    }
                }
            }
        }

        while (queue.length > 0) {
            [row, col] = queue.shift()

            const idx = row * this.state.width + col;
            if (visited[idx] === true) {
                continue;
            }
            visited[idx] = true;

            const cell = this.children[row].children[col];

            if (cell.state.isFlagged) {
                ; // don't  reveal flagged cells
            } else if (cell.state.isMine) {

                for (let i=0; i < this.state.height; i++) {
                    for (let j=0; j < this.state.width; j++) {
                        const c = this.children[i].children[j];
                        if (c.state.isMine) {
                            c.updateState({isRevealed: true})
                            c.updateProps({className: game_style.cellm})
                        }
                    }
                }

            } else if (!cell.state.isRevealed) {
                if (cell.state.count === 0) {

                    enqueue(row-1, col-1);
                    enqueue(row-1, col  );
                    enqueue(row-1, col+1);
                    enqueue(row  , col-1);
                    enqueue(row  , col+1);
                    enqueue(row+1, col-1);
                    enqueue(row+1, col  );
                    enqueue(row+1, col+1);

                }
                cell.updateState({isRevealed: true})
                cell.updateProps({className: game_style.cell2})
            } else if (cell.state.isRevealed && Object.keys(visited).length==1) {
                let cells = []
                for (let i=row-1;i<=row+1;i++) {
                    for (let j=col-1;j<=col+1;j++) {
                        if (i >= 0 && i < this.state.height) {
                            if (j >= 0 && j < this.state.width) {
                                cells.push(this.children[i].children[j])
                            }
                        }
                    }
                }
                cells = cells.filter(c => !c.state.isRevealed)
                const flag = !cells.reduce((a, c)=> a && c.state.isFlagged, true)
                cells.forEach(c => {
                    c.updateState({isFlagged: flag})
                    const cls = flag?game_style.cellf:game_style.cell
                    c.updateProps({className: cls})
                })

            }
        }
    }
}

export class Game extends DomElement {
    constructor() {
        super("div", {className: game_style.block}, [])

        const em_width = getComputedStyle(document.querySelector('body'))['font-size']
        const width = window.innerWidth / parseFloat(em_width)
        const default_size = Math.floor(Math.min(0.7 * (width / 1.5), 15))
        const default_count = Math.ceil(0.15 * default_size * default_size)
        console.log(default_size)

        this.appendChild(new DomElement("div", {className: game_style.padding}, []))

        let div;
        div = this.appendChild(new DomElement("div", {className: game_style.center_block}, []))
        this.board = new GameBoard(default_size, default_size, default_count)
        div.appendChild(new DomElement("div", {className: game_style.center_block}, [this.board]))

        this.appendChild(new DomElement("div", {className: game_style.padding}, []))

        div = this.appendChild(new DomElement("div", {className: game_style.center_block}, []))
        div.appendChild(new ButtonElement("New Game", ()=>{
            this.board.reset(
                this.spinW.props.value,
                this.spinH.props.value,
                this.spinC.props.value);
        }))

        this.appendChild(new DomElement("div", {className: game_style.padding}, []))

        div = this.appendChild(new DomElement("div", {className: game_style.center_block}, []))
        this.spinW = div.appendChild(new NumberInputElement(default_size));
        this.spinH = div.appendChild(new NumberInputElement(default_size));
        this.spinC = div.appendChild(new NumberInputElement(default_count));

        this.appendChild(new DomElement("div", {className: game_style.padding}, []))

        div = this.appendChild(new DomElement("div", {className: game_style.center_block}, []))
        div.appendChild(new TextElement("Tap / Left Click - Reveal"))
        div.appendChild(new DomElement("br", {}, []))
        div.appendChild(new TextElement("Right Click - Flag"))
        div.appendChild(new DomElement("br", {}, []))
        div.appendChild(new TextElement("Tap a revealed cell to flag adjacent cells"))


    }
}
