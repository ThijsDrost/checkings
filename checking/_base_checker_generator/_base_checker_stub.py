from __future__ import annotations

from typing import Callable, Self
import warnings
import collections  # noqa: F401
import os  # noqa: F401

import numpy as np  # noqa: F401

from ._no_val import NoValue
from .number_line import NumberLine
from ._validator_error import ValidatorError


class BaseChecker:
    def __init__(self, default=NoValue, number_line=NoValue, literals=NoValue, types=NoValue, converter=NoValue,
                 validators=NoValue, replace_none=False):
        """
        Parameters
        ----------
        default: any
            The default value of the attribute. If default is callable, this is used a default factory, the factory should have no
            arguments. If default is mutable, it must have a `copy` method. Mutability is checked by
            checking if the object has a `__setitem__` or `set` method.
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
        """

        def check_tuple(value, type_, name) -> tuple:
            if (not isinstance(value, tuple)) and (value is not NoValue):
                if isinstance(value, type_):
                    return (value,)
                else:
                    raise TypeError(f'`{name}` must be a tuple')
            return value

        def check_type[T](value: T, type_, name) -> T:
            if (not isinstance(value, type_)) and (value is not NoValue):
                raise TypeError(f'`{name}` must be a {type_.__name__}')
            return value

        if not isinstance(literals, tuple | type(NoValue)):
            literals = (literals,)

        self._default = default
        self._number_line = check_type(number_line, NumberLine, 'number_line')
        self._literals = check_type(literals, tuple, 'literals')
        self._types = check_tuple(types, type, 'types')
        self._converter = check_type(converter, Callable, 'converter')
        self._validators = check_tuple(validators, Callable, 'validators')
        self._replace_none = replace_none

    def _update(self):
        if self._number_line is not NoValue:
            if not self._number_line:
                raise ValueError('Number line is empty')
        if self._literals is not NoValue:
            # To keep the order of the literals, we need to do it this way instead of using a set
            self._literals = tuple(
                (self._literals[i] for i in range(len(self._literals)) if self._literals[i] not in self._literals[:i]))
            if not self._literals:
                raise ValueError('Literals are empty')
        if self._types is not NoValue:
            self._types = tuple(set(self._types))
            if not self._types:
                raise ValueError('Types are empty')

            if self._literals is not NoValue:
                old_len = len(self._literals)
                self._literals = tuple((literal for literal in self._literals if isinstance(literal, self._types)))
                if not self._literals:
                    raise ValueError('No literals are of the required type')
                if len(self._literals) != old_len:
                    warnings.warn('Some literals are not of the required type, they are removed from `literals`')

                old_len = len(self._types)
                self._types = tuple((t for t in self._types if any(isinstance(literal, t) for literal in self._literals)))
                if old_len != len(self._types):
                    warnings.warn('Some types are not present in `literals`, they are removed from `types`')

            if self._number_line is not NoValue:
                if (int not in self._types) and (float not in self._types):
                    self._number_line = NoValue
                    warnings.warn('number_line` is not used because `types` does not contain `int` or `float`')

    def __add__(self, other: Self) -> Self:
        if not isinstance(other, self.__class__):
            raise TypeError(f'Cannot add {type(other)} to {self.__class__}')

        def add_values(a, b, name):
            if a is not NoValue:
                if b is not NoValue:
                    raise ValueError(f'Cannot add two {name}')
                result = a
            else:
                result = b
            return result

        default = add_values(self._default, other._default, 'default values')
        converter = add_values(self._converter, other._converter, 'converters')

        # Tuples can be added together directly
        validators = self._validators + other._validators
        number_line = self._number_line + other._number_line
        literals = self._literals + other._literals
        types = self._types + other._types
        replace_none = self._replace_none or other._replace_none

        return self.__class__(default=default, number_line=number_line, literals=literals, types=types, converter=converter,
                              validators=validators, replace_none=replace_none)

    # def __sub__(self, other: Self) -> Self:
    #     if not isinstance(other, self.__class__):
    #         raise TypeError(f'Cannot subtract {type(other)} from {self.__class__}')
    #
    #     def subtract_values(a, b, name):
    #         if a == b:
    #             result = NoValue
    #         elif b is not NoValue:
    #             if a is not NoValue:
    #                 raise ValueError(f'To remove {name}, both descriptors must have the same {name},'
    #                                  f'not {a} and {b}')
    #             else:
    #                 raise ValueError(f'Cannot remove {name} from a descriptor that does not have a {name}')
    #         else:
    #             result = a
    #         return result
    #
    #     def subtract_numberlines(a, b):
    #         if a is NoValue:
    #             if b is NoValue:
    #                 return NoValue
    #             else:
    #                 warnings.warn(f'Trying to remove number line from a descriptor that does not have a number line, assuming'
    #                               f'that the number line is {NumberLine.full()}')
    #                 a = NumberLine.full()
    #         if b is NoValue:
    #             return a
    #         return a - b
    #
    #     def subtract_tuples(a, b, name):
    #         if a is not NoValue:
    #             if b is not NoValue:
    #                 result = tuple((val for val in a if val not in b))
    #             else:
    #                 result = a
    #         elif b is not NoValue:
    #             raise ValueError(f'Cannot remove {name} from a descriptor that does not have a {name}')
    #         else:
    #             result = NoValue
    #         return result
    #
    #     default = subtract_values(self._default, other._default, 'default value')
    #     validators = subtract_values(self._validators, other._validators, 'validators')
    #
    #     number_line = subtract_numberlines(self._number_line, other._number_line)
    #
    #     converter = subtract_tuples(self._converter, other._converter, 'converter')
    #     literals = subtract_tuples(self._literals, other._literals, 'literals')
    #     types = subtract_tuples(self._types, other._types, 'types')
    #
    #     replace_none = self._replace_none and not other._replace_none
    #
    #     for vals, name in ((number_line, 'number lines'), (literals, 'literals'), (types, 'types')):
    #         if vals is not NoValue:
    #             if not vals:
    #                 raise ValueError(f'{name} is empty, cannot remove all values')
    #
    #     return self.__class__(default=default, number_line=number_line, literals=literals, types=types, converter=converter,
    #                           validators=validators, replace_none=replace_none)

    def _check_type(self, value):
        if self._types is not NoValue:
            for t in self._types:
                if isinstance(value, t):
                    break
            else:
                return ValueError(
                    f'Value ({type(value)}) must be one of the following types: {self._tuple_str([t.__name__ for t in self._types])}')
        return None

    def _check_literal(self, value):
        if self._literals is not NoValue:
            if value not in self._literals:
                return ValueError(f'Value ({value}) must be one of the following: {self._tuple_str(self._literals)}')
        return None

    def _check_number_line(self, value):
        if self._number_line is not NoValue:
            return self._number_line.return_raise_check(value)
        return None

    def _check_validators(self, value):
        if self._validators is not NoValue:
            errors = []
            for index, validator in enumerate(self._validators):
                message = validator(value)
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
            raise ExceptionGroup(f'{name} has incorrect value: {value}', errs)

    @staticmethod
    def _tuple_str(values):
        if len(values) == 1:
            return f'({values[0]},)'
        return f'({", ".join(v.__repr__() for v in values)})'

    def __repr__(self):
        return f'{self.__class__.__name__}(Default={self._default}, NumberLine={self._number_line}, ' \
               f'Literals={self._literals}, Types={self._types}, Converter={self._converter}, ' \
               f'Validators={self._validators}))'

    def _get_default(self):
        if callable(self._default):
            return self._default()
        if hasattr(self._default, '__setitem__') or hasattr(self._default, 'set'):
            try:
                return self._default.copy()
            except AttributeError:
                raise ValueError('If default is mutable, it must have a `copy` method')
        else:
            return self._default

    @staticmethod
    def _invert(func):
        def wrapper(*args, **kwargs):
            return not func(*args, **kwargs)
        return wrapper
