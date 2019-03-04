#--------------------------------------------------------------------------
# I2C
# SPI
# SSH-key
#--------------------------------------------------------------------------
echo "********* SPI **********"
echo "Make sure SPI is enabled"
echo "raspi-config            "
echo "************************"
echo "                        "
echo "Press ENTER when done   "
read
echo "********* I2C **********"
echo "Make sure I2C is enabled"
echo "raspi-config            "
echo "************************"
echo "                        "
echo "Press ENTER when done   "
read
echo "******** KEYGEN ********"
echo "Accept all defauts      "
echo "Leave passphrase blank  "
echo "************************"
cd
ssh-keygen
echo "******** GITHUB ********"
echo "Upload content of       "
echo "~/.ssh/id_rsa.pub       " 
echo "to PHOX repo on GITHUB  "
echo "************************"
echo "                        "
echo "Press ENTER when done   "
read

#--------------------------------------------------------------------------
# Adding elementary packages
#--------------------------------------------------------------------------

sudo apt-get -y install synaptic
sudo apt-get -y install ipython 
sudo apt-get -y install jed
sudo apt-get -y install geany
sudo apt-get -y install python-qt4

#--------------------------------------------------------------------------
# Install ABElectronics package
#--------------------------------------------------------------------------

sudo python2.7 -m pip install git+https://github.com/abelectronicsuk/ABElectronics_Python_Libraries.git

#--------------------------------------------------------------------------
# Install pHox from GIT
#--------------------------------------------------------------------------

git clone git@github.com:NIVANorge/pHox.git



