# Swinburne SmartRack

Programs and Libraries to manage Cisco devices accessible via SmartRack at Swinburne University.

## Programs

Not developed yet...

## Libraries

It is expected that the user will use this package via installed programs as listed above. There
are two reasons to read the information in the **Libraries** section:

1) Testing installation prior to actual use/deployment
2) Developing new applications that use the internal libraries
 
### SmartRack

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


