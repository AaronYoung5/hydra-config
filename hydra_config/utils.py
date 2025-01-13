"""This module contains utility functions for use with Hydra."""

import argparse
import enum
import re
from functools import partial
from inspect import signature
from pathlib import Path
from typing import Any, Callable, Concatenate, Dict, List, Optional, Type

import hydra
import hydra_zen as zen
import RestrictedPython
import RestrictedPython.Eval
from hydra.core import global_hydra
from hydra.utils import get_object
from omegaconf import DictConfig, OmegaConf
from omegaconf._utils import is_primitive_type_annotation

from hydra_config.config import HydraContainerConfig

# =============================================================================


def run_hydra(
    main_fn: Optional[
        Callable[[Concatenate[HydraContainerConfig, ...]], None]
    ] = lambda *_, **__: None,
    /,
    *,
    parser: argparse.ArgumentParser = argparse.ArgumentParser(),
    config_path: Path | str = Path.cwd() / "configs",
    config_name: str = "base",
    instantiate: bool = True,
    **kwargs,
):
    """This function is the main entry point for the hydra application.

    The benefits of using this setup rather than the compose API is that we can
    use the sweeper and launcher APIs, which are not available in the compose API.

    An additional ``--hydra-help`` flag is added to the parser to print the hydra help
    message when passed.

    Args:
        main_fn (Callable[[Concatenate[[HydraContainerConfig], ...], None]): The
            main function to be called after the hydra configuration is parsed. It
            should take the config as an argument and kwargs which correspond to the
            argument parser returns. We don't return the config directly because hydra
            allows multi-run sweeps and it doesn't make sense to return multiple
            configs in this case.

            Example:

            .. code-block:: python

                def main(config: HydraContainerConfig, *, verbose: int):
                    pass

                parser = argparse.ArgumentParser()
                parser.add_argument("--verbose", type=int, default=0)

                run_hydra(main_fn=main, parser=parser)

    Keyword Args:
        parser (argparse.ArgumentParser): The parser to use for the hydra
            application. If None, a new parser will be created.
        config_path (Path | str): The path to the config directory. This should be the
            absolute path to the directory containing the config files. By default,
            this is set to the current working directory.
        config_name (str): The name of the config file to use. This should be the
            name of the file without the extension. By default, this is set to
            "base".
        instantiate (bool): Whether to instantiate the config. If False, create
            will be used.
        kwargs: Additional keyword arguments to pass to the instantiate function.
    """

    # Add one default argument for the --hydra-help message
    parser.add_argument(
        "--no-instantiate",
        action="store_false",
        dest="instantiate",
        help="Don't instantiate the config.",
    )
    parser.add_argument(
        "--hydra-help", action="store_true", help="Print the hydra help message."
    )

    original_print_help = parser.print_help

    def hydra_custom_help(file=None):
        original_print_help(file)
        if global_hydra.GlobalHydra.instance().is_initialized():
            global_hydra.GlobalHydra.instance().hydra.app_help()

    parser.print_help = hydra_custom_help

    def hydra_argparse_override(fn: Callable, /):
        """This function allows us to add custom argparse parameters prior to hydra
        parsing the config.

        We want to set some defaults for the hydra config here. This is a workaround
        in a way such that we don't

        Note:
            Augmented from hydra discussion #2598.
        """
        import sys
        from functools import partial

        parsed_args, unparsed_args = parser.parse_known_args()

        # Move --hydra-help to unparsed_args if it's present
        # Hydra has a weird bug (I think) that doesn't allow overrides when
        # --hydra-help is passed, so remove all unparsed arguments if --hydra-help
        # is passed.
        if parsed_args.hydra_help:
            unparsed_args = ["--hydra-help"]
        del parsed_args.hydra_help

        # By default, argparse uses sys.argv[1:] to search for arguments, so update
        # sys.argv[1:] with the unparsed arguments for hydra to parse (which uses
        # argparse).
        sys.argv[1:] = unparsed_args

        return partial(fn, **vars(parsed_args))

    config_path = str(config_path) if isinstance(config_path, Path) else config_path

    @hydra.main(config_path=config_path, config_name=config_name, version_base=None)
    @hydra_argparse_override
    def main(config: DictConfig, instantiate: bool = instantiate, **fn_kwargs):
        if instantiate:
            config = HydraContainerConfig.instantiate(config, **kwargs)

        return main_fn(config, **fn_kwargs)

    main()


# =============================================================================


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
    **kwargs: Any,
) -> Any:
    """Build a Hydra Zen configuration for a given function or class.

    Args:
        func_or_cls (Callable[..., Any] | Type[Any]): The function or class to build a
            configuration for.
        auto_detect (bool): Automatically detect and store parameter types. Defaults to
            True.
        group (str): The group name for the configuration. Defaults to an empty string.
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
                if is_primitive_type_annotation(type_hint) or type_hint is Any:
                    continue

                # Only store the type hint if it is a non-primitive
                store(type_hint, name=param.name, group=group)

                defaults[param.name] = "???"

    hydra_defaults = ["_self_"] + [
        {name: default} for name, default in defaults.items()
    ]

    kwargs.setdefault("populate_full_signature", True)
    kwargs.setdefault("zen_dataclass", {}).setdefault("cls_name", func_or_cls.__name__)
    return zen.builds(func_or_cls, hydra_defaults=hydra_defaults, **kwargs)


# =============================================================================


def safe_eval(src: str, additional_vars: Dict[str, Any] = {}) -> Any:
    """
    Evaluate a string containing a Python expression in a safe manner.

    This function uses
    `RestrictedPython <https://restrictedpython.readthedocs.io/en/latest/>`_ to evaluate
    the expression, only allowing certain built-in functions and types, and any
    additional variables provided. It prevents execution of arbitrary code or access to
    unauthorized functions and methods.

    A number of built-in functions are supported, as provided by ``utility_builtins``,
    ``safe_builtins``, and ``limited_builtins`` from
    `here <https://restrictedpython.readthedocs.io/en/latest/usage/\
        api.html#restricted-builtins>`_.

    Args:
        src (str): The source code to evaluate.
        additional_vars (Dict[str, Any]): A dictionary of additional variables or
            functions to include in the evaluation environment.

            Warning:
                This can be unsafe if the variables are not properly sanitized, thus
                ``additional_vars`` should be used with caution.

    Returns:
        Any: The result of the evaluated expression.

    Example:
        >>> safe_eval("1 + 2")
        3
        >>> safe_eval("max([1, 2, 3])")
        3
        >>> safe_eval("math.sqrt(a)", {'a': 16})
        4.0
    """
    safe_globals = {
        **RestrictedPython.utility_builtins,
        **RestrictedPython.safe_builtins,
        **RestrictedPython.limited_builtins,
        "_getiter_": RestrictedPython.Eval.default_guarded_getiter,
    }
    byte_code = RestrictedPython.compile_restricted(
        src, filename="<inline code>", mode="eval"
    )
    return eval(byte_code, safe_globals, additional_vars)


def glob(key: str, flattened: bool, _root_: DictConfig) -> Dict:
    """This resolver will glob a key in the config. This is useful for finding all keys
    that match a pattern. This is particularly useful for finding all keys that match a
    pattern in a nested config. This is effectively select, but allows ``*`` to be used
    as a wildcard.

    This method works by finding all ``*`` in the key and then iterating over all
    subsequent keys that match the globbed pattern.

    Note:
        yaml files aren't necessarily built to support globbing (like xml), so
        this method is fairly slow and should be used sparingly.

    Note:
        List indexing is limited in support. To index an element in a list, you
        must use bracket notation. For instance, ``a[0].b`` is supported, but ``a.0.b``
        is not.

    Args:
        key (str): The key to glob. This is a dotlist key, like ``a.b.*``. Multiple
            globs can be used, like ``a.*.c.*.d.*``. Globs in keys can be used, as
            well, such as ``a.ab*.c``
        flatten (bool): If true, the output will be a dict of the leaf keys and
            the accumulated values if there are like leaf keys. If False, the
            output will be a nested dict. Defaults to False.
        _root_ (DictConfig): The root config.
    """

    def recursive_glob(config: DictConfig | Any, keys: List[str]) -> Dict:
        if not keys or not isinstance(config, DictConfig):
            return config

        # We'll loop over all the keys and find each match with the passed key/pattern
        result = {}
        current_key = keys[0].replace("*", ".*")
        for sub_key, sub_value in config.items():
            if sub_value is None:  # Skip None values, probably optionals
                continue

            if match := re.fullmatch(current_key, sub_key):
                # If it's a match, we'll recursively glob the next key
                matched_key = match.group()
                result[matched_key] = recursive_glob(sub_value, keys[1:])

        # This adds support for direct indexing. This is currently the only supported
        # way to do list accessing for globbing. To check, we'll clean the parentheses
        # and see if the key exists in the config as is.
        # NOTE: this is done after the recursive globbing in case the the key is found
        # earlier
        for cleaned_key in re.sub(r"^\((.*)\)$", r"\1", current_key).split("|"):
            if cleaned_key in result:
                continue

            if sub_value := OmegaConf.select(config, cleaned_key):
                # remove the brackets from the key
                cleaned_key = re.sub(r"^\((.*)\)$", r"\1", cleaned_key)
                result[cleaned_key] = recursive_glob(sub_value, keys[1:])

        return result

    def flatten(
        data: Dict[str, Any], values: Dict[str, List[Any]] = {}
    ) -> Dict[str, Any]:
        """This will flatten the nested dict to a flat dict where each key is a leaf
        key of the nested dict and the value is a list of all the values that were
        accumulated to that leaf key."""
        for k, v in data.items():
            if isinstance(v, dict):
                flatten(v, values)
            else:
                values.setdefault(k, [])
                values[k].append(v)
        return values

    # Glob the key(s)
    globbed = recursive_glob(_root_, key.split("."))

    # Return the flattened or nested dict
    return flatten(globbed) if flattened else globbed


def merge_with_kwargs(
    config: DictConfig,
    *,
    instantiate: bool = True,
    **kwargs,
) -> DictConfig:
    """This method will merge the kwargs into the config. This is useful for merging
    "late", as in after the config has been resolved (not instantiated). By specifying
    the merge to happen at instantiation time rather than at resolution time, it gives
    more freedom in defining overrides within the config.

    This is intended to be called from a yaml config file like:

    .. code-block:: yaml

        config_to_merge_late:
            _target_: <path_to>.merge_with_kwargs
            _recursive_: False
            config: ${...} # this is what the kwargs are merged into
            kwarg1: value1
            kwarg2: value2
            ...

    Note:
        You may want ``_recursive_=False`` (as above) to avoid instantiating the config
        before merging the kwargs. If you want to override a config attribute in the
        config object which is instantiated (i.e. is a partial), you won't have access
        to the config attribute (only the partial object), so you would want
        ``_recursive_=False``. Simpler cases can just use ``_recursive_=True``.

    Args:
        config (DictConfig): The config to merge the kwargs into.

    Keyword Args:
        kwargs: The kwargs to merge into the config.
    """
    config = OmegaConf.unsafe_merge(config, kwargs)

    if instantiate:
        return HydraContainerConfig.instantiate(config)
    return config


# =============================================================================


def instance_wrapper(
    *,
    instance: Any,
    key: Optional[str] = None,
    locate: bool = False,
    eval: bool = False,
    setitem: bool = False,
    **kwargs,
):
    """Wraps a class instance to allow setting class attributes after initialization.

    This utility is useful when not all attributes are available during class
    instantiation, allowing attributes to be set post-construction using either
    direct assignment, item setting, or attribute modification based on optional flags.

    Args:
        instance (Any): The class instance to wrap.
        key (Optional[str], optional): If provided, fetches the specified attribute
            from the instance to modify. Defaults to None.
        locate (bool, optional): If True, attempts to resolve attribute names
            dynamically (e.g., via object lookup). Defaults to False.
        eval (bool, optional): If True, evaluates attribute values using safe_eval
            before assignment. Defaults to False.
        setitem (bool, optional): If True, uses item assignment
            (e.g., ``instance[key]``) instead of ``setattr``. Defaults to False.
        **kwargs: Key-value pairs of attributes to set on the instance.

    Returns:
        Any: The modified instance.

    Raises:
        ValueError: If there is an error while setting an attribute.

    Example:

        .. code-block:: yaml

            obj_to_instantiate:
                _target_: <path_to>.instance_wrapper
                instance:
                    _target_: <class>
                    _args_: [arg1, arg2]
                    init_arg1: value1
                    init_arg2: value2
                set_arg1: value1
                set_arg2: value2

        For partial instantiation:

        .. code-block:: yaml

            partial_obj_to_instantiate:
                _target_: <path_to>.instance_wrapper
                instance:
                    _target_: <class>
                    _partial_: True
                    _args_: [arg1, arg2]
                    init_arg3: '???' # Set later
                set_arg1: value1
                set_arg2: value2

    """

    def setattrs(instance, **kwargs):
        try:
            for key, value in kwargs.items():
                if callable(value):
                    value = value()

                if locate:
                    key = get_object(key)
                if eval:
                    key = safe_eval(key)

                if isinstance(value, dict):
                    setattrs(getattr(instance, key), **value)
                elif setitem:
                    instance[key] = value
                else:
                    setattr(instance, key, value)
        except Exception as e:
            raise ValueError(f"Error when setting attribute {key=} to {value=}: {e}")
        return instance

    if isinstance(instance, partial):
        # If the instance is a partial, we'll setup a wrapper such that once the
        # partial is actually instantiated, we'll set the attributes of the instance
        # with the kwargs.
        partial_instance = instance
        config_kwargs = kwargs

        def wrapper(*args, **kwargs):
            if key is not None:
                instance = getattr(partial_instance, key)

            instance = partial_instance(*args, **kwargs)
            return setattrs(instance, **config_kwargs)

        return wrapper
    else:
        if key is not None:
            instance = getattr(instance, key)
        return setattrs(instance, **kwargs)


class HydraFlagWrapperMeta(enum.EnumMeta):
    """This is a simple metaclass to allow for the use of the | operator to combine
    flags. This means you can simply put ``flag1 | flag2`` in the yaml file and it will
    be combined into a single flag.

    The following forms are supported and any combination thereof:

    - ``flag1 | flag2 | flag3 | ...``
    - ``flag1|flag2|flag3|...``
    - ``flag1``
    """

    def __getitem__(cls, item):
        """This method allows for the use of the | operator to combine flags. This
        means you can simply put ``flag1 | flag2`` in the yaml file and it will be
        combined into a single flag.
        """

        if isinstance(item, str) and "|" in item:
            from functools import reduce

            items = [cls.__getitem__(i.strip()) for i in item.split("|")]
            return reduce(lambda x, y: x | y, items)
        return super().__getitem__(item)


# =============================================================================
# Misc


class classproperty:
    def __init__(self, func):
        self.fget = func

    def __get__(self, instance, owner):
        return self.fget(owner)
