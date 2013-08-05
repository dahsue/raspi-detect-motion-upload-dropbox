#!/usr/bin/python
#
# Copyright (C) 2013 Dany Ahsue <dahsue@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# Usage:
# ------
# ./motion_raspi.py camera_name
#
# Description:
# ------------
# Captures pictures from a foscam camera (tested with FI8910W) at regular 
# intervals, computes the difference between the current picture and the 
# previous one. If the entropy of the difference exceeds the average entropy 
# of previous differences + a sensivity value that you specify then a 
# change has occurred. If two consecutive changes happen then motion has been 
# detected and a 30s video from the foscam camera is recorded on the Raspberry
# Pi SD card and uploaded to your dropbox folder, if desired. Ctrl-C to stop
# the script.
#
# Pre-requisites:
# ---------------
# 1.Hardware: Raspberry Pi or any Linux machine and a foscam camera.
# 2.Mandatory: Create a ramdisk as follows to store pictures taken a regular 
#   intervals for the purpose of detecting motion. It is better to use a 
#   ramdisk, rather than the SD card, to store these temporary pictures:
#           mkdir /tmp/ramdisk    
#           chmod 777 /tmp/ramdisk
#           sudo mount -t tmpfs -o size=16M tmpfs /tmp/ramdisk/    
# 3.Mandatory: The configuration file 'motion_config.ini' must be in current 
#   directory. In motion_config.ini there must be a camera_name section and 
#   at the minimum you should provide the IP address and password for the 
#   foscam camera. See inside motion_config.ini for more detail.
# 4.Mandatory: By default Raspian does not have the Python Imaging Library 
#   (PIL) installed. You need to install it by issuing "sudo apt-get install
#   python-imaging" on a Raspian terminal.
# 5.Optional: If you want to upload the recorded videos to your dropbox folder
#   then the file 'dropbox_uploader.sh' must be in the current directory. 
#   You can download that file from 'github.com/andreafabrizi/Dropbox-Uploader'
#   

from PIL import Image, ImageChops
import math
import os
import time
import sys
import subprocess
import shlex
import shutil
from time import gmtime, strftime, localtime
import ConfigParser

################################################
# utility functions
################################################

def ConfigSectionMap(section):
    dict1 = {}
    options = Config.options(section)
    for option in options:
        try:
            dict1[option] = Config.get(section, option)
            if dict1[option] == -1:
                DebugPrint("skip: %s" % option)
        except:
            print("exception on %s!" % option)
            dict1[option] = None
    return dict1


def image_entropy(img):
    # calculate the entropy of an image
    histogram = img.histogram()
    histogram_length = sum(histogram)
    samples_probability = [float(h) / histogram_length for h in histogram]
    return -sum([p * math.log(p, 2) for p in samples_probability if p != 0])


def compute_average_entropy(img_entropy_list, max_list_size, img_entropy):
    img_entropy_list.append(img_entropy)
    size = len(img_entropy_list)
    while (size > max_list_size):
        discard = img_entropy_list.pop(0)  #remove 1st element, list at max 
        size = size - 1
    return ((sum(img_entropy_list))/size)


####################################################
# globals
####################################################
ramdisk_dir = "/tmp/ramdisk"                   #location of ramdisk
num_videos_captured = 0                        #track num videos captured
image_changed = 0                              #increment if img changed 
last_pic = "none"                              #keeps track of last pic
start_time = strftime("%Y-%m-%d,%H:%M:%S", localtime())  #start time of detect
entropy_list_size = 10                         #keep list of last n entropies
                                               # for average calculation
entropy_collection_interval = 10               #collect entropy for every n 
                                               # picture captures to ensure
                                               # that we compute decent average
entropy_list = []                              #list of entropies for
                                               # average computation
entropy_collection_index = entropy_collection_interval
average_img_diff_entropy = 0                


# debug flag
debug = False


####################################################
# inits
####################################################

# check ramdisk presence
if (not os.path.exists(ramdisk_dir)):
    print("Please create RAM disk by issuing the following commands:")
    print("   mkdir /tmp/ramdisk")
    print("   chmod 777 /tmp/ramdisk")
    print("   sudo mount -t tmpfs -o size=16M tmpfs /tmp/ramdisk/")
    sys.exit(1)

# get camera name from command line
if (len(sys.argv) < 2):
    print ("Usage is: motion_detect <camera_name>")
    sys.exit(1)
camera_name = sys.argv[1]

# get the parameters from motion_config.ini
if (not os.path.exists("./motion_config.ini")):
    print("Cannot open motion_config.ini")
    sys.exit(1)
Config = ConfigParser.ConfigParser()
Config.read("./motion_config.ini")
if (camera_name not in Config.sections()):
    print (camera_name + " does not exist in motion_config.ini")
    sys.exit(1)
cam_ip_addr = ConfigSectionMap(camera_name)['ip_address']
password = ConfigSectionMap(camera_name)['password']
sensitivity = float(ConfigSectionMap(camera_name)['sensitivity'])
pic_interval = float(ConfigSectionMap(camera_name)['capture_interval'])
num_pics = int(ConfigSectionMap(camera_name)['consecutive_changes'])
start_x = int(ConfigSectionMap(camera_name)['start_x'])
start_y = int(ConfigSectionMap(camera_name)['start_y'])
end_x = int(ConfigSectionMap(camera_name)['end_x'])
end_y = int(ConfigSectionMap(camera_name)['end_y'])
dropbox = ConfigSectionMap(camera_name)['dropbox']
video_record_time = int(ConfigSectionMap(camera_name)['video_record_time'])


#check if we need to crop image, foscam image size is 640x480
bNoCrop = False
if (end_x > 640):
    end_x = 640
if (end_y > 480):
    end_y = 480
if (end_x < start_x):
    print ("end_x cannot be smaller than start_x. check motion_config.ini")
    sys.exit(1)
if (end_y < start_y):
    print ("end_y cannot be smaller than start_y. check motion_config.ini")
    sys.exit(1)
if (start_x == 0 and start_y == 0 and end_x == 640 and end_y == 480):
    bNoCrop = True


#check if we need to copy to dropbox
bCopyToDropBox = False
if (dropbox == "yes"):
    bCopyToDropBox = True
    if (not os.path.exists("./dropbox_uploader.sh")):
        print("dropbox_uploader.sh not found in current directory. Please \
download it from github.com/andreafabrizi/Dropbox-Uploader")
        sys.exit(1)


#create directory for camera_name. It will be camera_name_videos
camera_videos_dir = "./" + camera_name + "_videos"
if (not os.path.isdir(camera_videos_dir)):
    os.mkdir(camera_videos_dir)


# image configurations
crop_box = (start_x, start_y, end_x, end_y)    #crop box of image
pic_dir = ramdisk_dir      #location of images used for comparison
py_pic1 = pic_dir + "py_pic1_" + camera_name   #img1 for comparison
py_pic2 = pic_dir + "py_pic2_" + camera_name   #img2 for comparison
py_pic_diff = pic_dir + "py_pic_diff_" + camera_name + ".png"  #img diff name
py_pic1_save = "py_pic1_" + camera_name        #name of pic1 saved for debug 
py_pic2_save = "py_pic2_" + camera_name        #name of pic2 saved for debug 
img_diff_save = "img_diff_" + camera_name      #name of pic diff saved, debug 
#foscam query strings
wget_cam_pic1 = "wget http://" + cam_ip_addr + \
                "/snapshot.cgi?user=admin\&pwd=" + password + \
                " -O " + py_pic1 + "  > /dev/null 2>&1"
wget_cam_pic2 = "wget http://" + cam_ip_addr + \
                "/snapshot.cgi?user=admin\&pwd=" + password + \
                " -O " + py_pic2 + " > /dev/null 2>&1"
wget_cam_video = "wget http://" + cam_ip_addr + \
                "/videostream.asf?user=admin\\&pwd=" + password + \
                " -O "

# starting....
print ("Starting motion detection for " + camera_name + \
       " at " + cam_ip_addr)


####################################################
# main loop
####################################################

while True:
    if (last_pic == "none"):
        #get both pic1 and pic2
        os.system(wget_cam_pic1)
        time.sleep(pic_interval)
        os.system(wget_cam_pic2)
        last_pic = "pic2"
    else:
        #we have a last pic, get pic1 or pic2
        time.sleep(pic_interval)
        if (last_pic == "pic1"):
            os.system(wget_cam_pic2)
            last_pic = "pic2"
        else:
            os.system(wget_cam_pic1)
            last_pic = "pic1"
    time.sleep(0.1) #sleep 0.1s after last wget to ensure image is downloaded

    try:
        pic1 = Image.open(open(py_pic1, 'rb'))
        pic2 = Image.open(open(py_pic2, 'rb'))
        if (bNoCrop == True):
            cropped_pic1 = pic1
            cropped_pic2 = pic2
        else:
            cropped_pic1 = pic1.crop(crop_box)
            cropped_pic2 = pic2.crop(crop_box)
            #cropped_pic1.save(py_pic1+'.png')
            #cropped_pic2.save(py_pic2+'.png')

        #Compute difference between last img and current img
        img = ImageChops.difference(cropped_pic1,cropped_pic2)
        if (debug == True):
            img.save(py_pic_diff) 
    except IOError, e:
        #error with last 2 images, get next 2                                  
        last_pic == "none"
        continue

    #Compute entropy of img difference
    img_diff_entropy = image_entropy(img)

    #compute average img diff entropy every entropy_collection_interval time
    # or if length of entropy_list < entropy_list_size
    entropy_collection_index += 1
    if (entropy_collection_index >= entropy_collection_interval or \
        len(entropy_list) < entropy_list_size):
        average_img_diff_entropy = compute_average_entropy(entropy_list, \
                                                           entropy_list_size, \
                                                           img_diff_entropy)
        entropy_collection_index = 0


    img_diff_entropy_str = "%.2f" % img_diff_entropy
    average_img_diff_entropy_str = "%.2f" % average_img_diff_entropy

    print  "[" + camera_name + ": " + start_time + "] diff entropy " + \
           img_diff_entropy_str + ", avg " + \
           average_img_diff_entropy_str + ", num videos " + \
           str(num_videos_captured)


    if (img_diff_entropy > average_img_diff_entropy + sensitivity):
        image_changed = image_changed + 1
    else:
        image_changed = 0

    if (image_changed >= num_pics):
        #record video

        if (debug == True):
            #Save pic b4 and after 
            cropped_pic1.save(py_pic1_save + "-" + \
                     strftime("%Y-%m-%d,%H:%M:%S", localtime()) + 
                              '.png')
            cropped_pic2.save(py_pic2_save + "-" + \
                     strftime("%Y-%m-%d,%H:%M:%S", localtime()) + 
                              '.png')
            img.save(img_diff_save + "-" + \
                     strftime("%Y-%m-%d,%H:%M:%S", localtime()) + '.png')

            pic1_entropy = image_entropy(cropped_pic1) 
            pic2_entropy = image_entropy(cropped_pic2)                         
 
            addString = "-" + str(pic1_entropy) + "," + \
                            str(pic2_entropy) + "," + str(img_diff_entropy)
        else:
            addString = ""

        #create process to record video
        try:
            pid = os.fork()
        except OSError, e:
            sys.exit(1)

        video_file_name = camera_videos_dir + "/" + \
                          camera_name + \
                          "_cam_" + \
                          strftime("%g.%m.%d_%H.%M.%S.asf", localtime()) + \
                          addString
        if (pid == 0):
            print("\nChild process starting video capture...\n")

            arg = shlex.split(wget_cam_video + video_file_name)
            p = subprocess.Popen(arg)
            time.sleep(video_record_time)
            p.kill()
            print("\nChild process exiting...");
            sys.exit(1)
        else:
            num_videos_captured += 1
            
            #wait for child to finish recording
            time.sleep(video_record_time+1)

            if (bCopyToDropBox):
                #shutil.copy(video_file_name, dropbox_dir) if dropbox
                # folder can be mounted on a linux dir. Not possible for raspy
                # so use dropbox_uploader.sh instead
                os.system("./dropbox_uploader.sh upload " + video_file_name)

            
            print ("Video captured, main process resuming...")
            last_pic = "none"  #get both pic1 and pic2 next time
            image_changed = 0
