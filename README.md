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
The Help tab on the application taskbar has useful information on how to use the software.