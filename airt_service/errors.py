# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/Errors.ipynb.

# %% auto 0
__all__ = ['HTTPError']

# %% ../notebooks/Errors.ipynb 3
import yaml
from typing import *
from pathlib import Path

import airt_service.sanitizer
from pydantic import BaseModel

# %% ../notebooks/Errors.ipynb 5
class HTTPError(BaseModel):
    """A class for raising custom http exceptions"""

    detail: str

    class Config:
        schema_extra = {
            "example": {"detail": "HTTPException"},
        }

# %% ../notebooks/Errors.ipynb 7
if Path("../errors.yml").is_file():
    errors_path = Path("../errors.yml")
elif Path("./errors.yml").is_file():
    errors_path = Path("./errors.yml")
elif Path("/errors.yml").is_file():
    errors_path = Path("/errors.yml")
elif Path("/tf/errors.yml").is_file():
    errors_path = Path("/tf/errors.yml")
else:
    raise ValueError("errors.yml file not found in given paths")

with open(errors_path) as f:
    ERRORS = yaml.safe_load(f)
