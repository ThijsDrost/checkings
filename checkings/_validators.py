import inspect
from typing import ParamSpec, TypeVar

from ._base_checker import BaseChecker
from ._no_val import NoValue

P = ParamSpec('P')
T = TypeVar('T')


def _calc_new_signature(old_func):
    old_sig = inspect.signature(old_func)
    old_parameters = list(old_sig.parameters.values())

    for p in old_parameters:
        if p.kind == p.VAR_POSITIONAL:
            msg = f"Cannot use `*args` for {old_func.__name__}, since the number of parameters must be fixed."
            raise ValueError(msg)

    parameters_names = tuple(par.name for par in old_parameters)
    if ("name" in parameters_names) or ("value" in parameters_names):
        msg = (
            f"Cannot have `name` or `value` as a parameter name for {old_func.__name__},"
            f" since these are used for the call method.",
        )
        raise ValueError(msg)

    params = list(old_sig.parameters.values())
    for i, param in enumerate(params):
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            break
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            break
    else:
        i = len(params)

    name_param = inspect.Parameter("name", inspect.Parameter.KEYWORD_ONLY, default=None)
    value_param = inspect.Parameter("value", inspect.Parameter.KEYWORD_ONLY, default=None)
    params.insert(i, name_param)
    params.insert(i, value_param)
    return old_sig.replace(parameters=params)


class _DirectCallMeta(type):
    """
    Metaclass that allows the Validator generator functions to be called directly with two extra parameters to directly
    do the validation without having to create a Validator instance.
    """
    def __new__(cls, name, bases, dct):
        new_class = super().__new__(cls, name, bases, dct)
        _attributes = [a for a in dir(new_class) if not a.startswith("_") and callable(getattr(new_class, a))]
        for a in _attributes:
            docs = inspect.cleandoc(getattr(new_class, a).__doc__)
            new_sig = _calc_new_signature(getattr(new_class, a))

            setattr(new_class, a, _DirectCallMeta._combine_call(getattr(new_class, a), new_sig))

            if docs is None:
                docs = ""

            def add_to_docs(docs, name, value):
                parameters_start = False
                split_docs = docs.split("\n")

                for index, line in enumerate(split_docs):
                    if line.startswith(name):
                        parameters_start = True
                    if parameters_start and split_docs[index - 1] != name and line.startswith("---"):
                        index -= 1
                        break
                else:
                    index += 1

                if parameters_start:
                    before = "\n".join(split_docs[:index])
                    after = "" if index == len(split_docs) else "\n".join(split_docs[index:])
                    new_docs = before + "\n" + inspect.cleandoc(value) + "\n" + after

                else:
                    new_docs = docs + f"\n{name}\n-----\n{inspect.cleandoc(value)}\n"
                return new_docs

            param_docs = """
            value: Optional[Any]
                The value to be validated, used for the direct call to the validator
            name: Optional[str]
                The name of the parameter to be validated, used for the direct call to the validator. This is used to 
                provide a more informative error message.
            """

            notes = """
            This function can be called directly by combining the parameters of the function and the call to 
            the validator. It assumes that both are called directly when either the number of arguments is 
            greater than the number of parameters for the function or when the `name` and/or `value` keyword 
            argument are used.
            """
            docs = add_to_docs(docs, "Parameters", param_docs)
            docs = add_to_docs(docs, "Notes", notes)

            getattr(new_class, a).__doc__ = docs

        return new_class

    @staticmethod
    def _combine_call(func, new_signature):
        """
        Combines the parameters of the function with the call to the validator, so that it can be called directly

        Parameters
        ----------
        func: callable
            The validator function

        Returns
        -------
            callable | None
        """
        def call(*args, **kwargs):
            nonlocal new_signature
            bound = new_signature.bind(*args, **kwargs)
            bound.apply_defaults()

            call_together = False
            if bound.arguments["name"] is not None:
                if bound.arguments["value"] is None:
                    msg = f"When calling {func.__name__}() with a name, a value must also be provided."
                    raise TypeError(msg)
                else:
                    call_together = True
            if bound.arguments["value"] is not None:
                if bound.arguments["name"] is None:
                    msg = f"When calling {func.__name__}() with a value, a name must also be provided."
                    raise TypeError(msg)

            if call_together:
                parameters = bound
                args = parameters.args
                kwargs = parameters.kwargs.copy()
                for name in ("value", "name"):
                    if name in kwargs:
                        kwargs.pop(name)
                    else:
                        args = args[:-1]
                return func(*args, **kwargs)(bound.arguments["value"], bound.arguments["name"])
            return func(*args, **kwargs)
        return call


class Validator(BaseChecker, metaclass=_DirectCallMeta):
    def __call__(self, value: T, name: str) -> T:
        self._update()
        if value is NoValue or ((value is None) and self._replace_none):
            default = self._get_default()
            if default is not NoValue:
                value = default
                name = f"`default of {name}`"
            else:
                msg = f"No value given and no default value for `{name}`"
                raise ValueError(msg)
        self._validate(value, name)
        return value
