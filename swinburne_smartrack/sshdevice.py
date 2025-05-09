"""
This module implements the SSHDevice class which is used to access a remote system via ssh, to be able to send text and to capture output
from the remote device.

The SSHDevice class contains methods that:
  - Connect to the remote device
  - Send text to the device
  - Read all text from the device until a timeout occurs
  - Read all text from the device until a specified prompt is seen or a timeout occurs
"""

# Import Libraries
# time     - Access system time functions
# re       - Regular Expressions
# logging  - Python logging module
# paramiko - ssh library to support remote connections
import time
import re
import logging
import paramiko


class SSHDevice:
    """
    Manages an SSH connection to a remote device.

    This class provides functionalities to establish and manage an SSH connection to a remote host using the Paramiko
    library. It includes methods to connect, send commands or text, and retrieve output from the device through the
    SSH communication channel. The class assures secure interaction with the remote host and provides error handling
    mechanisms during the connection process.
    """
    def __init__(self, hostname: str, username: str, password: str, port: int = 22):
        """
        Represents an SSH connection to a device.

        This class initializes and manages the parameters required to establish an SSH connection using the Paramiko library.
        It validates the input for hostname, username, password, and port values upon initialization. Internally, it sets up
        the necessary SSH client configuration for secure remote access.

        :param hostname: The hostname or IP address of the SSH server. Must be a valid URL.
        :param username: The username for authenticating to the SSH server.
        :param password: The password for authenticating to the SSH server.
        :param port: The port number to connect to on the SSH server. Default is 22.

        :raises ValueError: If the hostname is not a valid URL.
        :raises ValueError: If the username is not provided.
        :raises ValueError: If the password is not provided.
        """

        # Establish logger for SmartRack class
        self.__log = logging.getLogger('SSHDevice')
        self.__log.debug(f'Constructing Class')

        # Validate parameters
        url_pattern = r'^((?!-)[A-Za-z\d-]{1,63}(?<!-)\.)+[A-Za-z]{2,}$'
        if not re.match(url_pattern, hostname): raise ValueError(f'CiscoDevice: hostname {hostname} must be a valid URL')

        if not username: raise ValueError('CiscoDevice: username must be provided')
        if not password: raise ValueError('CiscoDevice: password must be provided')

        # Store connection details
        self.__hostname = hostname
        self.__port = port
        self.__username = username
        self.__password = password

        # Create the SSH client and set to accept remote key/certificate
        self.__log.debug('Creating SSH object')
        self.__client = paramiko.SSHClient()
        self.__client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.__channel = None

    def connect(self) -> None:
        """
        Connects to a remote host via SSH and establishes a session.

        This method uses provided connection details to establish an SSH session and open a shell channel for communication with the remote
        host. It ensures that a successful connection is achieved and flushes the input until a specific prompt is detected.

        :raises paramiko.ssh_exception.SSHException: If there is an error in establishing the connection.
        """
        self.__log.info(f'Connecting to {self.__hostname} at port {self.__port} with username {self.__username} and password {self.__password}')

        # Connect to the remote host
        self.__client.connect(self.__hostname, port=self.__port, username=self.__username, password=self.__password)
        self.__log.info('Connection established')

        # Open an SSH session
        self.__channel = self.__client.invoke_shell()
        self.__log.info('Successful connection')

        # Flush input until we see the SmartRack "Console>" response
        self.__log.info('Waiting to see "Console>" prompt')
        self.read_all_text_until('Console>', 2)

    def send_text(self, text: str) -> None:
        """
        Sends a given text to a connected device through the established channel.

        This method encodes the provided text in ASCII format and transmits it via the communication channel. It also logs the action,
        replacing newline characters with their escaped representation for cleaner logging output.

        :param text: The text message to be sent to the device.
        """
        self.__log.info(f'Sending text to device: "{text.replace('\r\n', '\\r\\n')}"')
        self.__channel.send(text.encode('ascii'))

    def read_all_text(self, timeout: int = 2) -> str:
        """
        Reads all input from the channel until the specified wait string is seen or the timeout period is reached.

        This method reads data from the channel in a loop and appends it to the result string until the specified conditions are met.

        :param timeout: The timeout value in seconds. Specifies how long the method should attempt to flush input before returning.
        :return: The accumulated input read from the channel up to the specified wait string or until the timeout occurs.
        """
        self.__log.info(f'Reading all text from device with a timeout of {timeout} seconds')

        while True:
            last_read = time.time()
            result = ''

            # Append one character at a time to result until the timeout has expired
            while time.time() - last_read < float(timeout):
                if self.__channel.recv_ready():
                    data = self.__channel.recv(1)
                    result += data.decode('ascii')
                    last_read = time.time()

            # Timeout has expired, if result is non-empty return string
            if result:
                self.__log.debug(f'Timeout expired, returning ({result})')
                return result

            # Nothing read from device in timeout period, prod the device to wakeup
            self.__log.info('Timeout expired, nothing read, prodding device to wakeup')
            self.send_text('\n')

    def read_all_text_until(self, wait_string: str = '', timeout: int = 2) -> str:
        """
        Reads all input from the channel until the specified wait string is seen or the timeout period is reached.

        This method reads data from the channel in a loop and appends it to the result string until the specified conditions are met.

        :param wait_string: The string to stop flushing the input. If the wait string is empty, the method will return an empty string immediately.
        :param timeout: The timeout value in seconds. Specifies how long the method should attempt to flush input before returning.
        :return: The accumulated input read from the channel up to the specified wait string or until the timeout occurs.
        """
        # If we want to read an empty string, return immediately
        if not wait_string: return ''

        self.__log.info(f'Flushing input until "{wait_string.replace("\r\n", "\\r\\n")}" is seen, timeout is {timeout} seconds')
        last_read = time.time()
        result = ''

        while time.time() - last_read < float(timeout) and wait_string not in result:
            if self.__channel.recv_ready():
                data = self.__channel.recv(1)
                result += data.decode('ascii')
                last_read = time.time()

        return result
