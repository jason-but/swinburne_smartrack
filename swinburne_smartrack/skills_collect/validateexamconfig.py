"""
This module implements the validate_exam_toml() function which loads the contents of the provided EXAM configuration from a TOML file into a dictionary to be
used. The dictionary structure is validated to ensure it conforms to a valid EXAM configuration.
"""

# Import System Libraries
import tomllib
import pathlib

# Import SmartRackLibrary modules
from swinburne_smartrack import Configuration


class ValidateError(Exception):
    """
    This exception is raised when the user chooses to terminate the application as a signal to cancel any further actions.
    """
    pass


def validate_exam_toml(file: pathlib.Path) -> dict:
    """
    Load the provided TOML file containing the exam configuration into a dictionary to return. The contents of the TOML file/dictionary are validated, and an
    exception is raised if the contents are invalid.

    :param file: TOML File containing the exam configuration parameters that will determine what is collected and how.

    :return: Dictionary containing the contents of the provided TOML file.
    """
    with open(file, 'rb') as f:
        try:
            result = tomllib.load(f)

            assert 'details' in result, 'EXAM TOML Configuration file does not contain [details] section'
            assert 'name' in result['details'], 'EXAM TOML Configuration [details] section does not contain name'
            assert 'unitcode' in result['details'], 'EXAM TOML Configuration [details] section does not contain unitcode'
            assert 'shortname' in result['details'], 'EXAM TOML Configuration [details] section does not contain shortname'

            assert 'collect' in result, 'EXAM TOML Configuration file does not contain [collect] section'
            assert 'timeout' in result['collect'], 'EXAM TOML Configuration [collect] section does not contain timeout'
            assert len(result['collect']) > 1, 'EXAM TOML Configuration [collect] section does not contain any devices'

            for name, details in result['collect'].items():
                if name != 'timeout':
                    assert 'type' in details, f'EXAM TOML Configuration device {name} does not specify a device type'
                    assert details['type'] in Configuration().manage, f'EXAM TOML Configuration device {name} type ({details["type"]}) is not a valid device type'
                    for key, commands in details.items():
                        if key != 'type':
                            assert key == 'extra', f'EXAM TOML Configuration for device ({name}) contains an invalid key ({key})'
                            assert isinstance(commands, list), f'Extra Commands configuration for ({name}) is not a list of commands (hint: extra = ["{commands}"])'
                            assert all(isinstance(command, str) for command in commands), f'Extra Commands configuration for ({name}) is not a list of strings (extra = {commands})'
                            assert len(commands) > 0, f'Extra Commands configuration for ({name}) is an empty list (extra = {commands})'

            if 'options' in result:
                assert (len(result['options'])) > 0, f'EXAM TOML Configuration [options] section does not contain any options'

        except Exception as e:
            raise ValidateError(f'Parsing TOML file "{file}" - {e}')

    return result
