from __future__ import annotations

from ._no_val import NoValue
from ._base_checker import BaseChecker


class Descriptor(BaseChecker):
    def __set_name__(self, owner, name):
        # Checking is done here, since this is called when all the descriptors are added together. This results in a
        # slightly strange error message, which states that the error was raised while calling __set_name__.

        # Set the name to default, so that the error message is more informative if the default value is not valid.
        if self._default is not NoValue:
            self._validate(self._default, f'Default value for `{name}`')
        self._update()

        self.owner = owner
        self.name = name
        self.private_name = f'_{name}'

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        if self._get_default() is not NoValue:
            return getattr(instance, self.private_name, self._default)
        return getattr(instance, self.private_name)

    def __set__(self, instance, value):
        if instance is None:
            return self

        if value is self:
            if self._default is not NoValue:
                value = self._default
            else:
                return self

        if value is NoValue or ((value is None) and self._replace_none):
            value = self._get_default()
            if value is NoValue:
                raise ValueError(f'No value given and no default value for `{self.name}`')
            self._validate(value, f'default value for `{self.name}`')
        else:
            if self._converter is not NoValue:
                value = self._converter(value)
            self._validate(value, self.name)
        setattr(instance, self.private_name, value)
