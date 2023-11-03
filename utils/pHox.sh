#!/bin/bash

sudo pigpiod

source /home/pi/env/bin/activate
python /home/pi/pHox/pHox_gui.py > /home/pi/log_pHox.out 2>&1

