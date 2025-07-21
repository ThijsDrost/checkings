import inspect

from ._base_checker import BaseChecker
from ._no_val import NoValue


class _DirectCallMeta(type):
    def __new__(cls, name, bases, dct):
        new_class = super().__new__(cls, name, bases, dct)
        _attributes = [a for a in dir(new_class) if not a.startswith('_') and callable(getattr(new_class, a))]
        for a in _attributes:
            docs = inspect.cleandoc(getattr(new_class, a).__doc__)
            setattr(new_class, a, _DirectCallMeta._combine_call(getattr(new_class, a)))
            func = getattr(new_class, a)

            if docs is None:
                docs = ''

            def add_to_docs(docs, name, value):
                parameters_start = False
                split_docs = docs.split('\n')
                for index, line in enumerate(split_docs):
                    if line.startswith(name):
                        parameters_start = True
                    if parameters_start and split_docs[index-1] != name and line.startswith("---"):
                        index -= 1
                        break
                else:
                    index += 1

                if parameters_start:
                    before = '\n'.join(split_docs[:index])

                    if index == len(split_docs):
                        after = ''
                    else:
                        after = '\n'.join(split_docs[index:])
                    new_docs = before + "\n" + inspect.cleandoc(value) + "\n" + after

                else:
                    new_docs = docs + f'\n{name}\n-----\n{inspect.cleandoc(value)}\n'
                return new_docs

            param_docs = \
            """
            value: Optional[Any]
                The value to be validated, used for the direct call to the validator
            name: Optional[str]
                The name of the parameter to be validated, used for the direct call to the validator. This is used to provide a more informative error message.
            """

            notes = \
            """
            This function can be called directly by combining the parameters of the function and the call to 
            the validator. It assumes that both are called directly when either the number of arguments is 
            greater than the number of parameters for the function or when the `name` and/or `value` keyword 
            argument are used.
            """
            docs = add_to_docs(docs, 'Parameters', param_docs)
            docs = add_to_docs(docs, 'Notes', notes)

            func.__doc__ = docs

        return new_class

    @staticmethod
    def _call_inside(func):
        def call(*args, **kwargs):
            if args or kwargs:
                return func()(*args, **kwargs)
            return func()
        return call

    @staticmethod
    def _combine_call(func):
        parameters = [p for p in inspect.signature(func).parameters.values()]

        min_args = 0
        min_kwargs = 0
        argkwargs = []
        num_parameters = len(parameters)
        for p in parameters:
            if p.kind == p.VAR_POSITIONAL:
                raise ValueError(f'Cannot use `*args` for {func.__name__}, since the number of parameters must be fixed.')
            if p.kind == p.VAR_KEYWORD:
                num_parameters -= 1
                continue
            if p.default is not p.empty:
                continue

            if p.kind == p.POSITIONAL_ONLY:
                min_args += 1
            elif p.kind == p.KEYWORD_ONLY:
                min_kwargs += 1
            elif p.kind == p.POSITIONAL_OR_KEYWORD:
                argkwargs += [p.name]

        parameters_names = tuple(par.name for par in parameters)
        if ('name' in parameters_names) or ('value' in parameters_names):
            raise ValueError(f'Cannot have `name` or `value` as a parameter name for {func.__name__},'
                             f' since these are used for the call method.')

        def call(*args, **kwargs):
            nonlocal min_args, min_kwargs, argkwargs
            argkwargs = argkwargs.copy()

            call_together = False
            if (len(args) + len(kwargs)) > num_parameters:
                call_together = True

            num = 2
            call_kwargs = {}
            for key in ['value', 'name']:
                if key in kwargs:
                    call_kwargs[key] = kwargs[key]
                    del kwargs[key]
                    num -= 1
                    call_together = True

            for key in kwargs:
                if key in argkwargs:
                    argkwargs.pop(argkwargs.index(key))

            if call_together:
                if len(args) < num + min_args + len(argkwargs):
                    num_missing = num + min_args + len(argkwargs) - len(args)
                    raise TypeError(
                        f'{func.__name__}() missing {num_missing} positional argument{"s" if num_missing > 1 else ""} (it needs {min_args + len(argkwargs)} itself, plus {num} for the direct call).')

                return func(*args[:-num], **kwargs)(*args[-num:], **call_kwargs)
            return func(*args, **kwargs)
        return call


class Validator(BaseChecker, metaclass=_DirectCallMeta):
    def __call__(self, value, name):
        self._update()
        if value is NoValue or ((value is None) and self._replace_none):
            default = self._get_default()
            if default is not NoValue:
                value = default
                name = f'`default of {name}`'
            else:
                raise ValueError(f'No value given and no default value for `{name}`')
        self._validate(value, name)
        return value
