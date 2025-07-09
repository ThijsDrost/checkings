# Checking Library

The `checking` library provides tools for validating Python dataclasses and variables. It includes a set of validators, descriptors, and error handling mechanisms to ensure data integrity and enforce constraints.

## Features

- **Validators**: Predefined validation logic for common use cases.
- **Descriptors**: Custom descriptors for managing attribute validation for use with dataclasses.

## Usage

### Validating variables

You can use the validator `Validator`.

```python
from checking import Validator

positive_num = Validator.positive(True)
positive_num(42)  # This will pass validation
positive_num(-10) # This will raise a ValidationError
```

### Dataclass descriptors

The library integrates with Python dataclasses to validate fields automatically.

```python
from dataclasses import dataclass
from checking import Descriptor

@dataclass
class Example:
    field: float = Descriptor.positive(include_zero=True, default=1.0)

example = Example(field=42) # This will pass validation
example.field = -10  # This will raise a ValidationError
```