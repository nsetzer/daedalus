
## Import and Export


### Module Import
```javascript
import module
import module.submodule

import module with {name[, name...]}

```

A javascript file can import other modules which are then made available
to the current scope using the imported name. Named Exports can brought
into the current scope by using the *with* keyword and specifing the names
in a curly bracketed comma separated list.

### Module Search Path

tbd

### File Import

```javascript
import './path/to/file.js'
```

A Module can be split into multiple files and the compiler will merge the files together.
An import statement with a relative path to another file will include that file within the module.
The contents are wrapped inside an IIFI providing a private namespace for non-exported variables.
All exported names from the file are available in the current scope and are also marked as exported from the module.

### Export

```javascript
export varname
export const varname [= expr]
export let varname [= expr]
export var varname [= expr]
export function funcname() {}
export class clsname {}
````

A module can export variables, named functions or classes.


## Optional Chaining Operator

[Reference](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/Optional_chaining)

The **optional chaining operator** allows for property access or returns nullish when the left hand side is **null** or **undefined**.

Until better browser support is available, the parser automatically transforms the operator in the following way.

```javascript
obj?.prop
((obj)||{}).prop
```

```javascript
callable?.([args...])
((callable)||(()=>null))([args...])
```

```javascript
obj?.[arg0]
((obj)||{})[arg0]
```

## Null Coalescing Operator

[Reference](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/Nullish_coalescing_operator)

The **null coalescing operator (??)** returns the right hand side when the left hand side is **null** or **undefined**.

Until better browser support is available, the parser automatically transforms the operator in the following way.

```javascript

a ?? b
((x,y)=>(x!==null&&x!==undefined)?x:y)(a,b)

```

