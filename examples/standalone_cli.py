from typing import Any

from hydra_config.cli import register_cli, run_cli


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


if __name__ == "__main__":
    run_cli(standalone_cli)
