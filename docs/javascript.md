
## Import and Export


### Import Daedalus package
```javascript
import module package_name
import package_name.subpackage

from module package_name import {name[, name...]}

```

Daedalus ignores standard javascript import syntax, To import a daedalus
package use the 'import module' syntax. The package is made available
to the current scope using the imported name. Named Exports can be brought
into the current scope by using the 'from module' syntax and specifing the names
in a curly bracketed comma separated list. Packages use a dotted-name to
specify a location on the filesystem.

### Module Search Path

The default search path includes the directory of the root javascript file.

### Module Include

```javascript
include './path/to/file.js'
```

A Module can be split into multiple files and the compiler will merge the files together.
An include statement with a relative path to another file will include that file within the module.
The contents are wrapped inside an IIFI providing a private namespace for non-exported variables.
All exported names from the file are available in the current scope and are automatically exported from the module.

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

## Extended Object Keys

```javascript
let obj = {
    min-width: '100px'
}
```

When specifying an object the 'key' can be an arbitrary constant expression
each token will be merged into a single string. This allows for an easier
way to specify CSS properties.


## UTF-32 support
utf-32 escape sequences are transformed into utf-16 surrogate pairs

```javascript
let s1 = "\U0001F441" // utf-32
let s2 = "\uD83D\uDC41" //utf-16
s1==s2
```