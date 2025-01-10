"""Hydra Config CLI utilities."""

from inspect import signature
from typing import Any, Callable, Type

import hydra_zen as zen


def store(
    func_or_cls: Callable[..., Any] | Type[Any],
    /,
    *,
    name: str = "",
    group: str = "",
    build: bool = True,
    **kwargs: Any,
) -> Any:
    """Store a function or class in Hydra Zen's store with a specific group and name.

    Args:
        func_or_cls (Callable[..., Any] | Type[Any]): The function or class to store.
        name (str): The name under which to store the function or class. Defaults to
            an empty string.
        group (str): The group name to associate with the store entry. Defaults to an
            empty string.
        **kwargs (Any): Additional arguments passed to `zen.store`.

    Returns:
        Any | None: The stored entry, or `None` if the entry already exists.
    """
    if not build:
        return zen.store(func_or_cls, group=group, name=func_or_cls.__name__, **kwargs)

    if ((group + name, func_or_cls.__name__)) in zen.store:
        return zen.store.get_entry(group + name, func_or_cls.__name__)["node"]

    if (None, func_or_cls.__name__) in zen.store:
        build = zen.store.get_entry(None, func_or_cls.__name__)["node"]
    else:
        build = builds(func_or_cls, group=name + "/", **kwargs)
    out = zen.store(build, group=group + name, name=func_or_cls.__name__)

    if isinstance(func_or_cls, type):
        if func_or_cls not in (str, int, float, bool):
            for sub_cls in func_or_cls.__subclasses__():
                store(sub_cls, name=name, group=group)

    return out


def builds(
    func_or_cls: Callable[..., Any] | Type[Any],
    /,
    *,
    auto_detect: bool = True,
    group: str = "",
    populate_full_signature: bool = True,
    **kwargs: Any,
) -> Any:
    """Build a Hydra Zen configuration for a given function or class.

    Args:
        func_or_cls (Callable[..., Any] | Type[Any]): The function or class to build a
            configuration for.
        auto_detect (bool): Automatically detect and store parameter types. Defaults to
            True.
        group (str): The group name for the configuration. Defaults to an empty string.
        populate_full_signature (bool): Whether to populate the full signature in the
            configuration. Defaults to True.
        **kwargs (Any): Additional arguments passed to `zen.builds`.

    Returns:
        Any: A dataclass representing the Hydra Zen configuration.
    """
    defaults: dict[str, str] = {}
    if auto_detect:
        sig = signature(func_or_cls)

        for param in sig.parameters.values():
            # Check if the parameter has a type hint
            if param.annotation is not param.empty:
                type_hint = param.annotation
                if type_hint is Any:
                    continue

                if type_hint not in (str, int, float, bool):
                    # Only store the type hint if it is a non-primitive
                    store(type_hint, name=param.name, group=group)

                    defaults[param.name] = "???"

    hydra_defaults = ["_self_"] + [
        {name: default} for name, default in defaults.items()
    ]

    return zen.builds(
        func_or_cls,
        populate_full_signature=populate_full_signature,
        hydra_defaults=hydra_defaults,
        zen_dataclass=dict(cls_name=func_or_cls.__name__),
        **kwargs,
    )


def register_cli(func: Callable | None = None, /, **kwargs) -> Callable:
    """Register a CLI command.

    The default name of the CLI command is the function's name.

    Args:
        func (Callable | None): The CLI function to register. If None, returns a
            decorator.

    Returns:
        Callable: The registered CLI function or a decorator if `func` is None.
    """

    def wrapper(func: Callable) -> Callable:
        kwargs.setdefault("name", func.__name__)
        zen.store(builds(func), **kwargs)

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
