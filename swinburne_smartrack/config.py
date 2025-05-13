

import tomllib

config = None

def load_config(filename: str) -> None:
    global config

    print('loading config')
    with open('config.toml', 'rb') as file:
        config = tomllib.load(file)

