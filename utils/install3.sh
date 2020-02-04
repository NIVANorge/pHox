#--------------------------------------------------------------------------
# I2C
# SPI
#--------------------------------------------------------------------------
echo "********* SPI/I2C ******"
echo "Make sure SPI is enabled"
echo "Make sure I2C is enabled"
echo "************************"
echo "You can start the script to run raspi-config"
echo "use raspi-config       "
echo "then reboot            "
echo "************************"
read -p "Skip? Y/[N] " ans
if [ "$ans" != "Y" ]
then 
    exit 0
fi
#--------------------------------------------------------------------------
# SSH-key
#--------------------------------------------------------------------------
echo "******** KEYGEN ********"
echo "Accept all defauts      "
echo "Leave passphrase blank  "
echo "************************"
echo "                        "
read -p "Skip? Y/[N] " ans
if [ "$ans" != "Y" ]
then
    ssh-keygen
fi
#--------------------------------------------------------------------------
# GITHUB ssh
#--------------------------------------------------------------------------
echo "******** GITHUB ********"
echo "Upload content of       "
echo "~/.ssh/id_rsa.pub       " 
echo "to PHOX repo on GITHUB  "
echo "************************"
echo "                        "
read -p "Press ENTER when done" ans
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
    sudo apt-get -y install python3-pigpio
    sudo apt-get -y install python3-pandas
    sudo apt-get -y install python3-usb
    sudo apt-get -y install python3-pyqtgraph
    sudo pip3 install asyncqt
    sudo pip3 install asyncio
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

sudo pip3 install seabreeze

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
    echo 'Exec=sudo /usr/bin/python3 /home/pi/pHox/pHox_gui.py' >> $f
    echo 'X-GNOME-Autostart-enabled=true'                      >> $f
    mv $f $g
fi
#--------------------------------------------------------------------------
# Install pHox from GIT
#--------------------------------------------------------------------------
echo "********* PHOX *********"
echo "Install PHOX            "
echo "from GIT                "
echo "************************"
echo "                        "
read -p "Skip? Y/[N] " ans
if [ "$ans" != "Y" ]
then
    cd
    git clone git@github.com:NIVANorge/pHox.git
fi
#--------------------------------------------------------------------------
# Install static IP on eth0
#--------------------------------------------------------------------------
echo "********* ETH0 *********"
echo "Install ETH0            "
echo "Static 192.168.0.90     "
echo "************************"
echo "                        "
read -p "Skip? Y/[N] " ans
if [ "$ans" != "Y" ]
then
    f="/etc/dhcpcd.conf"
    echo 'interface eth0'                 >> $f
    echo 'static ip_address=192.168.0.9'  >> $f
    echo 'static routers=192.168.0.1'     >> $f
fi




