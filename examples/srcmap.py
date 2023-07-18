
import os
import sys
import io
import json
import base64

from daedalus.lexer import Lexer, Token, TokenError
from daedalus.parser import Parser, xform_apply_file
from daedalus.formatter import Formatter
from daedalus.sourcemap import SourceMap
from daedalus.transform import TransformMinifyScope

html = """
<!DOCTYPE html>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,shrink-to-fit=no">
<html lang="en">
<head>
<script type="text/javascript" src='example.out.js'></script>
</head>
<body>
<div id="root">Enable Javascript to render site.</div>
</body>
</html>
"""

def debug(html, source, source_out, srcmap):

    print("---")
    print(source)
    print("---")
    print(source_out)
    print("---")

    source_lines = list(source.splitlines())

    print(srcmap['mappings'])
    all_fields = SourceMap.decode(srcmap['mappings'])

    tokens = Lexer().lex(source)
    token_map = {(t.line,t.index): t for t in tokens}


    for lineno, fields in enumerate(all_fields):

        for field in fields:
            if len(field) == 4:
                column, file_index, token_line, token_index = field
                symbol_index = 0
                symbol = ""
            if len(field) == 5:
                column, file_index, token_line, token_index, symbol_index = field
                symbol = ""

            # token = token_map[(token_line, token_index)]
            line = source_lines[token_line][token_index:]
            tokens = Lexer().lex(line)
            print("%6d %6d %s" % (lineno, column, tokens[0].value))

def save(html, source, source_out, srcmap):
    if not os.path.exists("./dist"):
        os.makedirs("./dist")

    with open("./dist/index.html", "w") as wf:
        wf.write(html)
        wf.write("\n")

    with open("./dist/example.js", "w") as wf:
        wf.write(source)
        wf.write("\n")

    with open("./dist/example.out.js", "w") as wf:
        wf.write("//# sourceMappingURL=example.out.js.map\n")
        wf.write(source_out)
        wf.write("\n")

    with open("./dist/example.out.js.map", "w") as wf:
        srcmapjson = json.dumps(srcmap)
        wf.write(srcmapjson)
        wf.write("\n")

    # the source map can be inlined in the generated source
    # note that the original source can also be inlined in the source map
    # allowing for one file with all context in it for debugging
    # this is not supported by daedalus
    with open("./dist/example.inline.js", "w") as wf:

        srcmap['sourcesContent'] = [source]
        srcmapjson = json.dumps(srcmap)
        encoded = base64.b64encode(srcmapjson.encode("UTF-8")).decode("utf-8")

        wf.write("//# sourceMappingURL=data:application/json;base64,")
        wf.write(encoded)
        wf.write("\n")
        wf.write(source_out)
        wf.write("\n")

def main():

    # TODO: increase number of word-tokens that get source mapped
    #       function, class, return etc
    #       symbol tokens are less important

    source = """

    function foo() {
        console.log("source maps are cool");
    }

    /**
     * doc string
     * line 2
     */

    function strange(a, b) {
        if (a < b) {
            return a + b
        } else if (a == b) {
            return b - a
        }
    }


    """


    tokens = Lexer({"preserve_documentation": False}).lex(source)
    mod = Parser().parse(tokens)
    TransformMinifyScope().transform(mod)
    xform_apply_file(mod, "example.js")
    fmt = Formatter({'minify': True})
    source_out = fmt.format(mod)
    srcmap = fmt.sourcemap.getSourceMap()

    #for key, val in srcmap.items():
    #    print(key, val)

    save(html, source, source_out, srcmap)

    debug(html, source, source_out, srcmap)

    # there is a source map visualizer here:
    # https://sokra.github.io/source-map-visualization/#typescript

    # to test the source map in firefox
    # cd dist
    # python -m http.server 8080
    # in the debug console, example.out.js,
    # right click on a word to view original position
    # you can jump between original and generated location


if __name__ == '__main__':
    main()