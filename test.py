import matplotlib.pyplot as plt
import pandas as pd 
import numpy as np



df = pd.read_csv('sp_stability.log')
autoadj = df.specint.where(df.specint>500).dropna()

plt.plot(df.led0.values,'b', label = 'led0')
plt.plot(df.led1.values,'y', label = 'led1')
plt.plot(df.led2.values,'r', label = 'led2')
plt.axhline(y = 15000,ls = '--')
plt.axhline(y = 16000,ls = '--')
plt.axhline(y = 12000,ls = '--')


print (autoadj.values)
print (df.specint.values)
#ind = np.where(df.specint.values == autoadj.values[0])
#plt.axvline(x=ind,ls = "--")

plt.plot(df.specint.values)

plt.legend()
plt.show()
#print (df)