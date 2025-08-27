import sys
from typing import Any

from pytest import raises

sys.path.append(".")  # Adjust the path to import from the parent directory
from checkings import strongly_typed

def test_strongly_typed():
    @strongly_typed
    def add(a: int, b: int) -> int:
        return a + b

    assert add(1, 2) == 3

    with raises(TypeError) as excinfo:
        add(1, "2")
    assert "Argument 'b' must be of type int, got str" == str(excinfo.value)

    with raises(TypeError) as excinfo:
        add("1", 2)
    assert "Argument 'a' must be of type int, got str" == str(excinfo.value)

    with raises(TypeError) as excinfo:
        add(1.0, 2)
    assert "Argument 'a' must be of type int, got float" == str(excinfo.value)

    with raises(TypeError) as excinfo:
        add(1, 2.0)
    assert "Argument 'b' must be of type int, got float" == str(excinfo.value)


    def add2(a, b: int) -> int:
        return a + b

    with raises(ValueError) as excinfo:
        strongly_typed(add2, True)
    assert "Parameter 'a' lacks a type annotation." == str(excinfo.value)

    def add3(a: Any, b: int) -> int:
        return a + b

    add3(1, 2)
