# Standalone CLI

This example demonstrates how to create a standalone CLI (i.e., with vanilla python functions and classes) to create a configurable command-line interface using `hydra-config`.

## Define various classes

First, we'll define variable classes which have different parameters. We'll define a `Config` class which will have a few derived classes to demonstrate automatic CLI declaration based on inheritance.

```python
from typing import Any

class Config:
    def __init__(self, param: Any):
        self.param = param


class ConfigInt(Config):
    def __init__(self, param: int):
        super().__init__(param)


class ConfigFloat(Config):
    def __init__(self, param: float):
        super().__init__(param)


class System:
    def __init__(self, config: Config):
        self.config = config
```

You do not need to explicitly tell `hydra-config` about these classes. The next step will show how to create a CLI using these classes.

## Register the CLI entrypoint

Next, we'll define a CLI entrypoint using a vanilla python function. We'll use the `@register_cli` decorator to register the function as a CLI entrypoint. The function signature will be used to infer the CLI parameters. It will walk through each non-primitive parameter (in this case, `System`) and recursively infer the parameters.

```python
from hydra_config.cli import register_cli, run_cli

@register_cli
def standalone_cli(system: System, x: int, flag: bool = False):
    print(
        "System Config Param:",
        system.config.param,
        type(system.config),
        type(system.config.param),
    )
    print("X:", x, type(x))
    print("Flag:", flag, type(flag))
```

```{warning}
As of writing, defining defaults for non-primitive types is not supported. This may be added in a future release.
```

## Call the CLI

Finally, we can call the CLI using the `run_cli` function. This will parse the command-line arguments and call the appropriate function.

```python
if __name__ == "__main__":
    run_cli(standalone_cli)
```

## Run the CLI

You can run the CLI using the following command:

```bash
python standalone_cli.py system=System x=1 system/config=ConfigFloat system.config.param=1
```
