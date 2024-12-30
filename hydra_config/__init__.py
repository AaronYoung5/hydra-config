"""``hydra_config`` is a package that provides utilities to simplify the usage of Hydra
in your project."""

from hydra.core.utils import setup_globals

from hydra_config.config import HydraContainerConfig, config_wrapper
from hydra_config.resolvers import register_new_resolver
from hydra_config.utils import HydraFlagWrapperMeta, run_hydra

# Call explicitly setup_globals() to ensure that Hydra is properly initialized
setup_globals()

__all__ = [
    "config_wrapper",
    "HydraContainerConfig",
    "run_hydra",
    "HydraFlagWrapperMeta",
    "register_new_resolver",
]
