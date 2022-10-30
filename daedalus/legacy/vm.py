

class VmClassTransform(TransformBaseV2):

    def visit(self, parent, token, index):

        if token.type == Token.T_CLASS:
            self._visit_class(parent, token, index)

    def _visit_class(self, parent, token, index):

        name = token.children[0]
        parent_class = token.children[1]
        block1 = token.children[2]
        #closure1 = token.children[3]

        constructor = None
        methods = []
        for meth in block1.children:

            if meth.children[0].value == "constructor":
                constructor = meth
            else:
                meth = meth.clone()
                meth.type = Token.T_LAMBDA

                _this = Token(Token.T_KEYWORD, token.line, token.index, "this")
                _attr = Token(Token.T_ATTR, token.line, token.index, meth.children[0].value)
                _getattr = Token(Token.T_GET_ATTR, token.line, token.index, ".", [_this, _attr])
                _assign = Token(Token.T_ASSIGN, token.line, token.index, "=", [_getattr, meth])
                methods.append(_assign)

        if constructor is not None:
            methods.extend(constructor.children[2].children)

        _this = Token(Token.T_KEYWORD, token.line, token.index, "this")
        _return = Token(Token.T_RETURN, token.line, token.index, "return", [_this])
        methods.append(_return)

        # the class constructor has a property which is the name of the class
        _this = Token(Token.T_KEYWORD, token.line, token.index, "this")
        _attr1 = Token(Token.T_ATTR, token.line, token.index, "constructor")
        _getattr1 = Token(Token.T_GET_ATTR, token.line, token.index, ".", [_this, _attr1])
        _object = Token(Token.T_OBJECT, token.line, token.index, "{}")
        _assign = Token(Token.T_ASSIGN, token.line, token.index, "=", [_getattr1, _object])
        methods.insert(0, _assign)

        _getattr1 = Token(Token.T_GET_ATTR, token.line, token.index, ".", [_this, _attr1])
        _attr2 = Token(Token.T_ATTR, token.line, token.index, "name")
        _getattr2 = Token(Token.T_GET_ATTR, token.line, token.index, ".", [_getattr1, _attr2])
        _clsname = Token(Token.T_STRING, token.line, token.index, repr(name.value))
        _assign = Token(Token.T_ASSIGN, token.line, token.index, "=", [_getattr2, _clsname])

        methods.insert(1, _assign)

        if parent_class.children:
        # if False:
            parent_class_name = parent_class.children[0].value
            _parent = Token(name.type, token.line, token.index, parent_class_name)
            _bind = Token(Token.T_ATTR, token.line, token.index, "bind")
            _this = Token(Token.T_KEYWORD, token.line, token.index, "this")
            _getattr = Token(Token.T_GET_ATTR, token.line, token.index, ".", [_parent, _bind])

            _arglist = Token(Token.T_ARGLIST, token.line, token.index, "()", [_this])
            _fncall = Token(Token.T_FUNCTIONCALL, token.line, token.index, "", [_getattr, _arglist])
            _super = Token(Token.T_LOCAL_VAR, token.line, token.index, "super")
            _assign = Token(Token.T_ASSIGN, token.line, token.index, "=", [_super, _fncall])

            # _super = Token("T_CREATE_SUPER", token.line, token.index, "super", [_parent, _this])
            methods.insert(0, _assign)

        # TODO: copy dict from PARENT_CLASS.prototype
        #       then update using CLASS.prototype
        #       -- may require a special python function

        # TODO: prototype must be a property of a class constructor
        #       __proto__ is the reference to the prototype used when constructing a class instance
        _this = Token(Token.T_KEYWORD, token.line, token.index, "this")
        _proto = Token(Token.T_ATTR, token.line, token.index, "prototype")
        _getattr = Token(Token.T_GET_ATTR, token.line, token.index, ".", [_this, _proto])
        _object = Token(Token.T_OBJECT, token.line, token.index, "{}")
        _assign = Token(Token.T_ASSIGN, token.line, token.index, "=", [_getattr, _object])
        methods.insert(0, _assign)

        _this1 = Token(Token.T_KEYWORD, token.line, token.index, "this")
        _proto1 = Token(Token.T_ATTR, token.line, token.index, "__proto__")
        _getattr1 = Token(Token.T_GET_ATTR, token.line, token.index, ".", [_this1, _proto1])
        _this2 = Token(Token.T_KEYWORD, token.line, token.index, "this")
        _proto2 = Token(Token.T_ATTR, token.line, token.index, "prototype")
        _getattr2 = Token(Token.T_GET_ATTR, token.line, token.index, ".", [_this2, _proto2])
        _assign = Token(Token.T_ASSIGN, token.line, token.index, "=", [_getattr1, _getattr2])
        methods.insert(1, _assign)

        if constructor is None:

            _name = Token(Token.T_TEXT, token.line, token.index, 'constructor', [])
            _arglist = Token(Token.T_ARGLIST, token.line, token.index, '()', [])
            _block = Token(Token.T_BLOCK, token.line, token.index, '{}', [])
            #_closure = Token(Token.T_CLOSURE, token.line, token.index, '', [])
            _meth = Token(Token.T_METHOD, token.line, token.index, '', [_name,_arglist, _block])

            constructor = _meth
        else:

            constructor = constructor.clone()

        constructor.children[2].children = methods

        constructor.type = Token.T_FUNCTION
        constructor.children[0] = name

        #print("new class ", parent.type, name.value, len(constructor.children), constructor.children[3])

        parent.children[index] = constructor