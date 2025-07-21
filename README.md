# Checking Library

The `checking` library provides tools for validating Python dataclasses and variables. It includes a set of validators, descriptors, and error handling mechanisms to ensure data integrity and enforce constraints.

## Features

- **Validators**: Predefined validation logic for common use cases.
- **Descriptors**: Custom descriptors for managing attribute validation for use with dataclasses.

## Usage

### Validating variables

You can use the validator `Validator`. You can either first create a validator and then use it, or you can combine the
creation and validation. When validating a value, you pass the value and a name for the variable, the name is used in error messages.

```python
from checking import Validator

positive_num = Validator.positive(True)
positive_num(42, "somenumber")  # This will pass validation
positive_num(-10, "somenumber") # This will raise a ValidationError

# These are the same as above, but by directly calling the validator with validation parameters
Validator.positive(True, 42, "somenumber")  # This will raise a ValidationError
Validator.positive(True, -10, "somenumber")  # This will raise a ValidationError
```

It is also possible to construct a custom validator
```python
from checking import Validator

validator_literals = Validator(literals=('a', 'b', 'c'))  # This will validate that the input is one of the specified literals
validator_literals('a', "somestring")  # This will pass validation
validator_literals('d', "somestring")  # This will raise a ValidationError

validator_types = Validator(types=(tuple, list))  # This will validate that the input is a tuple or a list
validator_types([1, 2, 3], "somelist")  # This will pass validation
validator_types('not a list', "somelist")  # This will raise a ValidationError

validator_converter = Validator(types=(int, float), converter=float)  # This will validate that the input is a number and if not try to convert it to float
value = validator_converter('3.14', "somenumber")  # This will pass validation and return the float
validator_converter('not a number', "somenumber")  # This will raise a ValidationError
```

### Dataclass descriptors

The library integrates with Python dataclasses to validate fields automatically, similarly to Validators.

```python
from dataclasses import dataclass
from checking import Descriptor

@dataclass
class Example:
    field: float = Descriptor.positive(include_zero=True, default=1.0)

example = Example(field=42) # This will pass validation
example.field = -10  # This will raise a ValidationError
```