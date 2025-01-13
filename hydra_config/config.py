"""This module provides a base class for working with Hydra configs."""

import enum
import types
from copy import deepcopy
from dataclasses import dataclass, field, fields, make_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Self, Tuple

import hydra_zen as zen
import yaml
from omegaconf import MISSING, DictConfig, ListConfig, OmegaConf

# =============================================================================


def config_wrapper(cls=None, /, **kwargs):
    """This is a wrapper of the dataclass decorator that adds the class to the hydra
    store.

    The hydra store is used to construct structured configs from the yaml files.

    We'll also do some preprocessing of the dataclass fields such that all type hints
    are supported by hydra. Hydra only supports a certain subset of types, so we'll
    convert the types to supported types using the _sanitized_type method from
    hydra_zen.

    Keyword Args:
        kw: The kwargs to pass to the dataclass decorator. The following defaults
            are set:

            - repr: False
            - eq: False
            - slots: True
            - kw_only: True
    """

    # Update the kwargs for the dataclass with some defaults
    default_dataclass_kw = dict(repr=False, eq=False, slots=True, kw_only=True)
    kwargs = {**default_dataclass_kw, **kwargs}

    def wrapper(original_cls):
        # Preprocess the fields to convert the types to supported types
        # Only certain primitives are supported by hydra/OmegaConf, so we'll convert
        # these types to supported types using the _sanitized_type method from hydra_zen
        # We'll just include the fields that are defined in this class and not in a base
        # class.
        cls = dataclass(original_cls, **kwargs)

        new_fields = []
        for f in fields(cls):
            # Ignore non-initialized fields
            new_fields.append((f.name, zen.DefaultBuilds._sanitized_type(f.type), f))

        # Create the new dataclass with the sanitized types
        kwargs["bases"] = cls.__bases__
        hydrated_cls = make_dataclass(cls.__name__, new_fields, **kwargs)

        # Copy over custom methods from the original class
        for attr_name in dir(cls):
            if attr_name not in hydrated_cls.__dict__:
                attr = getattr(cls, attr_name)
                if not callable(attr) and not isinstance(attr, property):
                    continue

                try:
                    if hasattr(attr, "__func__"):
                        # If it's a bound method, we need to rebind it to the new
                        # class
                        setattr(
                            hydrated_cls,
                            attr_name,
                            types.MethodType(attr.__func__, hydrated_cls),
                        )
                    else:
                        setattr(hydrated_cls, attr_name, attr)
                except TypeError:
                    pass

        # This is a fix for a bug in the underlying cloudpickle library which is used
        # by hydra/submitit (a hydra plugin) to pickle the configs. Since we're using
        # dataclasses, when pickled, their state doesn't propagate correctly to the new
        # process when it's unpickled. A fix is to define the dataclasses in separate
        # modules, but since we're using make_dataclass all in the same one, we have to
        # explicitly set the module of the class here.
        # See https://github.com/cloudpipe/cloudpickle/issues/386 for a related bug.
        # TODO submit bug report on cloudpickle. #386 is fixed, but _MISSED_TYPE is
        # still an issue.
        hydrated_cls.__module__ = cls.__module__

        # Add to the hydra store
        zen.store(
            hydrated_cls,
            name=original_cls.__name__,
            zen_dataclass=dict(cls_name=original_cls.__name__),
        )

        return hydrated_cls

    if cls is None:
        return wrapper
    return wrapper(cls)


# =============================================================================


@config_wrapper
class HydraContainerConfig:
    """Base dataclass which provides additional methods for working with configs."""

    config: Optional[DictConfig] = field(default=None)
    """The original, uninstantiated config. This is maintained within each nested
    instantiated config to allow for proper serialization and deserialization, as well
    as printing the config as a yaml string."""
    custom: Optional[Dict[str, Any]] = field(default_factory=dict)
    """ Custom data to use. This is useful for code-specific logic (i.e. not in yaml
    files) where you want to store data that is not necessarily defined in the config.
    """

    @classmethod
    def instantiate(
        cls,
        config: DictConfig | ListConfig,
        *,
        _convert_: str = "object",
        **kwargs,
    ) -> Self:
        """Instantiate the config into an object.

        Args:
            config (DictConfig | ListConfig): The config to instantiate.

        Keyword Args:
            _convert_ (str): The conversion method to use. Defaults to "object", meaning
                all structured configs will be converted to their dataclass equivalent.
            **kwargs: Additional keyword arguments to pass to the instantiation method.
        """

        instance: Self = zen.instantiate(config, _convert_=_convert_, **kwargs)
        OmegaConf.resolve(config)

        # Iteratively set the config attribute for all nested configs
        def set_config_attr(obj: Any, config: DictConfig | ListConfig):
            if isinstance(obj, HydraContainerConfig):
                if obj.config is None:
                    obj.config = config
                if not OmegaConf.is_config(obj.config):
                    obj.config = OmegaConf.create(obj.config)
                for k, v in obj.config.items():
                    if hasattr(obj, k):
                        set_config_attr(getattr(obj, k), v)
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    if k in config:
                        set_config_attr(v, config[k])
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    set_config_attr(v, config[i])

        # After instantiation, we'll set the config attribute for all nested configs
        # `config` is ignored by omegaconf, so has to come after initialization
        set_config_attr(instance, config)

        return instance

    @classmethod
    def compose(
        cls,
        config_dir: Path | str,
        config_name: str,
        *,
        overrides: List[str] = [],
        return_hydra_config: bool = False,
        **kwargs,
    ) -> (
        Self
        | DictConfig
        | ListConfig
        | Tuple[Self | DictConfig | ListConfig, DictConfig]
    ):
        """Compose a config using the Hydra compose API. This will return the config as
        a HydraContainerConfig instance.

        Args:
            config_dir (Path | str): The path to the config directory.
            config_name (str): The name of the config file.

        Keyword Args:
            overrides (List[str]): The overrides to use when composing the config.
            return_hydra_config (bool): Whether to return the HydraConfig object.
            **kwargs: Additional keyword arguments to pass to the instantiation method.
        """

        import hydra
        from hydra.core.global_hydra import GlobalHydra
        from hydra.core.hydra_config import HydraConfig

        if GlobalHydra.instance().is_initialized():
            GlobalHydra.instance().clear()

        with hydra.initialize_config_dir(str(config_dir), version_base=None):
            hydra_config = hydra.compose(
                config_name=config_name, overrides=overrides, return_hydra_config=True
            )
            HydraConfig.instance().set_config(hydra_config)
            del hydra_config.hydra

        config = cls.create(hydra_config, **kwargs)
        if return_hydra_config:
            return config, HydraConfig.get()
        return config

    @classmethod
    def load(
        cls,
        *args,
        instantiate: bool = True,
        pattern: Optional[str] = None,
        **instantiate_kwargs,
    ) -> Self | DictConfig | ListConfig:
        """Wrapper around OmegaConf.load to instantiate the config.

        Keyword Args:
            instantiate (bool): Whether to instantiate the config into an object.
            pattern (Optional[str]): The specific pattern to select from the loaded
                config.
            **instantiate_kwargs: Additional keyword arguments to pass to the
                instantiation method.
        """
        loaded = OmegaConf.load(*args)
        if pattern is not None:
            loaded = OmegaConf.select(loaded, pattern)
        if instantiate:
            return cls.instantiate(loaded, **instantiate_kwargs)
        else:
            return loaded

    @classmethod
    def create(
        cls,
        *args,
        instantiate: bool = True,
        instantiate_kwargs: dict[str, Any] = {},
        **kwargs,
    ) -> Self | DictConfig | ListConfig:
        """Wrapper around OmegaConf.create to instantiate the config.

        Keyword Args:
            instantiate (bool): Whether to instantiate the config into an object.
            **instantiate_kwargs: Additional keyword arguments to pass to the
                instantiation method.
        """
        created = OmegaConf.unsafe_merge(cls, *args, kwargs)
        if instantiate:
            return cls.instantiate(created, **instantiate_kwargs)
        else:
            return created

    def merge_with(self, *others: DictConfig | ListConfig | Dict | List) -> Self:
        """Wrapper around OmegaConf.merge to merge the config with another config.

        Args:
            others (DictConfig | ListConfig | Dict | List): The other config(s) to
                merge with.
        """
        # Do an unsafe merge so types aren't checked
        merged = OmegaConf.unsafe_merge(self.config, *others)
        return self.instantiate(merged)

    def copy(self) -> Self:
        """Wrapper around the copy method to return a new instance of this class.

        Note:

            This method will perform a deepcopy, meaning the :meth:`__getstate__` and
            :meth:`__setstate__` methods will be called. This is fairly slow since
            the object is pickled and unpickled.
        """
        return deepcopy(self)

    def save(
        self,
        path: Path | str,
        *,
        header: str = None,
    ):
        """Saves the config to a yaml file.

        Args:
            path (Path | str): The path to save the config to.

        Keyword Args:
            header (str): The header to add to the top of the yaml file.
        """

        with open(path, "w") as f:
            if header:
                f.write(f"{header}\n")
            f.write(self.to_yaml())

    def to_yaml(self) -> str:
        """Wrapper around OmegaConf.to_yaml to convert the config to a yaml string.
        Adds some custom representers.

        This uses the stored config attribute to convert to yaml. If the config is None,
        this will return the default string representation of the object.
        """

        assert self.config is not None, "Config is None, cannot convert to yaml."

        def str_representer(dumper: yaml.Dumper, data: str):
            style = None
            if "\n" in data:
                # Will use the | style for multiline strings.
                style = "|"
            elif data == MISSING:
                # Will wrap ??? in quotes, yaml doesn't like this otherwise
                style = '"'
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)

        def path_representer(dumper: yaml.Dumper, data: Path):
            return dumper.represent_scalar("tag:yaml.org,2002:str", str(data))

        def flag_representer(dumper: yaml.Dumper, data: enum.Flag):
            data = "|".join([m.name for m in type(data) if m in data])
            return dumper.represent_scalar("tag:yaml.org,2002:str", data)

        dumper = yaml.CDumper
        dumper.add_representer(str, str_representer)
        dumper.add_multi_representer(Path, path_representer)
        dumper.add_multi_representer(enum.Flag, flag_representer)
        config = OmegaConf.to_container(self.config)
        return yaml.dump(
            config,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            Dumper=dumper,
        )

    def __getstate__(self) -> DictConfig:
        """This is used to pickle the object. We'll return the config as the state."""
        return self.config

    def __setstate__(self, state: DictConfig):
        """This is used to unpickle the object. We'll set the config from the state."""
        instance = self.instantiate(state)
        for field_name in self.__dataclass_fields__.keys():
            setattr(self, field_name, getattr(instance, field_name))

    def __str__(self) -> str:
        """Convert the config to a yaml string."""
        if self.config is None:
            return zen.to_yaml(self)
        return self.to_yaml()
