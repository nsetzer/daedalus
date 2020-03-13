
import os
import sys
import readline

from daedalus.lexer import Lexer, Token, TokenError
from daedalus.parser import Parser
from daedalus.interpreter import Interpreter

class ExitRepl(Exception):
    pass

def unescape(text):

    out = ""
    g = text.__iter__()
    while True:
        try:
            c = next(g)
            if c == '\\':
                c = next(g)
                if c == 'n':
                    out += "\n"
                elif c == 'e':
                    pass
                elif c == 'w':
                    pass
                elif c == 'a':
                    pass
                elif c == 'h':
                    pass
                elif c == 'u':
                    pass
                elif c == '[':
                    pass
                elif c == ']':
                    pass
                elif c == '0':
                    s = next(g) + next(g)
                    pass
                else:
                    out += c
            else:
                out += c

        except StopIteration:
            break
    return out

def get_prompt():
    #prompt = os.environ.get('PS1', "$")
    #prompt = unescape(prompt)
    #parts = [p for p in prompt.split("\n") if p.strip()]
    #parts[-1] = "(daedalus) " + parts[-1]
    # return '\n'.join(parts)
    return "\n(daedalus)\n>>> "

class Repl(object):
    def __init__(self):
        super(Repl, self).__init__()

        self.prompt = get_prompt()
        self.globals = {}

    def main(self):

        while True:
            try:
                text = input(self.prompt)
                self._main(text)
            except ExitRepl as e:
                break
            except KeyboardInterrupt as e:
                pass
            except TokenError as e:
                print("exception", e)
            except Exception as e:
                print("exception", e)

    def _main(self, text):

        text = text.strip()

        if not text.strip():
            return

        if text == "quit" or text == "exit" or text == "q":
            raise ExitRepl()

        if text == "help":
            return

        if text == "diag":
            return

        # self.globals['globals'] = lambda: list(sorted(self.globals.keys()))

        tokens = Lexer().lex(text)
        ast = Parser().parse(tokens)
        interp = Interpreter(filename="<string>", globals=self.globals, flags=Interpreter.CF_REPL)

        interp.compile(ast)

        result = interp.function_body()

        if isinstance(result, dict):

            self.globals.update(result)
            if result and "_" in result:
                print(result["_"])
        else:
            print(result)

def main():

    repl = Repl()

    repl.main()


if __name__ == '__main__':
    main()
