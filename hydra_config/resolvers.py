"""This module contains custom resolvers for OmegaConf."""

import re
from pathlib import Path
from typing import Any, Dict, Optional

from omegaconf import DictConfig, ListConfig, OmegaConf
from omegaconf.errors import ConfigKeyError

from hydra_config.config import HydraContainerConfig
from hydra_config.utils import safe_eval

# =============================================================================


def register_new_resolver(name: str, replace: bool = True, **kwargs):
    """Register a new resolver with OmegaConf.

    Args:
        name (str): The name of the resolver.
        replace (bool): Whether to replace the resolver if it already exists.
        **kwargs: Additional keyword arguments to pass to
            ``OmegaConf.register_new_resolver``.
    """

    def decorator(fn):
        OmegaConf.register_new_resolver(name, fn, replace=replace, **kwargs)
        return fn

    return decorator


@register_new_resolver("search")
def search_resolver(
    key: str | None = None,
    /,
    mode: Optional[str] = "value",
    *,
    depth: int = 0,
    _parent_: DictConfig,
) -> Any:
    """This method will recursively search up the parent chain for the key and return
    the value. If the key is not found, will raise a KeyError.

    For instance, a heavily nested value might want to access a value some level
    higher but it may be hazardous to use relative paths (i.e. ${..key}) since
    the config may be changed. Instead, we'll search up for a specific key to set the
    value to. Helpful for setting unique names for an object in a nested config.

    Note:
        This technically uses hidden attributes (i.e. _parent).

    Args:
        key (str | None): The key to search for. Could be none (like when mode is
            "parent_key").
        mode (Optional[str]): The mode to use. Defaults to "value". Available modes:
            - "value": Will return the value of the found key. Key must be set.
            - "parent_key": Will return the parent's key. If key is None, won't do
            any recursion and will return the parent's key.
            - "path": Will return the path to the key.
        depth (Optional[int]): The depth of the search. Used internally
            in this method and unsettable from the config. Avoids checking the parent
            key.
        _parent_ (DictConfig): The parent config to search in.
    """
    if _parent_ is None:
        # Parent will be None if we're at the top level
        raise ConfigKeyError(f"Key {key} not found in parent chain.")

    if mode == "value":
        if key in _parent_:
            # If the key is in the parent, we'll return the value
            return _parent_[key]
        else:
            # Otherwise, we'll keep searching up the parent chain
            return search_resolver(
                key, mode=mode, depth=depth + 1, _parent_=_parent_._parent
            )
    elif mode == "parent_key":
        if key is None:
            # If the key is None, we'll return the parent's key
            assert _parent_._key() is not None, "Parent key is None."
            return _parent_._key()
        elif _parent_._key() == key:
            assert _parent_._parent._key() is not None, "Parent key is None."
            return _parent_._parent._key()

        if depth != 0 and isinstance(_parent_, DictConfig) and key in _parent_:
            # If we're at a key that's not the parent and the parent has the key we're
            # looking for, we'll return the parent
            return search_resolver(None, mode=mode, depth=depth + 1, _parent_=_parent_)
        else:
            # Otherwise, we'll keep searching up the parent chain
            return search_resolver(
                key, mode=mode, depth=depth + 1, _parent_=_parent_._parent
            )
    elif mode == "path":
        if key in _parent_:
            # If the key is in the parent, we'll return the path
            return _parent_._get_full_key(key)
        else:
            # Otherwise, we'll keep searching up the parent chain
            return search_resolver(
                key, mode=mode, depth=depth + 1, _parent_=_parent_._parent
            )


@register_new_resolver("parent")
def parent_resolver(
    key: Optional[str] = None, mode: str = "parent_key", *, _parent_: DictConfig
) -> Any:
    """This resolver is a wrapper around the search resolver with a default mode of
    "parent_key". This will return the parent's key."""
    return search_resolver(key, mode=mode, _parent_=_parent_)


@register_new_resolver("eval")
def eval_resolver(key: str, /, *, _root_: DictConfig) -> Any:
    """This resolver will evaluate the key as a python expression. This is useful for
    evaluating `any` expression. The resolver calls
    :meth:`~hydra_config.utils.safe_eval`, so only a (safe) subset of python is
    available."""

    try:
        return safe_eval(key)
    except Exception as e:
        _root_._format_and_raise(
            key=key,
            value=key,
            msg=f"Error evaluating expression '{key}': {e}",
            cause=e,
        )


@register_new_resolver("glob")
def glob_resolver(
    pattern: str,
    config: Optional[DictConfig | ListConfig | str] = None,
    /,
    *,
    _root_: DictConfig,
) -> ListConfig | DictConfig:
    """This resolver will return a list of keys that match the pattern. This is useful
    for selecting a subset of keys in a config. The pattern should be a regex pattern.
    If the config is a string, it will be treated as a dotpath to a config."""

    if config is None:
        config = _root_

    if isinstance(config, str):
        config = OmegaConf.select(_root_, config)
    if isinstance(config, DictConfig):
        return {k: v for k, v in config.items() if re.match(pattern, k)}
    if isinstance(config, ListConfig):
        return [v for v in config if re.match(pattern, v)]


@register_new_resolver("hydra_select")
def hydra_select(
    key: str, default: Optional[Any] = None, /, *, _root_: DictConfig
) -> Any | None:
    """This is similar to the regular hydra resolver, but this won't through an error
    if the global hydra config is unset. Instead, it will return another interpolation
    using dotpath notation directly. As in, ${hydra_select:runtime.choices.test}, if
    HydraConfig is unset, will return ${hydra.runtime.choices.test}."""
    from hydra.core.hydra_config import HydraConfig

    try:
        return OmegaConf.select(HydraConfig.get(), key, default=default)
    except ValueError:
        return OmegaConf.select(
            _root_, f"hydra.{key}", default=default, throw_on_missing=True
        )


@register_new_resolver("path")
def path_resolver(*parts: str) -> Path:
    """Simple resolver to join paths together."""
    return Path(*parts)


@register_new_resolver("read")
def read_resolver(path: str) -> str:
    """Simple resolver to read a file."""
    with open(path, "r") as f:
        return f.read()


@register_new_resolver("custom")
def custom_resolver(target: str, default: Optional[Any] = None, /):
    """This resolver is a wrapper around the select resolver to grab an entry in a
    parent :attr:`~hydra_config.config.HydraContainerConfig.custom` field.
    """
    return f"${{oc.select:${{search:custom,'path'}}.{target}, {default}}}"


@register_new_resolver("float_to_str")
def float_to_str_resolver(value: float) -> str:
    """This resolver will convert a float to a string. This is useful for saving
    floats as strings in a config for a filename. All periods will be replaced with
    'p' and all negatives will be replaced with 'n'; e.g. ``-0.5`` will be converted
    to ``'n0p5'``."""
    return str(value).replace(".", "p").replace("-", "n")


@register_new_resolver("locate")
def locate_resolver(fn: str, /, cast_to: Optional[str] = None) -> Any:
    """This resolver will locate an object using the :meth:`hydra.utils.get_object`
    method."""
    from hydra.utils import get_object

    obj = get_object(fn)
    if cast_to is not None:
        if cast_to == "str":
            return str(obj)
        elif cast_to == "int":
            return int(obj)
        elif cast_to == "float":
            return float(obj)
        elif cast_to == "bool":
            return bool(obj)
        else:
            raise ValueError(f"Invalid cast_to value: {cast_to}")
    return obj


@register_new_resolver("getitem")
def getitem_resolver(obj: ListConfig, key: int) -> Any:
    """This resolver will get an item from a list."""
    return obj[key]


@register_new_resolver("target")
def target_resolver(target: str, /, *args) -> Dict[str, Any]:
    """This is a resolver which serves as a proxy for the _target_ attribute used
    in hydra. Basically :attr:`target` will be defined as ``_target_`` and the rest of
    the attributes will be passed as arguments to the target. You should always
    default to using ``_target_`` directly in your config, but because interpolations
    `may` be resolved prior to or instead of instantiate, it may be desired to resolve
    interpolations before instantiations."""
    return {"_target_": target, "_args_": args}


@register_new_resolver("instantiate")
def instantiate_resolver(target: str | DictConfig, /, *args, _root_: DictConfig) -> Any:
    """This resolver will instantiate a target using the HydraContainerConfig. If the
    target is a string, it will be resolved using the target_resolver. If the target is
    a DictConfig, it will be passed directly to the HydraContainerConfig.instantiate
    method."""
    try:
        if isinstance(target, str):
            target = target_resolver(target, *args)
        return HydraContainerConfig.instantiate(target)
    except Exception as e:
        _root_._format_and_raise(
            key=target,
            value=target,
            msg=f"Error instantiating target '{target}': {e}",
            cause=e,
        )
