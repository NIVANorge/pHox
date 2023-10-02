#!/bin/bash

# exit on error
set -e

# raspberry pi does ask for password by default
sudo apt update && sudo apt -y upgrade
sudo apt install -y build-essential
sudo apt install -y libhdf5-dev \
    libusb-0.1-4 \
    libatlas-base-dev \
    ffmpeg \
    libsm6 \
    libxext6 \
    '^libxcb.*-dev' \
    libx11-xcb-dev \
    libglu1-mesa-dev \
    libxrender-dev \
    libxi-dev \
    libxkbcommon-dev \
    libxkbcommon-x11-dev \
    qtbase5-dev \
    qtchooser \
    qt5-qmake \
    qtbase5-dev-tools \
    pigpio
sudo apt autoremove -y

# install and activate venv
python3 -m pip install --user --upgrade pip
python3 -m pip install --user virtualenv
python3 -m venv $HOME/env
