import sys

sys.path.append(".")  # Adjust the path to import from the parent directory

from checking.number_line import Bound, Range, EmptyRange


def test():
    range1 = Range(Bound(0, True), Bound(10, True))
    range2 = Range(Bound(5, True), Bound(15, True))
    range3 = Range(Bound(5, False), Bound(10, True))
    range4 = Range(Bound(10, True), Bound(15, True))
    range5 = Range(Bound(0, True), Bound(5, True))
    range6 = Range(Bound(0, False), Bound(10, False))
    range7 = Range(Bound(0, True), Bound(10, True))
    range8 = Range(Bound(0, True), Bound(0, True))
    range9 = Range(Bound(10, True), Bound(10, True))
    range10 = Range(Bound(0, False), Bound(10, True))
    range11 = Range(Bound(4, True), Bound(4, True))
    range12 = Range(Bound(0, True), Bound(10, False))

    assert(0 in range12, True)
    assert(5 in range12, True)
    assert(10 in range12, False)

    def assertion(got, expectation):
        if not isinstance(expectation, tuple):
            expectation = (expectation,)
        assert expectation == got, f"Expected {expectation}, but got {got}"

    assertion(range1 + range2, Range(Bound(0, True), Bound(15, True)))
    assertion(range1 - range2, Range(Bound(0, True), Bound(5, False)))
    assertion(range2 - range1, Range(Bound(10, False), Bound(15, True)))
    assertion(range1 - range4, Range(Bound(0, True), Bound(10, False)))
    assertion(range1 - range3, Range(Bound(0, True), Bound(5, True)))
    assertion(range1 - range5, Range(Bound(5, False), Bound(10, True)))
    assertion(range1 - range7, EmptyRange)
    assertion(range1 - range8, Range(Bound(0, False), Bound(10, True)))
    assertion(range1 - range9, Range(Bound(0, True), Bound(10, False)))
    assertion(range1 - range10, Range(Bound(0, True), Bound(0, True)))
    assertion(range1 - range12, Range(Bound(10, True), Bound(10, True)))
    assertion(
        range1 - range11,
        (
            Range(Bound(0, True), Bound(4, False)),
            Range(Bound(4, False), Bound(10, True)),
        ),
    )
    assertion(
        range1 - range6,
        (
            Range(Bound(0, True), Bound(0, True)),
            Range(Bound(10, True), Bound(10, True)),
        ),
    )

    range1 = Range(Bound(0, False), Bound(10, False))
    range2 = Range(Bound(0, True), Bound(10, True))
    range3 = Range(Bound(0, True), Bound(10, False))
    range4 = Range(Bound(0, False), Bound(10, True))
    range5 = Range(Bound(10, True), Bound(20, True))
    range6 = Range(Bound(5, False), Bound(15, False))
    range7 = Range(Bound(5, True), Bound(15, True))

    assertion(range1 + range2, Range(Bound(0, True), Bound(10, True)))
    assertion(range2 + range1, Range(Bound(0, True), Bound(10, True)))
    assertion(range1 + range3, Range(Bound(0, True), Bound(10, False)))
    assertion(range3 + range1, Range(Bound(0, True), Bound(10, False)))
    assertion(range1 + range4, Range(Bound(0, False), Bound(10, True)))
    assertion(range4 + range1, Range(Bound(0, False), Bound(10, True)))
    assertion(range1 + range5, Range(Bound(0, False), Bound(20, True)))
    assertion(range5 + range1, Range(Bound(0, False), Bound(20, True)))
    assertion(range1 + range6, Range(Bound(0, False), Bound(15, False)))
    assertion(range6 + range1, Range(Bound(0, False), Bound(15, False)))
    assertion(range1 + range7, Range(Bound(0, False), Bound(15, True)))
    assertion(range7 + range1, Range(Bound(0, False), Bound(15, True)))


if __name__ == "__main__":
    test()
