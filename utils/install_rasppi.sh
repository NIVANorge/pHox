#--------------------------------------------------------------------------
# Elementary packages
#--------------------------------------------------------------------------
echo "******* PACKAGES *******"
echo "Adding packages         "
echo "************************"
echo "                        "
read -p "Skip? Y/[N] " ans
if [ "$ans" != "Y" ]
then
    sudo apt-get update && apt-get -y upgrade
    sudo apt-get install -y build-essential
    sudo apt-get install -y libhdf5-dev \
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

    python3 -m pip install --user --upgrade pip
    python3 -m pip install --user virtualenv
    python3 -m venv env
    source env/bin/activate
    python3 -m pip install -r requirements.txt
fi

#--------------------------------------------------------------------------
# Seabreeze
#--------------------------------------------------------------------------
echo "Install Seabreeze package "
echo "Raspbian includes configuration for pip to use piwheels by default.  "
echo "If you're using an alternative distribution (or an older version of Raspbian)"
echo "you can use piwheels by placing the following lines in /etc/pip.conf:"
echo "[global]"
echo " extra-index-url=https://www.piwheels.org/simple "
read -p "Skip? Y/[N] " ans
if [ "$ans" != "Y" ]
then
    sudo python3 -m pip install seabreeze
fi

#--------------------------------------------------------------------------
# Install ABElectronics package
#--------------------------------------------------------------------------
echo "***** ABELECTRONICS ****"
echo "Adding ABElectronics    "
echo "************************"
echo "                        "
read -p "Skip? Y/[N] " ans
if [ "$ans" != "Y" ]
then
    sudo python3 -m pip install git+https://github.com/abelectronicsuk/ABElectronics_Python_Libraries.git
fi

#--------------------------------------------------------------------------
# Install PIGPIO
#--------------------------------------------------------------------------
echo "******** PIGPIO ********"
echo "Install PIGPIO          "
echo "************************"
echo "                        "
read -p "Skip? Y/[N] " ans
if [ "$ans" != "Y" ]
then
    sudo systemctl start pigpiod
    sudo systemctl enable pigpiod
fi

#--------------------------------------------------------------------------
# Install SSH
#--------------------------------------------------------------------------
echo "******** SSH ***********"
echo "Install SSH             "
echo "************************"
echo "                        "
read -p "Skip? Y/[N] " ans
if [ "$ans" != "Y" ]
then
    sudo systemctl enable ssh
    sudo systemctl start ssh
fi

#--------------------------------------------------------------------------
# Install Autostart
#--------------------------------------------------------------------------
echo "****** AUTOSTART *******"
echo "Install autostart file (NOT FOR PCO2)"
echo "************************"
echo "                        "
read -p "Skip? Y/[N] " ans
if [ "$ans" != "Y" ]
then
    f="/tmp/pHox.desktop"
    g="/home/pi/.config/autostart/pHox.desktop"
    if [ ! -d "/home/pi/.config/autostart" ]
    then
        mkdir -p "/home/pi/.config/autostart"
    fi
    echo '[Desktop Entry]'                                     >  $f
    echo 'Type=Application'                                    >> $f
    echo 'NAME=pHox'                                           >> $f
    echo "Exec=sudo bash -c 'cd /home/pi/pHox && /usr/bin/python3 /home/pi/pHox/pHox_gui.py'" >> $f
    cp $f "/home/pi/Desktop"
    echo 'X-GNOME-Autostart-enabled=true'                      >> $f
    mv $f $g
fi

#--------------------------------------------------------------------------
# Install Autostart
#--------------------------------------------------------------------------
echo "****** AUTOSTART for PCO2 *******"
echo "Install autostart file for PCO2"
echo "************************"
echo "                        "
read -p "Skip? Y/[N] " ans
if [ "$ans" != "Y" ]
then
    f="/tmp/pHox.desktop"
    g="/home/pi/.config/autostart/pHox.desktop"
    if [ ! -d "/home/pi/.config/autostart" ]
    then
        mkdir -p "/home/pi/.config/autostart"
    fi
    echo '[Desktop Entry]'                                     >  $f
    echo 'Type=Application'                                    >> $f
    echo 'NAME=pHox'                                           >> $f
    echo "Exec=sudo bash -c 'cd /home/pi/pHox && /usr/bin/python3 /home/pi/pHox/pco2.py'" >> $f
    cp $f "/home/pi/Desktop"
    echo 'X-GNOME-Autostart-enabled=true'                      >> $f
    mv $f $g
fi

#--------------------------------------------------------------------------
# Install static IP on eth0
#--------------------------------------------------------------------------
echo "********* ETH0 *********"
echo "Install ETH0            "
echo "Static 192.168.0.9     "
echo "************************"
echo "                        "
read -p "Skip? Y/[N] " ans
if [ "$ans" != "Y" ]
then
    f="/etc/dhcpcd.conf"
    {
    echo -e '\ninterface eth0' '\nstatic ip_address=192.168.0.9/24' '\nstatic routers=192.168.0.1'
    } >> $f
fi
