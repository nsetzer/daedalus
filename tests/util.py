
from daedalus.lexer import Token

def edit_distance(hyp, ref, eq=None):
    """
    given: two sequences hyp and ref (str, list, or bytes)

    solve E(i,j) -> E(m,n)
    """

    if len(hyp) == 0:
        return [(None, elem) for elem in ref], 0, 0, 0, len(ref)

    if len(ref) == 0:
        return [(elem, None) for elem in hyp], 0, 0, len(hyp), 0

    e = [0,]*(len(hyp)*len(ref))
    s = lambda i,j: i*len(ref)+j
    d = lambda i,j: 0 if hyp[i]==ref[j] else 1
    E = lambda i,j: e[s(i,j)]

    e[s(0,0)] = d(0,0)

    # build the error table using dynamic programming
    # first build the top and left edge
    for i in range(1,len(hyp)):
        e[s(i,0)] = min([1+i, d(i,0)+i])

    for j in range(1,len(ref)):
        e[s(0,j)] = min([1+j, d(0,j)+j])

    # fill in remaining squares
    for i in range(1,len(hyp)):
        for j in range(1,len(ref)):
            e[s(i,j)] = min([1+E(i-1,j),1+E(i,j-1),d(i,j)+E(i-1,j-1)])

    # reverse walk
    # find number of substitutions/insertions/deletions
    i=len(hyp)-1
    j=len(ref)-1
    seq = []
    cor=sub=del_=ins=0
    while i > 0 and j > 0:
        _a,_b,_c,_d = E(i,j),E(i-1,j),E(i,j-1),E(i-1,j-1)

        if _d<=_a and _d<_b and _d<_c:
            seq.append((hyp[i], ref[j]))
            if eq(hyp[i], ref[j]):
                cor+=1;
            else:
                sub+=1
            i,j = i-1,j-1
        elif _b <= _c:
            seq.append((hyp[i], None))
            i = i-1
            ins+=1
        else:
            seq.append((None, ref[j]))
            j = j-1
            del_+=1

    while i >= 0 and j >= 0:
        seq.append((hyp[i], ref[j]))
        if eq(hyp[i], ref[j]):
            cor+=1
        else:
            sub+=1
        i = i-1
        j = j-1

    while i >= 0:
        seq.append((hyp[i], None))
        i = i-1
        ins+=1

    while j >= 0:
        seq.append((None, ref[j]))
        j = j-1
        del_+=1

    if sub + ins + del_ == 0:
        assert cor == len(hyp), (cor, len(hyp))

    return reversed(seq), cor, sub, ins, del_

def tokcmp(a, b):
    if a is None:
        return False
    if b is None:
        return False

    _, tok1 = a
    _, tok2 = b

    return tok1.type == tok2.type and tok1.value == tok2.value

def parsecmp(expected, actual, debug=False):

    a = actual.flatten()
    b = expected.flatten()

    seq, cor, sub, ins, del_ = edit_distance(a, b, tokcmp)

    error_count = sub + ins + del_
    if error_count > 0 or debug:
        print("\n--- %-50s | --- %-.50s" % ("    HYP", "    REF"))
        for a, b in seq:
            c = ' ' if tokcmp(a, b) else '|'
            if not a:
                a = (0, None)
            if not b:
                b = (0, None)
            print("%3d %-50r %s %3d %-.50r" % (a[0], a[1], c, b[0], b[1]))
        print(actual.toString(2))
    return error_count

def TOKEN(t,v,*children):
    return Token(getattr(Token,t), 1, 0, v, children)
