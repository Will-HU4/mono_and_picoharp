import sys
import struct
import ctypes
from array import *
from ctypes import *
#OTO USB2.0 spectrameter's VID & PID
VID = 1592
PID = 2732
#OTOdll = CDLL("UserApplication.dll")
OTOdll = ctypes.cdll.LoadLibrary("UserApplication.dll")
#Check how many device is connected with PC.
intDeviceamout = c_uint64(0)
OTOdll.UAI_SpectrometerGetDeviceAmount.restype = ctypes.c_uint64
OTOdll.UAI_SpectrometerGetDeviceAmount(VID,PID,byref(intDeviceamout))
print("Device amount:")
print(intDeviceamout.value)

if intDeviceamout.value < 1:
    print("NO device connecting")
    exit()

#Open Device
DeviceHandle = c_uint64(0)
OTOdll.UAI_SpectrometerOpen.restype = ctypes.c_uint64
OTOdll.UAI_SpectrometerOpen(0,byref(DeviceHandle),VID,PID)
print("Device handle:")
print(DeviceHandle.value)

#Get Framesize
intFramesize = c_uint64(0)
OTOdll.UAI_SpectromoduleGetFrameSize.restype = ctypes.c_uint64
OTOdll.UAI_SpectromoduleGetFrameSize(DeviceHandle,byref(intFramesize))
print("Device framesize:")
print(intFramesize.value)

#if intFramesize.value ==0:
#     print("Framesize is invalid")
#     exit()

#Get Module name
charModulename = create_string_buffer(16)
OTOdll.UAI_SpectrometerGetModelName(DeviceHandle,byref(charModulename))
print ("Module name:")
print (repr(charModulename.value))

#Get Serial number
#emp = array(
charSerialnumber = create_string_buffer(16)
OTOdll.UAI_SpectrometerGetSerialNumber(DeviceHandle,byref(charSerialnumber))
print ("Serial number:")
print (repr(charSerialnumber.value))


#Init array
#TempLambda = create_string_buffer(sizeof(c_float*intFramesize.value))
#TempIntensity = create_string_buffer(sizeof(c_float*intFramesize.value))
TempLambda = (c_float*intFramesize.value)()
TempIntensity = (c_float*intFramesize.value)()

#Get wavelength
OTOdll.UAI_SpectrometerWavelengthAcquire(DeviceHandle,byref(TempLambda))

Lambda = []
for i in range(0,intFramesize.value):
    Lambda.append(TempLambda[i])

Intensity = []

for i in range(1,100,+1):
    #Get Intensity
    OTOdll.UAI_SpectrometerDataOneshot(DeviceHandle,i*1000,byref(TempIntensity),1)

    #Do Background
    OTOdll.UAI_BackgroundRemove(DeviceHandle,i*1000,byref(TempIntensity))

    #Do Linearity
    OTOdll.UAI_LinearityCorrection(DeviceHandle,intFramesize,byref(TempIntensity))

    Intensity = []
    for i in range(0,intFramesize.value):
        Intensity.append(TempIntensity[i])
    print(Lambda[0] , Intensity[0])