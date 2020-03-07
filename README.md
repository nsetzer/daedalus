# Daedalus

[Live Demo](https://nsetzer.github.io/daedalus/)

javascript web framework for building single page applications

Daedalus is an unopinionated javascript web framework used for creating Single Page Applications.
A javascript to javascript compiler written in python is used to merge javascript source code into a single file.
A sample web server is also provided for testing and supports reloading of javascript source.

Supports:
* ES6
* Basic Javascript minification (60% of original size)
* Precompiled style sheets

### Install

Installing the package will add the Daedalus CLI to the path

```bash
python setup.py install
```

## Daedalus-JS Documentation
* [Element](./docs/element.md)
* [Javascript Changes](./docs/javascript.md)

### Daedalus-PY CLI Documentation

```bash
daedalus serve index.js
daedalus compile index.js index.min.js
daedalus build index.js ./build
```

## Examples

### Serve Demo

```bash
daedalus serve ./examples/minesweeper.js
```

### Single Page Application Demo

```bash
python examples/server.py
```

### Roadmap

* Enhance support for pre-compiled style sheets
* Javascript Modules