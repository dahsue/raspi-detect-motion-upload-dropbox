#Detect motion, record and upload to dropbox
If you have a Foscam camera and a Raspberry Pi you can run this Python script to record videos and upload to your dropbox
folder when it detects motion.

#Name
motion_raspi.py

#Usage

     ./motion_raspi.py camera_name

#Description
This program captures pictures from a foscam camera (tested with FI8910W) at regular 
intervals, computes the difference between the current picture and the 
previous one. If the entropy of the difference exceeds the average entropy 
of previous differences + a sensivity value that you specify then a 
change has occurred. If two consecutive changes happen then motion has been 
detected and a 30s video from the foscam camera is recorded and saved on the Raspberry
Pi SD card. It is also uploaded to your dropbox folder, if desired. For motion detection
purpose you can configure the program to detect change on the entire image (640x480)
or within a particular rectangular area. Ctrl-C to stop the program.

#Pre-requisites
- Hardware: Raspberry Pi or any Linux machine and a foscam camera.
- Mandatory: Create a ramdisk as follows to store pictures taken a regular 
     intervals for the purpose of detecting motion. It is better to use a 
     ramdisk, rather than the SD card, to store these temporary pictures:
  
          mkdir /tmp/ramdisk    
          chmod 777 /tmp/ramdisk
          sudo mount -t tmpfs -o size=16M tmpfs /tmp/ramdisk/    
          
- Mandatory: The configuration file 'motion_config.ini' must be in current 
     directory. In motion_config.ini there must be a camera_name section and 
     at the minimum you should provide the IP address and password for the 
     foscam camera. See inside motion_config.ini for more detail.
- Mandatory: By default Raspian does not have the Python Imaging Library 
     (PIL) installed. You need to install it by issuing "sudo apt-get install
     python-imaging" on a Raspian terminal.
- Optional: If you want to upload the recorded videos to your dropbox folder
     then the file 'dropbox_uploader.sh' must be in the current directory. 
     You can download that file from 'github.com/andreafabrizi/Dropbox-Uploader'

#Sample output on terminal

       ./motion_raspi.py entrance_cam
	     Starting motion detection for entrance_cam at 192.168.1.2
	     [entrance_cam: 2013-08-04,16:24:12] diff entropy 4.48, avg 4.48, num videos 2
	     [entrance_cam: 2013-08-04,16:24:12] diff entropy 4.51, avg 4.50, num videos 2
	     etc...

The values displayed are: date and time program started, entropy of current image diff,
average entropy of previous diffs and the number of videos recorded.



