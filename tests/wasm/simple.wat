(module
  (func (export "addTwo") (param i32 i32) (result i32)
    local.get 0
    local.get 1
    i32.add
  )
  (func (export "callAddTwo") (result i32)
    i32.const 1
    i32.const 2
    call 0)
)