#! cd .. && python -m daedalus.vm
import os
import io
import struct
import ctypes
import binascii
import operator
import ast as pyast
import math
import random
import re
import time
import traceback
import urllib.request
import logging

from . import vm_opcodes as opcodes

from .token import Token, TokenError
from .lexer import Lexer
from .parser import Parser, ParseError
from .transform import TransformBaseV2, TransformIdentityBlockScope
from .builder import findModule

from .vm_compiler import VmCompiler, VmTransform, VmInstruction, \
    VmClassTransform2
from .vm_primitive import vmGetAst, JsObject, JsObjectPropIterator, \
    VmFunction, jsc, JsUndefined, JsString, JsNumber, JsSet, JsArray, \
    JsObjectCtor, JsMath, JsNumberObject

class JsAssert(JsObject):
    def __init__(self):
        super(JsAssert, self).__init__()

    @jsc
    def throws(self):
        return """
            function map(extype, fn, msg) {

                try {
                    fn()
                } catch (e) {
                    if (e instanceof extype) {
                        console.log(msg)
                    } else {
                        console.log("function threw unexpected exception")
                    }
                }

            }
        """

class JsTimerFactory(object):
    def __init__(self, runtime):
        super(JsTimerFactory, self).__init__()
        self.runtime = runtime

        self.nextTimerId = 1
        self.timers = {}
        self.intervals = {}
        self.queue = []

    def _setInterval(self, fn, delay, *args):

        timerId = self.nextTimerId
        self.nextTimerId += 1

        timeout = time.time() + delay/1000.0

        posargs = JsObject()

        stackgenerator = lambda: [self.runtime._new_frame(fn, len(args), args, JsObject())]

        self.intervals[timerId] = (timeout, delay, stackgenerator)

        # TODO: priority queue
        self.queue.append((timeout, timerId))

        return timerId

    def _setTimeout(self, fn, delay, *args):

        timerId = self.nextTimerId
        self.nextTimerId += 1

        timeout = time.time() + delay/1000.0

        frame = self.runtime._new_frame(fn, len(args), args, JsObject())
        stack = [frame]

        self.timers[timerId] = (timeout, delay, stack)

        # TODO: priority queue
        self.queue.append((timeout, timerId))

        return timerId

    def _clearTimeout(self, fn, delay, *args):
        pass

    def _wait(self, timeout=1000):
        """
         wait up to timeout milliseconds for any timer to expire
         returns the number of milliseconds slept for
        """

        # TODO: just look at the queue and decide how long to sleep

        now = time.time()

        expires_in = timeout/1000.0

        if self.queue:
            t = self.queue[0][0]
            expires_in = min(expires_in, t - now)

        expires_in = max(expires_in, 0)

        if expires_in > 0:
            time.sleep(expires_in)

        # TODO: this pushes a value on the stack for every call
        #frame = self.stack_frames[-1]
        #frame.sp -= 3

        return int(expires_in * 1000.0)

    def _wait_zero(self, timeout=1000):
        """
         wait up to timeout milliseconds for any timer to expire
         returns early if any timer expires (ignore intervals for now)
         returns the number of milliseconds slept for
        """

        if len(self.timers) == 0:
            return 0

        return self._wait(timeout)

    def check(self):

        if self.queue:

            now = time.time()
            if now > self.queue[0][0]:
                timeout, timerId = self.queue.pop(0)

                if timerId in self.timers:
                    stack = self.timers[timerId][2]
                    del self.timers[timerId]
                    return stack
                elif timerId in self.intervals:
                    _, delay, stackgenerator = self.intervals[timerId]
                    timeout = now + delay/1000.0
                    # TODO: priority queue
                    self.queue.append((timeout, timerId))
                    return stackgenerator()

        return None

class JsPromiseFactory(object):
    def __init__(self, runtime):
        super(JsPromiseFactory, self).__init__()
        self.runtime = runtime

    def __call__(self, callback=None):
        return JsPromise(callback)

class JsPromise(JsObject):

    PENDING = 1
    FULFILLED = 2
    REJECTED = 3

    def __init__(self, callback=None):
        # callback: (resolve, reject) => {}
        super(JsPromise, self).__init__()
        self.callback = callback
        self._state = JsPromise.PENDING
        self._result = None
        self._error = None

        setattr(self, "then", self._then)
        setattr(self, "catch", self._catch)
        setattr(self, "finally", self._finally)

        self._invoke()

    def _invoke(self):
        if isinstance(self.callback, VmFunction):
            # TODO: implement threads in the single runtime
            from .vm import VmRuntime
            runtime = VmRuntime()
            runtime.initfn(self.callback, [self._resolve, self._reject], JsObject())
            try:
                rv, _ = runtime.run()
                if runtime.exception:
                    self._reject(runtime.exception.value)
                #else:
                #    self._resolve(rv)
            except Exception as e:
                self._reject(e)
        else:
            try:
                rv = self.callback()
                self._resolve(rv)
            except Exception as e:
                self._reject(e)

        if self._state == JsPromise.PENDING:
            self._state = JsPromise.REJECTED

        return

    def _resolve(self, res):
        #print("resolve promise", res)
        if self._state == JsPromise.PENDING:
            self._state = JsPromise.FULFILLED
        self._result = res

    def _reject(self, err):
        #print("reject promise", res)
        self._state = JsPromise.REJECTED
        self._error = err

    @jsc
    def _then(self):
        return """
            function _then(onFulfilled, onRejected) {
                // onFulfilled : value => {}
                // onRejected : reason => {}

                // TODO: wait for state to be 2 or 3

                if (this._state === 2) {
                    if (onFulfilled) {
                        onFulfilled(this._result)
                    }
                } else {
                    if (onRejected) {
                        onRejected(this._error)
                    }
                }

                return this
            }
        """

    @jsc
    def _catch(self):
         return """
            function _catch(onRejected) {
                return this._then(undefined, onRejected)
            }
        """

    @jsc
    def _finally(self):
         return """
            function _finally(onFinally) {
                return this._then(onFinally, onFinally)
            }
        """

class JsFetchResponse(JsObject):

    def __init__(self, pyresponse):
        super(JsFetchResponse, self).__init__()

        self.ok = 200 <= pyresponse.status < 300
        self.pyresponse = pyresponse

    def json(self):
        print("get json")
        return JsPromise(lambda: self.pyresponse.json())

    def text(self):
        print("get text")
        return JsPromise(lambda: JsString(self.pyresponse.read().decode("utf-8")))

def fetch(url, parameters):

    #    method: 'POST',
    #    headers: {
    #      'Content-Type': 'application/json'
    #    },
    #    redirect: 'follow', # manual, *follow, error
    #    body

    url = str(url)

    method = parameters.getAttr('method')
    if method is JsUndefined.instance:
        method = 'GET'
    method = str(method)

    headers = parameters.getAttr('headers')
    if headers is JsUndefined.instance:
        headers = JsObject()
    headers = {str(k):str(v) for k,v in headers._data.items()}

    data = parameters.getAttr('data')
    if data is JsUndefined.instance:
        data = None

    def request():
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        response = urllib.request.urlopen(request, timeout=1)
        return JsFetchResponse(response)

    return JsPromise(lambda: request())

class JsDocument(JsObject):

    def __init__(self):
        super(JsDocument, self).__init__()

        self.html = JsElement()
        self.head = JsElement()
        self.body = JsElement()

        self.html.setAttr("type", JsString("html"))
        self.head.setAttr("type", JsString("head"))
        self.body.setAttr("type", JsString("body"))

        self.html.children = JsArray([self.head, self.body])

    @staticmethod
    def createElement(name):

        elem = JsElement()
        elem.setAttr("type", name)

        if name.value == "style":
            elem.setAttr("sheet", JsElement())

        return elem

    @staticmethod
    def createTextNode(text):

        dom = JsElement()
        dom.setAttr("type", JsString("TEXT_ELEMENT"))
        dom.setAttr("nodeValue", text)

        return dom

    def querySelector(self, query):
        if query == "body":
            return self.body

    def getElementsByTagName(self, tagname):

        if tagname == "HEAD":
            return [self.head]

        if tagname == "BODY":
            return [self.body]

        return []

    def getElementById(self, elemid):

        if elemid == "root":
            return self.body

    def toString(self):

        return self.html.toString()

class JsElement(JsObject):

    def __init__(self):
        super(JsElement, self).__init__(None)

        self.rules = JsArray()
        self.children = JsArray()
        self.style = JsObject()

    #def __repr__(self):
    #    x = super().__repr__()
    #    return "<JsElement(" + str(self.rules) + "," + str(self.children) + ")>" + x

    def toString(self, depth=0):

        type_ = self.getAttr("type")

        if type_:

            if type_.value == "sheet":
                return ">?sheet"
            elif type_.value == "text/css":
                elem = self.getAttr("sheet")
                s = "  "*depth + "<style>\n"
                for rule in elem.rules.array:
                    s += "  "*depth
                    s += rule
                    s += "\n"
                s += "  "*depth
                s += "</style>"
                return JsString(s)
            elif type_.value == "TEXT_ELEMENT":
                return "  "*depth + self.getAttr("nodeValue")
            else:
                s = "  "*depth + "<%s" % type_
                for key in JsObject.keys(self).array:
                    key=key.value
                    if key == "type" or key.startswith("_$"):
                        continue
                    attr =  self.getAttr(key)
                    if key == "className":
                        key = "class"
                    s += " %s=\"%s\"" % (key, attr)
                s += ">\n"
                for child in self.children.array:
                    s += child.toString(depth + 1)
                    s += "\n"
                s += "  "*depth + "</%s>" % type_

                return JsString(s)
        else:
            return "undefined type"


    def appendChild(self, child):
        self.children.push(child)

    def insertBefore(self, child, other):
        self.children.push(child)

    def insertRule(self, text, index=0):
        self.rules.push(text)

    def addRule(self, selector, text):
        self.insertRule(selector + " {" + text + "}", self.rules.length)

    def hasChildNodes(self):
        return self.children.length > 0

    @property
    def lastChild(self):
        return self.children.array[-1]

    def addEventListener(self, event, fn):
        print("dom register event", event)

class JsWindow(JsObject):

    def __init__(self):
        super(JsWindow, self).__init__()

    def addEventListener(self, event, callback):
        pass

    def requestIdleCallback(self, callback, options):
        print("requestIdleCallback", callback, options)

    def getComputedStyle(self, dom):
        obj = JsObject()
        obj.setAttr("font-size", 16)
        return obj

    @property
    def innerWidth(self):
        return 1920

    @property
    def innerHeight(self):
        return 1080

class JsNavigator(JsObject):

    def __init__(self):
        super(JsNavigator, self).__init__()

        self.appVersion = JsString("0")
        self.userAgent = JsString("daedalus")
        self.appName = JsString("daedalus")

class JsRegExp(object):
    def __init__(self, expr, flags):
        super(JsRegExp, self).__init__()

        iflags = 0

        cflags = {
            "i": re.IGNORECASE,
        }

        for c in flags.value:
            if c in cflags:
                iflags |= cflags[c]

        self.reg = re.compile(expr.value, iflags)

class JsSystem(JsObject):

    def writeTextFileSync(self, path, content, options=None):
        """
        options: dictionary containing:
            append: boolean: default false
            create: boolean: default true
        """
        with open(path.value, "w") as wf:
            wf.write(content.value)

def JsInstanceOf(inst, cls):
    proto1 = inst.getAttr('__proto__')
    proto2 = cls.prototype
    breakpoint()
    return proto1 is proto2

def populate_builtins(runtime, obj):

    console = lambda: None
    console.log = print
    _Symbol = lambda: None
    _Symbol.iterator = JsString("_x_daedalus_js_prop_iterator")

    history = lambda: None
    history.pushState = lambda x: None

    obj['console'] = console
    obj['document'] = JsDocument()
    obj['Promise'] = JsPromiseFactory(runtime)
    obj['fetch'] = fetch
    obj['Set'] = JsSet
    obj['Array'] = JsArray
    obj['Object'] = JsObjectCtor()
    obj['window'] = JsWindow()
    obj['navigator'] = JsNavigator()
    obj['parseFloat'] = lambda x: float(x.value if hasattr(x, 'value') else x)
    obj['parseInt'] = lambda x, base=10: x
    obj['isNaN'] = lambda x: False
    obj['RegExp'] = JsRegExp
    obj['Symbol'] = _Symbol
    obj['history'] = history
    obj['pystr'] = str
    obj['assert'] = JsAssert()
    obj['Number'] = JsNumberObject()
    obj['Math'] = JsMath()
    obj['System'] = JsSystem()
    obj['_x_daedalus_js_instance_of'] = JsInstanceOf
