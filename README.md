3D-MUSE-acquire
==========

Setting up the software
------------

Install python 3.11 from Microsoft Store  
https://www.microsoft.com/store/productid/9NRWMJP3717K?ocid=pdpshare

Install Visual Studio Code  
https://code.visualstudio.com/

Download a zip of this repository  
https://github.com/ckolluru/3D-MUSE-acquire/archive/refs/heads/master.zip

Unzip the contents of this zip file and move it to a suitable folder location  

Open Visual Studio Code  

Click on the extensions button on the left, search for python and install the extension  
VS Marketplace Link: https://marketplace.visualstudio.com/items?itemName=ms-python.python
This is not a python interpreter, this just allows visual studio to format and display python code properly  

Set the default terminal profile  
Press Ctrl + Shift + P  
Search for Terminal: Select Default Profile  
Select command line  

Now go to File > Open Folder  
Select the folder with this code that was unzipped  
You should see all the files in the explorer tab on the left  

Open main.py file and pin it  

Now on the menu bar, select terminal > new terminal  
In the terminal window, run the install command  
The requirements.txt file should list all Python libraries that the software depends on, and they will be installed using:  
```
pip install -r requirements.txt
```

Setting up micromanager
------------
In Micromanager, a configuration file is created to connect to the specific hardware  
Open Micromanager and select (none) in the configuration window

Go to devices > hardware configuration wizard and follow the steps from the micromanager Zaber device pages, to set up the XYZ stages. 
Select spinnaker camera and find the blackfly camera you are using, set it up as well. Status should say OK

We also set up DemoCamera (DHub) and select the Demo Objective (this is a dummy item that lets us specify an objective magnification)
![Objective mag setup 1](docs/obj_mag_1.png)

Select ok on this window
![Objective mag setup 2](docs/obj_mag_2.png)

Select the Demo Objective
![Objective mag setup 3](docs/obj_mag_3.png)

You should see a DCamera and DObjective setup
![Objective mag setup 4](docs/obj_mag_4.png)

Leave defaults on step 3 and 4. In step 3, it may leave focus stage direction empty, select positive towards sample if that's the case.

In step 5, it should show you a table of states and labels for the demo objective turret. Leave as is.
![Objective mag setup 5](docs/obj_mag_5.png)

Save the configuration file in a suitable location, preferably in the same folder as this repository.

Next, we will enter the pixel size values for each of the objectives
Go to Devices > Pixel Size Calibration, select New
Click OK on the warning window where it says devices will move
![Pixel size cal 1](docs/pixel_size_1.png)

Give a suitable name in the pixel config editor (say 4x), enter pixel size (um), and click on the calculate button
The 3x3 affine transform will be updated based on the pixel size. 
Select the DObjective-Label for the use in group checkbox.
The python code assumes that the 4x is objective-A, 10x is objective-B, 2x is objective-C
Select the current property value appropriately from the dropdown in DObjective-Label row
![Pixel size cal 2](docs/pixel_size_2.png)

Repeat this process for all the objectives you need, use the appropriate objective names
![Pixel size cal 3](docs/pixel_size_3.png)
![Pixel size cal 4](docs/pixel_size_4.png)

Save this pixel configuration to the same device cfg file, ok to overwrite

Now, when the objective magnification is used from this software's dropdown, Micromanager will automatically be updated
See the bottom most line in the micromanager window, where it says

Image info (from camera), Image intensity range, xyz nm/px

Modifications based on COM ports
------------
Ensure that the COM port for the Arduino is correctly entered. It is hardcoded for now.
In main.py, go to the ```initialize_arduino()``` function. Change the line as needed

```
self.board = pyfirmata.Arduino(str("COM5"))
```

Running the software
------------
Go to ```bin\``` folder and run the batch script  ```3D-MUSE-acquire.bat```
- It will start a command window, do not close that at any time when using the application  

Software screenshot
------------
<p align="center">
  <img src="bin/Software screenshot.PNG" alt="3D-MUSE-acquire software"/>
</p>

Getting help
------------
The Help tab > Instructions button on the application's  taskbar has useful information on how to use the software  
It has information on how to keep a block in the microtome, how to clean the knife, how to set up a trimming cycle, how to do an imaging cycle, how to stop in between handling error situations and how to shutdown the system.