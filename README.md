# pHox
Software for operating box instruments for automated spectrophotometric measurements (pH and CO3) developed in NIVA.
It also supports pCO2 instrument (TODO: description). 

#### supported box configurations:
* pH 
* pH + pCO2
* CO3
* pCO2

### Hot to use the program 
Normally, the boxes are set up for automatically starting software. If it does not happen, 
you can start it manually with: 

##### How to start the program manually: 

``` sudo python pHox_gui.py [OPTIONS]```  #append with needed options 

By default the program is starting pH mode. 
Append the command line argument with parameters if you want to change the mode:
 
* --pco2   # to run it in pco2 + pH mode
* --co3    # to run it in CO3 mode
* --onlypco2 # to run it in pCO2 mode 
* --debug  # to show logging messages of debug level (by default, only info level messages are shown)
* --localdev # to run the program in a local development mode (**only for testing**)
* --nodye  # do not inject dye during sample for not making a cuvette dirty (**only for testing**) 
* --stability # to test stability of a spectrophotometer. It this option is enabled,every time we get spectrum 
 to update the plot, this spectrum is also saved into sp_stability.log (**only for testing**)


### How to install the code when using the new box 
1. pull this repository
``` git pull origin https://github.com/NIVANorge/pHox.git ```
2. run install3.sh
```sudo bash install3.sh```
3. create the file **box_id.txt** in your home directory
4. make sure that the configuration for you box is in configs/ folder, if it is not there, 
create it. 

### Code  description

###### Versions and libraries

The code is written on Python and should be used with versions >= python3.7 
For the GUI development we used PyQT library

##### Folder structure  
 ![](utils/folder_structure.png)
 * spt,evl and log files description 
 
### Graphical part description 
Libraries: pyQT, pyqtgraph

###### Classes structure for GUI panel create 
![](utils/classes.png)

When you call the main module, pHox_gui.py, the main graphical panel is created. 
Depending on the options, it will be Panel_pH, Panel_PCO2_only or Panel_CO3
In these classes, all widgets, all timers are created.  

######  qss styles 
###### Live plotting

### Communication part

![](utils/instrument_classes.png)
* Communication with the spectrometer
* Communication with raspberri pi, valves, pumps
* Udp and ferrybox data 

#### TODO: Subthemes: 

* Configuration files 
* Local testing 
* Measurement algorithm 
* Light source or LED, auto adjustment 
* Autostart and autostop 


* precisions
* asynchronous parts

* Logic and modes 
    * Continuous mode 
    * Single measurement mode
    * Calibration mode 


 