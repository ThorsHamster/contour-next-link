# contour-next-link

Connecting sensor between Medtronic Contour NextLink 2.4 and Homeassistant. See also [smarthome](https://github.com/ThorsHamster/smarthome).

## Getting Started
* Make sure you have the following dependencies installed:  
    * `python`
    * `pip`
    * `python-dev`
    * `libusb-1.0-0-dev`
    * `libudev-dev`
    * `liblzo2-dev`
    * `libhidapi-dev`
    * `libhidapi-libusb0`

* Clone this project
* Set linux udev rules, like described [here](install/Install.md)
* Install the dependencies from Pipfile.lock with
```
$ pipenv install --deploy
```
* Plug in your Contour NextLink 2.4 USB stick

Now you can try the script by calling the module from the parent directory
```
$ pipenv run python main.py
```

## Known Issues
* Assumed pump time was in UTC, but this doesn't ring true for non DST times (in Melbourne, anyway)
