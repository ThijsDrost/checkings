from dataclasses import dataclass


@dataclass(frozen=True)
class NoVal:
    __module__ = 'General.checking'

    def __iter__(self):
        return self

    def __next__(self):
        raise StopIteration

    def __add__(self, other):
        return other

    def __radd__(self, other):
        return other

    def __sub__(self, other):
        return -other

    def __rsub__(self, other):
        return other

    def __bool__(self):
        return False

    def __eq__(self, other):
        return False

    def __ne__(self, other):
        return True

    def __repr__(self):
        return 'NoValue'

    def __str__(self):
        return 'NoValue'


NoValue = NoVal()
