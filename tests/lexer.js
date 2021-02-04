
// default function args
// binop assignment operators


export class Token {

    constructor(type, value, children=null, line=0, column=0) {
        this.type = type
        this.value = value
        this.children = children
        this.line = line
        this.column = column
    }
}

Token.T_NEWLINE = 'T_NEWLINE'
Token.T_TEXT = 'T_TEXT'
Token.T_STRING = 'T_STRING'
Token.T_NUMBER = 'T_NUMBER'
Token.T_SPECIAL = 'T_SPECIAL'

/*
A string iterator which keeps track of the
current position (line number and column), and allows
for peeking ahead of the current position by 1 or more characters
*/
export class StringIterator {

    constructor(str) {
        this.str = str
        this.index = 0
        this.length = str.length
        this.peek_char = ""
        this.line = 1
        this.column = -1

    }

    next() {
        let c = ''
        if (this.index <= this.length) {
            c = this.str[this.index]
            //this.index ++    // works
            //this.index += 1  // doesnt work
            this.index = this.index + 1
            return c
        }
        return null
    }

    getch() {
        let c='';
        if (this.peek_char.length > 0) {
            c = this.peek_char[0]
            this.peek_char = this.peek_char.slice(1)
        } else {
            c = this.next()
        }

        if (c == '\n') {
            this.line += 1
            this.column = -1
        }

        this.column += 1

        return c
    }

    peek() {
        let c = this.next()
        this.peek_char = this.peek_char + c
        return c
    }
}

export class LexerBase {

    constructor(iter, default_type) {

        this.iter = iter

        this._default_type = default_type
        this._type = default_type
        this._tok = ""
        this._initial_line = -1
        this._initial_index = -1
        this.tokens = []
    }

    lex() {

        while (true) {

            c = this.iter.getch()
            if (c === null) {
                break;
            }

            if (c === "\n") {
                this._maybe_push()
                this._push_endl()
            } else if (c == ' ' || c == '\t') {
                this._maybe_push()
            } else {
                this._putch(c)
            }
        }

        this._maybe_push()

    }

    _putch(c) {

        if (this._initial_line < 0) {
            this._initial_line = this.iter.line
            this._initial_index = this.iter.column
        }

        this._tok += c
    }

    _push() {
        next_token = new Token(
            this._type,
            this._tok,
            [],
            this._initial_line,
            this._initial_index
        )

        this.tokens.push(next_token)

        this._type = this._default_type
        this._initial_line = -1
        this._initial_index = -1
        this._reset()
    }

    _maybe_push() {

        if (this._tok.length > 0) {
            this._push()
        }
    }

    _push_endl() {
        const tail = this.tail()
        if (tail.type === Token.T_NEWLINE) {
            return
        }

        this.tokens.push(new Token(Token.T_NEWLINE, "", [], this.iter.line, 0))

        this._type = this._default_type
        this._initial_line = -1
        this._initial_index = -1
        this._reset()
    }

    _reset() {

        this._tok = ""
    }

    tail() {
        if (this.tokens.length > 0) {
            return this.tokens[this.tokens.length - 1];
        }
        return {type: "", value: ""};
    }
}



export function main() {

    iter = new StringIterator("hello world")

    lexer = new LexerBase(iter, Token.T_TEXT)

    lexer.lex()

    console.log(lexer.tokens)

    return 2
}

