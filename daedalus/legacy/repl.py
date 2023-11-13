

# magic import for better input support
# may not be available on windows
try:
    import readline
except ImportError:
    pass

from daedalus.lexer import TokenError
from daedalus.jseval import JsContext
from daedalus.builtins import defaultGlobals

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
                    next(g) + next(g)
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
        self.ctxt = JsContext()

    def main(self):

        while True:
            try:

                text = input(self.prompt)
                # check for a multi-line input
                text = text.strip()
                while text.endswith("\\"):
                    text = text[:-1] + input("> ")
                    text = text.strip()

                # process the line
                self._main(text)
            except ExitRepl:
                break
            except KeyboardInterrupt:
                pass
            except TokenError as e:
                print("exception", e)
            except Exception as e:
                print("exception", e)

    def _main(self, text):

        text = text.strip()

        if not text:
            return

        elif text == "quit" or text == "exit" or text == "q":
            raise ExitRepl()

        elif text == "help":
            pass

        elif text == "diag":
            pass

        elif text == "globals":
            defaults = defaultGlobals()

            for key, val in self.ctxt.globals.items():

                if key in defaults and defaults[key] is val:
                    continue

                print(key, val)

        elif text.startswith("ast "):
            text = text[4:]
            ast = self.ctxt.parsejs(text)
            print(ast.toString(3, pad=".  "))

        elif text.startswith("dis "):
            text = text[4:]
            compiler = self.ctxt.compilejs(text)
            compiler.dump()

        else:
            result = self.ctxt.evaljs(text)

            if isinstance(result, dict):
                if result and "_" in result:
                    print(result["_"])
            else:
                print(result)

def main():

    repl = Repl()

    repl.main()


if __name__ == '__main__':
    main()
