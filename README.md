# Swinburne SmartRack

Programs and Libraries to manage Cisco devices accessible via SmartRack at Swinburne University.

## Installation

Should be possible via a pip install

```console
pip install swinburne_smartrack
```

### Create smartrack.toml file

The SmartRack package uses a system configuration file to know how to access the SmartRack system
and what to do to manage the connected devices. You will need to create a file on your system. You
can specify this file directly to all libraries/programs, or if not it will be loaded automatically
default location. All library code will look first in `~/.config/cisco/smartrack.toml`, then in
`/etc/cisco/smartrack.toml` to load this file.

```toml
################################################################################
## Definition of SmartRack Servers and how to connect to them
##
## smartrack_servers.ROOM - Shortname "ROOM" for the server
## description            - Text description for server to display on UI
## url                    - URL to access the get_all.php page on the server
################################################################################
[smartrack_servers]

[smartrack_servers.ATC328]
description = "Cisco Devices in ATC328"
url = "https://ictencsvr2.ict.swin.edu.au/agent/get_all.php"

[smartrack_servers.ATC329]
description = "Cisco Devices in ATC329"
url = "https://ictencsvr6.ict.swin.edu.au/agent/get_all.php"

[smartrack_servers.ATC330]
description = "Cisco Devices in ATC330"
url = "https://ictencsvr11.ict.swin.edu.au/agent/get_all.php"

################################################################################
## Properties to manage a SmartRack device
##
## usernames     - List of usernames to cycle through when attempting to put device in enable mode (optional)
## passwords     - List of passwords to cycle through when attempting to put device in enable mode (optional)
## manage.DEVICE - Device type (router, switch, asa)
## collect       - List of commands to capture output for when collecting student work for this device
## erase         - List of commands to send to device to clean all stored configuration
## restart       - List of commands to send to device to reload the device
################################################################################
[manage]
passwords = [ "pass1", "pass2" ]

# Commands to collect/erase-config/restart a router
[manage.router]
collect = [ "sh run", "sh ip int brief", "sh ip route" , "sh access-lists", "sh ip dhcp binding", "sh ip dhcp pool", "sh ip ospf neighbour", "sh ip ospf" ]
erase = [ "erase startup-config", "", "" ]
restart = [ "reload", "", "", "no", "", "" ]

# Commands to collect/erase-config/restart a switch
[manage.switch]
collect = [ "sh run", "sh ip int brief", "sh vlan brief", "sh int trunk", "sh port-security", "sh spanning-tree" ]
erase = [ "erase startup-config", "", "", "delete vlan.dat", "", "", "" ]
restart = [ "reload", "", "", "no", "", "" ]

# Commands to collect/erase-config/restart an ASA firewall
[manage.asa]
collect = [ "sh run", "sh ip int brief" ]
erase = [ "write erase", "", "" ]
restart = [ "reload", "", "", "no", "", "" ]

################################################################################
## Configuration options to manage exam collection
##
## base_dir          - Base directory for collecting exams, files will be stored in sub-directories under here
## semester_map      - Session directory path includes year and semester. This list maps month numbers to semester names
## information_file  - Filename created by skills_collect for each student containing exam information, selected student options, and marking rubric information
## requirements_file - Filename created in collection directory with the exam requirements/solution (copied from file provided to skills_collect
################################################################################
[skills]
base_dir = "<put_directory_here>"
semester_map = [ "Sum", "Sum", "Sum", "S1", "S1", "S1", "S1", "S1", "S2", "S2", "S2", "S2" ]
information_file = "exam_info.toml"
requirements_file = "solution.ini"
```

## Testing Installation

The Swinburne SmartRack package comes with four test scripts to evaluate that the installed code
works properly. Each of the tests can be used to evaluate functionality

Execute:
```code
python -m swinburne_smartrack -h
```

To see all available test commands. For all commands, you may specify `-c smartrack.toml` to use 
a local `smartrack.toml` file. Alternatively, not specifying the `-c` option will load from the
previously mentioned directories.

### Test 1 - Confirming SmartRack access

Usage:
```code
python -m -c smartrack.toml smartrack
```

The program will ask you to select from the SmartRack servers (you may choose multiple). You will
then be required to enter your SmartRack username/password.

The test will access SmartRack, download all devices you have booked, and display access/login
parameters in a table format

### Test 2 - Connect to Cisco Device and test access

Usage:
```code
python -m swinburne_smartrack ciscodevice hostname username password [port]
```

You will need the cisco device access information as reported in the previous test to test.

| Parameter  | Description                                                     |
|------------|:----------------------------------------------------------------|
| `hostname` | URL of server hosting that we can access the router/switch from |
| `username` | Username required to connect to the device via ssh              |
| `password` | Password required to connect to the device via ssh              |
| `port`     | (Optional) Port number to use with ssh protcol (default: 22)    |

The test will:
 - Connect to the device using connection parameters in arguments
 - Place the device into enable mode
 - Capture the output of "sh ip int brief" and display as a table
 - Create a Loopback interface and set an IP address
 - Re-capture the output of "sh ip int brief" and display as a table

### Test 3 - Test Device Collection within a sub-process

Usage:
```code
python -m swinburne_smartrack devicemanager [-o OUTPUT_DIR] hostname username password [port]
```

The `OUTPUT_DIR` parameter is optional. If not provided `OUTPUT_DIR=test_collect`

The function sets up and starts the DeviceManager sub-process, using the arguments provided to connect
to the device. It will automatically determine the device type (router or switch) and:
 - Connect to the device using connection parameters
 - Place the device into enable mode
 - Run the "collect" task on the device, capturing output of the commands configured in the configuration
   file
 - Display a progress message as each sub-task completes
 - Cleans up and destroys the sub-process upon completion

### Test 4 - Test Device Collection within a sub-process

Usage:
```code
python -m swinburne_smartrack multidevice
```

Brings everything together into a mini-application.
 - Uses SmartRackTUI and SmartRack to extract connection information for all devices booked by the user.
 - Creates a list of DeviceManager processes to connect to each booked device.
 - Registers each DeviceManager process to execute the "erase" task to delete any saved configurations.
 - Creates a MultiDeviceManager instance and tasks it to run all DeviceManager processes with a timeout
   of 30 seconds
 - Separately lists all devices that successfully, and unsuccessfully, completed the tasks.

## Programs

swinburne_smartrack also installs four executable programs that can be used to manage running of
Skills Exams within Swinburne. If you plan to use swinburne_smartrack as a library, you will not need
to use these applications

### Display Smartrack Configuration

Usage:
```code
smartrack_config [-c CONFIG FILE]
```

Load and validate the `smartrack.toml` file. Print and display the contents in a user-friendly manner
to screen.

### Clean SmartRack Devices

Usage:
```code
smartrack_clean [-c CONFIG_FILE] [-t TIMEOUT]
```

| Parameter     | Description                                                       |
|---------------|:------------------------------------------------------------------|
| `CONFIG_FILE` | (Optional) `smartrack.toml` file to use (default=use system file) |
| `TIMEOUT`     | (Optional) Timeout in seconds to abort attempt (default=120s)     |

Access all booked devices from selected SmartRack servers and attempt to logon and clean all devices.

### Validate Exam Collection Configuration File

Usage:
```code
skills_validate_config exam_config
```

| Parameter     | Description                                                                     |
|---------------|:--------------------------------------------------------------------------------|
| `exam_config` | Exam collection TOML file providing parameters of how to collect a skills exam. |

Load and validate the `exam_config` TOML file. Print and display the contents in a user-friendly manner
to screen.

Format of `exam_config` TOML file

```toml
[details]
name      = "Long Description of Exam"
unitcode  = "code" # Defines (a part of) the sub-directory where collected exams will be stored 
shortname = "name" # Defines (a part of) the sub-directory where collected exams will be stored

# What to collect from SmartRack and how
[collect]
timeout = 180

[collect.Device1]
type = "router"

[collect.Device2]
type = "router"
extra = [ "show run", "show ip int brief" ]

# Ask which exam paper we are running
[options]
scheme = [ "A", "B", "C", "D" ]
```

Information to understand the TOML file contents:
 - Collected exam will be stored in `base_dir/unitcode/YYYY_SS/shortname`
 - You may collect as many devices as required, the subnames (eg. `collect.Device1`) must match the
   names within SmartRack (`12345678_Device1`) as created by the exam booking spreadsheet.
 - Allowed device types are `router`, `switch`, or `asa`
 - `extra` is optional and is a list of extra commands to capture from this device (above and beyond)
   those listed in `smartrack.toml`
 - The `[options]` section is optional and will allow for different exams for each student.

### Run/Collect a Skills Exam 

Usage:
```code
skills_collect [-c CONFIG FILE] exam_config solution
```

Run and collect all student exams using the specified `exam_config` Exam Configuration TOML file.

Following collection, the following two files are created in each students collection directory:

| File             | Contents                                                                                                                                |
|------------------|:----------------------------------------------------------------------------------------------------------------------------------------|
 | `solution.ini`  | A copy of the `solution` INI file (as per the original exam collection program) to allow for later marking                              |
| `exam_info.toml` | A TOML file containing Exam information including the name, individual options for the student, and the rubric to be used in assessment |

The filenames (`solution.ini` and `exam_info.toml`) can be changed by modifying the `smartrack.toml` file.

## Developers

If you wish to develop your own applications using the swinburne_smartrack package, you will find 
that all the library files and classes are fully documented and can be accessed via the Python
help() function.

The classes that can be imported via ```import swinburne_smartrack``` are:

1) ```Configuration``` - Singleton class to read SmartRack configuration toml file and make parameters available.
2) ```SmartRack``` - Class to download booked device connection information from SmartRack and to filter devices for selection.
3) ```SmartRackTUI``` - Text-based User Interface to query User for SmartRack information, and then return a SmartRack device with booked devices.
4) ```CiscoDevice``` - Class to manage connection and control of a remotely connected (via ssh) Cisco Device.
5) ```DeviceManager``` - Implements a multiprocessing sub-process to manage a Cisco Device to perform a set of registered tasks.
6) ```MultiDeviceManager``` - Manage multiple DeviceManager classes running in parallel along with a console display to update progress.
