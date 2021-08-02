
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

plt.style.use('ggplot')
df = pd.read_csv('data/data_pH/pH.log')
df['Time'] = pd.to_datetime(df['Time'],format = '%Y-%m-%d_%H:%M')
fig, ax = plt.subplots(2)
#df = df[df.Time > '2021-07-15']

myFmt = mdates.DateFormatter('%m-%d %H:%M')

ax[0].set_title('pH insitu')
ax[0].set_ylim(0,12)
ax[1].set_title('Latitude')
ax[0].set(xticklabels=[])
ax[1].xaxis.set_major_formatter(myFmt)
ax[0].plot(df.Time.values, df.pH_insitu.values,'o--',
			markeredgecolor = 'k',markersize = 3)
ax[1].plot(df.Time.values,df.Lat.values,'o--',
			markeredgecolor = 'k',markersize = 3)
plt.xticks(rotation=20)
plt.tight_layout()
plt.show()

