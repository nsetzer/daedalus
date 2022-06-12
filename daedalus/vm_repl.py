#! cd .. && python -m daedalus.vm_repl
import os
import sys

# magic import for better input support
# may not be available on windows
try:
    import readline
except ImportError as e:
    pass

from .vm import vmGetAst, VmRuntime
from .vm_compiler import VmCompiler, VmInstruction, VmGlobals
from . import vm_opcodes as opcodes

from .token import TokenError
from .parser import ParseError

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
        self.compiler = VmCompiler()
        self.compiler._repl = True
        self.runtime = VmRuntime()
        self.runtime._init_builtins()
        self.runtime.warn_stack = False
        self.globals_ = VmGlobals()

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

        if not text:
            return

        elif text == "quit" or text == "exit" or text == "q":
            raise ExitRepl()

        elif text == "help":
            print("javascript repl")
            print("  ast expr  : print ast for expr")
            print("  dis expr  : print disassembly for expr")
            print("  exit      : exit repl")
            print("  expr      : run js expr")
            print("  globals   : print all globals and values")
            print("  help      : show this menu")
            print("  quit      : exit repl")

        elif text == "globals":

            for key, val in self.globals_.values.items():

                print(key, val)

        elif text.startswith("ast "):
            text = text[4:]
            ast =vmGetAst(text)
            print(ast.toString(3, pad=".  "))

        elif text.startswith("dis "):
            text = text[4:]
            ast =vmGetAst(text)
            mod = self.compiler.compile(ast, globals_=self.globals_)
            mod.functions[0].instrs.insert(0, VmInstruction(opcodes.const.NULL))
            mod.functions[0].instrs.append(VmInstruction(opcodes.ctrl.RETURN))

            mod.dump()

        else:
            ast =vmGetAst(text)
            mod = self.compiler.compile(ast, globals_=self.globals_)
            mod.functions[0].instrs.insert(0, VmInstruction(opcodes.const.NULL))
            mod.functions[0].instrs.append(VmInstruction(opcodes.ctrl.RETURN))
            self.runtime.init(mod, builtins=False)

            result, mod_globals = self.runtime.run()

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
