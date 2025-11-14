"""
This module implements the Configuration class which is used to manage the SmartRack configuration for all library modules and applications.
"""

# Import System Libraries
import logging.config
import tomllib
import os
import pathlib


class Configuration:
    """
    Manages the application configuration using a singleton pattern.

    This class ensures that only one instance of the configuration is created and shared across the application. It dynamically loads configuration
    from a TOML file, either specified by the user or found in predefined default paths. The configuration file must include required sections like
    'smartrack_servers' and 'manage'. Additionally, the class integrates logging configuration if the debug section is present in the file.

    :ivar _instance: Singleton instance of the class; ensures one instance across the application.
    :ivar _initialized: Indicates if the configuration has already been initialized to prevent reinitialization.
    """
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        """
        Implements a singleton pattern to ensure only one instance of the class is created, shared across any number of instantiations. Each call to
        this class returns the same instance, maintaining the state across calls.

        :param cls: The class being instantiated.
        :param args: Positional arguments that are passed during instantiation.
        :param kwargs: Keyword arguments that are passed during instantiation.

        :returns: A single instance of the class.
        """
        if not cls._instance: cls._instance = super(Configuration, cls).__new__(cls)
        return cls._instance

    def __init__(self, filename: str = None):
        """
        Initializes the configuration of the application, attempting to load from the specified TOML configuration file or default configuration
        file paths. If no valid file is found, it raises a FileNotFoundError Exception.

        The constructor checks if a configuration has already been instantiated (via the `_initialized` flag) to prevent reinitialization. If a
        filename is provided, it looks for that specific file. If no filename is provided, it attempts to load the configuration from a predefined
        list of default paths. The configuration file must contain certain mandatory sections, including 'smartrack_servers' and 'manage'.

        If present, the `debug` section in the configuration will initialize the logging system based on the provided dictionary configuration.
        If any configuration file raises an error during parsing, logging for the corresponding error is generated and the constructor continues
        trying other files in the list.

        :param filename: An optional path to a specific configuration file. If not provided, a set of default configuration files are attempted.

        :raises FileNotFoundError: If no valid configuration file is found.
        """
        # If a configuration has already been loaded, just return
        if self._initialized: return

        self.config = {}

        # Set list of files to try to load as configuration (either provided or first ~/.config/cisco/smartrack.toml and backup /etc/cisco/smartrack.toml
        config_files = [pathlib.Path(filename)] if filename else [pathlib.Path(p, 'smartrack.toml') for p in [pathlib.Path(os.environ['HOME'], '.config', 'cisco'), pathlib.Path('/etc', 'cisco'), ]]

        # Try loading each file in turn, terminate constructor on first successful load
        for file in config_files:
            if file.is_file():
                with open(file, 'rb') as f:
                    try:
                        self.config = tomllib.load(f)

                        assert 'smartrack_servers' in self.config, 'TOML Configuration file does not contain the "smartrack_servers" section'
                        assert 'manage' in self.config, 'TOML Configuration file does not contain the "manage" section'
                        assert 'skills' in self.config, 'TOML Configuration file does not contain the "skills" section'

                        if 'debug' in self.config:
                            logging.config.dictConfig(self.config['debug'])

                        self._initialized = True
                        return
                    except Exception as e:
                        logging.warning(f'ERROR: Parsing configuration file "{file}" - {e}')
                        pass

        # If we got here, no configuration file was loaded, raise exception
        raise FileNotFoundError('Valid configuration file not found')

    @property
    def smartrack_servers(self):
        """
        Retrieves the configuration value for 'smartrack_servers' as a class property.

        :return: The value associated with the 'smartrack_servers' key in the configuration dictionary.
        """
        return self.config['smartrack_servers']

    @property
    def manage(self):
        """
        Retrieves the configuration value for 'manage' as a class property.

        :return: The value associated with the 'manage' key in the configuration dictionary.
        """
        return self.config['manage']

    @property
    def skills(self):
        """
        Retrieves the configuration value for 'skills' as a class property.

        :return: The value associated with the 'skills' key in the configuration dictionary.
        """
        return self.config['skills']
