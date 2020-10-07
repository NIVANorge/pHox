


#--------------------------------------------------------------------------
echo "********* SPI/I2C ******"
echo "Make sure SPI is enabled"
echo "Make sure I2C is enabled"
echo "Make sure VNC is enabled"
echo "Set up the correct time"
echo "************************"
echo "You can start the script to run raspi-config"
echo "use raspi-config       "
echo "then reboot            "
echo "************************"


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
    sudo apt-get -y install synaptic
    sudo apt-get -y install jed
    sudo apt-get -y install geany
    sudo apt-get -y install ipython 
    sudo apt-get -y install pigpio
    sudo apt-get -y install python3-pyqt5
    sudo apt-get -y install python3-pandas
    sudo apt-get -y install python3-usb
    sudo apt-get -y install python3-pyqtgraph
    sudo pip3 install asyncqt
    sudo pip3 install asyncio
    sudo pip3 install seabreeze
fi

#---
# Seabreeze 
# 
echo "Install Seabreeze package "
echo "Raspbian includes configuration for pip to use piwheels by default.  "
echo "If you're using an alternative distribution (or an older version of Raspbian)"
echo "you can use piwheels by placing the following lines in /etc/pip.conf:"
echo "[global]"
echo " extra-index-url=https://www.piwheels.org/simple " 



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
echo "Install autostart file  "
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




