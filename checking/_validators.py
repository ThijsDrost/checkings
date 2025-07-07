import inspect

from ._base_checker import BaseChecker
from ._no_val import NoValue


class _DirectCallMeta(type):
    def __new__(cls, name, bases, dct):
        new_class = super().__new__(cls, name, bases, dct)
        _attributes = [a for a in dir(new_class) if not a.startswith('_') and callable(getattr(new_class, a))]
        for a in _attributes:
            docs = getattr(new_class, a).__doc__
            setattr(new_class, a, _DirectCallMeta._combine_call(getattr(new_class, a)))
            func = getattr(new_class, a)

            if docs is None:
                print(a)
                docs = ''

            func.__doc__ = (docs +
                            f'\n'
                            f'Notes\n'
                            f'-----\n'
                            f'This function can be called directly by combining the parameters of the function and the call to '
                            f'the validator. It assumes that both are called directly when either the number of arguments is '
                            f'greater than the number of parameters for the function or when the `name` and/or `value` keyword '
                            f'argument are used.')

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
        parameters = inspect.signature(func).parameters
        num_parameters = len(parameters)
        parameters_names = list(parameters.keys())
        if ('name' in parameters_names) or ('value' in parameters_names):
            raise ValueError(f'Cannot have `name` or `value` as a parameter name for {func.__name__},'
                             f' since these are used for the call method.')

        def call(*args, **kwargs):
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

            if call_together:
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
