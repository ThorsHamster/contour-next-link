[![Tests](https://github.com/ThorsHamster/contour-next-link/actions/workflows/main.yml/badge.svg)](https://github.com/ThorsHamster/contour-next-link/actions/workflows/main.yml)

# contour-next-link

Connecting script between Medtronic Contour NextLink 2.4 and Homeassistant. See also [smarthome](https://github.com/ThorsHamster/smarthome).

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
$ python -m pip install --upgrade pipenv wheel
$ pipenv install --deploy
```
* Add all necessary constants to the environment variables, e.g. in a bashrc file
```
$ nano ~/.bashrc
```
* Add following exports to your bashrc file:
```
export HOMEASSISTANT_IP=<IP OF YOUR HOMEASSISTANT SERVER>
export HOMEASSISTANT_PORT=<PORT OF YOUR HOMEASSISTANT SERVER>
export HOMEASSISTANT_TOKEN=<LONG LIVED ACCESS TOKEN>
```
You can find a manual on how to create a long lived access token [here](https://www.home-assistant.io/docs/authentication/) or [here](https://developers.home-assistant.io/docs/auth_api/#long-lived-access-token)
* Update the bash environment with
```
$ source ~/.bashrc
```
* Plug in your Contour NextLink 2.4 USB stick

Now you can try the script by calling the module from the parent directory
```
$ pipenv run python main.py
```

## Known Issues
* Assumed pump time was in UTC, but this doesn't ring true for non DST times (in Melbourne, anyway)
* Drops some packages and gets instable after some days of continous work

## Optional

### Daily reboot

To improve the runtime stability, a daily reboot could be done with e.g.
1. Open sudo crontab
    ```
    $ sudo crontab -e
    ```
2. Add daily restarts at e.g. 10am (see [here](https://crontab.guru/) for help)
    ```
    $ 0 10 * * * /sbin/shutdown -r now
    ```
3. Create startup bash script in your home drive like /home/<YOUR USER>/startup.sh
    ```
    #!/bin/bash

    export HOMEASSISTANT_IP=<IP OF YOUR HOMEASSISTANT SERVER>
    export HOMEASSISTANT_PORT=<PORT OF YOUR HOMEASSISTANT SERVER>
    export HOMEASSISTANT_TOKEN=<LONG LIVED ACCESS TOKEN>
    
    tmux new-session -d -c "/home/<YOUR USER>/contour-next-link/" -s 0 "pipenv run python main.py"

    ```
4. Open user crontab
    ```
    $ crontab -e
    ```
5. Add reboot command
    ```
    SHELL=/bin/bash
    PWD=/home/<YOUR USER>
    LOGNAME=<YOUR USER>
    HOME=/home/<YOUR USER>
    LANG=en_GB.UTF-8
    SHLVL=1
    PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin
    _=/bin/env
    @reboot /bin/bash /home/<YOUR USER>/startup.sh >> /dev/null 2>&1
    ```
   
You can now connect to the session via
    ```
    $ tmux attach-session -t 0
    ```
