"""APatch Blender: contract-governed operations for Blender."""

from .contracts import Contract, ContractError, load_contract

__all__ = ["Contract", "ContractError", "load_contract"]
__version__ = "0.1.0"
