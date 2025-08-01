from dataclasses import dataclass

from pytest import raises

from checkings import Descriptor, ValidatorError


@dataclass
class Tester:
    value: float = Descriptor.positive_float(include_zero=True)
    value2: int = Descriptor.is_int()
    value3: float = Descriptor.is_float(default=1.5)


def test_descriptor():
    with raises(ValidatorError) as e:
        Tester(value=-1.0, value2=1, value3=1.5)
    assert isinstance(e.value.exceptions[0], ValueError)

    with raises(ValidatorError) as e:
        Tester(value=1.0, value2=1.46, value3=1.5)
    assert isinstance(e.value.exceptions[0], TypeError)

    tester = Tester(value=0.0, value2=1)
    assert tester.value == 0.0
    assert tester.value2 == 1
    assert tester.value3 == 1.5

    with raises(ValidatorError) as e:
        @dataclass
        class Tester2:
            value: int = Descriptor.is_int(default=1.5)
    assert isinstance(e.value.exceptions[0], TypeError)


if __name__ == "__main__":
    test_descriptor()