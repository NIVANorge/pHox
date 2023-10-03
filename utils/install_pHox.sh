#!/bin/bash

# exit on error
set -e

# pHox will search for this file to check a pHox number
echo "pHox0" > $HOME/box_id.txt

cp pHox.sh $HOME/

# it will change an owner to root
sudo cp pHox.service /lib/systemd/system/

# activate a python environment
source $HOME/env/bin/activate
# install python modules into the venv
python -m pip install -r ../requirements.txt
python -m pip install pigpio
python -m pip install seabreeze
python -m pip install git+https://github.com/abelectronicsuk/ABElectronics_Python_Libraries.git

sudo systemctl enable pHox.service

