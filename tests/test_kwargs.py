import sys

from pytest import raises

sys.path.append(".")
from checkings import check_kwargs, default_kwargs, Validator, ValidatorError


def test_default_kwargs():
    defaults = {
        'a': 1,
        'b': 'hello',
    }
    vals = {
        'a': 2,
        'b': 'hi',
    }

    values = default_kwargs(vals, **defaults)
    assert values == vals

    values = default_kwargs({}, **defaults)
    assert values == defaults

    values = default_kwargs({'a': 2}, **defaults)
    assert values == {'a': 2, 'b': 'hello'}

def test_check_kwargs():
    kwargs_checker = {
        'a': int,
        'b': str,
    }
    vals = {
        'a': 2,
        'b': 'hi',
    }
    defaults = {
        'a': 1,
        'b': 'hello',
    }

    check_kwargs('some_function', vals, kwargs_checker)
    with raises(TypeError):
        check_kwargs('some_function', {'a': 'nope', 'b': 'hi'}, kwargs_checker)
    with raises(TypeError):
        check_kwargs('some_function', {'a': 2}, kwargs_checker, b=1)
    with raises(TypeError):
        check_kwargs('some_function', {'a': 2, 'b': 'hi', 'c': 1}, kwargs_checker)

    values = check_kwargs('some_function', vals, kwargs_checker, **defaults)
    assert values == vals

    values = check_kwargs('some_function', {}, kwargs_checker, **defaults)
    assert values == defaults

    values = check_kwargs('some_function', {'a': 2}, kwargs_checker, **defaults)
    assert values == {'a': 2, 'b': 'hello'}


    kwargs_checker2 = {
        'a': int,
        'b': Validator.length(2),
    }
    check_kwargs('some_function', {'a': 2, 'b': 'hi'}, kwargs_checker2)
    with raises(ValueError) as e:
        check_kwargs('some_function', {'a': 2, 'b': 'h'}, kwargs_checker2)
    assert isinstance(e.value.__cause__, ValidatorError)

