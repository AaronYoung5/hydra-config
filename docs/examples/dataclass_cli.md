# Dataclass-based CLI

This example shows how to build a CLI using dataclasses and hydra-config.

## Define classes

```python
from typing import Any
from hydra_config import HydraContainerConfig, config_wrapper

@config_wrapper
class Config(HydraContainerConfig):
    param_any: Any

@config_wrapper
class ConfigInt(Config):
    param_int: int

@config_wrapper
class ConfigFloat(Config):
    param_float: float


class System:
    def __init__(self, config: Config):
        self.config = config
```

## Register the CLI entrypoint

```python
from hydra_config.cli import register_cli, run_cli

@register_cli
def dataclass_cli(system: System, x: int, flag: bool = False):
    print("System Config Param:", system.config.param_any, type(system.config.param_any))
    print("X:", x, type(x))
    print("Flag:", flag, type(flag))
```

## Call the CLI

```python
if __name__ == "__main__":
    run_cli(dataclass_cli)
```

## Run the CLI

```bash
python examples/dataclass_cli.py system=System system/config=Config x=1 system.config.param_any=1
```
