from __future__ import annotations

import collections  # noqa: F401
import os  # noqa: F401
import warnings
from collections.abc import Callable
from typing import Self

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    np = None
    HAS_NUMPY = False


from ._no_val import NoValue  # noqa
from .number_line import NumberLine  # noqa
from ._validator_error import ValidatorError  # noqa


class BaseChecker:
    def __init__(
        self,
        default=NoValue,
        default_factory=NoValue,
        number_line=NoValue,
        literals=NoValue,
        types=NoValue,
        converter=NoValue,
        validators=NoValue,
        replace_none=False,
    ):
        """
        Parameters
        ----------
        default: any
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], any]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[any, ...] | any
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[any], any]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[any], Exception | None], ...] | Callable[[any], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.

        Raises
        ------
        TypeError
            If `default_factory` is not a callable, or if `literals`, `types`, or `converter` are not of the correct
            type.
        ValueError
            If both `default` and `default_factory` are provided, or if `literals`, `types`, or `validators` are not
            tuples or the correct type, or if `number_line` is empty.
        """

        def check_tuple(value, type_, name) -> tuple:
            if (not isinstance(value, tuple)) and (value is not NoValue):
                if isinstance(value, type_):
                    return (value,)
                msg = f"`{name}` must be a tuple"
                raise TypeError(msg)
            return value

        def check_type[T](value: T, type_, name) -> T:
            if (not isinstance(value, type_)) and (value is not NoValue):
                msg = f"`{name}` must be a {type_.__name__}, not {type(value).__name__}"
                raise TypeError(msg)
            return value

        if not isinstance(literals, tuple | type(NoValue)):
            literals = (literals,)

        if not hasattr(default, "__hash__"):
            try:
                default.copy()
            except AttributeError as e:
                msg = "If default is mutable (ie. doesn't have an hash), it must have a `copy` method"
                raise ValueError(msg) from e

        self._default = default
        self._default_factory = check_type(default_factory, Callable, "default_factory")
        if (default is not NoValue) and (default_factory is not NoValue):
            msg = "Cannot use both `default` and `default_factory`"
            raise ValueError(msg)
        self._number_line = check_type(number_line, NumberLine, "number_line")
        self._literals = check_type(literals, tuple, "literals")
        self._types = check_tuple(types, type, "types")
        self._converter = check_type(converter, Callable, "converter")
        self._validators = check_tuple(validators, Callable, "validators")
        self._replace_none = replace_none

    def _update(self):
        if (self._number_line is not NoValue) and (not self._number_line):
            msg = "Number line is empty"
            raise ValueError(msg)
        if self._literals is not NoValue:
            # To keep the order of the literals, we need to do it this way instead of using a set
            self._literals = tuple(
                self._literals[i] for i in range(len(self._literals)) if self._literals[i] not in self._literals[:i]
            )
            if not self._literals:
                msg = "Literals are empty"
                raise ValueError(msg)
        if self._types is not NoValue:
            self._types = tuple(set(self._types))
            if not self._types:
                msg = "Types are empty"
                raise ValueError(msg)

            if self._literals is not NoValue:
                old_len = len(self._literals)
                self._literals = tuple(literal for literal in self._literals if isinstance(literal, self._types))
                if not self._literals:
                    msg = "No literals are of the required type"
                    raise ValueError(msg)
                if len(self._literals) != old_len:
                    warnings.warn(
                        "Some literals are not of the required type, they are removed from `literals`",
                    )

                old_len = len(self._types)
                self._types = tuple(t for t in self._types if any(isinstance(literal, t) for literal in self._literals))
                if old_len != len(self._types):
                    warnings.warn(
                        "Some types are not present in `literals`, they are removed from `types`",
                    )

            if (self._number_line is not NoValue) and (int not in self._types) and (float not in self._types):
                self._number_line = NoValue
                warnings.warn(
                    "number_line` is not used because `types` does not contain `int` or `float`",
                )

    def __add__(self, other: Self) -> Self:
        if not isinstance(other, self.__class__):
            msg = f"Cannot add {type(other)} to {self.__class__}"
            raise TypeError(msg)

        def add_values(a, b, name):
            if a is not NoValue:
                if b is not NoValue:
                    raise ValueError(f"Cannot add two {name}")
                result = a
            else:
                result = b
            return result

        default = add_values(self._default, other._default, "default values")
        converter = add_values(self._converter, other._converter, "converters")
        default_factory = add_values( self._default_factory, other._default_factory, "default factories")

        # Tuples can be added together directly
        validators = self._validators + other._validators
        number_line = self._number_line + other._number_line
        literals = self._literals + other._literals
        types = self._types + other._types
        replace_none = self._replace_none or other._replace_none

        return self.__class__(
            default=default,
            default_factory=default_factory,
            number_line=number_line,
            literals=literals,
            types=types,
            converter=converter,
            validators=validators,
            replace_none=replace_none,
        )

    def _check_type(self, value):
        if self._types is not NoValue:
            for t in self._types:
                if isinstance(value, t):
                    break
            else:
                if len(self._types) == 1:
                    msg = f"Value ({value}) must be of type {self._types[0].__name__}, found {type(value).__name__}"
                else:
                    msg = (f"Value ({value}) must be one of the following types: "
                           f"{self._tuple_str([t.__name__ for t in self._types])}, found {type(value).__name__}")
                return TypeError(msg)
        return None

    def _check_literal(self, value):
        if (self._literals is not NoValue) and (value not in self._literals):
            msg = f"Value ({value}) must be one of the following: {self._tuple_str(self._literals)}"
            return ValueError(msg)
        return None

    def _check_number_line(self, value):
        if self._number_line is not NoValue:
            return self._number_line.return_raise_check(value)
        return None

    def _check_validators(self, value):
        if self._validators is not NoValue:
            errors = []
            for validator in self._validators:
                try:
                    message = validator(value)
                except BaseException as e:  # noqa: BLE001
                    msg = f"Validator named {validator.__name__} raised an exception: {e}",
                    errors.append(
                        ValueError(msg)
                    )
                else:
                    if isinstance(message, Exception):
                        errors.append(message)
            if errors:
                return ValidatorError("Value did not pass all validators", errors)
        return None

    def _validate(self, value, name):
        errs = []
        type_err = self._check_type(value)
        lit_err = self._check_literal(value)
        num_err = self._check_number_line(value)
        val_err = self._check_validators(value)
        if type_err:
            errs.append(type_err)
        if lit_err:
            errs.append(lit_err)
        if num_err:
            errs.append(num_err)
        if val_err:
            errs.append(val_err)
        if errs:
            msg = f"{name} has incorrect value: {value}"
            raise ValidatorError(msg, errs)

    @staticmethod
    def _tuple_str(values):
        if len(values) == 1:
            return f"({values[0]},)"
        return f"({', '.join(v.__repr__() for v in values)})"

    def __repr__(self):
        return (
            f"{self.__class__.__name__}(Default={self._default}, NumberLine={self._number_line}, "
            f"Literals={self._literals}, Types={self._types}, Converter={self._converter}, "
            f"Validators={self._validators}))"
        )

    def _get_default(self):
        if self._default is NoValue:
            return self._default_factory() if self._default_factory is not NoValue else NoValue
        if not hasattr(self._default, "__hash__"):
            return self._default.copy()
        else:
            return self._default

    @staticmethod
    def _invert(func):
        def wrapper(*args, **kwargs):
            return not func(*args, **kwargs)

        return wrapper
