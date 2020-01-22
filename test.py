import matplotlib.pyplot as plt
import pandas as pd 


df = pd.read_csv('sp_stability.log')
plt.plot(df.led0.values,'b', label = 'led0')
plt.plot(df.led1.values,'y', label = 'led1')
plt.plot(df.led2.values,'r', label = 'led2')
plt.legend()
plt.show()
#print (df)