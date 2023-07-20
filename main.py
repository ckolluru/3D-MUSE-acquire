print('Initializing 3D-MUSE-acquire, please wait..')

import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QFileDialog, QDialog
from PyQt5 import uic
import os
from pycromanager import Studio, Core
import pyfirmata
import glob

from imaging_module import imagingClass
from trimming_module import trimmingClass
from stitching_module import *

import logging

# Class derived from QMainWindow, loads the UI and handles UI requests
class Window(QMainWindow):
	def __init__(self):
		super(Window, self).__init__()
		uic.loadUi('ui files\mainwindow.ui', self)
		self.show() 

		# Class variables
		# Arduino board 
		self.board = None

		# Trimming class thread
		self.trimmingThread = None

		# Imaging class thread
		self.imagingThread = None
		
		# Micromanager core (used to set configuration properties, stage homing, set stage positions, camera ROI info)
		self.core = None

		# Micromanager studio (used to get XYZ positions from Multi-D acquisition window)
		self.studio = None

		# Stitching module
		self.stitcher = None

	# Home the XYZ stages (push button callback function)
	def home_stages(self):

		try:
			# Get the core
			self.core = Core()	

			# Change the stage timeout to a large value since it may take many seconds to move the stages to zero position
			self.core.set_property('Core', 'TimeoutMs', '40000')	
			
			# Block UI interaction (disable the buttons, line edit items etc.)
			self.block_ui(True)

			# Home the stages
			self.core.home("XYStage")
			self.core.home("Stage")

			# Enable UI interaction back again
			self.block_ui(False)

			# Disable the home stages button, since you do not have to run it again (only needed if stages are rebooted)
			self.homeStagesPushButton.setEnabled(False)

		except:
			# If you can't get a handle of micromanager core, it is probably not open, so show a message box
			msgBox = QMessageBox()
			msgBox.setText("Did not find MicroManager to be open, ensure that it is open.")
			msgBox.exec()

	# Get XYZ positions from Micromanager Multi-D acquisition window
	def get_xyz_positions(self):

		try:
			# Get the studio object, report exceptions as needed
			self.studio = Studio()
		except Exception as e:
			print(str(e))
			return None, None

		# Pull current Multi-D acquisition window positions
		position_list_manager = self.studio.positions()
		position_list = position_list_manager.get_position_list()
		number_positions = position_list.get_number_of_positions()

		# Initialize position variables
		xy_positions = np.empty((number_positions, 2))
		z_positions = np.empty((number_positions))

		# Iterate through position list to extract XY and Z positions
		# XY positions are in XYStage label, Z positions are in Stage label    
		for idx in range(number_positions):
			pos = position_list.get_position(idx)
			for ipos in range(pos.size()):
				stage_pos = pos.get(ipos)
				if (stage_pos.get_stage_device_label() == 'XYStage'):
					xy_positions[idx,:] = [stage_pos.x, stage_pos.y]
				if (stage_pos.get_stage_device_label() == 'Stage'):
					z_positions[idx] = stage_pos.x

		# Return the position arrays
		return xy_positions, z_positions

	# Initialize the arduino board
	def initialize_arduino(self):

		# If the board was not initialized previously
		if self.board is None:

			# Define the arduino board using the specific COM port 
			# (hardcoded for now, will not change as long as the USB is plugged in on the same place)
			self.board = pyfirmata.Arduino(str("COM5"))

			# Set input and output pins
			self.board.digital[8].mode = pyfirmata.OUTPUT
			self.board.digital[9].mode = pyfirmata.OUTPUT
			self.board.digital[10].mode = pyfirmata.OUTPUT        
			self.board.digital[12].mode = pyfirmata.INPUT

			# Start the iterator
			it = pyfirmata.util.Iterator(self.board)
			it.start()

			# Switch off the emergency stop, cutting and light source, this uses inverted logic
			# We currently do not use the emergency stop from the Arduino, use the physical switches on the microtome
			# Pin 9 is cutting, pin 10 is light source
			self.board.digital[8].write(1)
			self.board.digital[9].write(1)
			self.board.digital[10].write(1)

			# Show a message in the status bar
			self.statusBar().showMessage('Arduino initialization complete', 5000)

			# Disable the initialize arduino button, since you only need to do this once per run
			self.initializeArduinoButton.setEnabled(False)
		
		# If the board is already set up, then show suitable message in the status bar
		else:
			self.statusBar().showMessage('Arduino already initialized, relaunch 3D-MUSE-acquire if required')

	# Switch on light source (checkbox callback function from GUI)
	def switch_on_light_source(self, isChecked):

		# If board is not set, show a message to the user to click on the initialize arduino button
		if self.board is None:
			msgBox = QMessageBox()
			msgBox.setText("Arduino board is not initialized, please press the Initialize Arduino button")
			msgBox.exec()

			# Set the checkbox back to unchecked
			self.switchOnLightCheckbox.setChecked(False)
			return None
		
		# If board is set, set the arduino pin as required. Inverted logic, 0 is on, 1 is off.
		else:
			if isChecked:
				self.board.digital[10].write(0)
			else:
				self.board.digital[10].write(1)

	# Stop acquisition (trimming or imaging), callback from UI button press stop acquisition
	def stop_run(self):

		# If trimming, stop the trimming thread
		if self.TRIMMING_FLAG:
			if self.trimmingThread is not None:
				self.trimmingThread.stop()

		# If imaging, stop the imaging thread
		else:
			if self.imagingThread is not None:
				self.imagingThread.stop()	

		# Reset the progress bar and say that the acquisition has been stopped.
		self.progressBar.setValue(0)
		self.statusBar().showMessage('Acquisition stopped.', 4000)	

	# Disable UI elements, utility function
	def block_ui(self, flag):

		# For the start/stop acquisition button, disconnect all other callback functions
		try:
			self.startAcquisitionButton.released.disconnect()
		except TypeError:
			print('No functions set up to run on start/stop push button click.')
			pass

		# If block UI is requested, disable UI elements as appropriate, connect the stop acquisition button to stop_run
		if flag:
			self.storageDirEdit.setEnabled(False)
			self.numberCutsEdit.setEnabled(False)
			self.trimBlockCheckbox.setEnabled(False)
			self.autoFocusEveryLineEdit.setEnabled(False)
			self.homeStagesPushButton.setEnabled(False)
			self.storageDirButton.setEnabled(False)
			self.exposureTimeLineEdit.setEnabled(False)
			self.skipEveryLineEdit.setEnabled(False)
			self.objectiveComboBox.setEnabled(False)
			self.widget.setEnabled(False)
			self.startAcquisitionButton.setText('Stop acquisition')
			self.startAcquisitionButton.released.connect(self.stop_run)

			self.label_1.setEnabled(False)
			self.label_2.setEnabled(False)
			self.label_3.setEnabled(False)
			self.label_4.setEnabled(False)
			self.label_5.setEnabled(False)
			self.label.setEnabled(False)

		# If un-block UI is requested, enable UI elements as appropriate, connect the start acquisition button to run_acquisition
		else:
			self.storageDirEdit.setEnabled(True)
			self.numberCutsEdit.setEnabled(True)
			self.trimBlockCheckbox.setEnabled(True)
			self.autoFocusEveryLineEdit.setEnabled(True)
			self.homeStagesPushButton.setEnabled(True)
			self.storageDirButton.setEnabled(True)
			self.exposureTimeLineEdit.setEnabled(True)
			self.skipEveryLineEdit.setEnabled(True)
			self.objectiveComboBox.setEnabled(True)
			self.widget.setEnabled(True)
			self.startAcquisitionButton.setText('Start acquisition')
			self.startAcquisitionButton.released.connect(self.run_acquisition)

			self.label_1.setEnabled(True)
			self.label_2.setEnabled(True)
			self.label_3.setEnabled(True)
			self.label_4.setEnabled(True)
			self.label_5.setEnabled(True)
			self.label.setEnabled(True)
		
	# Open directory to store raw data, create a file open dialog box
	def open_storage_dir(self):
		title = "Open Folder to save data"
		flags = QFileDialog.ShowDirsOnly
		path = QFileDialog.getExistingDirectory(self,
												title,
												os.path.expanduser("."),
												flags)

		self.storageDirEdit.setText(path)

		self.statusBar().showMessage('Storage folder location saved', 2000)

	# Progress bar update from threads
	def progressUpdate(self, value):
		self.progressBar.setValue(value)  
 
	# Progress bar minimum value update from threads 
	def progressMinimum(self, value):
		self.progressBar.setMinimum(value)
  
	# Progress bar maximum value update from threads 
	def progressMaximum(self, value):
		self.progressBar.setMaximum(value)
  
	# Set status bar from threads
	def statusBarMessage(self, string):
		self.statusBar().showMessage(string)

	# Complete signal from the threads, stop the appropriate thread based on return value
	# completeSignal is the object that is used from the threads, emit 1 for imagingThread, 2 for trimmingThread
	def acquisitionComplete(self, value):
		if value == 1:
			self.statusBar().showMessage("Imaging session complete")
			self.imagingThread.terminate_thread()
		if value == 2:
			self.statusBar().showMessage("Trimming session complete")
			self.trimmingThread.terminate_thread()

		# Reset progress bar, make UI available again
		self.progressBar.setValue(0)
		self.block_ui(False)

	# Open a dialog box with instructions
	def open_instructions(self):

		# Create an instance of the dialog to open the .ui file
		dialog = QDialog()

		# Load the .ui file into the dialog
		uic.loadUi("ui files\helpwindow.ui", dialog)

		# Show the dialog
		dialog.show()
				
	# Run the acquisition (callback from UI start acquisition button press)
	def run_acquisition(self):

		# Get the storage directory
		self.STORAGE_DIRECTORY = str(self.storageDirEdit.text())

		# Set up logging file, will append for each run
		logfile = self.STORAGE_DIRECTORY + '\\muse_application.log'
		logging.basicConfig(filename = logfile, filemode = 'a', level = logging.DEBUG, format = '%(asctime)s - %(levelname)s: %(message)s', datefmt = '%m/%d/%Y %I:%M:%S %p')

		# If the arduino was not initialized, show the message and ask the user to do that
		if self.board is None:
			msgBox = QMessageBox()
			msgBox.setText("Arduino board is not initialized, press Initialize Arduino button first.")
			msgBox.exec()
			return None
					
		# Disable the UI so that user cannot edit line items during acquisition cycle, re-enable any time you return from this function
		self.block_ui(True)
		
		# Number of cuts, progress bar is defined from this value
		num_cuts = int(self.numberCutsEdit.text())
		self.progressBar.setMinimum(0)
		self.progressBar.setMaximum(num_cuts)

		# Trimming flag, this decides whether trimming or imaging thread needs to be created
		self.TRIMMING_FLAG = self.trimBlockCheckbox.isChecked()

		# If trimming is selected
		if self.TRIMMING_FLAG:	

			# Log the info to the log file		
			logging.info('----TRIMMING CYCLE----')
			logging.info('Trimming set to %s cuts', num_cuts)

			# Create the thread object of the trimmingClass, send relavent info
			self.trimmingThread = trimmingClass(num_cuts, self.board, str(self.storageDirEdit.text()))

			# Connect signals in the thread object to function names in this file
			# Progress update, acquisition complete signal, status bar messages
			self.trimmingThread.progressSignal.connect(self.progressUpdate)
			self.trimmingThread.progressMinimumSignal.connect(self.progressMinimum)
			self.trimmingThread.progressMaximumSignal.connect(self.progressMaximum)
			self.trimmingThread.completeSignal.connect(self.acquisitionComplete)
			self.trimmingThread.statusBarSignal.connect(self.statusBarMessage)

			# Start the thread (will call run() function in the thread object)
			self.trimmingThread.start()

		# Imaging
		else:

			# Get XYZ positions for the tiles from Multi-D acquisition window
			xy_positions, z_positions = self.get_xyz_positions()

			if xy_positions is None and z_positions is None:
				msgBox = QMessageBox()
				msgBox.setText("Could not retrieve positions, ensure that MicroManager is open and positions are set in the Multi-D acquisition, position lsit tab.")
				msgBox.exec()
				self.block_ui(False)
				return
			
			# Calculate number of tiles
			xyz_positions = np.hstack((xy_positions, np.expand_dims(z_positions, axis=1)))
			self.NUM_TILES = xy_positions.shape[0]			
			
			# Find previous imaging acquisitions in the storage directory folder
			# The string "MUSE_acq" is provided in the call to Micromanager later
			# Micromanager adds each new acquisition as MUSE_acq_1, MUSE_acq_2, MUSE_acq_3 etc.
			prev_acqs = glob.glob(self.STORAGE_DIRECTORY + r'\\MUSE_acq_*')	
			
			# Log the info to a log file
			logging.info('---- IMAGING CYCLE ' + str(len(prev_acqs) + 1) + '----')
			logging.info('Imaging set to % s cuts', num_cuts)

			logging.info('Received XYZ positions from Micromanager')
			logging.info('XY positions are: %s', xy_positions)
			logging.info('Z positions are: %s', z_positions)

			print('XY positions')
			print(xy_positions)

			print('Z positions')
			print(z_positions)

			# Stitching is needed if there is more than one tile
			self.STITCHING_FLAG = (self.NUM_TILES != 1)

			# Set up path to a text file that will have the tile configuration (this is used by ITKMontage to place the tiles correctly initially)
			self.TILE_CONFIG_PATH = self.STORAGE_DIRECTORY + r'\\TileConfiguration_acq_' + str(len(prev_acqs) + 1) + '.txt'	
			
			# Find number of tiles in x and y, used to figure out the stitched image size
			num_tiles_x = len(np.unique(xy_positions[:,0]))
			num_tiles_y = len(np.unique(xy_positions[:,1]))

			# If no tiles were found, alert the user
			if num_tiles_x == 0 and num_tiles_y == 0:
				msgBox = QMessageBox()
				msgBox.setText("Did not find tile set up in MicroManager. Please ensure tile positions are specified using the MultiD Acq. window in MicroManager.")
				msgBox.exec()

				self.block_ui(False)
				return None

			# Total number of tiles should be equal to the product of tiles in x and tiles in y
			# It should be a grid configuration, cannot be random
			if self.NUM_TILES != (num_tiles_x * num_tiles_y):
				msgBox = QMessageBox()
				msgBox.setText("Did not find tiles in the expected grid pattern. Ensure you use positions directly from the create grid button in the Multi-D acquisition, edit position tab.")
				msgBox.exec()
				
				self.block_ui(False)
				return None
			
			# Log info on tiles and update status bar with a message
			logging.info('Found %s tiles', self.NUM_TILES)	
			self.statusBar().showMessage('Found ' + str(num_tiles_x) + ' tiles in x and ' + str(num_tiles_y) + ' tiles in y')

			# Z stack focusing inputs
			# z start should be less than zero, z_stop should be greater than zero, z_step should be positive
			# if (z_start, z_stop, z_step) are (-3, 3, 1), you will image at z-3, z-2, z-1, z, z+1, z+2, z+3
			self.Z_STACK_STITCHING = False
			self.z_start = float(self.z_startLineEdit.text())
			self.z_stop = float(self.z_stopLineEdit.text())
			self.z_step = float(self.z_stepLineEdit.text())

			# If either of these values are not zero, focusing may be required in the Z stack
			if not (self.z_start == 0 and self.z_stop == 0 and self.z_step == 0):
				self.Z_STACK_STITCHING = True

			# Ensure that the parameter values are what we expect, else return
			# start should be less than zero
			if self.z_start > 0:				
				msgBox = QMessageBox()
				msgBox.setText("Z Start value is greater than 0, which is invalid. It should be less than zero, please retry.")
				msgBox.exec()

				self.block_ui(False)
				return None
			
			# stop should be greater than zero			
			if self.z_stop < 0:				
				msgBox = QMessageBox()
				msgBox.setText("Z Stop value is less than 0, which is invalid. It should be greater than zero, please retry.")
				msgBox.exec()

				self.block_ui(False)
				return None
			
			# step size should be less than stop-start
			if self.z_step > abs(self.z_start - self.z_stop):
				msgBox = QMessageBox()
				msgBox.setText("Z Step value is greater than the absolute value of Z start - Z stop. It should be less than that value, please retry.")
				msgBox.exec()

				self.block_ui(False)
				return None
			
			# If z stack stitching needs to be done, ensure step size is not zero
			if self.Z_STACK_STITCHING:
				if self.z_step == 0:
					msgBox = QMessageBox()
					msgBox.setText("Z Step cannot be zero. Please retry.")
					msgBox.exec()

					self.block_ui(False)
					return None				
			
			# Ensure z_step is always positive
			self.z_step = abs(self.z_step)
						
			# Setup Micromanager Core if not set up previously			
			if self.core is None:					
				self.core = Core()

			# Set up the correct objective parameter settings from the dropdown value selected
			# This sets the pixel size in the NDTiff stacks generated by MicroManager
			if str(self.objectiveComboBox.currentText()) == '4x':
				self.core.set_config('Objective', 'Objective-A')
				
			if str(self.objectiveComboBox.currentText()) == '10x':
				self.core.set_config('Objective', 'Objective-B')

			# Get XY pixel size in microns, camera tile size in pixels (X and Y)
			self.PIXEL_SIZE = self.core.get_pixel_size_um()
			roi = self.core.get_roi()
			self.TILE_SIZE_X = roi.width
			self.TILE_SIZE_Y = roi.height

			# Log this info to the log file
			print('Pixel size set to ' + str(self.PIXEL_SIZE) + ', Tile size set to (rows, cols): ' + str(self.TILE_SIZE_X) + ' ' + str(self.TILE_SIZE_Y))			
			logging.info('Pixel size set to ' + str(self.PIXEL_SIZE) + ', Tile size set to (rows, cols): ' + str(self.TILE_SIZE_X) + ' ' + str(self.TILE_SIZE_Y))

			# Identify the correct sorting of the tiles, this is used to arrange the order of tiles before sending to the stitching module (ITKMontage)
			if self.STITCHING_FLAG:
				self.stitcher = Stitcher()

				# Hardcode in the max positions for X and Y stages, change if stages are changed
				x_stage_max = 25400
				y_stage_max = 20000

				self.SORTED_INDICES =self.stitcher.convert_xy_positions_to_tile_configuration(xy_positions, self.PIXEL_SIZE, self.TILE_CONFIG_PATH, x_stage_max, y_stage_max)

			# Pycro-manager acquisition (this is the interval time between events, used to calculate the minimum start time of an event)
			# Our acquisition will not exactly follow this time interval since we wait for cutting signal between imaging cycles
			# So it is ok to keep this to really small value
			time_interval_s = 0.001
			
			# Get number of images to collect based on the skip images value
			num_images = len(range(0, num_cuts, int(self.skipEveryLineEdit.text())+1))

			# Get values of autofocus every __ images, and skip every __ slices
			autoFocusEvery = int(self.autoFocusEveryLineEdit.text())				
			skipEvery = int(self.skipEveryLineEdit.text())

			# Log this info to the log file
			logging.info('Skipping imaging every %s slices', skipEvery)
			logging.info('Autofocus set to occur every %s images', autoFocusEvery)
			logging.info('This will generate %s images', num_images)	

			# Calculate actual section thickness in the image stack
			# Hardcoded as one section on the microtome is 3 microns
			z_thickness = 3 * (skipEvery + 1)

			# Set folder name for the stitched directory based on the next acquisition number
			# All acquisitions get a stitched directory, it will be empty if only a single tile was set up
			self.STITCHED_DIRECTORY = self.STORAGE_DIRECTORY + r'\\MUSE_stitched_acq_' + str(len(prev_acqs) + 1) + '.zarr'

			# Create this stitched directory irrespective of the stitching flag being set
			# If you want to create this folder only when stitching is done, move this line into the next if statement.
			os.makedirs(self.STITCHED_DIRECTORY, exist_ok=True)

			# Set up the zarr storage with the stitched image size, chunk size specifications etc.
			if self.STITCHING_FLAG:
				self.stitcher.set_up_zarr_store_for_stitched_images(self.STITCHED_DIRECTORY, num_images, self.NUM_TILES, self.TILE_SIZE_X, self.TILE_SIZE_Y, num_tiles_x, num_tiles_y, z_thickness)
			
			# Set exposure time and startup group and stage move timeout value
			self.core.set_exposure(int(self.exposureTimeLineEdit.text()))
			self.core.set_config('Startup', 'Initialization')
			self.core.set_property('Core', 'TimeoutMs', '40000')

			# Log the exposure time info
			logging.info('Set eposure time to %s', int(self.exposureTimeLineEdit.text()))

			# Create an object of imaging class, pass all relavent parameters to its initialization
			self.imagingThread = imagingClass(self.STORAGE_DIRECTORY, xyz_positions, num_cuts, num_images, time_interval_s, self.board, self.studio,
													self.NUM_TILES, self.STITCHING_FLAG, self.SORTED_INDICES, self.stitcher,  self.TILE_SIZE_Y, self.TILE_SIZE_X, 
													self.PIXEL_SIZE, self.TILE_CONFIG_PATH, self.core, autoFocusEvery, skipEvery, self.Z_STACK_STITCHING, self.z_start,
													self.z_stop, self.z_step)
			
			# Connect progress update, acquisition complete and status bar signals with appropriate functions in this file
			self.imagingThread.progressSignal.connect(self.progressUpdate)
			self.imagingThread.progressMinimumSignal.connect(self.progressMinimum)
			self.imagingThread.progressMaximumSignal.connect(self.progressMaximum)
			self.imagingThread.completeSignal.connect(self.acquisitionComplete)
			self.imagingThread.statusBarSignal.connect(self.statusBarMessage)

			# Start the thread
			self.imagingThread.start()

# File entry point
if __name__ == "__main__":

	# Generic Qt application code, show the UI, handle user requests using signal/slot mechanism
	# Signal and slots can be modified in Qt Designer
	app = QApplication([])
	window = Window()
	window.show()
	sys.exit(app.exec())