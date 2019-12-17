format = {
    'pH':'.4f',
    "pK": ".4f", 
    "e1": ".6f",
    "e2": ".6f",
    "e3": ".6f",
    "vNTC": ".5f",
    'salinity': ".2f" ,
    "A1": ".5f",
    "A2": ".5f",
    "Tdeg": ".4f", 
    "dye_vol_inj": ".2f" ,
    "fcS": ".2f" ,
    "Anir": ".2f" }

precision  = {
    'pH':  4,
    "pK": 4, 
    "e1": 6,
    "e2": 6,
    "e3": 6,
    "vNTC": 5,
    'salinity': 2,
    "A1": 5,
    "A2": 5,
    "Tdeg": 4, 
    "vol_injected": 2,
    "Anir": 2,
    'longitude':6,
    'latitude':6,
    'fb_temperature': 3
    'salinity': 3,
    "pH_lab": 4,
    "T_lab": 4,
    "perturbation": 3
    "evalAnir": 3

    }



            s+= ',%.6f,%.6f,%.3f,%.3f' % (
            fbox['longitude'], fbox[],
            fbox['temperature'], fbox['salinity'])

        s+= ',%.4f,%.4f,%.3f,%.3f' %pHeval