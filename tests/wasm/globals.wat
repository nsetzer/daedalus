(module
  (import "env" "g" (global (mut i32)))
  (func (export "f")
    i32.const 100
    global.set 0))