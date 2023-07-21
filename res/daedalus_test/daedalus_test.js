
$import("daedalus", {})
$import("unittest", {})

export const Root = unittest.UnitTestRoot

unittest.Test("optional_chaining_attr", ()=>{
    const x = {y: 123}
    unittest.assert.equal(x?.y, 123)
})

unittest.Test("optional_chaining_attr_null", ()=>{
    const x = null
    unittest.assert.isNone(x?.y)
})

unittest.Test("optional_chaining_call", ()=>{
    const x = () => 123

    unittest.assert.equal(x?.(), 123)
})

unittest.Test("optional_chaining_call_null", ()=>{
    const x = null
    unittest.assert.isNone(x?.())
})

unittest.Test("optional_chaining_subscr", ()=>{
    const x = [1,2,3]

    unittest.assert.equal(x?.[0], 1)
})

unittest.Test("optional_chaining_subscr_null", ()=>{
    const x = null
    unittest.assert.isNone(x?.[0])
})