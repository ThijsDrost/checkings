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
 
    @classmethod
    def default(cls, default: any, **kwargs) -> Self:
        """
        Set default value to `default`.

        Parameters
        ----------
        default: any
            The default value
        """
        return cls(default=default, **kwargs)
     
    @classmethod
    def default_int(cls, default: any, **kwargs) -> Self:
        """
        Check if the value is an instance of an int with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        """
        return cls(default=default, **kwargs) + cls(types=(int,), **kwargs)
     
    @classmethod
    def default_float(cls, default: any, **kwargs) -> Self:
        """
        Check if the value is an instance of a float with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        """
        return cls(default=default, **kwargs) + cls(types=(float,), **kwargs)
     
    @classmethod
    def default_str(cls, default: any, **kwargs) -> Self:
        """
        Check if the value is an instance of a str with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        """
        return cls(default=default, **kwargs) + cls(types=(str,), **kwargs)
     
    @classmethod
    def default_tuple(cls, default: any, **kwargs) -> Self:
        """
        Check if the value is an instance of a tuple with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        """
        return cls(default=default, **kwargs) + cls(types=(tuple,), **kwargs)
     
    @classmethod
    def default_dict(cls, default: any, **kwargs) -> Self:
        """
        Check if the value is an instance of a dict with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        """
        return cls(default=default, **kwargs) + cls(types=(dict,), **kwargs)
     
    @classmethod
    def default_list(cls, default: any, **kwargs) -> Self:
        """
        Check if the value is an instance of a list with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        """
        return cls(default=default, **kwargs) + cls(types=(list,), **kwargs)
     
    @classmethod
    def default_slice(cls, default: any, **kwargs) -> Self:
        """
        Check if the value is an instance of a slice with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        """
        return cls(default=default, **kwargs) + cls(types=(slice,), **kwargs)
     
    @classmethod
    def default_integer(cls, default: any, **kwargs) -> Self:
        """
        Check if the value is an instance of an integer with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        """
        return cls(default=default, **kwargs) + cls(types=(int,), **kwargs)
     
    @classmethod
    def default_number(cls, default: any, **kwargs) -> Self:
        """
        Check if the value is an instance of a number with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        """
        return cls(default=default, **kwargs) + cls(types=(int, float), **kwargs)
     
    @classmethod
    def default_string(cls, default: any, **kwargs) -> Self:
        """
        Check if the value is an instance of a string with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        """
        return cls(default=default, **kwargs) + cls(types=(str,), **kwargs)
     
    @classmethod
    def default_dictionary(cls, default: any, **kwargs) -> Self:
        """
        Check if the value is an instance of a dictionary with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        """
        return cls(default=default, **kwargs) + cls(types=(dict,), **kwargs)
     
    @classmethod
    def integer_greater_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of an integer and is greater than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def integer_larger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of an integer and is larger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def integer_bigger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of an integer and is bigger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def integer_smaller_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of an integer and is smaller than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def integer_less_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of an integer and is less than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def integer_in_range(cls, start_val: float, end_val: float, start_inclusive: bool = True, end_inclusive: bool = True, **kwargs) -> Self:
        """
        Check if the value is an instance of an integer and is between `start_val` and `end_val`.

        Parameters
        ----------
        start_val: float
            The start of the included range
        end_val: float
            The end of the included range
        start_inclusive: bool = True
            Whether the lower bound is included in the range
        end_inclusive: bool = True
            Whether the upper bound is included in the range
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def integer_between(cls, start_val: float, end_val: float, start_inclusive: bool = False, end_inclusive: bool = False, **kwargs) -> Self:
        """
        Check if the value is an instance of an integer and is between `start_val` and `end_val`.

        Parameters
        ----------
        start_val: float
            The start of the included range
        end_val: float
            The end of the included range
        start_inclusive: bool = False
            Whether the lower bound is included in the range
        end_inclusive: bool = False
            Whether the upper bound is included in the range
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def number_greater_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of a number and is greater than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def number_larger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of a number and is larger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def number_bigger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of a number and is bigger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def number_smaller_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of a number and is smaller than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def number_less_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of a number and is less than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def number_in_range(cls, start_val: float, end_val: float, start_inclusive: bool = True, end_inclusive: bool = True, **kwargs) -> Self:
        """
        Check if the value is an instance of a number and is between `start_val` and `end_val`.

        Parameters
        ----------
        start_val: float
            The start of the included range
        end_val: float
            The end of the included range
        start_inclusive: bool = True
            Whether the lower bound is included in the range
        end_inclusive: bool = True
            Whether the upper bound is included in the range
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def number_between(cls, start_val: float, end_val: float, start_inclusive: bool = False, end_inclusive: bool = False, **kwargs) -> Self:
        """
        Check if the value is an instance of a number and is between `start_val` and `end_val`.

        Parameters
        ----------
        start_val: float
            The start of the included range
        end_val: float
            The end of the included range
        start_inclusive: bool = False
            Whether the lower bound is included in the range
        end_inclusive: bool = False
            Whether the upper bound is included in the range
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def float_greater_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of a float and is greater than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        """
        return cls(types=(float,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def float_larger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of a float and is larger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        """
        return cls(types=(float,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def float_bigger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of a float and is bigger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        """
        return cls(types=(float,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def float_smaller_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of a float and is smaller than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        """
        return cls(types=(float,), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def float_less_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of a float and is less than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        """
        return cls(types=(float,), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def float_in_range(cls, start_val: float, end_val: float, start_inclusive: bool = True, end_inclusive: bool = True, **kwargs) -> Self:
        """
        Check if the value is an instance of a float and is between `start_val` and `end_val`.

        Parameters
        ----------
        start_val: float
            The start of the included range
        end_val: float
            The end of the included range
        start_inclusive: bool = True
            Whether the lower bound is included in the range
        end_inclusive: bool = True
            Whether the upper bound is included in the range
        """
        return cls(types=(float,), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def float_between(cls, start_val: float, end_val: float, start_inclusive: bool = False, end_inclusive: bool = False, **kwargs) -> Self:
        """
        Check if the value is an instance of a float and is between `start_val` and `end_val`.

        Parameters
        ----------
        start_val: float
            The start of the included range
        end_val: float
            The end of the included range
        start_inclusive: bool = False
            Whether the lower bound is included in the range
        end_inclusive: bool = False
            Whether the upper bound is included in the range
        """
        return cls(types=(float,), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def int_greater_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of an int and is greater than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def int_larger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of an int and is larger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def int_bigger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of an int and is bigger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def int_smaller_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of an int and is smaller than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def int_less_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of an int and is less than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def int_in_range(cls, start_val: float, end_val: float, start_inclusive: bool = True, end_inclusive: bool = True, **kwargs) -> Self:
        """
        Check if the value is an instance of an int and is between `start_val` and `end_val`.

        Parameters
        ----------
        start_val: float
            The start of the included range
        end_val: float
            The end of the included range
        start_inclusive: bool = True
            Whether the lower bound is included in the range
        end_inclusive: bool = True
            Whether the upper bound is included in the range
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def int_between(cls, start_val: float, end_val: float, start_inclusive: bool = False, end_inclusive: bool = False, **kwargs) -> Self:
        """
        Check if the value is an instance of an int and is between `start_val` and `end_val`.

        Parameters
        ----------
        start_val: float
            The start of the included range
        end_val: float
            The end of the included range
        start_inclusive: bool = False
            Whether the lower bound is included in the range
        end_inclusive: bool = False
            Whether the upper bound is included in the range
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def positive_integer(cls, include_zero: bool, **kwargs) -> Self:
        """
        Check if the value positive and is an instance of an integer.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        """
        return cls(number_line=NumberLine.positive(include_zero=include_zero), **kwargs) + cls(types=(int,), **kwargs)
     
    @classmethod
    def positive_number(cls, include_zero: bool, **kwargs) -> Self:
        """
        Check if the value positive and is an instance of a number.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        """
        return cls(number_line=NumberLine.positive(include_zero=include_zero), **kwargs) + cls(types=(int, float), **kwargs)
     
    @classmethod
    def positive_float(cls, include_zero: bool, **kwargs) -> Self:
        """
        Check if the value positive and is an instance of a float.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        """
        return cls(number_line=NumberLine.positive(include_zero=include_zero), **kwargs) + cls(types=(float,), **kwargs)
     
    @classmethod
    def positive_int(cls, include_zero: bool, **kwargs) -> Self:
        """
        Check if the value positive and is an instance of an int.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        """
        return cls(number_line=NumberLine.positive(include_zero=include_zero), **kwargs) + cls(types=(int,), **kwargs)
     
    @classmethod
    def negative_integer(cls, include_zero: bool, **kwargs) -> Self:
        """
        Check if the value negative and is an instance of an integer.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        """
        return cls(number_line=NumberLine.negative(include_zero=include_zero), **kwargs) + cls(types=(int,), **kwargs)
     
    @classmethod
    def negative_number(cls, include_zero: bool, **kwargs) -> Self:
        """
        Check if the value negative and is an instance of a number.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        """
        return cls(number_line=NumberLine.negative(include_zero=include_zero), **kwargs) + cls(types=(int, float), **kwargs)
     
    @classmethod
    def negative_float(cls, include_zero: bool, **kwargs) -> Self:
        """
        Check if the value negative and is an instance of a float.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        """
        return cls(number_line=NumberLine.negative(include_zero=include_zero), **kwargs) + cls(types=(float,), **kwargs)
     
    @classmethod
    def negative_int(cls, include_zero: bool, **kwargs) -> Self:
        """
        Check if the value negative and is an instance of an int.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        """
        return cls(number_line=NumberLine.negative(include_zero=include_zero), **kwargs) + cls(types=(int,), **kwargs)
     
    @classmethod
    def greater_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of a number and is greater than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def larger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of a number and is larger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def bigger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of a number and is bigger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def smaller_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of a number and is smaller than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def less_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of a number and is less than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def in_range(cls, start_val: float, end_val: float, start_inclusive: bool = True, end_inclusive: bool = True, **kwargs) -> Self:
        """
        Check if the value is an instance of a number and is between `start_val` and `end_val`.

        Parameters
        ----------
        start_val: float
            The start of the included range
        end_val: float
            The end of the included range
        start_inclusive: bool = True
            Whether the lower bound is included in the range
        end_inclusive: bool = True
            Whether the upper bound is included in the range
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def between(cls, start_val: float, end_val: float, start_inclusive: bool = False, end_inclusive: bool = False, **kwargs) -> Self:
        """
        Check if the value is an instance of a number and is between `start_val` and `end_val`.

        Parameters
        ----------
        start_val: float
            The start of the included range
        end_val: float
            The end of the included range
        start_inclusive: bool = False
            Whether the lower bound is included in the range
        end_inclusive: bool = False
            Whether the upper bound is included in the range
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def positive(cls, include_zero: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of a number and positive.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.positive(include_zero=include_zero), **kwargs)
     
    @classmethod
    def negative(cls, include_zero: bool, **kwargs) -> Self:
        """
        Check if the value is an instance of a number and negative.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.negative(include_zero=include_zero), **kwargs)
     
    @classmethod
    def even(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of an integer and is even.
        """
        return cls(types=(int,), **kwargs) + cls(validators=is_even(), **kwargs)
     
    @classmethod
    def odd(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of an integer and is odd.
        """
        return cls(types=(int,), **kwargs) + cls(validators=is_odd(), **kwargs)
     
    @classmethod
    def contains(cls, contains: str, **kwargs) -> Self:
        """
        Check if the value contains `contains`.

        Parameters
        ----------
        contains: str
            The value to contain
        """
        return cls(validators=check_contains(contains=contains), **kwargs)
     
    @classmethod
    def literals(cls, literals: collections.abc.Sequence, **kwargs) -> Self:
        """
        Check if the value is one of `literals`.

        Parameters
        ----------
        literals: collections.abc.Sequence
            The literals to check against
        """
        return cls(literals=literals, **kwargs)
     
    @classmethod
    def non_zero(cls, **kwargs) -> Self:
        """
        Check if the value is not zero.
        """
        return cls(number_line=non_zero(), **kwargs)
     
    @classmethod
    def length(cls, length: int, **kwargs) -> Self:
        """
        Check if the value of length `length`.

        Parameters
        ----------
        length: int
            The correct length
        """
        return cls(validators=check_len(length=length), **kwargs)
     
    @classmethod
    def lengths(cls, min_length: int, max_length: int, **kwargs) -> Self:
        """
        Check if the value of length between `min_length` and `max_length` (both inclusive).

        Parameters
        ----------
        min_length: int
            The minimum length
        max_length: int
            The maximum length
        """
        return cls(validators=check_lens(min_length=min_length, max_length=max_length), **kwargs)
     
    @classmethod
    def sorted(cls, **kwargs) -> Self:
        """
        Check if the value is sorted.
        """
        return cls(validators=check_sorted(), **kwargs)
     
    @classmethod
    def is_int(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of an int.
        """
        return cls(types=(int,), **kwargs)
     
    @classmethod
    def is_float(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a float.
        """
        return cls(types=(float,), **kwargs)
     
    @classmethod
    def is_str(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a str.
        """
        return cls(types=(str,), **kwargs)
     
    @classmethod
    def is_tuple(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a tuple.
        """
        return cls(types=(tuple,), **kwargs)
     
    @classmethod
    def is_dict(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a dict.
        """
        return cls(types=(dict,), **kwargs)
     
    @classmethod
    def is_list(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a list.
        """
        return cls(types=(list,), **kwargs)
     
    @classmethod
    def is_slice(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a slice.
        """
        return cls(types=(slice,), **kwargs)
     
    @classmethod
    def is_integer(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of an integer.
        """
        return cls(types=(int,), **kwargs)
     
    @classmethod
    def is_number(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a number.
        """
        return cls(types=(int, float), **kwargs)
     
    @classmethod
    def is_string(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a string.
        """
        return cls(types=(str,), **kwargs)
     
    @classmethod
    def is_dictionary(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a dictionary.
        """
        return cls(types=(dict,), **kwargs)
     
    @classmethod
    def is_container(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Container (:external+python:py:class:`collections.abc.Container`).
        """
        return cls(types=(collections.abc.Container,), **kwargs)
     
    @classmethod
    def is_hashable(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of an Hashable (:external+python:py:class:`collections.abc.Hashable`).
        """
        return cls(types=(collections.abc.Hashable,), **kwargs)
     
    @classmethod
    def is_iterable(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of an Iterable (:external+python:py:class:`collections.abc.Iterable`).
        """
        return cls(types=(collections.abc.Iterable,), **kwargs)
     
    @classmethod
    def is_reversible(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Reversible (:external+python:py:class:`collections.abc.Reversible`).
        """
        return cls(types=(collections.abc.Reversible,), **kwargs)
     
    @classmethod
    def is_generator(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Generator (:external+python:py:class:`collections.abc.Generator`).
        """
        return cls(types=(collections.abc.Generator,), **kwargs)
     
    @classmethod
    def is_sized(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Sized (:external+python:py:class:`collections.abc.Sized`).
        """
        return cls(types=(collections.abc.Sized,), **kwargs)
     
    @classmethod
    def is_callable(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Callable (:external+python:py:class:`collections.abc.Callable`).
        """
        return cls(types=(collections.abc.Callable,), **kwargs)
     
    @classmethod
    def is_collection(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Collection (:external+python:py:class:`collections.abc.Collection`).
        """
        return cls(types=(collections.abc.Collection,), **kwargs)
     
    @classmethod
    def is_sequence(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`).
        """
        return cls(types=(collections.abc.Sequence,), **kwargs)
     
    @classmethod
    def is_mutable_sequence(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a MutableSequence (:external+python:py:class:`collections.abc.MutableSequence`).
        """
        return cls(types=(collections.abc.MutableSequence,), **kwargs)
     
    @classmethod
    def is_byte_string(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a ByteString (:external+python:py:class:`collections.abc.ByteString`).
        """
        return cls(types=(collections.abc.ByteString,), **kwargs)
     
    @classmethod
    def is_set(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Set (:external+python:py:class:`collections.abc.Set`).
        """
        return cls(types=(collections.abc.Set,), **kwargs)
     
    @classmethod
    def is_mutable_set(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a MutableSet (:external+python:py:class:`collections.abc.MutableSet`).
        """
        return cls(types=(collections.abc.MutableSet,), **kwargs)
     
    @classmethod
    def is_mapping(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Mapping (:external+python:py:class:`collections.abc.Mapping`).
        """
        return cls(types=(collections.abc.Mapping,), **kwargs)
     
    @classmethod
    def is_mutable_mapping(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a MutableMapping (:external+python:py:class:`collections.abc.MutableMapping`).
        """
        return cls(types=(collections.abc.MutableMapping,), **kwargs)
     
    @classmethod
    def is_mapping_view(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a MappingView (:external+python:py:class:`collections.abc.MappingView`).
        """
        return cls(types=(collections.abc.MappingView,), **kwargs)
     
    @classmethod
    def is_items_view(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of an ItemsView (:external+python:py:class:`collections.abc.ItemsView`).
        """
        return cls(types=(collections.abc.ItemsView,), **kwargs)
     
    @classmethod
    def is_keys_view(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a KeysView (:external+python:py:class:`collections.abc.KeysView`).
        """
        return cls(types=(collections.abc.KeysView,), **kwargs)
     
    @classmethod
    def is_values_view(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a ValuesView (:external+python:py:class:`collections.abc.ValuesView`).
        """
        return cls(types=(collections.abc.ValuesView,), **kwargs)
     
    @classmethod
    def is_awaitable(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of an Awaitable (:external+python:py:class:`collections.abc.Awaitable`).
        """
        return cls(types=(collections.abc.Awaitable,), **kwargs)
     
    @classmethod
    def is_async_iterable(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of an AsyncIterable (:external+python:py:class:`collections.abc.AsyncIterable`).
        """
        return cls(types=(collections.abc.AsyncIterable,), **kwargs)
     
    @classmethod
    def is_async_iterator(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of an AsyncIterator (:external+python:py:class:`collections.abc.AsyncIterator`).
        """
        return cls(types=(collections.abc.AsyncIterator,), **kwargs)
     
    @classmethod
    def is_coroutine(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Coroutine (:external+python:py:class:`collections.abc.Coroutine`).
        """
        return cls(types=(collections.abc.Coroutine,), **kwargs)
     
    @classmethod
    def is_async_generator(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of an AsyncGenerator (:external+python:py:class:`collections.abc.AsyncGenerator`).
        """
        return cls(types=(collections.abc.AsyncGenerator,), **kwargs)
     
    @classmethod
    def is_buffer(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Buffer (:external+python:py:class:`collections.abc.Buffer`).
        """
        return cls(types=(collections.abc.Buffer,), **kwargs)
     
    @classmethod
    def list_of(cls, of_type: type, **kwargs) -> Self:
        """
        Check if the value is an instance of a list and contains values of type `of_type`.

        Parameters
        ----------
        of_type: type
            The type to check against
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=of_type), **kwargs)
     
    @classmethod
    def list_of_int(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a list and contains values of type `int`.
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(int,)), **kwargs)
     
    @classmethod
    def list_of_float(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a list and contains values of type `float`.
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(float,)), **kwargs)
     
    @classmethod
    def list_of_str(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a list and contains values of type `str`.
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(str,)), **kwargs)
     
    @classmethod
    def list_of_tuple(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a list and contains values of type `tuple`.
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(tuple,)), **kwargs)
     
    @classmethod
    def list_of_dict(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a list and contains values of type `dict`.
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(dict,)), **kwargs)
     
    @classmethod
    def list_of_list(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a list and contains values of type `list`.
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(list,)), **kwargs)
     
    @classmethod
    def list_of_slice(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a list and contains values of type `slice`.
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(slice,)), **kwargs)
     
    @classmethod
    def list_of_integer(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a list and contains values of type `int`.
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(int,)), **kwargs)
     
    @classmethod
    def list_of_number(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a list and contains values of type `int` or `float`.
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(int, float)), **kwargs)
     
    @classmethod
    def list_of_string(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a list and contains values of type `str`.
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(str,)), **kwargs)
     
    @classmethod
    def list_of_dictionary(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a list and contains values of type `dict`.
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(dict,)), **kwargs)
     
    @classmethod
    def tuple_of(cls, of_type: type, **kwargs) -> Self:
        """
        Check if the value is an instance of a tuple and contains values of type `of_type`.

        Parameters
        ----------
        of_type: type
            The type to check against
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=of_type), **kwargs)
     
    @classmethod
    def tuple_of_int(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a tuple and contains values of type `int`.
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(int,)), **kwargs)
     
    @classmethod
    def tuple_of_float(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a tuple and contains values of type `float`.
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(float,)), **kwargs)
     
    @classmethod
    def tuple_of_str(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a tuple and contains values of type `str`.
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(str,)), **kwargs)
     
    @classmethod
    def tuple_of_tuple(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a tuple and contains values of type `tuple`.
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(tuple,)), **kwargs)
     
    @classmethod
    def tuple_of_dict(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a tuple and contains values of type `dict`.
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(dict,)), **kwargs)
     
    @classmethod
    def tuple_of_list(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a tuple and contains values of type `list`.
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(list,)), **kwargs)
     
    @classmethod
    def tuple_of_slice(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a tuple and contains values of type `slice`.
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(slice,)), **kwargs)
     
    @classmethod
    def tuple_of_integer(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a tuple and contains values of type `int`.
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(int,)), **kwargs)
     
    @classmethod
    def tuple_of_number(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a tuple and contains values of type `int` or `float`.
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(int, float)), **kwargs)
     
    @classmethod
    def tuple_of_string(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a tuple and contains values of type `str`.
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(str,)), **kwargs)
     
    @classmethod
    def tuple_of_dictionary(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a tuple and contains values of type `dict`.
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(dict,)), **kwargs)
     
    @classmethod
    def sequence_of(cls, of_type: type, **kwargs) -> Self:
        """
        Check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `of_type`.

        Parameters
        ----------
        of_type: type
            The type to check against
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=of_type), **kwargs)
     
    @classmethod
    def sequence_of_int(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `int`.
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(int,)), **kwargs)
     
    @classmethod
    def sequence_of_float(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `float`.
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(float,)), **kwargs)
     
    @classmethod
    def sequence_of_str(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `str`.
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(str,)), **kwargs)
     
    @classmethod
    def sequence_of_tuple(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `tuple`.
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(tuple,)), **kwargs)
     
    @classmethod
    def sequence_of_dict(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `dict`.
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(dict,)), **kwargs)
     
    @classmethod
    def sequence_of_list(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `list`.
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(list,)), **kwargs)
     
    @classmethod
    def sequence_of_slice(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `slice`.
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(slice,)), **kwargs)
     
    @classmethod
    def sequence_of_integer(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `int`.
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(int,)), **kwargs)
     
    @classmethod
    def sequence_of_number(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `int` or `float`.
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(int, float)), **kwargs)
     
    @classmethod
    def sequence_of_string(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `str`.
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(str,)), **kwargs)
     
    @classmethod
    def sequence_of_dictionary(cls, **kwargs) -> Self:
        """
        Check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `dict`.
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(dict,)), **kwargs)
     
    @classmethod
    def starts_with(cls, start: str, **kwargs) -> Self:
        """
        Check if the value is an instance of a str and starts with `start`.

        Parameters
        ----------
        start: str
            The correct start
        """
        return cls(types=(str,), **kwargs) + cls(validators=check_starts_with(start=start), **kwargs)
     
    @classmethod
    def ends_with(cls, end: str, **kwargs) -> Self:
        """
        Check if the value is an instance of a str and ends in `end`.

        Parameters
        ----------
        end: str
            The correct end
        """
        return cls(types=(str,), **kwargs) + cls(validators=check_ends_with(end=end), **kwargs)
     
    @classmethod
    def numpy_dim(cls, dims: int, **kwargs) -> Self:
        """
        Check if the value is an instance of a numpy array and has `dims` dimensions.

        Parameters
        ----------
        dims: int
            The correct number of dimensions
        """
        return cls(types=(np.ndarray,), **kwargs) + cls(validators=check_numpy_dims(dims=dims), **kwargs)
     
    @classmethod
    def numpy_shape(cls, shape: tuple[int], **kwargs) -> Self:
        """
        Check if the value is an instance of a numpy array and has shape `shape`.

        Parameters
        ----------
        shape: tuple[int]
            The correct shape
        """
        return cls(types=(np.ndarray,), **kwargs) + cls(validators=check_numpy_shape(shape=shape), **kwargs)
     
    @classmethod
    def numpy_dtype(cls, dtype: type, **kwargs) -> Self:
        """
        Check if the value is an instance of a numpy array and has dtype `dtype`.

        Parameters
        ----------
        dtype: type
            The correct dtype
        """
        return cls(types=(np.ndarray,), **kwargs) + cls(validators=check_numpy_dtype(dtype=dtype), **kwargs)
     
    @classmethod
    def sequence_of_length(cls, length: int, **kwargs) -> Self:
        """
        Check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and of length `length`.

        Parameters
        ----------
        length: int
            The correct length
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_len(length=length), **kwargs)
     
    @classmethod
    def sequence_between_lengths(cls, min_length: int, max_length: int, **kwargs) -> Self:
        """
        Check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and of length between `min_length` and `max_length` (both inclusive).

        Parameters
        ----------
        min_length: int
            The minimum length
        max_length: int
            The maximum length
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_lens(min_length=min_length, max_length=max_length), **kwargs)
     
    @classmethod
    def list_of_length(cls, length: int, **kwargs) -> Self:
        """
        Check if the value is an instance of a list and of length `length`.

        Parameters
        ----------
        length: int
            The correct length
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_len(length=length), **kwargs)
     
    @classmethod
    def list_between_lengths(cls, min_length: int, max_length: int, **kwargs) -> Self:
        """
        Check if the value is an instance of a list and of length between `min_length` and `max_length` (both inclusive).

        Parameters
        ----------
        min_length: int
            The minimum length
        max_length: int
            The maximum length
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_lens(min_length=min_length, max_length=max_length), **kwargs)
     
    @classmethod
    def tuple_of_length(cls, length: int, **kwargs) -> Self:
        """
        Check if the value is an instance of a tuple and of length `length`.

        Parameters
        ----------
        length: int
            The correct length
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_len(length=length), **kwargs)
     
    @classmethod
    def tuple_between_lengths(cls, min_length: int, max_length: int, **kwargs) -> Self:
        """
        Check if the value is an instance of a tuple and of length between `min_length` and `max_length` (both inclusive).

        Parameters
        ----------
        min_length: int
            The minimum length
        max_length: int
            The maximum length
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_lens(min_length=min_length, max_length=max_length), **kwargs)
     
    @classmethod
    def numpy_array_of_length(cls, length: int, **kwargs) -> Self:
        """
        Check if the value is an instance of a numpy array and of length `length`.

        Parameters
        ----------
        length: int
            The correct length
        """
        return cls(types=(np.ndarray,), **kwargs) + cls(validators=check_len(length=length), **kwargs)
     
    @classmethod
    def numpy_array_between_lengths(cls, min_length: int, max_length: int, **kwargs) -> Self:
        """
        Check if the value is an instance of a numpy array and of length between `min_length` and `max_length` (both inclusive).

        Parameters
        ----------
        min_length: int
            The minimum length
        max_length: int
            The maximum length
        """
        return cls(types=(np.ndarray,), **kwargs) + cls(validators=check_lens(min_length=min_length, max_length=max_length), **kwargs)
     
    @classmethod
    def is_path(cls, **kwargs) -> Self:
        """
        Check if the value is a valid path.
        """
        return cls(validators=check_path(), **kwargs)
     
    @classmethod
    def is_dir(cls, **kwargs) -> Self:
        """
        Check if the value is a valid directory.
        """
        return cls(validators=check_dir(), **kwargs)
     
    @classmethod
    def is_file(cls, **kwargs) -> Self:
        """
        Check if the value is a valid file.
        """
        return cls(validators=check_file(), **kwargs)
     
    @classmethod
    def numpy(cls, dims: int, shape: int | tuple[int], dtype: type, **kwargs) -> Self:
        """
        Check if the value is an instance of a numpy array and has `dims` dimensions, shape `shape` and dtype `dtype`.

        Parameters
        ----------
        dims: int
            The correct number of dimensions
        shape: int | tuple[int]
            The correct shape
        dtype: type
            The correct dtype
        """
        return cls(types=(np.ndarray,), **kwargs) + cls(validators=check_numpy(dims=dims, shape=shape, dtype=dtype), **kwargs)
    

def check_inside_type(type_):
    def checker(value):
        if not all(isinstance(val, type_) for val in value):
            return ValueError(f"Value must contain only values of type {type}")
        return None
    return checker

def non_zero():
    return NumberLine.exclude_from_floats(0, 0, False, False)

def is_even():
    def checker(value):
        if value % 2 != 0:
            return ValueError("Value must be even")
        return None
    return checker

def is_odd():
    def checker(value):
        if value % 2 == 0:
            return ValueError("Value must be odd")
        return None
    return checker

def check_starts_with(start):
    def checker(value):
        if not value.startswith(start):
            return ValueError(f"Value must start with {start}")
        return None
    return checker

def check_ends_with(end):
    def checker(value):
        if not value.endswith(end):
            return ValueError(f"Value must end with {end}")
        return None
    return checker

def check_numpy_dims(dims):
    def checker(value):
        if value.ndim != dims:
            return ValueError(f"Value must have {dims} dimensions, not {value.ndim}")
        return None
    return checker

def check_numpy_shape(shape):
    def checker(value):
        if value.shape != shape:
            return ValueError(f"Value must have shape {shape}, not {value.shape}")
        return None
    return checker

def check_numpy_dtype(dtype):
    def checker(value):
        if value.dtype != dtype:
            return ValueError(f"Value must have dtype {dtype}, not {value.dtype}")
        return None
    return checker

def check_numpy(dims, shape, dtype):
    def checker(value):
        nonlocal shape
        if value.ndim != dims:
            return ValueError(f"Value must have {dims} dimensions, not {value.ndim}")
        if isinstance(shape, int):
            shape = (shape,)
        if value.shape != shape:
            return ValueError(f"Value must have shape {shape}, not {value.shape}")
        if value.dtype != dtype:
            return ValueError(f"Value must have dtype {dtype}, not {value.dtype}")
        return None
    return checker

def check_path():
    def checker(value):
        if not os.path.exists(value):
            return ValueError(f"Path does not exist")
        return None
    return checker

def check_dir():
    def checker(value):
        if not os.path.isdir(value):
            return ValueError(f"Path is not a directory")
        return None
    return checker

def check_file():
    def checker(value):
        if not os.path.isfile(value):
            return ValueError(f"Path is not a file")
        return None
    return checker

def check_len(length):
    def checker(value):
        if len(value) != length:
            return ValueError(f"Length must be {length}, not {len(value)}")
        return None
    return checker

def check_lens(min_length, max_length):
    def checker(value):
        if not min_length <= len(value) <= max_length:
            return ValueError(f"Length must be between {min_length} and {max_length}, not {len(value)}")
        return None
    return checker

def check_contains(contains):
    def checker(value):
        if contains not in value:
            return ValueError(f"Value must contain {contains}")
        return None
    return checker

def check_sorted():
    def checker(value):
        if isinstance(value, np.ndarray):
            if not np.all(value[:-1] <= value[1:]):
                return ValueError(f"Value must be sorted")
        else:
            if all(value[i] <= value[i+1] for i in range(len(value) - 1)):
                return ValueError(f"Value must be sorted")
        return None
    return checker

