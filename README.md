# pHox
Software for running the pH Ferrybox box

#### available configurations:
* pH
* pH + pCO2
* CO3

### How to install the code when using the new box 

1. pull this repository
```
git pull origin https://github.com/NIVANorge/pHox.git
```
2. run install3.sh
```
bash install3.sh
```
3. create the file box_id.txt in your home directory
3. make sure that the configuration for you box is in configs/ folder, if it is not there, 
create it. 

### How to run the code  
```
sudo python pHox_gui.py  #append with needed options
```

append the command line argument with parameters: 

* --pco2   # to run it in pco2 + pH mode
* --co2    # to run it in CO3 mode
* --debug  # to show logging messages of debug level (by default, only info level messages are shown)
* --localdev # to run the program in a local development mode (only for testing)
* --nodye  # Do not inject dye during sample for not making a cuvette dirty (only for testing) 
* --stability # to test stability of a spectrophotomer. It this option is enabled,every time we get spectrum 
 to update the plot, this spectrum is also saved into sp_stability.log (only for testing)