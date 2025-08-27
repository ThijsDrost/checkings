import inspect
from typing import Callable

def strongly_typed(func: Callable, strict: bool = False) -> Callable:
    """
    A decorator to enforce type checking based on function annotations.

    If a parameter does not have a type annotation, it is not checked.

    Parameters
    ----------
    func : Callable
        The function to be decorated.
    strict : bool, optional
        If True, all parameters must have type annotations, by default False.

    Raises
    ------
    TypeError
        If an argument does not match its annotated type.
    ValueError
        If strict is True and a parameter lacks a type annotation for any parameter.
    """
    sig = inspect.signature(func)
    annotations = func.__annotations__

    if strict:
        # Ensure all parameters have type annotations
        for param in sig.parameters.values():
            if param.name not in annotations:
                msg = f"Parameter '{param.name}' lacks a type annotation."
                raise ValueError(msg)

    def wrapper(*args, **kwargs):
        bound_args = sig.bind(*args, **kwargs)
        for name, value in bound_args.arguments.items():
            if name in annotations:
                expected_type = annotations[name]
                if not isinstance(value, expected_type):
                    msg = f"Argument '{name}' must be of type {expected_type.__name__}, got {type(value).__name__}"
                    raise TypeError(msg)
        return func(*args, **kwargs)

    return wrapper