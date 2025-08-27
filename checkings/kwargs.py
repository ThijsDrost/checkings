from typing import Any

from ._validators import Validator
from ._validator_error import ValidatorError

def default_kwargs(kwargs: dict[str, Any], defaults: Any) -> dict[str, Any]:
    """
    Fill in default values for missing keyword arguments.

    Parameters
    ----------
    kwargs: dict[str, Any]
        The keyword arguments.
    defaults: dict[str, Any]
        The default values for the keyword arguments.

    Returns
    -------
    dict[str, Any]
        The keyword arguments with default values filled in.

    Notes
    -----
    This function returns a copy of the defaults dictionary updated with the provided kwargs. Thus, if defaults contains
    a mutable object, all the returned dictionaries will share the same object, which may lead to unexpected behavior.
    To avoid this, pass a copy of the mutable object as a default value.
    """
    defaults = defaults.copy()
    defaults.update(kwargs)
    return defaults

def check_kwargs(function_name, kwargs, key_type: dict[str, type | Validator], defaults=None):
    """
    Check the types of keyword arguments and fill in default values.

    This function checks both the provided kwargs and the defaults against the expected types. If a keyword
    argument is missing, it is filled in with the default value. If a keyword argument is provided that is not
    in the key_type dictionary, a TypeError is raised. If a keyword argument has an incorrect type, a TypeError is raised.
    If a Validator raises a ValidatorError, it is caught and re-raised as a ValueError with additional context.

    Parameters
    ----------
    function_name: str
        The name of the function for error messages.
    kwargs: dict[str, Any]
        The keyword arguments to check.
    key_type: dict[str, type | Validator]
        A dictionary mapping keyword argument names to their expected types or Validator instances.
    defaults: dict[str, Any], optional
        Default values for keyword arguments.

    Returns
    -------
    dict[str, Any]
        The keyword arguments with default values filled in.

    Raises
    ------
    TypeError
        If a keyword argument has an incorrect type or is unexpected.
    ValueError
        If a Validator raises a ValidatorError.

    Notes
    -----
    This function returns a copy of the defaults dictionary updated with the provided kwargs. Thus, if defaults contains
    a mutable object, all the returned dictionaries will share the same object, which may lead to unexpected behavior.
    To avoid this, pass a copy of the mutable object as a default value.
    """
    def check(kwargs, key_type, defaults):
        default_str = "default value of " if defaults else ""

        for key, val in kwargs.items():
            if key in key_type:
                if isinstance(key_type[key], Validator):
                    try:
                        key_type[key](val, key)
                    except ValidatorError as e:
                        msg = f"Validation failed for {default_str}kwarg '{key}' of {function_name}"
                        raise ValueError(msg) from e
                elif isinstance(key_type[key], type):
                    if not isinstance(val, key_type[key]):
                        msg = (f"Expected type {key_type[key].__name__} for {default_str}kwarg '{key}' of {function_name},"
                               f" got {type(val).__name__}")
                        raise TypeError(msg)
                else:
                    msg = f"Invalid type specification for kwarg '{key}' of {function_name}"
                    raise TypeError(msg)
            else:
                msg = f"{function_name} got an unexpected {default_str[:-3]}keyword argument '{key}'"
                raise TypeError(msg)

    check(kwargs, key_type, defaults=False)
    if defaults is not None:
        check(defaults, key_type, defaults=True)
    else:
        defaults = {}
    return default_kwargs(kwargs, defaults)
