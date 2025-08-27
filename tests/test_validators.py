from pytest import raises

from checkings import Validator, ValidatorError


def test_validator():
    with raises(ValidatorError) as e:
        Validator.positive(include_zero=True)(-1, "test")
    assert isinstance(e.value.exceptions[0], ValueError)

    with raises(ValidatorError) as e:
        Validator.is_int()(1.46, "test")
    assert isinstance(e.value.exceptions[0], TypeError)

    Validator.is_int()(1, "test")
    Validator.positive_float(include_zero=True)(0.0, "test")


if __name__ == "__main__":
    test_validator()
