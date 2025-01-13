"""Hydra Config CLI utilities."""

from types import FunctionType, UnionType
from typing import Callable, get_type_hints

import hydra_zen as zen

from hydra_config.utils import builds


def _sanitize_type_hints(func: FunctionType) -> FunctionType:
    original_hints = get_type_hints(func)
    sanitized_hints = {}

    for param, hint in original_hints.items():
        if type(hint) is UnionType:
            sanitized_hints[param] = hint.__args__[0]
        else:
            sanitized_hints[param] = hint

    func.__annotations__.update(sanitized_hints)
    return func


def register_cli(func: Callable | None = None, /, **kwargs) -> Callable:
    """Register a CLI command.

    Example:

        .. literalinclude:: /../examples/standalone_cli.py


    Args:
        func (Callable | None): The CLI function to register. If None, returns a
            decorator.

    Returns:
        Callable: The registered CLI function or a decorator if `func` is None.
    """

    def wrapper(func: Callable) -> Callable:
        kwargs.setdefault("name", func.__name__)
        zen.store(builds(_sanitize_type_hints(func)), **kwargs)

        return func

    if func is None:
        return wrapper
    return wrapper(func)


def run_cli(func: Callable, /, **kwargs) -> None:
    """Run a CLI command.

    Args:
        func (Callable): The CLI command to run.
    """
    kwargs.setdefault("config_path", None)
    kwargs.setdefault("config_name", func.__name__)
    kwargs.setdefault("version_base", "1.3")

    zen.store.add_to_hydra_store()
    zen.zen(func).hydra_main(**kwargs)
