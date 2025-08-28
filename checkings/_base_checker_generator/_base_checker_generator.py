from __future__ import annotations

import inspect
import itertools
import os
import pathlib
import shutil
from collections.abc import Callable, Iterable, Sequence
from dataclasses import KW_ONLY, dataclass
import numpy as np

from checkings._no_val import NoValue

VALIDATOR_FUNCS = {}


@dataclass
class Parameter:
    name: str | None
    param_name: str
    type: str
    description: str
    _ = KW_ONLY
    default: object = NoValue
    call_value: str = NoValue

    def __post_init__(self):
        if self.call_value is NoValue:
            self.call_value = self.name

    def copy(self):
        return Parameter(
            self.name,
            self.param_name,
            self.type,
            self.description,
            default=self.default,
            call_value=self.call_value,
        )


@dataclass
class Validator:
    name: str
    param_name: str
    function: str
    _ = KW_ONLY
    docstring_description: str = None
    parameters: Sequence[Parameter] = None
    add_func: str | Callable = None

    def __post_init__(self):
        if self.docstring_description is None:
            self.docstring_description = self.name.replace("_", " ").lower()
        if isinstance(self.add_func, Callable):
            self.add_func = "\n".join(inspect.getsourcelines(self.add_func)[0])

    def get_docstring_description(self):
        description = self.docstring_description
        if self.parameters is not None:
            for index in range(len(self.parameters)):
                if self.parameters[index].name is None:
                    continue
                description = description.replace(
                    f"{{{index}}}",
                    self.parameters[index].name,
                )
        return description

    @staticmethod
    def combine(validators: Sequence[Validator]) -> Sequence[Validator]:
        for index in range(len(validators)):
            for index_p in range(len(validators[index].parameters)):
                num = 1
                for index2 in range(len(validators[index + 1 :])):
                    for index_p2 in range(len(validators[index2].parameters)):
                        if validators[index].parameters[index_p].name == validators[index2].parameters[index_p2].name:
                            if (
                                validators[index].parameters[index_p].name[-1].isdigit()
                                and validators[index2].parameters[index_p2].name[-1].isdigit()
                            ):
                                continue
                            if (
                                validators[index].parameters[index_p].name[-1] != "1"
                                and validators[index].parameters[index_p].name[-1].isdigit()
                            ) or validators[index2].parameters[index_p2].name[-1].isdigit():
                                raise ValueError("Something went wrong")

                            if num == 1:
                                validators[index].parameters[index_p].name += str(num)
                                num += 1
                            validators[index].parameters[index_p2].name += str(num)
                            num += 1
        return validators

    def copy(self):
        if isinstance(self.parameters, Sequence):
            parameters = [param.copy() for param in self.parameters]
        else:
            parameters = self.parameters
        return Validator(
            self.name,
            self.param_name,
            self.function,
            self.docstring_description,
            parameters,
            self.add_func,
        )

    def fill_parameter_in_function(
        self,
        param_name: str,
        value: str,
        name: str | None = None,
    ) -> Validator:
        if name is None:
            name = value
        if self.add_func is None:
            msg = "No add_func to fill in"
            raise ValueError(msg)
        if param_name not in self.add_func:
            msg = f"Parameter {param_name} not found in add_func"
            raise ValueError(msg)
        params = [param.copy() for param in self.parameters]
        found = False
        docstring_description = self.docstring_description
        for index, param in enumerate(params):
            if param.param_name == param_name:
                found = True
                param.name = None
                param.call_value = value
                docstring_description = docstring_description.replace(
                    f"{{{index}}}",
                    name,
                )
                params[index] = param
        if not found:
            msg = f"Parameter {param_name} not found in parameters"
            raise ValueError(msg)
        add_func = "\n".join(
            (line.replace(param_name, "") if "def" in line else line.replace(param_name, value))
            for line in self.add_func.split("\n")
        )
        return Validator(
            self.name,
            self.param_name,
            self.function,
            docstring_description,
            params,
            add_func,
        )


def make_checker(validators: Sequence[Validator], prefix=""):
    func_name = "_".join([validator.name for validator in validators if validator.name])

    def param_str(param: Parameter):
        if param.default is NoValue:
            return f"{param.name}: {param.type}"
        return f"{param.name}: {param.type} = {param.default}"

    param_validators = [validator for validator in validators if validator.parameters is not None]
    parameters = [param for validator in param_validators for param in validator.parameters]
    parameters.sort(key=lambda x: x.default is not NoValue)

    parameter_string = ""
    found_kwargs = False
    for param in parameters:
        if param.name is None:
            continue
        if param.default is NoValue:
            parameter_string += f", {param.name}: {param.type}"
        else:
            if not found_kwargs:
                parameter_string += ", *"
                found_kwargs = True
            parameter_string += f", {param.name}: {param.type} = {param.default}"

    kwargs = (", default = NoValue, default_factory = NoValue, number_line = NoValue, literals = NoValue, "
              "types = NoValue, converter = NoValue, validators = NoValue, replace_none = NoValue")
    if not found_kwargs:
        parameter_string += ", *"
    parameter_string += kwargs


    description_validators = [validator for validator in validators if validator.param_name != "default"]
    description = "Generate checker to check if the value "
    if len(description_validators) == 0:
        description = ""
    elif len(description_validators) == 1:
        description += description_validators[0].get_docstring_description()
    elif len(description_validators) == 2:
        description += (
            f"{description_validators[0].get_docstring_description()} "
            f"and {description_validators[1].get_docstring_description()}"
        )
    else:
        description += ", and ".join(
            [validator.get_docstring_description() for validator in description_validators],
        )

    if "default" in [validator.param_name for validator in validators]:
        if len(description_validators) == 0:
            description = "Set default value to `default`"
        else:
            description += " with default value `default`"

    def param_description(param: Parameter):
        first_line = f"\t\t{param.name}: {param.type}"
        if param.default is not NoValue:
            first_line += f" = {param.default}"
        first_line += "\n\t\t\t"
        first_line += param.description
        return first_line

    parameter_description = "\n".join(
        [param_description(param) for param in parameters if param.name is not None],
    )

    def call_str(validator: Validator):
        def param_string(param: Parameter):
            return f"{param.param_name}={param.call_value}"

        name = "cls("

        if validator.param_name in ("types", "literals", "default"):
            name += f"{validator.param_name}={validator.function}"
        else:
            parameters = validator.parameters or []
            name += (
                f"{validator.param_name}={validator.function}("
                f"{', '.join([param_string(param) for param in parameters])})"
            )

        name += "," if name[-1] != "(" else ""
        return name + ")"

    call_string = (" + ".join([call_str(validator) for validator in validators])
                   + "+ cls(default = default, default_factory = default_factory, number_line = number_line,"
                     " literals = literals, types = types, converter = converter, validators = validators,"
                     " replace_none = replace_none)")

    add_func = ""

    parameters_header = ""
    if parameter_description:
        parameters_header = "\n\n\t\tParameters\n\t\t----------\n"

    func = f""" 
    @classmethod
    def {prefix}{func_name}(cls{parameter_string}) -> Self:
        \"\"\"
        {description}.{parameters_header}{parameter_description}
        
        Other Parameters
        -------
        default: object
            The default value of the attribute. If default is mutable, it must have a `copy` method. An object is
            considered mutable if it does not have a `__hash__` method.
        default_factory: Callable[[], object]
            A function that returns the default value of the attribute.
        number_line: NumberLine
            A NumberLine instance which the attribute must lie on.
        literals: tuple[object, ...] | object
            The literals that the attribute must be one of
        types: tuple[type, ...] | type
            The types that the attribute must be one of
        converter: Callable[[object], object]
            A function that converts the attribute to a new value
        validators: tuple[Callable[[object], Exception | None], ...] | Callable[[object], Exception | None]
            A tuple of functions that check if the attribute is valid. The value is assumed correct when the function
            neither returns nor raises and exception.
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
        \"\"\"{add_func}
        return {call_string}
    """.replace("\t", "    ")

    for validator in validators:
        if isinstance(validator.add_func, str):
            val, _ = validator.add_func.split("(", 1)
            val = val.removeprefix("def ")
            if val not in VALIDATOR_FUNCS:
                VALIDATOR_FUNCS[val] = validator.add_func
    return func


def capital_to_underscore(name):
    return "".join(
        [(x if x.islower() else "_" + x.lower()) for x in name],
    ).removeprefix("_")


def a_or_an(word):
    if word[0].lower() in "aeiouh":
        return "an"
    return "a"


# Types
_integer_val = Validator(
    "integer",
    "types",
    "(int,)",
    docstring_description="is an instance of an integer",
)
_number_val = Validator(
    "number",
    "types",
    "(int, float)",
    docstring_description="is an instance of a number",
)
_string_val = Validator(
    "string",
    "types",
    "(str,)",
    docstring_description="is an instance of a string",
)
_dictionary_val = Validator(
    "dictionary",
    "types",
    "(dict,)",
    docstring_description="is an instance of a dictionary",
)
types = {
    name: Validator(
        name.lower(),
        "types",
        f"({name},)",
        docstring_description=f"is an instance of {a_or_an(name)} {name}",
    )
    for name in ["int", "float", "str", "tuple", "dict", "list", "slice"]
}
types = types | {
    "integer": _integer_val,
    "number": _number_val,
    "string": _string_val,
    "dictionary": _dictionary_val,
}
numbers = {name: types[name] for name in ["integer", "number", "float", "int"]}


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


contains_type = Validator(
    "of_type",
    "validators",
    "check_inside_type",
    docstring_description="contains values of type `{0}`",
    parameters=[Parameter("of_type", "type_", "type", "The type to check against")],
    add_func=check_inside_type,
)

# ABCs
abc_names = [
    "Container",
    "Hashable",
    "Iterable",
    "Reversible",
    "Generator",
    "Sized",
    "Callable",
    "Collection",
    "Sequence",
    "MutableSequence",
    "ByteString",
    "Set",
    "MutableSet",
    "Mapping",
    "MutableMapping",
    "MappingView",
    "ItemsView",
    "KeysView",
    "ValuesView",
    "Awaitable",
    "AsyncIterable",
    "AsyncIterator",
    "Coroutine",
    "AsyncGenerator",
    "Buffer",
]
abcs = {
    name: Validator(
        capital_to_underscore(name),
        "types",
        f"(collections.abc.{name},)",
        docstring_description=f"is an instance of {a_or_an(name)} {name} (:external+python:py:class:`collections.abc.{name}`)",
    )
    for name in abc_names
}

# Has
def check_has_attr(attr):
    def checker(value):
        if not hasattr(value, attr):
            msg = f"Value must have attribute {attr}"
            return ValueError(msg)
        return None
    return checker
has_attr = Validator(
    "has_attr",
    "validators",
    "check_has_attr",
    docstring_description="has attribute `{0}`",
    parameters=[Parameter("attr", "attr", "str", "The attribute to check for")],
    add_func=check_has_attr,
)

def check_has_method(method):
    def checker(value):
        if not hasattr(value, method) or not callable(getattr(value, method)):
            msg = f"Value must have method {method}"
            return ValueError(msg)
        return None
    return checker
has_method = Validator(
    "has_method",
    "validators",
    "check_has_method",
    docstring_description="has method `{0}`",
    parameters=[Parameter("method", "method", "str", "The method to check for")],
    add_func=check_has_method,
)
def check_has_property(property):
    def checker(value):
        if not hasattr(value, property) or not isinstance(getattr(value, property), property):
            msg = f"Value must have property {property}"
            return ValueError(msg)
        return None
    return checker
has_property = Validator(
    "has_property",
    "validators",
    "check_has_property",
    docstring_description="has property `{0}`",
    parameters=[Parameter("property", "property", "str", "The property to check for")],
    add_func=check_has_property
)

# Numbers
larger_values = [
    Validator(
        f"{name}_than",
        "number_line",
        "NumberLine.bigger_than_float",
        docstring_description=f"is {name} than `{{{0}}}`",
        parameters=[
            Parameter("min_val", "value", "float", "The minimum value"),
            Parameter(
                "inclusive",
                "inclusive",
                "bool",
                "Whether the value is allowed to be equal to the minimum value",
            ),
        ],
    )
    for name in ["greater", "larger", "bigger"]
]  # 'more'
less_values = [
    Validator(
        f"{name}_than",
        "number_line",
        "NumberLine.smaller_than_float",
        docstring_description=f"is {name} than `{{{0}}}`",
        parameters=[
            Parameter("max_val", "value", "float", "The maximum value"),
            Parameter(
                "inclusive",
                "inclusive",
                "bool",
                "Whether the value is allowed to be equal to the maximum value",
            ),
        ],
    )
    for name in ["smaller", "less"]
]  # 'fewer', 'lower'
positive = Validator(
    "positive",
    "number_line",
    "NumberLine.positive",
    parameters=[
        Parameter(
            "include_zero",
            "include_zero",
            "bool",
            "Whether the value is allowed to be equal to zero",
        ),
    ],
)
negative = Validator(
    "negative",
    "number_line",
    "NumberLine.negative",
    parameters=[
        Parameter(
            "include_zero",
            "include_zero",
            "bool",
            "Whether the value is allowed to be equal to zero",
        ),
    ],
)
in_range = Validator(
    "in_range",
    "number_line",
    "NumberLine.between_float",
    docstring_description="is between `{0}` and `{1}`",
    parameters=[
        Parameter("start_val", "start", "float", "The start of the included range"),
        Parameter("end_val", "end", "float", "The end of the included range"),
        Parameter(
            "start_inclusive",
            "start_inclusive",
            "bool",
            "Whether the lower bound is included in the range",
            True,
        ),
        Parameter(
            "end_inclusive",
            "end_inclusive",
            "bool",
            "Whether the upper bound is included in the range",
            True,
        ),
    ],
)
between = Validator(
    "between",
    "number_line",
    "NumberLine.between_float",
    docstring_description="is between `{0}` and `{1}`",
    parameters=[
        Parameter("start_val", "start", "float", "The start of the included range"),
        Parameter("end_val", "end", "float", "The end of the included range"),
        Parameter(
            "start_inclusive",
            "start_inclusive",
            "bool",
            "Whether the lower bound is included in the range",
            False,
        ),
        Parameter(
            "end_inclusive",
            "end_inclusive",
            "bool",
            "Whether the upper bound is included in the range",
            False,
        ),
    ],
)

non_zero = Validator(
    "non_zero",
    "number_line",
    "non_zero",
    docstring_description="is not zero",
    add_func="def non_zero():\n\treturn NumberLine.exclude_from_floats(0, 0, False, False)",
)

def is_even():
    def checker(value):
        if value % 2 != 0:
            msg = "Value must be even"
            return ValueError(msg)
        return None
    return checker
even = Validator(
    "even",
    "validators",
    "is_even",
    docstring_description="is even",
    add_func=is_even,
)

def is_odd():
    def checker(value):
        if value % 2 == 0:
            msg = "Value must be odd"
            return ValueError(msg)
        return None
    return checker
odd = Validator(
    "odd",
    "validators",
    "is_odd",
    docstring_description="is odd",
    add_func=is_odd,
)

# Strings
def check_starts_with(start):
    def checker(value):
        if not value.startswith(start):
            msg = f"Value must start with {start}"
            return ValueError(msg)
        return None
    return checker
starts_with = Validator(
    "starts_with",
    "validators",
    "check_starts_with",
    docstring_description="starts with `{0}`",
    parameters=[Parameter("start", "start", "str", "The correct start")],
    add_func=check_starts_with,
)

def check_ends_with(end):
    def checker(value):
        if not value.endswith(end):
            msg = f"Value must end with {end}"
            return ValueError(msg)
        return None
    return checker
ends_with = Validator(
    "ends_with",
    "validators",
    "check_ends_with",
    docstring_description="ends in `{0}`",
    parameters=[Parameter("end", "end", "str", "The correct end")],
    add_func=check_ends_with,
)

# NumPy
numpy_array = Validator(
    "numpy_array",
    "types",
    "(np.ndarray,)",
    docstring_description="is an instance of a numpy array",
)

def check_numpy_dims(dims):
    def checker(value):
        if value.ndim != dims:
            msg = f"Value must have {dims} dimensions, not {value.ndim}"
            return ValueError(msg)
        return None
    return checker
numpy_dims = Validator(
    "numpy_dims",
    "validators",
    "check_numpy_dims",
    docstring_description="has `{0}` dimensions",
    parameters=[Parameter("dims", "dims", "int", "The correct number of dimensions")],
    add_func=check_numpy_dims,
)

def check_numpy_shape(shape):
    def checker(value):
        if value.shape != shape:
            msg = f"Value must have shape {shape}, not {value.shape}"
            return ValueError(msg)
        return None
    return checker
numpy_shape = Validator(
    "numpy_shape",
    "validators",
    "check_numpy_shape",
    docstring_description="has shape `{0}`",
    parameters=[Parameter("shape", "shape", "tuple[int]", "The correct shape")],
    add_func=check_numpy_shape,
)

def check_numpy_dtype(dtype):
    def checker(value):
        if value.dtype != dtype:
            msg = f"Value must have dtype {dtype}, not {value.dtype}"
            return ValueError(msg)
        return None
    return checker
numpy_dtype = Validator(
    "numpy_dtype",
    "validators",
    "check_numpy_dtype",
    docstring_description="has dtype `{0}`",
    parameters=[Parameter("dtype", "dtype", "type", "The correct dtype")],
    add_func=check_numpy_dtype,
)

def check_numpy_subdtype(subdtype):
    def checker(value):
        if not np.issubdtype(value.dtype, subdtype):
            msg = f"Value must have subdtype of {subdtype}, not {value.dtype}"
            return ValueError(msg)
        return None
    return checker
numpy_subdtype = Validator(
    "numpy_subdtype",
    "validators",
    "check_numpy_subdtype",
    docstring_description="has subdtype `{0}`",
    parameters=[Parameter("subdtype", "subdtype", "type", "The correct subdtype")],
    add_func=check_numpy_subdtype,
)

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
numpy_dim_shape_dtype = Validator(
    "numpy",
    "validators",
    "check_numpy",
    docstring_description="has `{0}` dimensions, shape `{1}` and dtype `{2}`",
    parameters=[
        Parameter("dims", "dims", "int", "The correct number of dimensions"),
        Parameter("shape", "shape", "int | tuple[int]", "The correct shape"),
        Parameter("dtype", "dtype", "type", "The correct dtype"),
    ],
    add_func=check_numpy,
)


# Paths
def check_path():
    def checker(value):
        if not os.path.exists(value):
            msg = f"Path `{value}` does not exist"
            return ValueError(msg)
        return None
    return checker
path_val = Validator(
    "path",
    "validators",
    "check_path",
    docstring_description="is a valid path",
    add_func=check_path,
)

def check_dir():
    def checker(value):
        if not os.path.isdir(value):
            msg = f"Path `{value}` is not a directory"
            return ValueError(msg)
        return None
    return checker
dir_val = Validator(
    "dir",
    "validators",
    "check_dir",
    docstring_description="is a valid directory",
    add_func=check_dir,
)

def check_file():
    def checker(value):
        if not os.path.isfile(value):
            msg = f"Path `{value}` is not a file"
            return ValueError(msg)
        return None
    return checker
file_val = Validator(
    "file",
    "validators",
    "check_file",
    docstring_description="is a valid file",
    add_func=check_file,
)


# Miscellaneous
def check_len(length):
    def checker(value):
        if len(value) != length:
            msg = f"Length must be {length}, not {len(value)}"
            return ValueError(msg)
        return None
    return checker
length = Validator(
    "length",
    "validators",
    "check_len",
    docstring_description="of length `{0}`",
    parameters=[Parameter("length", "length", "int", "The correct length")],
    add_func=check_len,
)

def check_lens(min_length, max_length):
    def checker(value):
        if not min_length <= len(value) <= max_length:
            msg = f"Length must be between {min_length} and {max_length}, not {len(value)}"
            return ValueError(msg)
        return None
    return checker
lengths = Validator(
    "lengths",
    "validators",
    "check_lens",
    docstring_description="of length between `{0}` and `{1}` (both inclusive)",
    parameters=[
        Parameter("min_length", "min_length", "int", "The minimum length"),
        Parameter("max_length", "max_length", "int", "The maximum length"),
    ],
    add_func=check_lens,
)

def check_contains(contains):
    def checker(value):
        if contains not in value:
            msg = f"Value must contain {contains}"
            return ValueError(msg)
        return None
    return checker
contains = Validator(
    "contains",
    "validators",
    "check_contains",
    docstring_description="contains `{0}`",
    parameters=[Parameter("contains", "contains", "str", "The value to contain")],
    add_func=check_contains,
)
# literals = Validator(
#     "literals",
#     "literals",
#     "literals",
#     docstring_description="is one of `{0}`",
#     parameters=[
#         Parameter(
#             "literals",
#             "literals",
#             "collections.abc.Sequence",
#             "The literals to check against",
#         ),
#     ],
# )


def check_sorted():
    def checker(value):
        def value_error(wrong):
            return ValueError(
                f"Value must be sorted, goes wrong at index{'es' if len(wrong) > 1 else ''} {wrong}",
            )

        if HAS_NUMPY:  # noqa: F821
            if isinstance(value, np.ndarray):  # noqa: F821
                values = value[:-1] <= value[1:]
                if not np.all(values):  # noqa: F821
                    wrong = np.argwhere(~values)[:, 0]  # noqa: F821
                    return value_error(wrong)
        elif all(value[i] <= value[i + 1] for i in range(len(value) - 1)):
            wrong = [i for i in range(len(value) - 1) if value[i] > value[i + 1]]
            return value_error(wrong)
        return None

    return checker


sorted_val = Validator(
    "sorted",
    "validators",
    "check_sorted",
    docstring_description="is sorted",
    add_func=check_sorted,
)
# default = Validator(
#     "default",
#     "default",
#     "default",
#     parameters=[Parameter("default", "default", "object", "The default value")],
# )


def make_combinations(file_handle, *args: Iterable[Validator]):
    for comb in itertools.product(*args):
        file_handle.write(make_checker(comb))


def write_validators(file_handle, validators: Iterable[Validator], prefix=""):
    for validator in validators:
        file_handle.write(make_checker([validator], prefix=prefix))


def write_validator_name(file_handle, validators: Iterable[Validator], name: str):
    validators = [validator.copy() for validator in validators]
    validators[0].name = name
    for i in range(1, len(validators)):
        validators[i].name = ""
    file_handle.write(make_checker(validators))


def write_funcs(file_handle):
    def remove_indentation(func):
        lines = [line for line in func.split("\n") if line]
        indents = lines[0].find("def ")
        return "\n".join(line[indents:] for line in lines)

    file_handle.write("\n")
    for func in VALIDATOR_FUNCS.values():
        if isinstance(func, str):
            # Remove '# noqa: F821' from functions.

            # but the checks are wanted in the generated file
            new_func = func.replace("# noqa: F821", "")
            # Replace tabs with spaces
            new_func = new_func.replace("\t", " " * 4)
            file_handle.write(remove_indentation(new_func))
            file_handle.write("\n\n")


path = pathlib.Path(os.path.realpath(__file__)).parent
stub_loc = os.path.join(path, "_base_checker_stub.py")
out_loc = os.path.join(path.parent, "_base_checker.py")
stub_str = shutil.copy(stub_loc, out_loc)
with open(out_loc, "a") as file:
    # Default
    # write_validators(file, [default])
    # make_combinations(file, [default], types.values())

    # Numeric
    make_combinations(
        file,
        numbers.values(),
        larger_values + less_values + [in_range, between],
    )
    make_combinations(file, [positive, negative], numbers.values())
    for validator in larger_values + less_values + [in_range, between, positive, negative]:
        write_validator_name(file, [numbers["number"], validator], name=validator.name)
    for validator in [even, odd]:
        write_validator_name(file, [numbers["integer"], validator], name=validator.name)

    # Types
    write_validators(file, [contains, non_zero, length, lengths, sorted_val])
    write_validators(file, types.values(), prefix="is_")
    write_validators(file, abcs.values(), prefix="is_")
    for container in [types["list"], types["tuple"], abcs["Sequence"]]:
        write_validator_name(
            file,
            [container, contains_type],
            name=f"{container.name}_of",
        )
        for type_ in types.values():
            name = type_.name
            type_name = type_.function
            replace_name = type_name.replace("(", "").replace(")", "").replace(", ", "` or `").replace(",", "")

            validator = contains_type.fill_parameter_in_function(
                "type_",
                type_name,
                replace_name,
            )
            write_validator_name(
                file,
                [container, validator],
                name=f"{container.name}_of_{name}",
            )

    # Has
    write_validators(file, [has_attr, has_method, has_property])

    # Strings
    write_validator_name(file, [types["str"], starts_with], name="starts_with")
    write_validator_name(file, [types["str"], ends_with], name="ends_with")

    # Numpy
    for name, validator in (
        ("numpy_dim", numpy_dims),
        ("numpy_shape", numpy_shape),
        ("numpy_dtype", numpy_dtype),
        ("numpy_subdtype", numpy_subdtype),
    ):
        write_validator_name(file, [numpy_array, validator], name=name)

    # Sequence length
    for validator in [abcs["Sequence"], types["list"], types["tuple"], numpy_array]:
        write_validator_name(
            file,
            [validator, length],
            name=f"{validator.name}_of_length",
        )
        write_validator_name(
            file,
            [validator, lengths],
            name=f"{validator.name}_between_lengths",
        )

    # Paths
    write_validators(file, [path_val, dir_val, file_val], prefix="is_")

    # Numpy
    write_validator_name(file, [numpy_array, numpy_dim_shape_dtype], name="numpy")

    # Miscellaneous
    file.write("\n\n")
    validator_funcs = [
        contains_type,
        non_zero,
        even,
        odd,
        starts_with,
        ends_with,
        numpy_dims,
        numpy_shape,
        numpy_dtype,
        numpy_dim_shape_dtype,
        path_val,
        dir_val,
        file_val,
        length,
        lengths,
        contains,
        sorted_val,
        numpy_subdtype,
    ]
    write_funcs(file)

# %%
