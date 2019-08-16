#--------------------------------------------------------------------------
# I2C
# SPI
#--------------------------------------------------------------------------
echo "********* SPI/I2C ******"
echo "Make sure SPI is enabled"
echo "Make sure I2C is enabled"
echo "************************"
echo "use raspi-config       "
echo "then reboot            "
echo "************************"
read -p "Do you want to run raspi-config? [Y]/N " ans
if [ "$ans" != "N" ]
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
    sudo apt-get -y install ipython 
    sudo apt-get -y install jed
    sudo apt-get -y install geany
    sudo apt-get -y install python-qt4
    sudo apt-get -y install pigpio
    sudo apt-get -y install python-pigpio
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
    sudo python2.7 -m pip install git+https://github.com/abelectronicsuk/ABElectronics_Python_Libraries.git
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
    ## New method via systemd
    systemctl start pigpiod
    systemctl enable pigpiod
    ## Old method via upstart system
    #f="/tmp/pigpio.conf"
    #g="/etc/init/pigpio.conf"
    #echo '# pigpio'                       > $f
    #echo 'description	"PIGPIO daemon"' >> $f
    #echo 'start on runlevel [2345]'      >> $f
    #echo 'stop on runlevel [!2345]'      >> $f
    #echo 'respawn'                       >> $f
    #echo 'respawn limit 10 5'            >> $f
    #echo 'umask 022'                     >> $f
    #echo 'expect stop'                   >> $f
    #echo 'console none'                  >> $f
    #echo 'pre-start script'              >> $f
    #echo '    test -x /usr/bin/pigpiod || { stop; exit 0; }' >> $f
    #echo 'end script'                    >> $f
    #echo 'exec /usr/bin/pigpiod'         >> $f
    #sudo mv $f $g
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
    echo '[Desktop Entry]'                                  > $f
    echo 'Type=Application'                                >> $f
    echo 'NAME=pHox'                                       >> $f
    echo 'Exec=sudo /usr/bin/python /home/pi/pHox/pHox.py' >> $f
    echo 'X-GNOME-Autostart-enabled=true'                  >> $f
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
    echo '#interface eth0'                    >> $f
    echo 'static ip_address=192.168.0.90/24'  >> $f
    echo 'static routers=192.168.0.1'         >> $f
fi


