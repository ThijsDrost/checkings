# ruff: noqa: E501

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
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
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
                    msg = f"Cannot add two {name}"
                    raise ValueError(msg)
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
                    msg = f"Validator named {validator.__name__} raised an exception: {e}"
                    errors.append(ValueError(msg))
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
    def integer_greater_than(cls, min_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an integer and is greater than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def integer_larger_than(cls, min_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an integer and is larger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def integer_bigger_than(cls, min_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an integer and is bigger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def integer_smaller_than(cls, max_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an integer and is smaller than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def integer_less_than(cls, max_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an integer and is less than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def integer_in_range(cls, start_val: float, end_val: float, *, start_inclusive: bool = True, end_inclusive: bool = True, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
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
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def integer_between(cls, start_val: float, end_val: float, *, start_inclusive: bool = False, end_inclusive: bool = False, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
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
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def number_greater_than(cls, min_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is greater than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int, float),) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def number_larger_than(cls, min_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is larger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int, float),) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def number_bigger_than(cls, min_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is bigger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int, float),) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def number_smaller_than(cls, max_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is smaller than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int, float),) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def number_less_than(cls, max_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is less than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int, float),) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def number_in_range(cls, start_val: float, end_val: float, *, start_inclusive: bool = True, end_inclusive: bool = True, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
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
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int, float),) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def number_between(cls, start_val: float, end_val: float, *, start_inclusive: bool = False, end_inclusive: bool = False, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
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
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int, float),) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def float_greater_than(cls, min_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a float and is greater than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(float,),) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def float_larger_than(cls, min_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a float and is larger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(float,),) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def float_bigger_than(cls, min_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a float and is bigger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(float,),) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def float_smaller_than(cls, max_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a float and is smaller than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(float,),) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def float_less_than(cls, max_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a float and is less than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(float,),) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def float_in_range(cls, start_val: float, end_val: float, *, start_inclusive: bool = True, end_inclusive: bool = True, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
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
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(float,),) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def float_between(cls, start_val: float, end_val: float, *, start_inclusive: bool = False, end_inclusive: bool = False, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
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
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(float,),) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def int_greater_than(cls, min_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an int and is greater than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def int_larger_than(cls, min_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an int and is larger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def int_bigger_than(cls, min_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an int and is bigger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def int_smaller_than(cls, max_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an int and is smaller than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def int_less_than(cls, max_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an int and is less than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def int_in_range(cls, start_val: float, end_val: float, *, start_inclusive: bool = True, end_inclusive: bool = True, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
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
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def int_between(cls, start_val: float, end_val: float, *, start_inclusive: bool = False, end_inclusive: bool = False, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
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
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def positive_integer(cls, include_zero: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value positive and is an instance of an integer.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(number_line=NumberLine.positive(include_zero=include_zero),) + cls(types=(int,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def positive_number(cls, include_zero: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value positive and is an instance of a number.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(number_line=NumberLine.positive(include_zero=include_zero),) + cls(types=(int, float),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def positive_float(cls, include_zero: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value positive and is an instance of a float.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(number_line=NumberLine.positive(include_zero=include_zero),) + cls(types=(float,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def positive_int(cls, include_zero: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value positive and is an instance of an int.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(number_line=NumberLine.positive(include_zero=include_zero),) + cls(types=(int,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def negative_integer(cls, include_zero: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value negative and is an instance of an integer.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(number_line=NumberLine.negative(include_zero=include_zero),) + cls(types=(int,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def negative_number(cls, include_zero: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value negative and is an instance of a number.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(number_line=NumberLine.negative(include_zero=include_zero),) + cls(types=(int, float),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def negative_float(cls, include_zero: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value negative and is an instance of a float.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(number_line=NumberLine.negative(include_zero=include_zero),) + cls(types=(float,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def negative_int(cls, include_zero: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value negative and is an instance of an int.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(number_line=NumberLine.negative(include_zero=include_zero),) + cls(types=(int,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def greater_than(cls, min_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is greater than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int, float),) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def larger_than(cls, min_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is larger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int, float),) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def bigger_than(cls, min_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is bigger than `min_val`.

        Parameters
        ----------
        min_val: float
            The minimum value
        inclusive: bool
            Whether the value is allowed to be equal to the minimum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int, float),) + cls(number_line=NumberLine.bigger_than_float(value=min_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def smaller_than(cls, max_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is smaller than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int, float),) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def less_than(cls, max_val: float, inclusive: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a number and is less than `max_val`.

        Parameters
        ----------
        max_val: float
            The maximum value
        inclusive: bool
            Whether the value is allowed to be equal to the maximum value
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int, float),) + cls(number_line=NumberLine.smaller_than_float(value=max_val, inclusive=inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def in_range(cls, start_val: float, end_val: float, *, start_inclusive: bool = True, end_inclusive: bool = True, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
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
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int, float),) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def between(cls, start_val: float, end_val: float, *, start_inclusive: bool = False, end_inclusive: bool = False, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
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
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int, float),) + cls(number_line=NumberLine.between_float(start=start_val, end=end_val, start_inclusive=start_inclusive, end_inclusive=end_inclusive),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def positive(cls, include_zero: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a number and positive.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int, float),) + cls(number_line=NumberLine.positive(include_zero=include_zero),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def negative(cls, include_zero: bool, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a number and negative.

        Parameters
        ----------
        include_zero: bool
            Whether the value is allowed to be equal to zero
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int, float),) + cls(number_line=NumberLine.negative(include_zero=include_zero),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def even(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an integer and is even.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),) + cls(validators=is_even(),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def odd(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an integer and is odd.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),) + cls(validators=is_odd(),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def contains(cls, contains: str, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value contains `contains`.

        Parameters
        ----------
        contains: str
            The value to contain
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(validators=check_contains(contains=contains),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    # @classmethod
    # def literals(cls, literals: collections.abc.Sequence, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
    #     """
    #     Generate checker to check if the value is one of `literals`.
    #
    #     Parameters
    #     ----------
    #     literals: collections.abc.Sequence
    #         The literals to check against
    #
    #     Other Parameters
    #     -------
    #     default: object
    #         The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
    #         considered mutable if it does not have a `__hash__` method.
    #     default_factory: Callable[[], object]
    #         A function that returns the default value of the attribute.
    #     number_line: NumberLine
    #         The number line that the attribute must be on
    #     literals: tuple[object, ...] | object
    #         The literals that the attribute must be
    #     types: tuple[type, ...] | type
    #         The types that the attribute must be
    #     converter: Callable[[object], object]
    #         A function that converts the attribute to the correct type
    #     validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
    #         A tuple of functions that check if the attribute is valid
    #     replace_none: bool
    #         Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
    #         default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
    #         the default value.
    #
    #     Returns
    #     -------
    #     Self
    #         A new instance of the class with the given validators and other parameters applied
    #
    #     Notes
    #     -------
    #     The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
    #     raise errors when also trying to set the same value manually.
    #     """
    #     return cls(literals=literals,)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def non_zero(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is not zero.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(number_line=non_zero(),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def length(cls, length: int, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value of length `length`.

        Parameters
        ----------
        length: int
            The correct length
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(validators=check_len(length=length),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def lengths(cls, min_length: int, max_length: int, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value of length between `min_length` and `max_length` (both inclusive).

        Parameters
        ----------
        min_length: int
            The minimum length
        max_length: int
            The maximum length
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(validators=check_lens(min_length=min_length, max_length=max_length),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def sorted(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is sorted.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(validators=check_sorted(),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_int(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an int.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_float(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a float.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(float,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_str(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a str.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(str,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_tuple(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(tuple,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_dict(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a dict.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(dict,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_list(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a list.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(list,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_slice(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a slice.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(slice,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_integer(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an integer.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_number(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a number.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(int, float),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_string(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a string.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(str,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_dictionary(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a dictionary.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(dict,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_container(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Container (:external+python:py:class:`collections.abc.Container`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Container,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_hashable(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an Hashable (:external+python:py:class:`collections.abc.Hashable`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Hashable,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_iterable(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an Iterable (:external+python:py:class:`collections.abc.Iterable`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Iterable,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_reversible(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Reversible (:external+python:py:class:`collections.abc.Reversible`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Reversible,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_generator(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Generator (:external+python:py:class:`collections.abc.Generator`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Generator,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_sized(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Sized (:external+python:py:class:`collections.abc.Sized`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Sized,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_callable(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Callable (:external+python:py:class:`collections.abc.Callable`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Callable,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_collection(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Collection (:external+python:py:class:`collections.abc.Collection`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Collection,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_sequence(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Sequence,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_mutable_sequence(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a MutableSequence (:external+python:py:class:`collections.abc.MutableSequence`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.MutableSequence,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_byte_string(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a ByteString (:external+python:py:class:`collections.abc.ByteString`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.ByteString,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_set(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Set (:external+python:py:class:`collections.abc.Set`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Set,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_mutable_set(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a MutableSet (:external+python:py:class:`collections.abc.MutableSet`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.MutableSet,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_mapping(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Mapping (:external+python:py:class:`collections.abc.Mapping`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Mapping,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_mutable_mapping(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a MutableMapping (:external+python:py:class:`collections.abc.MutableMapping`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.MutableMapping,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_mapping_view(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a MappingView (:external+python:py:class:`collections.abc.MappingView`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.MappingView,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_items_view(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an ItemsView (:external+python:py:class:`collections.abc.ItemsView`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.ItemsView,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_keys_view(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a KeysView (:external+python:py:class:`collections.abc.KeysView`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.KeysView,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_values_view(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a ValuesView (:external+python:py:class:`collections.abc.ValuesView`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.ValuesView,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_awaitable(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an Awaitable (:external+python:py:class:`collections.abc.Awaitable`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Awaitable,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_async_iterable(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an AsyncIterable (:external+python:py:class:`collections.abc.AsyncIterable`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.AsyncIterable,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_async_iterator(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an AsyncIterator (:external+python:py:class:`collections.abc.AsyncIterator`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.AsyncIterator,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_coroutine(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Coroutine (:external+python:py:class:`collections.abc.Coroutine`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Coroutine,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_async_generator(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of an AsyncGenerator (:external+python:py:class:`collections.abc.AsyncGenerator`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.AsyncGenerator,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_buffer(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Buffer (:external+python:py:class:`collections.abc.Buffer`).
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Buffer,),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def list_of(cls, of_type: type, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `of_type`.

        Parameters
        ----------
        of_type: type
            The type to check against
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(list,),) + cls(validators=check_inside_type(type_=of_type),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def list_of_int(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `int`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(list,),) + cls(validators=check_inside_type(type_=(int,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def list_of_float(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `float`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(list,),) + cls(validators=check_inside_type(type_=(float,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def list_of_str(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `str`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(list,),) + cls(validators=check_inside_type(type_=(str,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def list_of_tuple(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `tuple`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(list,),) + cls(validators=check_inside_type(type_=(tuple,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def list_of_dict(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `dict`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(list,),) + cls(validators=check_inside_type(type_=(dict,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def list_of_list(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `list`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(list,),) + cls(validators=check_inside_type(type_=(list,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def list_of_slice(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `slice`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(list,),) + cls(validators=check_inside_type(type_=(slice,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def list_of_integer(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `int`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(list,),) + cls(validators=check_inside_type(type_=(int,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def list_of_number(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `int` or `float`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(list,),) + cls(validators=check_inside_type(type_=(int, float)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def list_of_string(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `str`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(list,),) + cls(validators=check_inside_type(type_=(str,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def list_of_dictionary(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a list and contains values of type `dict`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(list,),) + cls(validators=check_inside_type(type_=(dict,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def tuple_of(cls, of_type: type, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `of_type`.

        Parameters
        ----------
        of_type: type
            The type to check against
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(tuple,),) + cls(validators=check_inside_type(type_=of_type),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def tuple_of_int(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `int`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(tuple,),) + cls(validators=check_inside_type(type_=(int,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def tuple_of_float(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `float`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(tuple,),) + cls(validators=check_inside_type(type_=(float,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def tuple_of_str(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `str`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(tuple,),) + cls(validators=check_inside_type(type_=(str,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def tuple_of_tuple(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `tuple`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(tuple,),) + cls(validators=check_inside_type(type_=(tuple,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def tuple_of_dict(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `dict`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(tuple,),) + cls(validators=check_inside_type(type_=(dict,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def tuple_of_list(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `list`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(tuple,),) + cls(validators=check_inside_type(type_=(list,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def tuple_of_slice(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `slice`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(tuple,),) + cls(validators=check_inside_type(type_=(slice,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def tuple_of_integer(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `int`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(tuple,),) + cls(validators=check_inside_type(type_=(int,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def tuple_of_number(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `int` or `float`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(tuple,),) + cls(validators=check_inside_type(type_=(int, float)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def tuple_of_string(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `str`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(tuple,),) + cls(validators=check_inside_type(type_=(str,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def tuple_of_dictionary(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and contains values of type `dict`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(tuple,),) + cls(validators=check_inside_type(type_=(dict,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def sequence_of(cls, of_type: type, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `of_type`.

        Parameters
        ----------
        of_type: type
            The type to check against
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Sequence,),) + cls(validators=check_inside_type(type_=of_type),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def sequence_of_int(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `int`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Sequence,),) + cls(validators=check_inside_type(type_=(int,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def sequence_of_float(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `float`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Sequence,),) + cls(validators=check_inside_type(type_=(float,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def sequence_of_str(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `str`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Sequence,),) + cls(validators=check_inside_type(type_=(str,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def sequence_of_tuple(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `tuple`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Sequence,),) + cls(validators=check_inside_type(type_=(tuple,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def sequence_of_dict(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `dict`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Sequence,),) + cls(validators=check_inside_type(type_=(dict,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def sequence_of_list(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `list`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Sequence,),) + cls(validators=check_inside_type(type_=(list,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def sequence_of_slice(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `slice`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Sequence,),) + cls(validators=check_inside_type(type_=(slice,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def sequence_of_integer(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `int`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Sequence,),) + cls(validators=check_inside_type(type_=(int,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def sequence_of_number(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `int` or `float`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Sequence,),) + cls(validators=check_inside_type(type_=(int, float)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def sequence_of_string(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `str`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Sequence,),) + cls(validators=check_inside_type(type_=(str,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def sequence_of_dictionary(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and contains values of type `dict`.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Sequence,),) + cls(validators=check_inside_type(type_=(dict,)),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def has_attr(cls, attr: str, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value has attribute `attr`.

        Parameters
        ----------
        attr: str
            The attribute to check for
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(validators=check_has_attr(attr=attr),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def has_method(cls, method: str, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value has method `method`.

        Parameters
        ----------
        method: str
            The method to check for
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(validators=check_has_method(method=method),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def has_property(cls, property: str, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value has property `property`.

        Parameters
        ----------
        property: str
            The property to check for
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(validators=check_has_property(property=property),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def starts_with(cls, start: str, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a str and starts with `start`.

        Parameters
        ----------
        start: str
            The correct start
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(str,),) + cls(validators=check_starts_with(start=start),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def ends_with(cls, end: str, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a str and ends in `end`.

        Parameters
        ----------
        end: str
            The correct end
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(str,),) + cls(validators=check_ends_with(end=end),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def numpy_dim(cls, dims: int, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a numpy array and has `dims` dimensions.

        Parameters
        ----------
        dims: int
            The correct number of dimensions
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(np.ndarray,),) + cls(validators=check_numpy_dims(dims=dims),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def numpy_shape(cls, shape: tuple[int], *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a numpy array and has shape `shape`.

        Parameters
        ----------
        shape: tuple[int]
            The correct shape
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(np.ndarray,),) + cls(validators=check_numpy_shape(shape=shape),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def numpy_dtype(cls, dtype: type, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a numpy array and has dtype `dtype`.

        Parameters
        ----------
        dtype: type
            The correct dtype
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(np.ndarray,),) + cls(validators=check_numpy_dtype(dtype=dtype),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def numpy_subdtype(cls, subdtype: type, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a numpy array and has subdtype `subdtype`.

        Parameters
        ----------
        subdtype: type
            The correct subdtype
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(np.ndarray,),) + cls(validators=check_numpy_subdtype(subdtype=subdtype),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def sequence_of_length(cls, length: int, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and of length `length`.

        Parameters
        ----------
        length: int
            The correct length
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Sequence,),) + cls(validators=check_len(length=length),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def sequence_between_lengths(cls, min_length: int, max_length: int, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a Sequence (:external+python:py:class:`collections.abc.Sequence`) and of length between `min_length` and `max_length` (both inclusive).

        Parameters
        ----------
        min_length: int
            The minimum length
        max_length: int
            The maximum length
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(collections.abc.Sequence,),) + cls(validators=check_lens(min_length=min_length, max_length=max_length),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def list_of_length(cls, length: int, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a list and of length `length`.

        Parameters
        ----------
        length: int
            The correct length
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(list,),) + cls(validators=check_len(length=length),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def list_between_lengths(cls, min_length: int, max_length: int, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a list and of length between `min_length` and `max_length` (both inclusive).

        Parameters
        ----------
        min_length: int
            The minimum length
        max_length: int
            The maximum length
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(list,),) + cls(validators=check_lens(min_length=min_length, max_length=max_length),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def tuple_of_length(cls, length: int, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and of length `length`.

        Parameters
        ----------
        length: int
            The correct length
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(tuple,),) + cls(validators=check_len(length=length),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def tuple_between_lengths(cls, min_length: int, max_length: int, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a tuple and of length between `min_length` and `max_length` (both inclusive).

        Parameters
        ----------
        min_length: int
            The minimum length
        max_length: int
            The maximum length
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(tuple,),) + cls(validators=check_lens(min_length=min_length, max_length=max_length),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def numpy_array_of_length(cls, length: int, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a numpy array and of length `length`.

        Parameters
        ----------
        length: int
            The correct length
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(np.ndarray,),) + cls(validators=check_len(length=length),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def numpy_array_between_lengths(cls, min_length: int, max_length: int, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is an instance of a numpy array and of length between `min_length` and `max_length` (both inclusive).

        Parameters
        ----------
        min_length: int
            The minimum length
        max_length: int
            The maximum length
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(np.ndarray,),) + cls(validators=check_lens(min_length=min_length, max_length=max_length),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_path(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is a valid path.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(validators=check_path(),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_dir(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is a valid directory.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(validators=check_dir(),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def is_file(cls, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
        """
        Generate checker to check if the value is a valid file.
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(validators=check_file(),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
     
    @classmethod
    def numpy(cls, dims: int, shape: int | tuple[int], dtype: type, *, default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue) -> Self:
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
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            The number line that the attribute must be on
        literals: tuple[object, ...] | object
            The literals that the attribute must be
        types: tuple[type, ...] | type
            The types that the attribute must be
        converter: Callable[[object], object]
            A function that converts the attribute to the correct type
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid
        replace_none: bool
            Whether to replace `None` values with the default value. If `True`, `None` values will be replaced with the
            default value. If `False`, `None` values will raise an error. NoValue values will always be replaced with
            the default value.
        
        Returns
        -------
        Self
            A new instance of the class with the given validators and other parameters applied
            
        Notes
        -------
        The kwarg parameters described in the "Other Parameters" may already be set by the function itself, so this may
        raise errors when also trying to set the same value manually.
        """
        return cls(types=(np.ndarray,),) + cls(validators=check_numpy(dims=dims, shape=shape, dtype=dtype),)+ cls(default = default, default_factory = default_factory, number_line = number_line, literals = literals, types = types, converter = converter, validators = validators, replace_none = replace_none)
    


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

