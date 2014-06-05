import katdal
import katpoint
import os
import pylab as plt
import numpy as np
import scipy.interpolate as interpolate

def select_and_average(filename, average_time):
    # Read a file into katdal, and average the data to the prescribed averaging time
    # Returns the weather data and timestamps with the correct averaging interval
    data = katdal.open(filename)

    raw_timestamps = data.sensor.timestamps
    raw_wind_speed = data.sensor.get('Enviro/asc.wind.speed')
    raw_temperature = data.sensor.get('Enviro/asc.air.temperature')
    raw_dumptime = data.dump_period

    # Get azel of each antenna and separation of each antenna
    sun = katpoint.Target('Sun, special',antenna=data.ants[0])
    alltimestamps=data.timestamps[:]
    solar_seps=np.zeros_like(alltimestamps)
    for dumpnum,timestamp in enumerate(alltimestamps):
        azeltarget = katpoint.construct_azel_target(katpoint.deg2rad(data.az[dumpnum,0]),katpoint.deg2rad(data.el[dumpnum,0]))
        azeltarget.antenna = data.ants[0]
        solar_seps[dumpnum] = katpoint.rad2deg(azeltarget.separation(sun,timestamp))
    #Determine number of dumps to average
    num_average = max(int(np.round(average_time/raw_dumptime)),1)

    #Array of block indices
    indices = range(min(num_average,raw_timestamps.shape[0]),raw_timestamps.shape[0]+1,min(num_average,raw_timestamps.shape[0]))
    
    timestamps = np.average(np.array(np.split(raw_timestamps,indices)[:-1]),axis=1)
    wind_speed = np.average(np.array(np.split(raw_wind_speed,indices)[:-1]),axis=1)
    temperature = np.average(np.array(np.split(raw_temperature,indices)[:-1]),axis=1)

    dump_time = raw_dumptime * num_average

    return (timestamps,alltimestamps , wind_speed, temperature, dump_time, solar_seps, data.ants[0])


def rolling_window(a, window,axis=-1,pad=False,mode='reflect',**kargs):
    """
     This function produces a rolling window shaped data with the rolled data in the last col
        a      :  n-D array of data  
        window : integer is the window size
        axis   : integer, axis to move the window over
                 default is the last axis.
        pad    : {Boolean} Pad the array to the origanal size
        mode : {str, function} from the function numpy.pad
        One of the following string values or a user supplied function.
        'constant'      Pads with a constant value.
        'edge'          Pads with the edge values of array.
        'linear_ramp'   Pads with the linear ramp between end_value and the
                        array edge value.
        'maximum'       Pads with the maximum value of all or part of the
                        vector along each axis.
        'mean'          Pads with the mean value of all or part of the
                      con  vector along each axis.
        'median'        Pads with the median value of all or part of the
                        vector along each axis.
        'minimum'       Pads with the minimum value of all or part of the
                        vector along each axis.
        'reflect'       Pads with the reflection of the vector mirrored on
                        the first and last values of the vector along each
                        axis.
        'symmetric'     Pads with the reflection of the vector mirrored
                        along the edge of the array.
        'wrap'          Pads with the wrap of the vector along the axis.
                        The first values are used to pad the end and the
                        end values are used to pad the beginning.
        <function>      of the form padding_func(vector, iaxis_pad_width, iaxis, **kwargs)
                        see numpy.pad notes
        **kargs are passed to the function numpy.pad
        
    Returns:
        an array with shape = np.array(a.shape+(window,))
        and the rolled data on the last axis
        
    Example:
        import numpy as np
        data = np.random.normal(loc=1,scale=np.sin(5*np.pi*np.arange(10000).astype(float)/10000.)+1.1, size=10000)
        stddata = rolling_window(data, 400).std(axis=-1)
    """
    if axis == -1 : axis = len(a.shape)-1 
    if pad :
        pad_width = []
        for i in xrange(len(a.shape)):
            if i == axis: 
                pad_width += [(window//2,window//2 -1 +np.mod(window,2))]
            else :  
                pad_width += [(0,0)] 
        a = np.pad(a,pad_width=pad_width,mode=mode,**kargs)
    a1 = np.swapaxes(a,axis,-1) # Move target axis to last axis in array
    shape = a1.shape[:-1] + (a1.shape[-1] - window + 1, window)
    strides = a1.strides + (a1.strides[-1],)
    return np.lib.stride_tricks.as_strided(a1, shape=shape, strides=strides).swapaxes(-2,axis) # Move original axis to 


def select_environment(timestamps, wind_speed, temperature, dump_time, antenna, condition='normal'):
    """ Flag data for environmental conditions. Options are:
    normal: Wind < 9.8m/s, -5C < Temperature < 40C, DeltaTemp < 3deg in 20 minutes
    optimal: Wind < 2.9m/s, -5C < Temperature < 35C, DeltaTemp < 2deg in 10 minutes
    ideal: Wind < 1m/s, 19C < Temp < 21C, DeltaTemp < 1deg in 30 minutes

    return 3 sets of flags for the normal ideal and optimal cases (one flag per timestamp) 
    """

    # Get the sustained 5 minute wind speeds
    wind_5min = np.mean(rolling_window(wind_speed, int(np.round(300.0/dump_time)), pad=True),axis=1)
    temp_10min = np.mean(rolling_window(temperature, int(np.round(600.0/dump_time)), pad=True), axis=1)

    # Fit a smooth function (cubic spline) in time to the temperature data
    fit_temp = interpolate.UnivariateSpline(timestamps,temp_10min,k=3,s=0)

    #fit_temp_grad = fit_temp.derivative()

    # Day/Night
    # Night is defined as when the Sun is at -5deg.
    # Set up Sun target
    sun = katpoint.Target('Sun, special',antenna=antenna)
    sun_elevation = katpoint.rad2deg(sun.azel(timestamps)[1])

    # Apply limits on environmental conditions
    good = [True] * timestamps.shape[0]

    # Set up limits on environmental conditions
    if condition=='ideal':
        wind5minlim    =   1.
        windgustlim    =   1.
        temp_low       =   19.
        temp_high      =   21.
        deltatemp      =   1./(30.*60.)
        sun_elev_lim   =   -5.
    elif condition=='optimal':
        wind5minlim    =   2.9
        windgustlim    =   4.1
        temp_low       =   -5.
        temp_high      =   35.
        deltatemp      =   2./(10.*60.)
        sun_elev_lim    =   -5.
    elif condition=='normal':
        wind5minlim    =   9.8
        windgustlim    =   13.4
        temp_low       =   -5.
        temp_high      =   40.
        deltatemp      =   3./(20.*60.)
        sun_elev_lim   =   100.       #Daytime
    else:
        return good

    #Average and wind gust limits
    good = good & (wind_5min < wind5minlim)
    good = good & (wind_speed < windgustlim)

    #Temperature limits
    good = good & ((fit_temp(timestamps) > temp_low) & (fit_temp(timestamps) < temp_high))
    
    #Get the temperature gradient
    temp_grad = [fit_temp.derivatives(timestamp)[1] for timestamp in timestamps]
    good = good & (np.abs(temp_grad) < deltatemp)

    #Day or night?
    good = good & (sun_elevation < sun_elev_lim)

    return good

                
def plot_weather(filename,timestamps,alltimestamps,wind_speed,temperature,dump_time,solar_seps,antenna,normalflag,optimalflag,idealflag):

    #Get the flag bins
    rejects = ~normalflag
    normal = normalflag & (~optimalflag)
    optimal = optimalflag & (~idealflag)
    ideal = idealflag

    timeoffsets = (timestamps - timestamps[0])/3600.0
    alltimes = (alltimestamps - alltimestamps[0])/3600.0
    #Set up the figure
    fig = plt.figure(figsize=(8.3,11.7))
    #date format for plots
    fig.subplots_adjust(hspace=0.0)
    #Plot the gain vs elevation for each target
    ax1 = plt.subplot(411)
    plt.xlim(timeoffsets[0], timeoffsets[-1])
    plt.title('Atmospheric Conditions')
    plt.ylabel('Wind Speed (km/s)')
    # Wind
    plt.plot(timeoffsets[np.where(rejects)], wind_speed[np.where(rejects)], 'r.')
    plt.plot(timeoffsets[np.where(normal)], wind_speed[np.where(normal)], 'b.')
    plt.plot(timeoffsets[np.where(optimal)], wind_speed[np.where(optimal)], 'g.')
    plt.plot(timeoffsets[np.where(ideal)], wind_speed[np.where(ideal)], 'y.')
    # Temperature
    ax2 = plt.subplot(412)
    plt.xlim(timeoffsets[0], timeoffsets[-1])
    plt.ylabel('Temperature (Celcius)')
    plt.plot(timeoffsets[np.where(rejects)], temperature[np.where(rejects)], 'r.')
    plt.plot(timeoffsets[np.where(normal)], temperature[np.where(normal)], 'b.')
    plt.plot(timeoffsets[np.where(optimal)], temperature[np.where(optimal)], 'g.')
    plt.plot(timeoffsets[np.where(ideal)], temperature[np.where(ideal)], 'y.')
    # Sun Elevation
    sun = katpoint.Target('Sun, special',antenna=antenna)
    sun_elevation = katpoint.rad2deg(sun.azel(timestamps)[1])
    ax3 = plt.subplot(413)
    plt.xlim(timeoffsets[0], timeoffsets[-1])
    plt.ylabel('Sun elevation (deg.)')
    plt.plot(timeoffsets[np.where(rejects)], sun_elevation[np.where(rejects)], 'r.')
    plt.plot(timeoffsets[np.where(normal)], sun_elevation[np.where(normal)], 'b.',label="Normal")
    plt.plot(timeoffsets[np.where(optimal)], sun_elevation[np.where(optimal)], 'g.',label="Optimal")
    plt.plot(timeoffsets[np.where(ideal)], sun_elevation[np.where(ideal)], 'y.',label="Ideal")
    legend = plt.legend(loc='best')
    plt.setp(legend.get_texts(), fontsize='small')

    # Sun distance
    ax4=plt.subplot(414)
    plt.xlim(timeoffsets[0], timeoffsets[-1])
    plt.ylim(0.,180.)
    plt.ylabel('Pointing-Sun angle (deg.)')
    plt.xlabel('Time since start (hours)')
    plt.plot(alltimes, solar_seps)
    
    fig.savefig(filename)

def condition_report(filename, output_dirname = '.', average_time=5.0):
    timestamps, alltimestamps, wind_speed, temperature, dump_time, sun_distance, antenna = select_and_average(filename, average_time)
    #Got the data now make the bins
    normalflag=select_environment(timestamps, wind_speed, temperature, dump_time, antenna, condition='normal')
    optimalflag=select_environment(timestamps, wind_speed, temperature, dump_time, antenna, condition='optimal')
    idealflag=select_environment(timestamps, wind_speed, temperature, dump_time, antenna, condition='ideal')
    output_filename = os.path.join(output_dirname, os.path.splitext(os.path.basename(filename))[0]+'_ConditionReport.pdf')
    plot_weather(output_filename,timestamps,alltimestamps,wind_speed,temperature,dump_time,sun_distance,antenna,normalflag,optimalflag,idealflag)

