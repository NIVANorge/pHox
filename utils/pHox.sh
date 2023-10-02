#!/bin/bash

source /home/pi/env/bin/activate

python /home/pi/pHox/pHox_gui.py --localdev > /home/pi/log_pHox.out 2>&1

