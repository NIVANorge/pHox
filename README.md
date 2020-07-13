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
 
| Command     |   Description                                  |
|-------------|:-----------------------------------------------|
|--co3        | CO3 mode                                       |
|--pco2       | pco2 + pH mode                                 |
|--onlypco2   | only pCO2 mode                                 |
|--localdev   | local development mode (**testing**)           |
|--debug      | show logging messages of debug level           |
|--nodye      | do not inject dye during sample (**testing**)  |
|--stability  | test stability of a spectrophotometer          |

### How to install the code when using the new box 
1. pull this repository
``` git pull origin https://github.com/NIVANorge/pHox.git ```
2. run install3.sh
```sudo bash install3.sh```
3. create the file **box_id.txt** in your home directory
4. make sure that the configuration for you box is in configs/ folder, if it is not there, 
create it. 

### Program  description

###### Versions and libraries

The program is written on Python and should be used with versions >= python3.7 
For the GUI development we used PyQT library


Libraries: pyQT, pyqtgraph

##### Folder structure  
 ![](utils/folder_structure.png)
 * spt,evl and log files description 
 

### Graphical part description 
###### Classes structure for GUI panel create 
![](utils/classes.png)


When you call the main module, pHox_gui.py, the main graphical panel is created. 
Depending on the options, it will be Panel_pH, Panel_PCO2_only or Panel_CO3
In these classes, all widgets, all timers are created.  

######  qss styles 
###### Live plotting

### Communication part
* Configuration files 
* Local testing 
* Measurement algorithm 
* Light source or LED, auto adjustment 
* Autostart and autostop 

![](utils/instrument_classes.png)
* Communication with the spectrometer
* Communication with raspberri pi, valves, pumps
* Udp and ferrybox data 

### Logic desctiption 
* Logic and modes 
    * Continuous mode 
    * Single measurement mode
    * Calibration mode 
#### Auto Adjusting of light source or LEDs 
In order to make a pH measurement, we need a strong light signal. 
The light intensity on spectrophotometer should be close to Threshold value at 3 
defined wavelengths (NIR,HI,I2) for pH and one wavelength for CO3. 

![](utils/autoadjust_fig_upd.png) 

Threshold depends on the maximum possible light intensity and depends on a Spectrophotometer type.

        "LIGHT_THRESHOLD_STS": 15500,            
        "LIGHT_THRESHOLD_FLAME": 60000  
        
The intensity can be regulated by changing the intensity of LEDs (or light source) can be regulated (values 0-100)
or by changing the spectrophotometer integration time. Both parameters can be changed 
either manually (using sliders in the Manual tab, int_time combobox in the config tab) or automatically.

In the configuration file, the option for auto adjusting is defined: it can be "ON", "OFF", 
or "ON_NORED"

        "Autoadjust_state": "ON"

If state is ON, then at each measurement, the autoadjust function will be run.        
if "ON_NORED" is chosen, only blue and green will be checked for pH. Red can be blocked by biofouling, 
but is not as important for the results as blue and yellow. For CO3, the regular autoadjust will happen for both 
"ON" and "ON_NORED" since the instensity for CO3 is controlled only by spectrophotometer integration time.

If state is 'ON' or 'ON_NORED', the autoAdjust_LED or autoAdjust_IntTime.
The code contains function for auto adjusting LED
Every time measurement is started (both in single measurement mode, single measurement mode 
and if auto adjust button is clicked), the autoadjust function will be triggered. 


Then, the options are also shown in  the GUI, in the config tab. 





* precisions
* asynchronous parts
#### TODO: Subthemes: 








 