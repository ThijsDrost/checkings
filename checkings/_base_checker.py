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
 
    @classmethod
    def default(cls, default: any, **kwargs) -> Self:
        """
        Set default value to `default`.

        Parameters
        ----------
        default: any
            The default value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(default=default, **kwargs)
     
    @classmethod
    def default_int(cls, default: any, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an int with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(default=default, **kwargs) + cls(types=(int,), **kwargs)
     
    @classmethod
    def default_float(cls, default: any, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a float with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(default=default, **kwargs) + cls(types=(float,), **kwargs)
     
    @classmethod
    def default_str(cls, default: any, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a str with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(default=default, **kwargs) + cls(types=(str,), **kwargs)
     
    @classmethod
    def default_tuple(cls, default: any, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(default=default, **kwargs) + cls(types=(tuple,), **kwargs)
     
    @classmethod
    def default_dict(cls, default: any, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a dict with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(default=default, **kwargs) + cls(types=(dict,), **kwargs)
     
    @classmethod
    def default_list(cls, default: any, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a list with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(default=default, **kwargs) + cls(types=(list,), **kwargs)
     
    @classmethod
    def default_slice(cls, default: any, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a slice with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(default=default, **kwargs) + cls(types=(slice,), **kwargs)
     
    @classmethod
    def default_integer(cls, default: any, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an integer with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(default=default, **kwargs) + cls(types=(int,), **kwargs)
     
    @classmethod
    def default_number(cls, default: any, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(default=default, **kwargs) + cls(types=(int, float), **kwargs)
     
    @classmethod
    def default_string(cls, default: any, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a string with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(default=default, **kwargs) + cls(types=(str,), **kwargs)
     
    @classmethod
    def default_dictionary(cls, default: any, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a dictionary with default value `default`.

        Parameters
        ----------
        default: any
            The default value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(default=default, **kwargs) + cls(types=(dict,), **kwargs)
     
    @classmethod
    def integer_greater_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an integer and is greater than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def integer_larger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an integer and is larger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def integer_bigger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an integer and is bigger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def integer_smaller_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an integer and is smaller than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def integer_less_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an integer and is less than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def integer_in_range(cls, start_val: float, end_val: float, start_inclusive: bool = True, end_inclusive: bool = True, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an integer and is between `start_val` and `end_val`.

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
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def integer_between(cls, start_val: float, end_val: float, start_inclusive: bool = False, end_inclusive: bool = False, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an integer and is between `start_val` and `end_val`.

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
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def number_greater_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is greater than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def number_larger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is larger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def number_bigger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is bigger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def number_smaller_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is smaller than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def number_less_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is less than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def number_in_range(cls, start_val: float, end_val: float, start_inclusive: bool = True, end_inclusive: bool = True, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is between `start_val` and `end_val`.

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
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def number_between(cls, start_val: float, end_val: float, start_inclusive: bool = False, end_inclusive: bool = False, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is between `start_val` and `end_val`.

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
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def float_greater_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a float and is greater than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(float,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def float_larger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a float and is larger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(float,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def float_bigger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a float and is bigger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(float,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def float_smaller_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a float and is smaller than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(float,), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def float_less_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a float and is less than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(float,), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def float_in_range(cls, start_val: float, end_val: float, start_inclusive: bool = True, end_inclusive: bool = True, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a float and is between `start_val` and `end_val`.

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
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(float,), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def float_between(cls, start_val: float, end_val: float, start_inclusive: bool = False, end_inclusive: bool = False, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a float and is between `start_val` and `end_val`.

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
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(float,), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def int_greater_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an int and is greater than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def int_larger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an int and is larger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def int_bigger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an int and is bigger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def int_smaller_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an int and is smaller than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def int_less_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an int and is less than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def int_in_range(cls, start_val: float, end_val: float, start_inclusive: bool = True, end_inclusive: bool = True, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an int and is between `start_val` and `end_val`.

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
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def int_between(cls, start_val: float, end_val: float, start_inclusive: bool = False, end_inclusive: bool = False, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an int and is between `start_val` and `end_val`.

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
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def positive_integer(cls, include_zero: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value positive and is an instance of an integer.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(number_line=NumberLine.positive(include_zero=include_zero), **kwargs) + cls(types=(int,), **kwargs)
     
    @classmethod
    def positive_number(cls, include_zero: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value positive and is an instance of a number.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(number_line=NumberLine.positive(include_zero=include_zero), **kwargs) + cls(types=(int, float), **kwargs)
     
    @classmethod
    def positive_float(cls, include_zero: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value positive and is an instance of a float.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(number_line=NumberLine.positive(include_zero=include_zero), **kwargs) + cls(types=(float,), **kwargs)
     
    @classmethod
    def positive_int(cls, include_zero: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value positive and is an instance of an int.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(number_line=NumberLine.positive(include_zero=include_zero), **kwargs) + cls(types=(int,), **kwargs)
     
    @classmethod
    def negative_integer(cls, include_zero: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value negative and is an instance of an integer.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(number_line=NumberLine.negative(include_zero=include_zero), **kwargs) + cls(types=(int,), **kwargs)
     
    @classmethod
    def negative_number(cls, include_zero: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value negative and is an instance of a number.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(number_line=NumberLine.negative(include_zero=include_zero), **kwargs) + cls(types=(int, float), **kwargs)
     
    @classmethod
    def negative_float(cls, include_zero: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value negative and is an instance of a float.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(number_line=NumberLine.negative(include_zero=include_zero), **kwargs) + cls(types=(float,), **kwargs)
     
    @classmethod
    def negative_int(cls, include_zero: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value negative and is an instance of an int.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(number_line=NumberLine.negative(include_zero=include_zero), **kwargs) + cls(types=(int,), **kwargs)
     
    @classmethod
    def greater_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is greater than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def larger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is larger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def bigger_than(cls, min_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is bigger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def smaller_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is smaller than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def less_than(cls, max_val: float, inclusive: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is less than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive), **kwargs)
     
    @classmethod
    def in_range(cls, start_val: float, end_val: float, start_inclusive: bool = True, end_inclusive: bool = True, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is between `start_val` and `end_val`.

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
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def between(cls, start_val: float, end_val: float, start_inclusive: bool = False, end_inclusive: bool = False, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is between `start_val` and `end_val`.

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
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive), **kwargs)
     
    @classmethod
    def positive(cls, include_zero: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number and positive.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.positive(include_zero=include_zero), **kwargs)
     
    @classmethod
    def negative(cls, include_zero: bool, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number and negative.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int, float), **kwargs) + cls(number_line=NumberLine.negative(include_zero=include_zero), **kwargs)
     
    @classmethod
    def even(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an integer and is even.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs) + cls(validators=is_even(), **kwargs)
     
    @classmethod
    def odd(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an integer and is odd.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs) + cls(validators=is_odd(), **kwargs)
     
    @classmethod
    def contains(cls, contains: str, **kwargs) -> Self:
        """
        Generate checker to check if the value contains `contains`.

        Parameters
        ----------
        contains: str
            The value to contain
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(validators=check_contains(contains=contains), **kwargs)
     
    @classmethod
    def literals(cls, literals: collections.abc.Sequence, **kwargs) -> Self:
        """
        Generate checker to check if the value is one of `literals`.

        Parameters
        ----------
        literals: collections.abc.Sequence
            The literals to check against
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(literals=literals, **kwargs)
     
    @classmethod
    def non_zero(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is not zero.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(number_line=non_zero(), **kwargs)
     
    @classmethod
    def length(cls, length: int, **kwargs) -> Self:
        """
        Generate checker to check if the value of length `length`.

        Parameters
        ----------
        length: int
            The correct length
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(validators=check_len(length=length), **kwargs)
     
    @classmethod
    def lengths(cls, min_length: int, max_length: int, **kwargs) -> Self:
        """
        Generate checker to check if the value of length between `min_length` and `max_length` (both inclusive).

        Parameters
        ----------
        min_length: int
            The minimum length
        max_length: int
            The maximum length
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(validators=check_lens(min_length=min_length, max_length=max_length), **kwargs)
     
    @classmethod
    def sorted(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is sorted.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(validators=check_sorted(), **kwargs)
     
    @classmethod
    def is_int(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an int.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs)
     
    @classmethod
    def is_float(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a float.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(float,), **kwargs)
     
    @classmethod
    def is_str(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a str.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(str,), **kwargs)
     
    @classmethod
    def is_tuple(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(tuple,), **kwargs)
     
    @classmethod
    def is_dict(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a dict.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(dict,), **kwargs)
     
    @classmethod
    def is_list(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a list.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(list,), **kwargs)
     
    @classmethod
    def is_slice(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a slice.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(slice,), **kwargs)
     
    @classmethod
    def is_integer(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an integer.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int,), **kwargs)
     
    @classmethod
    def is_number(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a number.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(int, float), **kwargs)
     
    @classmethod
    def is_string(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a string.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(str,), **kwargs)
     
    @classmethod
    def is_dictionary(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a dictionary.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(dict,), **kwargs)
     
    @classmethod
    def is_container(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Container (:external+python:py:class:`collections.abc.Container`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Container,), **kwargs)
     
    @classmethod
    def is_hashable(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an Hashable (:external+python:py:class:`collections.abc.Hashable`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Hashable,), **kwargs)
     
    @classmethod
    def is_iterable(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an Iterable (:external+python:py:class:`collections.abc.Iterable`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Iterable,), **kwargs)
     
    @classmethod
    def is_reversible(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Reversible (:external+python:py:class:`collections.abc.Reversible`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Reversible,), **kwargs)
     
    @classmethod
    def is_generator(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Generator (:external+python:py:class:`collections.abc.Generator`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Generator,), **kwargs)
     
    @classmethod
    def is_sized(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Sized (:external+python:py:class:`collections.abc.Sized`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Sized,), **kwargs)
     
    @classmethod
    def is_callable(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Callable (:external+python:py:class:`collections.abc.Callable`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Callable,), **kwargs)
     
    @classmethod
    def is_collection(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Collection (:external+python:py:class:`collections.abc.Collection`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Collection,), **kwargs)
     
    @classmethod
    def is_sequence(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Sequence,), **kwargs)
     
    @classmethod
    def is_mutable_sequence(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a MutableSequence (:external+python:py:class:`collections.abc.MutableSequence`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.MutableSequence,), **kwargs)
     
    @classmethod
    def is_byte_string(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a ByteString (:external+python:py:class:`collections.abc.ByteString`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.ByteString,), **kwargs)
     
    @classmethod
    def is_set(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Set (:external+python:py:class:`collections.abc.Set`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Set,), **kwargs)
     
    @classmethod
    def is_mutable_set(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a MutableSet (:external+python:py:class:`collections.abc.MutableSet`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.MutableSet,), **kwargs)
     
    @classmethod
    def is_mapping(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Mapping (:external+python:py:class:`collections.abc.Mapping`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Mapping,), **kwargs)
     
    @classmethod
    def is_mutable_mapping(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a MutableMapping (:external+python:py:class:`collections.abc.MutableMapping`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.MutableMapping,), **kwargs)
     
    @classmethod
    def is_mapping_view(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a MappingView (:external+python:py:class:`collections.abc.MappingView`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.MappingView,), **kwargs)
     
    @classmethod
    def is_items_view(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an ItemsView (:external+python:py:class:`collections.abc.ItemsView`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.ItemsView,), **kwargs)
     
    @classmethod
    def is_keys_view(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a KeysView (:external+python:py:class:`collections.abc.KeysView`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.KeysView,), **kwargs)
     
    @classmethod
    def is_values_view(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a ValuesView (:external+python:py:class:`collections.abc.ValuesView`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.ValuesView,), **kwargs)
     
    @classmethod
    def is_awaitable(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an Awaitable (:external+python:py:class:`collections.abc.Awaitable`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Awaitable,), **kwargs)
     
    @classmethod
    def is_async_iterable(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an AsyncIterable (:external+python:py:class:`collections.abc.AsyncIterable`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.AsyncIterable,), **kwargs)
     
    @classmethod
    def is_async_iterator(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an AsyncIterator (:external+python:py:class:`collections.abc.AsyncIterator`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.AsyncIterator,), **kwargs)
     
    @classmethod
    def is_coroutine(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Coroutine (:external+python:py:class:`collections.abc.Coroutine`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Coroutine,), **kwargs)
     
    @classmethod
    def is_async_generator(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of an AsyncGenerator (:external+python:py:class:`collections.abc.AsyncGenerator`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.AsyncGenerator,), **kwargs)
     
    @classmethod
    def is_buffer(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Buffer (:external+python:py:class:`collections.abc.Buffer`).
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Buffer,), **kwargs)
     
    @classmethod
    def list_of(cls, of_type: type, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `of_type`.

        Parameters
        ----------
        of_type: type
            The type to check against
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=of_type), **kwargs)
     
    @classmethod
    def list_of_int(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `int`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(int,)), **kwargs)
     
    @classmethod
    def list_of_float(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `float`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(float,)), **kwargs)
     
    @classmethod
    def list_of_str(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `str`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(str,)), **kwargs)
     
    @classmethod
    def list_of_tuple(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `tuple`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(tuple,)), **kwargs)
     
    @classmethod
    def list_of_dict(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `dict`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(dict,)), **kwargs)
     
    @classmethod
    def list_of_list(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `list`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(list,)), **kwargs)
     
    @classmethod
    def list_of_slice(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `slice`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(slice,)), **kwargs)
     
    @classmethod
    def list_of_integer(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `int`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(int,)), **kwargs)
     
    @classmethod
    def list_of_number(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `int` or `float`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(int, float)), **kwargs)
     
    @classmethod
    def list_of_string(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `str`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(str,)), **kwargs)
     
    @classmethod
    def list_of_dictionary(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `dict`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_inside_type(type_=(dict,)), **kwargs)
     
    @classmethod
    def tuple_of(cls, of_type: type, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `of_type`.

        Parameters
        ----------
        of_type: type
            The type to check against
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=of_type), **kwargs)
     
    @classmethod
    def tuple_of_int(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `int`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(int,)), **kwargs)
     
    @classmethod
    def tuple_of_float(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `float`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(float,)), **kwargs)
     
    @classmethod
    def tuple_of_str(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `str`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(str,)), **kwargs)
     
    @classmethod
    def tuple_of_tuple(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `tuple`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(tuple,)), **kwargs)
     
    @classmethod
    def tuple_of_dict(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `dict`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(dict,)), **kwargs)
     
    @classmethod
    def tuple_of_list(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `list`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(list,)), **kwargs)
     
    @classmethod
    def tuple_of_slice(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `slice`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(slice,)), **kwargs)
     
    @classmethod
    def tuple_of_integer(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `int`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(int,)), **kwargs)
     
    @classmethod
    def tuple_of_number(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `int` or `float`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(int, float)), **kwargs)
     
    @classmethod
    def tuple_of_string(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `str`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(str,)), **kwargs)
     
    @classmethod
    def tuple_of_dictionary(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `dict`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_inside_type(type_=(dict,)), **kwargs)
     
    @classmethod
    def sequence_of(cls, of_type: type, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `of_type`.

        Parameters
        ----------
        of_type: type
            The type to check against
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=of_type), **kwargs)
     
    @classmethod
    def sequence_of_int(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `int`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(int,)), **kwargs)
     
    @classmethod
    def sequence_of_float(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `float`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(float,)), **kwargs)
     
    @classmethod
    def sequence_of_str(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `str`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(str,)), **kwargs)
     
    @classmethod
    def sequence_of_tuple(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `tuple`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(tuple,)), **kwargs)
     
    @classmethod
    def sequence_of_dict(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `dict`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(dict,)), **kwargs)
     
    @classmethod
    def sequence_of_list(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `list`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(list,)), **kwargs)
     
    @classmethod
    def sequence_of_slice(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `slice`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(slice,)), **kwargs)
     
    @classmethod
    def sequence_of_integer(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `int`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(int,)), **kwargs)
     
    @classmethod
    def sequence_of_number(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `int` or `float`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(int, float)), **kwargs)
     
    @classmethod
    def sequence_of_string(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `str`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(str,)), **kwargs)
     
    @classmethod
    def sequence_of_dictionary(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `dict`.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_inside_type(type_=(dict,)), **kwargs)
     
    @classmethod
    def has_attr(cls, attr: str, **kwargs) -> Self:
        """
        Generate checker to check if the value has attribute `attr`.

        Parameters
        ----------
        attr: str
            The attribute to check for
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(validators=check_has_attr(attr=attr), **kwargs)
     
    @classmethod
    def has_method(cls, method: str, **kwargs) -> Self:
        """
        Generate checker to check if the value has method `method`.

        Parameters
        ----------
        method: str
            The method to check for
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(validators=check_has_method(method=method), **kwargs)
     
    @classmethod
    def has_property(cls, property: str, **kwargs) -> Self:
        """
        Generate checker to check if the value has property `property`.

        Parameters
        ----------
        property: str
            The property to check for
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(validators=check_has_property(property=property), **kwargs)
     
    @classmethod
    def starts_with(cls, start: str, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a str and starts with `start`.

        Parameters
        ----------
        start: str
            The correct start
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(str,), **kwargs) + cls(validators=check_starts_with(start=start), **kwargs)
     
    @classmethod
    def ends_with(cls, end: str, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a str and ends in `end`.

        Parameters
        ----------
        end: str
            The correct end
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(str,), **kwargs) + cls(validators=check_ends_with(end=end), **kwargs)
     
    @classmethod
    def numpy_dim(cls, dims: int, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a numpy array and has `dims` dimensions.

        Parameters
        ----------
        dims: int
            The correct number of dimensions
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(np.ndarray,), **kwargs) + cls(validators=check_numpy_dims(dims=dims), **kwargs)
     
    @classmethod
    def numpy_shape(cls, shape: tuple[int], **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a numpy array and has shape `shape`.

        Parameters
        ----------
        shape: tuple[int]
            The correct shape
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(np.ndarray,), **kwargs) + cls(validators=check_numpy_shape(shape=shape), **kwargs)
     
    @classmethod
    def numpy_dtype(cls, dtype: type, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a numpy array and has dtype `dtype`.

        Parameters
        ----------
        dtype: type
            The correct dtype
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(np.ndarray,), **kwargs) + cls(validators=check_numpy_dtype(dtype=dtype), **kwargs)
     
    @classmethod
    def numpy_subdtype(cls, subdtype: type, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a numpy array and has subdtype `subdtype`.

        Parameters
        ----------
        subdtype: type
            The correct subdtype
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(np.ndarray,), **kwargs) + cls(validators=check_numpy_subdtype(subdtype=subdtype), **kwargs)
     
    @classmethod
    def sequence_of_length(cls, length: int, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and of length `length`.

        Parameters
        ----------
        length: int
            The correct length
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_len(length=length), **kwargs)
     
    @classmethod
    def sequence_between_lengths(cls, min_length: int, max_length: int, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and of length between `min_length` and `max_length` (both inclusive).

        Parameters
        ----------
        min_length: int
            The minimum length
        max_length: int
            The maximum length
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(collections.abc.Sequence,), **kwargs) + cls(validators=check_lens(min_length=min_length, max_length=max_length), **kwargs)
     
    @classmethod
    def list_of_length(cls, length: int, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a list and of length `length`.

        Parameters
        ----------
        length: int
            The correct length
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_len(length=length), **kwargs)
     
    @classmethod
    def list_between_lengths(cls, min_length: int, max_length: int, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a list and of length between `min_length` and `max_length` (both inclusive).

        Parameters
        ----------
        min_length: int
            The minimum length
        max_length: int
            The maximum length
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(list,), **kwargs) + cls(validators=check_lens(min_length=min_length, max_length=max_length), **kwargs)
     
    @classmethod
    def tuple_of_length(cls, length: int, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and of length `length`.

        Parameters
        ----------
        length: int
            The correct length
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_len(length=length), **kwargs)
     
    @classmethod
    def tuple_between_lengths(cls, min_length: int, max_length: int, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and of length between `min_length` and `max_length` (both inclusive).

        Parameters
        ----------
        min_length: int
            The minimum length
        max_length: int
            The maximum length
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(tuple,), **kwargs) + cls(validators=check_lens(min_length=min_length, max_length=max_length), **kwargs)
     
    @classmethod
    def numpy_array_of_length(cls, length: int, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a numpy array and of length `length`.

        Parameters
        ----------
        length: int
            The correct length
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(np.ndarray,), **kwargs) + cls(validators=check_len(length=length), **kwargs)
     
    @classmethod
    def numpy_array_between_lengths(cls, min_length: int, max_length: int, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a numpy array and of length between `min_length` and `max_length` (both inclusive).

        Parameters
        ----------
        min_length: int
            The minimum length
        max_length: int
            The maximum length
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(np.ndarray,), **kwargs) + cls(validators=check_lens(min_length=min_length, max_length=max_length), **kwargs)
     
    @classmethod
    def is_path(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is a valid path.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(validators=check_path(), **kwargs)
     
    @classmethod
    def is_dir(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is a valid directory.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(validators=check_dir(), **kwargs)
     
    @classmethod
    def is_file(cls, **kwargs) -> Self:
        """
        Generate checker to check if the value is a valid file.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(validators=check_file(), **kwargs)
     
    @classmethod
    def numpy(cls, dims: int, shape: int | tuple[int], dtype: type, **kwargs) -> Self:
        """
        Generate checker to check if the value is an instance of a numpy array and has `dims` dimensions, shape `shape` and dtype `dtype`.

        Parameters
        ----------
        dims: int
            The correct number of dimensions
        shape: int | tuple[int]
            The correct shape
        dtype: type
            The correct dtype
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
        """
        return cls(types=(np.ndarray,), **kwargs) + cls(validators=check_numpy(dims=dims, shape=shape, dtype=dtype), **kwargs)
    


def is_even():
    def checker(value):
        if value % 2 != 0:
            msg = "Value must be even"
            return ValueError(msg)
        return None
    return checker

def is_odd():
    def checker(value):
        if value % 2 == 0:
            msg = "Value must be odd"
            return ValueError(msg)
        return None
    return checker

def check_contains(contains):
    def checker(value):
        if contains not in value:
            msg = f"Value must contain {contains}"
            return ValueError(msg)
        return None
    return checker

def non_zero():
    return NumberLine.exclude_from_floats(0, 0, False, False)

def check_len(length):
    def checker(value):
        if len(value) != length:
            msg = f"Length must be {length}, not {len(value)}"
            return ValueError(msg)
        return None
    return checker

def check_lens(min_length, max_length):
    def checker(value):
        if not min_length <= len(value) <= max_length:
            msg = f"Length must be between {min_length} and {max_length}, not {len(value)}"
            return ValueError(msg)
        return None
    return checker

def check_sorted():
    def checker(value):
        def value_error(wrong):
            return ValueError(
                f"Value must be sorted, goes wrong at index{'es' if len(wrong) > 1 else ''} {wrong}",
            )
        if HAS_NUMPY:  
            if isinstance(value, np.ndarray):  
                values = value[:-1] <= value[1:]
                if not np.all(values):  
                    wrong = np.argwhere(~values)[:, 0]  
                    return value_error(wrong)
        elif all(value[i] <= value[i + 1] for i in range(len(value) - 1)):
            wrong = [i for i in range(len(value) - 1) if value[i] > value[i + 1]]
            return value_error(wrong)
        return None
    return checker

def check_inside_type(type_):
    def checker(value):
        if any(not isinstance(val, type_) for val in value):
            errors = []
            for index, val in enumerate(value):
                if not isinstance(val, type_):
                    errors.append(f"value at {index} is of type {type(val)}")
            if len(errors) == 1:
                msg = f"Value must contain only values of type {type_}. Error: {errors[0]}"
                return ValueError(msg)
            msg = f"Value must contain only values of type {type_}. Errors: {', '.join(errors[:-1])}, and {errors[-1]}"
            return ValueError(msg)
        return None
    return checker

def check_has_attr(attr):
    def checker(value):
        if not hasattr(value, attr):
            msg = f"Value must have attribute {attr}"
            return ValueError(msg)
        return None
    return checker

def check_has_method(method):
    def checker(value):
        if not hasattr(value, method) or not callable(getattr(value, method)):
            msg = f"Value must have method {method}"
            return ValueError(msg)
        return None
    return checker

def check_has_property(property):
    def checker(value):
        if not hasattr(value, property) or not isinstance(getattr(value, property), property):
            msg = f"Value must have property {property}"
            return ValueError(msg)
        return None
    return checker

def check_starts_with(start):
    def checker(value):
        if not value.startswith(start):
            msg = f"Value must start with {start}"
            return ValueError(msg)
        return None
    return checker

def check_ends_with(end):
    def checker(value):
        if not value.endswith(end):
            msg = f"Value must end with {end}"
            return ValueError(msg)
        return None
    return checker

def check_numpy_dims(dims):
    def checker(value):
        if value.ndim != dims:
            msg = f"Value must have {dims} dimensions, not {value.ndim}"
            return ValueError(msg)
        return None
    return checker

def check_numpy_shape(shape):
    def checker(value):
        if value.shape != shape:
            msg = f"Value must have shape {shape}, not {value.shape}"
            return ValueError(msg)
        return None
    return checker

def check_numpy_dtype(dtype):
    def checker(value):
        if value.dtype != dtype:
            msg = f"Value must have dtype {dtype}, not {value.dtype}"
            return ValueError(msg)
        return None
    return checker

def check_numpy_subdtype(subdtype):
    def checker(value):
        if not np.issubdtype(value.dtype, subdtype):
            msg = f"Value must have subdtype of {subdtype}, not {value.dtype}"
            return ValueError(msg)
        return None
    return checker

def check_path():
    def checker(value):
        if not os.path.exists(value):
            msg = f"Path `{value}` does not exist"
            return ValueError(msg)
        return None
    return checker

def check_dir():
    def checker(value):
        if not os.path.isdir(value):
            msg = f"Path `{value}` is not a directory"
            return ValueError(msg)
        return None
    return checker

def check_file():
    def checker(value):
        if not os.path.isfile(value):
            msg = f"Path `{value}` is not a file"
            return ValueError(msg)
        return None
    return checker

def check_numpy(dims, shape, dtype):
    def checker(value):
        nonlocal shape
        if value.ndim != dims:
            msg = f"Value must have {dims} dimensions, not {value.ndim}"
            return ValueError(msg)
        if isinstance(shape, int):
            shape = (shape,)
        if value.shape != shape:
            msg = f"Value must have shape {shape}, not {value.shape}"
            return ValueError(msg)
        if value.dtype != dtype:
            msg = f"Value must have dtype {dtype}, not {value.dtype}"
            return ValueError(msg)
        return None
    return checker

