#! cd .. && python -m tests.util
from daedalus.lexer import Token
import time, math

def edit_distance(hyp, ref, eq=None):
    """
    given: two sequences hyp and ref (str, list, or bytes)

    solve E(i,j) -> E(m,n)
    """

    if len(hyp) == 0:
        return [(None, elem) for elem in ref], 0, 0, 0, len(ref)

    if len(ref) == 0:
        return [(elem, None) for elem in hyp], 0, 0, len(hyp), 0

    if eq is None:
        eq = lambda a, b: a == b

    e = [0, ] * (len(hyp) * len(ref))
    s = lambda i, j: i * len(ref) + j
    d = lambda i, j: 0 if eq(hyp[i], ref[j]) else 1
    E = lambda i, j: e[s(i, j)]

    e[s(0, 0)] = d(0, 0)

    # build the error table using dynamic programming
    # first build the top and left edge
    for i in range(1, len(hyp)):
        e[s(i, 0)] = min([1 + i, d(i, 0) + i])

    for j in range(1, len(ref)):
        e[s(0, j)] = min([1 + j, d(0, j) + j])

    # fill in remaining squares
    for i in range(1, len(hyp)):
        for j in range(1, len(ref)):
            e[s(i, j)] = min([1 + E(i - 1, j), 1 + E(i, j - 1), d(i, j) + E(i - 1, j - 1)])

    # reverse walk
    # find number of substitutions/insertions/deletions
    i = len(hyp) - 1
    j = len(ref) - 1
    seq = []
    cor = sub = del_ = ins = 0
    while i > 0 and j > 0:
        _a = E(i, j)            # current cost
        _b = E(i - 1, j)        # cost of insertion
        _c = E(i, j - 1)        # cost of deletion
        _d = E(i - 1, j - 1)    # cost of a substitution



        if _d <= _a and _d < _b and _d < _c:
            seq.append((hyp[i], ref[j]))
            if eq(hyp[i], ref[j]):
                cor += 1
                #print(abs(_d - _a), abs(_b - _a), abs(_a - _a), "cor")
            else:
                sub += 1
                #print(abs(_d - _a), abs(_b - _a), abs(_a - _a), "sub")
            i, j = i - 1, j - 1
        elif _b <= _c:
            seq.append((hyp[i], None))
            i = i - 1
            ins += 1
            #print(abs(_d - _a), abs(_b - _a), abs(_a - _a), "ins")
        else:
            seq.append((None, ref[j]))
            j = j - 1
            del_ += 1
            #print(abs(_d - _a), abs(_b - _a), abs(_a - _a), "del")

    while i >= 0 and j >= 0:
        seq.append((hyp[i], ref[j]))
        if eq(hyp[i], ref[j]):
            cor += 1
        else:
            sub += 1
        i = i - 1
        j = j - 1

    while i >= 0:
        seq.append((hyp[i], None))
        i = i - 1
        ins += 1

    while j >= 0:
        seq.append((None, ref[j]))
        j = j - 1
        del_ += 1

    if sub + ins + del_ == 0:
        assert cor == len(hyp), (cor, len(hyp))
    #print(cor, sub, ins, del_)
    #for i in range(len(hyp)):
    #    row = ["%5d" % E(i, j) for j in range(len(ref))]
    #    print(" ".join(row))

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

def TOKEN(t, v, *children):
    return Token(getattr(Token, t), 1, 0, v, children)

def solve_linear(X, Y):
    # solve y = m2*x*x + m1*x + b for m2, m1, b
    # given two samples points along the line

    m = (Y[1] - Y[0]) / (X[1] - X[0])
    b = Y[0] - m * X[0]

    return m, b

def solve_quadratic(X, Y):

    # solve y = m2*x*x + m1*x + b for m2, m1, b
    # given three samples points along the line

    v0 = (Y[1] - Y[0])
    v1 = (X[1] - X[0])
    v2 = (X[1] * X[1] - X[0] * X[0])
    f0 = (Y[2] - Y[0])
    f1 = (X[2] - X[0])
    f2 = (X[2] * X[2] - X[0] * X[0])

    # v0 = m2*v2 + m1*v1
    # f0 = m2*f2 + m1*f1

    # m2 = (v0 - m1*v1) / v2
    # f0 = ((v0 - m1*v1) / v2)*f2 + m1*f1
    # f0 = v0*f2/v2 - m1*v1*f2/v2 + m1*f1
    # f0 - v0*f2/v2 = m1*f1 - m1*v1*f2/v2
    # m1*(f1 - v1*f2/v2) = f0 - v0*f2/v2
    # m1 = (f0 - v0*f2/v2) / (f1 - v1*f2/v2)

    m1 = (f0 - v0 * f2 / v2) / (f1 - v1 * f2 / v2)
    m2 = (v0 - m1 * v1) / v2
    b = Y[0] - m2 * X[0] * X[0] - m1 * X[0]

    return (m2, m1, b)

def benchmark(x1, x2, func):

    # test the given function at 2 points on a line
    X = [x1, x2]
    Y = []

    td1 = time.perf_counter()
    for N in X:
        t1 = time.perf_counter()
        func(N)
        t2 = time.perf_counter()
        Y.append(t2 - t1)
    td2 = time.perf_counter()

    # compute y = m*x + b
    # then decide if x is linear, quadratic, logarithmic
    m, b = solve_linear(X, Y)

    # define equations used to compare against measured value
    eq1 = lambda n: m * n + b
    eq2a = lambda n: m * n * n + b

    eq3 = lambda n: m * n * math.log(n) + b

    names = [
        "n",
        "n*n",
        "n*log(n)",
        # n*n + n
        # n!
    ]

    # determine the percent error of the test function relative
    # to what was observed.
    error = [
        abs(Y[0] - eq1(X[0])) / Y[0],
        abs(Y[0] - eq2a(X[0])) / Y[0],
        abs(Y[0] - eq3(X[0])) / Y[0]
    ]

    # total duration needs to be above some minimum to be valid
    td = td2 - td1
    index = error.index(min(error))
    print(error)
    print(error[index])
    print(td)
    print(" eq = %.6f * %s %s %.6f" % (
        m, names[index], "-" if b < 0 else "+", abs(b)))


if __name__ == '__main__':

    seq, cor, sub, ins, del_ = edit_distance("biten", "kitten")

    error_count = sub + ins + del_
    if error_count > 0:
        for a, b in seq:
            c = ' ' if a == b else '|'
            if not a:
                a = "-"
            if not b:
                b = "-"
            print(a, b)

    #eq = lambda x: 2 * x * x + 3 * x + 4
    #X = [10, 20, 30]
    #Y = [eq(x) for x in X]
    #fn = solve_quadratic(X, Y)
    #print(fn)
