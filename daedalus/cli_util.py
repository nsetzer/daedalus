
import os
import sys
import argparse
import logging
import time
import cProfile

from .builder import Builder
from .server import SampleServer
from .lexer import Lexer
from .parser import Parser
from .formatter import Formatter
from .transform import TransformMinifyScope

def makedirs(path):
    if not os.path.exists(path):
        os.makedirs(path)

def copy_staticdir(staticdir, outdir):

    if staticdir and os.path.exists(staticdir):

        for dirpath, dirnames, filenames in os.walk(staticdir):
            paths = []
            for dirname in dirnames:
                src_path = os.path.join(dirpath, dirname)
                dst_path = os.path.join(outdir, "static", os.path.relpath(src_path, staticdir))
                if not os.path.exists(dst_path):
                    os.makedirs(dst_path)

            for filename in filenames:
                src_path = os.path.join(dirpath, filename)
                dst_path = os.path.join(outdir, "static", os.path.relpath(src_path, staticdir))
                with open(src_path, "rb") as rb:
                    with open(dst_path, "wb") as wb:
                        wb.write(rb.read())

def copy_favicon(builder, outdir):
    inp_favicon = builder.find("favicon.ico")
    out_favicon = os.path.join(outdir, "favicon.ico")
    with open(inp_favicon, "rb") as rb:
        with open(out_favicon, "wb") as wb:
            wb.write(rb.read())

def build(outdir, index_js, staticdir=None, staticdata=None, paths=None, platform=None, minify=False, onefile=False):

    if paths is None:
        paths = []

    if staticdata is None:
        staticdata = {}

    html_path_output = os.path.join(outdir, "index.html")
    js_path_output = os.path.join(outdir, "static", "index.js")
    css_path_output = os.path.join(outdir, "static", "index.css")

    builder = Builder(paths, staticdata, platform=platform)
    css, js, html = builder.build(index_js, minify=minify, onefile=onefile)

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

    copy_staticdir(staticdir, outdir)
    copy_favicon(builder, outdir)