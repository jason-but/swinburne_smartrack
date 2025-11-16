# Swinburne SmartRack

Programs and Libraries to manage Cisco devices accessible via SmartRack at Swinburne University.

## Installation

You can install the wheel file using:
```console
pip install swinburne_smartrack-x.y.z-none-whl
```

## Testing Installation

The Swinburne SmartRack package comes with four test scripts to evaluate that the installed code works properly

### Create smartrack.toml file

The SmartRack package uses a system configuration file to know how to access the SmartRack system
and what to do to manage the connected devices. You will need to create a file on your system.

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
## manage.DEVICE - Device type (router, switch, asa)
## collect       - List of commands to capture output for when collecting student work for this device
## erase         - List of commands to send to device to clean all stored configuration
## restart       - List of commands to send to device to reload the device
################################################################################
[manage]

# Commands to collect/erase-config/restart a router
[manage.router]
collect = [ "sh run", "sh ip int brief", "sh ip route" , "sh access-lists", "sh ip dhcp binding", "sh ip dhcp pool", "sh ip ospf neighbour", "sh ip ospf" ]
erase = [ "erase startup-config" ]
restart = [ "reload", "no" ]

# Commands to collect/erase-config/restart a switch
[manage.switch]
collect = [ "sh run", "sh ip int brief", "sh vlan brief", "sh int trunk", "sh vlan brief", "sh port-security", "sh spanning-tree" ]
erase = [ "erase startup-config", "delete vlan.dat" ]
restart = [ "reload", "no" ]

# Commands to collect/erase-config/restart an ASA firewall
[manage.asa]
collect = [ "sh run", "sh ip int brief" ]
erase = [ "write erase" ]
restart = [ "reload", "no" ]
```

### Accessing Tests

Execute:
```code
python -m swinburne_smartrack -h
```

Compiling library
```code
python -m build
```
## Programs

Not developed yet....

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

#### Testing

```console
python -m swinburne_smartrack.smartrack
``` 

The application will:

1) Open a dialog asking you to select the SmartRack servers (need VPN if doing from home)
2) Open a dialog asking you to enter username and password for SmartRack
3) Download all currently booked devices
4) Display login details for all devices in a table

The above command line has one optional parameter where you can set the logging level to display
more detailed information while the program is running

```console
python -m swinburne_smartrack.smartrack -h
usage: smartrack.py [-h] [-d {DEBUG,INFO,WARNING,ERROR,CRITICAL}]

SmartRack Test Suite

options:
  -h, --help            show this help message and exit
  -d {DEBUG,INFO,WARNING,ERROR,CRITICAL}, --debug {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Set logging level (default: INFO)
```

#### Usage

To be developed...


