

from module daedalus import {
    StyleSheet, DomElement,
    TextElement, ListItemElement, ListElement,
    HeaderElement, ButtonElement, NumberInputElement, LinkElement
}

const style = {
    header: StyleSheet({'text-align': 'center'}),
    row: StyleSheet({margin: 0, padding: 0, display: 'block'}),
    board: StyleSheet({margin: "0 auto", display: 'inline-block'}),
    cell: StyleSheet({
        border: {style: "outset"},
        background: "#AAAAAA",
        width: '1.7em',
        height: '1.7em',
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
        width: '1.7em',
        height: '1.7em',
        margin: 0,
        padding: 0,
        display: "inline-block",
        text: {align: 'center'},
        vertical: {align: 'middle'},
        font: {weight: 900}
    }),
    cellf: StyleSheet({border: {style: "outset"},
        background: "#003388",
        width: '1.7em',
        height: '1.7em',
        margin: 0,
        padding: 0,
        display: "inline-block",
        text: {align: 'center'},
        vertical: {align: 'middle'},
        font: {weight: 900}
    }),
    cellm: StyleSheet({border: {style: "inset"},
        background: "#880000",
        width: '1.7em',
        height: '1.7em',
        margin: 0,
        padding: 0,
        display: "inline-block",
        text: {align: 'center'},
        vertical: {align: 'middle'},
        font: {weight: 900}
    }),
    padding: StyleSheet({padding: {bottom: '1em'}}),
    center_block: StyleSheet({text: {align: 'center'}}),
    block: StyleSheet({display: "block"}),
    button: StyleSheet({
        border: {'radius': '.5em', color: '#085923', style: 'solid', width: '1px'},
        'background-image': 'linear-gradient(#14cc51, #0a6628)',
        'text-align': 'center',
        padding: ".3em"
    }),

    panel: StyleSheet({
        border: {'radius': '0 0 .5em .5em', color: '#646464', style: 'solid', width: '1px'},
        'background-image': 'linear-gradient(#D5D5D5, #7A7A7A)',
        'text-align': 'left',
        'padding-top': '.25em',
        'padding-bottom': '.25em',
        'padding-left': '1em',
        'padding-right': '1em',
    }),

    panelRow: StyleSheet({
        'padding-top': '.25em',
        'padding-bottom': '.25em',
        'padding-left': '1em',
        'padding-right': '1em',
        display: 'flex',
        'justify-content': 'space-between',
        'align-items': 'center',
    }),

    numberInput: StyleSheet({
        width: "3em"
    })

}

StyleSheet(`.${style.button}:hover`, {
    'background-image': 'linear-gradient(#0c7f33, #063f19)';
})

StyleSheet(`.${style.button}:active`, {
    'background-image': 'linear-gradient(#063f19, #0c7f33)';
})

class GameCell extends DomElement {
    constructor(board, row, col) {
        super("div", {className: style.cell}, [])

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

class GamePanel extends DomElement {

    constructor(width, height, mineCount) {
        super("div", {className: style.panel}, [])

        this.attrs = {
            row1: new DomElement("div", {className: style.panelRow}, []),
            row2: new DomElement("div", {className: style.panelRow}, []),
            counter: new TextElement(""),
            btnNewGame: new ButtonElement("New Game", this.handleNewGame.bind(this)),
            newGame: () => {console.log("error")},
            inpWidth: new NumberInputElement(),
            inpHeight: new NumberInputElement(),
            inpCount: new NumberInputElement(),
        }

        this.attrs.btnNewGame.addClassName(style.button)
        this.attrs.inpWidth.updateProps({maxlength: 2, size: 2, max: 75, value: width})
        this.attrs.inpHeight.updateProps({maxlength: 2, size: 2, max: 75, value: height})
        this.attrs.inpCount.updateProps({maxlength: 2, size: 2, max: 75, value: mineCount})

        this.attrs.inpWidth.addClassName(style.numberInput)
        this.attrs.inpHeight.addClassName(style.numberInput)
        this.attrs.inpCount.addClassName(style.numberInput)

        this.appendChild(this.attrs.row1)
        this.appendChild(this.attrs.row2)

        this.attrs.row1.appendChild(this.attrs.counter)
        this.attrs.row1.appendChild(this.attrs.btnNewGame)

        this.attrs.row2.appendChild(new TextElement("W:"))
        this.attrs.row2.appendChild(this.attrs.inpWidth)
        this.attrs.row2.appendChild(new TextElement("H:"))
        this.attrs.row2.appendChild(this.attrs.inpHeight)
        this.attrs.row2.appendChild(new TextElement("Mines:"))
        this.attrs.row2.appendChild(this.attrs.inpCount)
    }

    setMineCount(count) {
        this.attrs.counter.setText(`Mines: ${count}`)
    }

    handleNewGame(event) {
        console.log(this.attrs.newGame)
        this.attrs.newGame(
            this.attrs.inpWidth.props.value,
            this.attrs.inpHeight.props.value,
            this.attrs.inpCount.props.value,
        )

    }

    setNewGameCallback(callback) {
        this.attrs.newGame = callback
    }

}


class GameBoard extends DomElement {
    constructor(width, height, mineCount) {
        super("div", {className: style.board}, [])

        this.attrs = {
            panel: new GamePanel(width, height, mineCount),
            initialized: false,
        }

        this.reset(width, height, mineCount)

        this.attrs.panel.setNewGameCallback(this.reset.bind(this))
    }

    reset(width, height, mineCount) {

        this.children = []

        this.attrs.initialized = false

        this.updateState({
            width: width,
            height: height,
            mineCount: mineCount,
            flagCount: 0
        });

        let row = 0;
        while (row < height) {
            const row_elem = this.appendChild(new DomElement("div", {className: style.row}, []));
            let col = 0;
            while (col < width) {
                row_elem.appendChild(new GameCell(this, row, col));
                col ++;
            }
            row ++;
        }

        this.appendChild(this.attrs.panel)
        this.attrs.panel.setMineCount(mineCount)

    }

    placeMines(mrow, mcol) {
        let placed = 0
        while (placed < this.state.mineCount) {

            let row = daedalus.util.randomInt(0, this.state.height-1);
            let col = daedalus.util.randomInt(0, this.state.width-1);
            // don't place a mine where the user clicked
            if (row == mrow && col == mcol) {
                continue
            }
            const cell = this.children[row].children[col];
            if (!cell.state.isMine) {
                cell.updateState({isMine: true});
                placed++;
            }
        }
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

        if (!this.attrs.initialized) {
            this.placeMines(cell.state.row, cell.state.col)
            this.computeCounts()
            this.attrs.initialized = true
        }
        this.revealCell(cell.state.row, cell.state.col)
    }

    handleRightClick(cell) {
        if (!cell.state.isRevealed) {

            this.flagCell(cell, !cell.state.isFlagged);

        }
    }

    flagCell(cell, flag) {

        const prev = cell.state.isFlagged

        // if the state is not changing do nothing
        if (prev == flag) {
            return
        }

        // if the user has placed the maximum number of flags do
        // not place any more flags
        if (this.state.flagCount == this.state.mineCount && flag) {
            return
        }

        cell.updateState({isFlagged: flag})

        if (cell.state.isFlagged) {
            this.updateState({flagCount: this.state.flagCount+1})
            cell.updateProps({className: style.cellf})
        } else {
            this.updateState({flagCount: this.state.flagCount-1})
            cell.updateProps({className: style.cell})
        }

        this.attrs.panel.setMineCount(this.state.mineCount - this.state.flagCount)
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
                            c.updateProps({className: style.cellm})
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
                cell.updateProps({className: style.cell2})
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
                    ///c.updateState({isFlagged: flag})
                    //const cls = flag?style.cellf:style.cell
                    //c.updateProps({className: cls})
                    this.flagCell(c, flag)
                })

            }
        }
    }

}

export class Game extends DomElement {
    constructor() {
        super("div", {className: style.block}, [])

        const em_width = getComputedStyle(document.querySelector('body'))['font-size']
        const width = window.innerWidth / parseFloat(em_width)
        const default_size = Math.floor(Math.min(0.7 * (width / 1.7), 15))
        const default_count = Math.ceil(0.15 * default_size * default_size)

        this.appendChild(new DomElement("h2", {className: style.header}, [new TextElement("Minesweeper")]))
        this.appendChild(new DomElement("div", {className: style.header}, [new LinkElement("Powered By Daedalus", "https://github.com/nsetzer/daedalus/")]))

        this.appendChild(new DomElement("div", {className: style.padding}, []))

        let div;
        div = this.appendChild(new DomElement("div", {className: style.center_block}, []))
        this.board = new GameBoard(default_size, default_size, default_count)
        div.appendChild(new DomElement("div", {className: style.center_block}, [this.board]))

        this.appendChild(new DomElement("div", {className: style.padding}, []))

        div = this.appendChild(new DomElement("div", {className: style.center_block}, []))
        div.appendChild(new TextElement("Tap / Left Click - Reveal"))
        div.appendChild(new DomElement("br", {}, []))
        div.appendChild(new TextElement("Right Click - Flag"))
        div.appendChild(new DomElement("br", {}, []))
        div.appendChild(new TextElement("Tap a revealed cell to flag adjacent cells"))


    }
}
