
import os
import sys
import argparse
import logging
import time
import cProfile
import json
import base64

from .builder import Builder
from .server import SampleServer
from .lexer import Lexer
from .parser import Parser
from .formatter import Formatter
from .transform import TransformMinifyScope
from .webview import export_webchannel_js

def makedirs(path):
    if not os.path.exists(path):
        os.makedirs(path)

def copy_staticdir(staticdir, outdir, verbose=False):

    if staticdir and os.path.exists(staticdir):

        for dirpath, dirnames, filenames in os.walk(staticdir):
            if verbose:
                print("copy from %s" % dirpath)

            paths = []
            for dirname in dirnames:
                src_path = os.path.join(dirpath, dirname)
                dst_path = os.path.join(outdir, "static", os.path.relpath(src_path, staticdir))
                if verbose:
                    print(dst_path)
                if not os.path.exists(dst_path):
                    os.makedirs(dst_path)

            for filename in filenames:
                src_path = os.path.join(dirpath, filename)
                dst_path = os.path.join(outdir, "static", os.path.relpath(src_path, staticdir))
                if verbose:
                    print(dst_path)
                with open(src_path, "rb") as rb:
                    with open(dst_path, "wb") as wb:
                        wb.write(rb.read())

def copy_favicon(builder, outdir, verbose=False):
    inp_favicon = builder.find("favicon.ico")
    out_favicon = os.path.join(outdir, "favicon.ico")
    if verbose:
        print(inp_favicon, '=>', out_favicon)
    with open(inp_favicon, "rb") as rb:
        with open(out_favicon, "wb") as wb:
            wb.write(rb.read())

def build(outdir, index_js, staticdir=None, staticdata=None, paths=None, platform=None, minify=False, onefile=False, htmlname="index.html", sourcemap=False):
    # TODO: add verbose mode: show files copied and js files loaded
    verbose=True

    if paths is None:
        paths = []

    if staticdata is None:
        staticdata = {}

    html_path_output = os.path.join(outdir, htmlname)
    js_path_output = os.path.join(outdir, "static", "index.js")
    css_path_output = os.path.join(outdir, "static", "index.css")

    builder = Builder(paths, staticdata, platform=platform)
    builder.lexer_opts = {"preserve_documentation": not minify}
    builder.quiet = not verbose
    css, js, html = builder.build(index_js, minify=minify, onefile=onefile)

    if sourcemap:

        srcmap_routes, _ = builder.sourcemap
        srcmap = builder.sourcemap_obj

        sources = []
        for src in srcmap['sources']:
            path = srcmap_routes[src]
            with open(path) as rf:
                sources.append(rf.read())
        srcmap['sourcesContent'] = sources

        content = json.dumps(srcmap)

        if not onefile:
            makedirs(os.path.join(outdir, 'static'))
            js = "//# sourceMappingURL=index.js.map\n" + js
            with open(js_path_output + ".map", "w") as wf:
                wf.write(content)
        else:
            encoded = base64.b64encode(content.encode("UTF-8")).decode("utf-8")
            header = "//# sourceMappingURL=data:application/json;base64,"
            header += encoded + "\n"
            js = header + js
            # TODO: rebuild the html file with this js embedded
            raise NotImplementedError("sourcemap cannot be embedded in html yet")

    makedirs(outdir)

    with open(html_path_output, "w") as wf:
        cmd = 'daedalus ' + ' '.join(sys.argv[1:])
        wf.write("<!--%s-->\n" % cmd)
        wf.write(html)

    if not onefile:
        makedirs(os.path.join(outdir, 'static'))

        with open(js_path_output, "w") as wf:
            wf.write(js)

        with open(css_path_output, "w") as wf:
            wf.write(css)

    copy_staticdir(staticdir, outdir, verbose)
    copy_favicon(builder, outdir, verbose)

    if platform == "qt":
        qt_path_output = os.path.join(outdir, "static", "qwebchannel.js")
        if not os.path.exists(qt_path_output):
            export_webchannel_js(qt_path_output)


