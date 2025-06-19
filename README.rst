===============
raspi-gpio-mpdc
===============
This is a configurable Python service to run on `Raspberry Pi <https://www.raspberrypi.org>`_.

**raspi-gpio-mpdc** runs a Python script as a service on Raspberry Pi. It uses the `GPIO Zero <https://github.com/gpiozero/gpiozero>`_ package which allows 
selecting among various underlying pin factories. Tested with `pigpio <http://abyz.me.uk/rpi/pigpio/index.html>`_ library only.

Various GPIO inputs connected to buttons and rotary encoders can be configured to trigger certain events to control a MPD/Mopidy server. For that purpose, `python-mpd2 <https://pypi.org/project/python-mpd2/>`_ package is used as a MPD client interface.

Required packages
-----------------
* `Mopidy <https://mopidy.com/>`_ with `Mopidy-MPD <https://mopidy.com/ext/mpd>`_ extension (or another MPD server)
* pigpiod (or any other supported pin factory library)
* GPIO Zero
* `python3-systemd <https://github.com/systemd/python-systemd>`_
* python3-mpd / `python-mpd2 <https://github.com/Mic92/python-mpd2>`_
* `raspi-mpdc <https://github.com/mikiair/raspi-mpdc>`_

Installation
------------
Download raspi-gpio-mpdc via **Code** button or from `Releases <https://github.com/mikiair/raspi-gpio-mpdc/releases>`_ page (you most likely did already).
Unzip the received file:

   ``unzip raspi-gpio-mpdc-main.zip -d ~/raspi-gpio-mpdc``

Configure the service by editing the file ``raspi-gpio-mpdc.conf`` according to your external hardware circuit set-up (see Configuration_).
Then simply run the script ``install`` in the **script** sub-folder. It will download and install the required packages, 
copy the files to their destinations, will register the service, and finally start it.

If you need to change the configuration after installation, you might use the script ``reconfigure`` after editing the source configuration file.
This will stop the service, copy the changed configuration file to **/etc** folder (overwrites previous version!), and then start the service again.

If you downloaded a newer version of the service the script ``update`` will handle stop and start of the service, and will copy the new Python and service files.
However, this will not update any underlying packages or services.

For uninstall, use the provided script ``uninstall``.

Configuration
-------------
The configuration is defined in the file ``raspi-gpio-mpdc.conf``. Before installation, you will find the source file in the folder where you unzipped the package files. 
After installation, the active version is in **/etc** folder.

Section [GPIO]
==============
Section ``[GPIO]`` is mandatory. It requires one or more, but unique keys of the pattern ``ButtonN`` or ``RotEncN`` where N is replaced by integer numbers. 

1) The ``ButtonN`` key-value-pairs must be created based on this pattern:

   ``ButtonN = input_pin_number,up|dn|upex|dnex,press|release,trigger_event[,bouncetime_ms]``

   ``input_pin_number``
     The GPIO pin in BCM format to which a button is connected. If this GPIO pin is already in use by this or another application you will get an error and the service will not start.
   ``up|dn|upex|dnex``
     Selects the pull-up or pull-down resistor for the pin which can use Raspi internal ones, or *external* resistor provided by your circuit.
   ``press|release``
     Determines the button event for triggering the MPD event, namely when button is *pressed* or *released*.
   ``trigger_event``
     The MPD event to trigger. One of:
  
     * play_pause - toggle playback state between *play* and *pause*
     * play_stop - toggle playback state between *play* and *stop*
     * prev_track - select previous track
     * next_track - select next track
     * mute - toggle output state between *mute* and *unmute*
     * vol_up - increase output volume
     * vol_dn - decrease output volume
     * prev_src - switch to the previous source
     * next_src - switch to the next source
  
   ``bouncetime_ms``
     (*optional*) Defines the time in milliseconds during which subsequent button events will be ignored. Default is 50ms.

   e.g.

   ``Button0 = 9,upex,press,mute,100``

   configures pin GPIO9 as input expecting an external pull-up resistor, and acting when button is pressed with a bounce time of 100ms, to mute/unmute the output

#) The ``RotEncN`` key-value-pairs must be created based on this pattern:

   ``RotEncN = input_pin_A,input_pin_B,up|dn|upex|dnex,rot_ccw_event,rot_cw_event[,bouncetime_ms]``

   ``input_pin_A,input_pin_B``
     The pair of GPIO pins to which a rotary encoder is connected. The sequence of high-low-high transitions determines the rotation direction. (Remaining physical pins are usually connected to *GND* and a button switch.)
     If one or both of these GPIO pins are already in use by this or another application you will get an error and the service will not start.
   ``up|dn|upex|dnex``
     Selects the type of pull resistors for the two pins which can use Raspi internal ones, or *external* resistors provided by your circuit or module.
   ``rot_ccw_event``
     The event to trigger when the rotary encoder is turned counter-clockwise. Same as for buttons.
   ``rot_cw_event``
     The event to trigger when the rotary encoder is turned clockwise. Same as for buttons.
   ``bouncetime_ms``
     (*optional*) Defines the time in milliseconds during which subsequent encoder events will be ignored. Default is 20ms.
     
   e.g.
   
   ``RotEnc0 = 18,19,upex,vol_dn,vol_up``
   
   configures pins GPIO18 and GPIO19 expecting a pair of external pull-up resistors, to act as inputs from a rotary encoder which turns volume down and up, respectively.

Section [MPD]
=============
This is an optional section.

1) Optionally specify the MPD server to connect to. Default is ``localhost``.

   ``mpdhost = servername``
   
   ``servername``
     Name of the MPD server to connect to or its local IP address.
     
#) Optionally specify the port the MPD server uses. Default is 6600.

   ``mpdport = portnumber``
   
   ``portnumber``
     The port number which is used by the MPD server for connection.
   
#) Optionally specify a timeout in seconds to wait for connection built up. Default is 60 seconds.

   ``timeout = timeout_in_seconds``
   
   ``timeout_in_seconds``
     Time to wait for establishing the connection to the MPD server in seconds.
