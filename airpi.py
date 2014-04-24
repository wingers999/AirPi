#!/usr/bin/env python

#This file takes in inputs from a variety of sensor files, and outputs information to a variety of services
import sys
sys.dont_write_bytecode = True

import RPi.GPIO as GPIO
import ConfigParser
import time
import inspect
import os
import platform

from math import isnan
from sensors import sensor
from outputs import output

# add logging support
import logging, logging.handlers
LOG_FILENAME = os.path.join("/var/log/airpi" , 'airpi.log')
# Set up a specific logger with our desired output level
log = logging.getLogger(__name__)
# create handler and add it to the log
handler = logging.handlers.RotatingFileHandler(LOG_FILENAME, maxBytes = 40960, backupCount = 5)
log.addHandler(handler)
# create formatter and add it to the handler
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# set log message level
if len(sys.argv) > 1:
    if sys.argv[1] == "-d":
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)

# configuration files
cfgdir      = "/usr/local/etc/airpi"
sensorcfg   = os.path.join(cfgdir, 'sensors.cfg')
outputscfg  = os.path.join(cfgdir, 'outputs.cfg')
settingscfg = os.path.join(cfgdir, 'settings.cfg')

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM) #Use BCM GPIO numbers.

gpsPluginInstance = None

def pandl(mtype, msg, mvals=None):
    print("pandl vals {0} [{1}]".format(type(mvals), mvals))
    log.debug("pandl vals {0} [{1}]".format(type(mvals), mvals))
    try:
        if mvals != None:
            msg = msg.format(mvals)
    except Exception:
        raise

    print(msg)
    if mtype == "I":
        log.info(msg)
    elif mtype == "D":
        log.debug(msg)
    elif mtype == "E":
        log.error(msg)
    elif mtype == "Ex":
        log.exception(msg)

if not os.path.isfile(settingscfg):
    pandl("E", "Unable to access config file: {0}", settingscfg)
    sys.exit(1)

if not os.path.isfile(sensorcfg):
    pandl("E", "Unable to access config file: {0}", sensorscfg)
    sys.exit(1)

if not os.path.isfile(outputscfg):
    pandl("E", "Unable to access config file: {0}", outputscfg)
    sys.exit(1)

def get_subclasses(mod, cls):
    for name, obj in inspect.getmembers(mod):
        if hasattr(obj, "__bases__") and cls in obj.__bases__:
            return obj

class MissingField(Exception): pass

# Inputs
sensorPlugins = []
def getInputs():
    global gpsPluginInstance, sensorPlugins

    sensorConfig = ConfigParser.SafeConfigParser()
    sensorConfig.read(sensorcfg)
    sensorNames = sensorConfig.sections()

    for i in sensorNames:
        try:
            try:
                filename = sensorConfig.get(i,"filename")
            except Exception:
                pandl("Ex", "No filename config option found for sensor plugin {0}", i)
                raise
            try:
                enabled = sensorConfig.getboolean(i,"enabled")
            except Exception:
                enabled = True

            #if enabled, load the plugin
            if enabled:
                try:
                    mod = __import__('sensors.' + filename, fromlist = ['a']) #Why does this work?
                except Exception:
                    pandl("Ex", "Could not import sensor module {0}", filename)
                    raise

                try:
                    sensorClass = get_subclasses(mod, sensor.Sensor)
                    if sensorClass == None:
                        raise AttributeError
                except Exception:
                    pandl("Ex", "Could not find a subclass of sensor.Sensor in module {0}", filename)
                    raise

                try:
                    reqd = sensorClass.requiredData
                except Exception:
                    reqd = []
                try:
                    opt = sensorClass.optionalData
                except Exception:
                    opt = []

                pluginData = {}

                for requiredField in reqd:
                    if sensorConfig.has_option(i, requiredField):
                        pluginData[requiredField] = sensorConfig.get(i, requiredField)
                    else:
                        pandl("E", "Missing required field {0} for sensor plugin {1}", (requiredField, i))
                        raise MissingField

                for optionalField in opt:
                    if sensorConfig.has_option(i, optionalField):
                        pluginData[optionalField] = sensorConfig.get(i, optionalField)

                instClass = sensorClass(pluginData)
                sensorPlugins.append(instClass)
                # store sensorPlugins object for GPS plugin
                if i == "GPS":
                    gpsPluginInstance = instClass
                pandl("I", "Loaded sensor plugin {0}", i)
        except Exception as e: # add specific exception for missing module
            pandl("Ex", "Failed to import sensor plugin {0}: [{1}]", (i, e,))
            raise

# Outputs
outputPlugins = []
def getOutputs():
    global outputPlugins

    outputConfig = ConfigParser.SafeConfigParser()
    outputConfig.read(outputscfg)
    outputNames = outputConfig.sections()
    for i in outputNames:
        try:
            try:
                filename = outputConfig.get(i, "filename")
            except Exception:
                pandl("Ex", "No filename config option found for output plugin {0}", i)
                raise
            try:
                enabled = outputConfig.getboolean(i, "enabled")
            except Exception:
                enabled = False

            #if enabled, load the plugin
            if enabled:
                try:
                    mod = __import__('outputs.' + filename, fromlist = ['a']) #Why does this work?
                except Exception:
                    pandl("Ex", "Could not import output module {0}", filename)
                    raise

                try:
                    outputClass = get_subclasses(mod, output.Output)
                    if outputClass == None:
                        raise AttributeError
                except Exception:
                    pandl("Ex","Could not find a subclass of output.Output in module {0}", filename)
                    raise
                try:
                    reqd = outputClass.requiredData
                except Exception:
                    reqd = []
                try:
                    opt = outputClass.optionalData
                except Exception:
                    opt = []

                if outputConfig.has_option(i, "async"):
                    async = outputConfig.getbool(i, "async")
                else:
                    async = False

                pluginData = {}

                for requiredField in reqd:
                    if outputConfig.has_option(i, requiredField):
                        pluginData[requiredField] = outputConfig.get(i, requiredField)
                    else:
                        pandl("E", "Missing required field {0} for output plugin {1}", (requiredField, i))
                        raise MissingField

                for optionalField in opt:
                    if outputConfig.has_option(i, optionalField):
                        pluginData[optionalField] = outputConfig.get(i, optionalField)

                instClass = outputClass(pluginData)
                instClass.async = async
                outputPlugins.append(instClass)
                pandl("I", "Loaded output plugin {0}", i)
        except Exception as e: # add specific exception for missing module
            pandl("Ex", "Failed to import output plugin: {0} [{1}]", (i, e,))
            raise

# Main Loop
def getData():
    mainConfig = ConfigParser.SafeConfigParser()
    mainConfig.read(settingscfg)

    delayTime = mainConfig.getfloat("Main", "uploadDelay")
    redPin    = mainConfig.getint("Main", "redPin")
    greenPin  = mainConfig.getint("Main", "greenPin")
    GPIO.setup(redPin, GPIO.OUT, initial = GPIO.LOW)
    GPIO.setup(greenPin, GPIO.OUT, initial = GPIO.LOW)

    lastUpdated = 0
    keepRunning = True

    while keepRunning:
        try:
            curTime = time.time()
            if (curTime - lastUpdated) > delayTime:
                lastUpdated = curTime
                data = []
                #Collect the data from each sensor
                for i in sensorPlugins:
                    dataDict = {}
                    val = i.getVal()
                    if i == gpsPluginInstance:
                        if isnan(val[2]): # this means it has no data to upload.
                            continue
                        log.debug("GPS output: %s" % (val,))
                        # handle GPS data
                        dataDict["lat"]         = val[0]
                        dataDict["lon"]         = val[1]
                        dataDict["ele"]         = val[2]
                        dataDict["domain"]      = val[3]
                        dataDict["disposition"] = val[4]
                        dataDict["exposure"]    = val[5]
                        dataDict["name"]        = i.locnName
                        dataDict["type"]        = i.valType
                        dataDict["sensor"]      = i.sensorName
                    else:
                        if val == None: # this means it has no data to upload.
                            continue
                        dataDict["value"]  = val
                        dataDict["unit"]   = i.valUnit
                        dataDict["symbol"] = i.valSymbol
                        dataDict["type"]   = i.valType
                        dataDict["sensor"] = i.sensorName
                    data.append(dataDict)
                working = True
                try:
                    for i in outputPlugins:
                        working = working and i.outputData(data)
                    if working:
                        pandl("I", "Data output successfully")
                        GPIO.output(greenPin, GPIO.HIGH)
                    else:
                        pandl("I", "Data output unsuccessful")
                        GPIO.output(redPin, GPIO.HIGH)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    pandl("Ex", "Main Loop Exception: {0}", e)
                    keepRunning = False
                    raise
                else:
                    # delay before turning off LED
                    time.sleep(1)
                    GPIO.output(greenPin, GPIO.LOW)
                    GPIO.output(redPin, GPIO.LOW)
            # wait for remainder of delayTime
            waitTime = (delayTime - (time.time() - lastUpdated)) + 0.01
            if waitTime > 0:
                time.sleep(waitTime)
        except KeyboardInterrupt:
            pandl("I", "KeyboardInterrupt detected")
            keepRunning = False
        except Exception as e:
            log.exception("Unexpected Exception {0}".format(e))
            keepRunning = False
            raise
        # catch all
        except:
            raise


if __name__ == "__main__":
    log.info(">>>>>>>> AirPi starting <<<<<<<<")
    log.info("Python Info: {0} - {1} - {2}\n{3}".format(platform.platform(), platform.python_version(), platform.python_build(), str(platform.uname())))

    try:
        try:
            log.debug("Getting Inputs")
            getInputs()
            log.debug("Getting Outputs")
            getOutputs()
            log.debug("Getting Data")
            getData()
        except Exception as e:
            # Need to handle a SystemExit
            log.exception("Exception caught: {0}".format(e))
            # sys.exit(1)
    finally:
        # stop gps controller
        if gpsPluginInstance:
            log.info("Stopping gps controller")
            gpsPluginInstance.stopController()
        log.info(">>>>>>>> AirPi ending <<<<<<<<")
        # Shutdown the logging system
        logging.shutdown()
        # Exit here
        os._exit(0)
