import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QFileDialog, QDialog
from PyQt5 import uic
import os
from pycromanager import Studio, Core
import pyfirmata
import time
import glob

from acquisition_module import acquisitionClass
from trimming_module import trimmingClass
from stitching_module import *

import logging

class Window(QMainWindow):
	def __init__(self):
		super(Window, self).__init__()
		uic.loadUi('ui files\mainwindow.ui', self)
		self.show() 

		self.board = None
		self.studio = None

		self.dialog = None

		self.trimmingThread = None
		self.acquisitionThread = None
		
		self.core = None

	# Home stages
	def home_stages(self):

		try:
			self.core = Core()	
			self.core.set_property('Core', 'TimeoutMs', '25000')	
			
			self.block_ui(True)
			self.core.home("XYStage")
			self.core.home("Stage")
			self.block_ui(False)

			self.homeStagesPushButton.setEnabled(False)

		except:
			msgBox = QMessageBox()
			msgBox.setText("Did not find MicroManager to be open, ensure that it is open.")
			msgBox.exec()

	# Get XYZ positions from Micromanager
	def get_xyz_positions(self):

		try:
			self.studio = Studio()
		except Exception as e:
			print(str(e))
			return None, None

		# Pull current MDA window positions
		acq_manager = self.studio.acquisitions()
		acq_settings = acq_manager.get_acquisition_settings()
		position_list_manager = self.studio.positions()
		position_list = position_list_manager.get_position_list()
		number_positions = position_list.get_number_of_positions()
		xy_positions = np.empty((number_positions,2))
		z_positions = np.empty((number_positions))

		# Iterate through position list to extract XY positions    
		for idx in range(number_positions):
			pos = position_list.get_position(idx)
			for ipos in range(pos.size()):
				stage_pos = pos.get(ipos)
				if (stage_pos.get_stage_device_label() == 'XYStage'):
					xy_positions[idx,:] = [stage_pos.x, stage_pos.y]
				if (stage_pos.get_stage_device_label() == 'Stage'):
					z_positions[idx] = stage_pos.x

		return xy_positions, z_positions

	# Switch on light source upon user selection in GUI
	def switch_on_light_source(self, isChecked):

		if self.board is None:
			msgBox = QMessageBox()
			msgBox.setText("Arduino board is not initialized, please press the Initialize Arduino button")
			msgBox.exec()

			self.switchOnLightCheckbox.setChecked(False)
			return None
		
		else:
			if isChecked:
				self.board.digital[10].write(0)
			else:
				self.board.digital[10].write(1)

	def stop_run(self):
		if self.TRIMMING_FLAG:
			if self.trimmingThread is not None:
				self.trimmingThread.stop()

		else:
			if self.acquisitionThread is not None:
				self.acquisitionThread.stop()	

		self.progressBar.setValue(0)
		self.statusBar().showMessage('Acquisition stopped.', 4000)	

	def block_ui(self, flag):

		try:
			self.startAcquisitionButton.released.disconnect()
		except TypeError:
			print('No functions set up to run on start/stop push button click.')
			pass

		if flag:
			self.storageDirEdit.setEnabled(False)
			self.numberCutsEdit.setEnabled(False)
			self.trimBlockCheckbox.setEnabled(False)
			self.registerImageCheckbox.setEnabled(False)
			self.autoFocusEveryLineEdit.setEnabled(False)
			self.homeStagesPushButton.setEnabled(False)
			self.storageDirButton.setEnabled(False)
			self.exposureTimeLineEdit.setEnabled(False)
			self.skipEveryLineEdit.setEnabled(False)
			self.objectiveComboBox.setEnabled(False)
			self.startAcquisitionButton.setText('Stop acquisition')
			self.startAcquisitionButton.released.connect(self.stop_run)

			self.label_1.setEnabled(False)
			self.label_2.setEnabled(False)
			self.label_3.setEnabled(False)
			self.label_4.setEnabled(False)
			self.label_5.setEnabled(False)
			self.label.setEnabled(False)

		else:
			self.storageDirEdit.setEnabled(True)
			self.numberCutsEdit.setEnabled(True)
			self.trimBlockCheckbox.setEnabled(True)
			self.registerImageCheckbox.setEnabled(True)
			self.autoFocusEveryLineEdit.setEnabled(True)
			self.homeStagesPushButton.setEnabled(True)
			self.storageDirButton.setEnabled(True)
			self.exposureTimeLineEdit.setEnabled(True)
			self.skipEveryLineEdit.setEnabled(True)
			self.objectiveComboBox.setEnabled(True)
			self.startAcquisitionButton.setText('Start acquisition')
			self.startAcquisitionButton.released.connect(self.run_acquisition)

			self.label_1.setEnabled(True)
			self.label_2.setEnabled(True)
			self.label_3.setEnabled(True)
			self.label_4.setEnabled(True)
			self.label_5.setEnabled(True)
			self.label.setEnabled(True)

	# Initialize the arduino board
	def initialize_arduino(self):

		if self.board is None:

			# Define the arduino board (get from UI later, hardcode for now)
			#self.board = pyfirmata.Arduino(str(self.arduinoPortEdit.text()))
			self.board = pyfirmata.Arduino(str("COM5"))

			# Set input and output pins
			self.board.digital[8].mode = pyfirmata.OUTPUT
			self.board.digital[9].mode = pyfirmata.OUTPUT
			self.board.digital[10].mode = pyfirmata.OUTPUT        
			self.board.digital[12].mode = pyfirmata.INPUT

			# Start the iterator
			it = pyfirmata.util.Iterator(self.board)
			it.start()

			# Switch off the emergency stop, cutting and light source, inverted logic
			self.board.digital[8].write(1)
			self.board.digital[9].write(1)
			self.board.digital[10].write(1)

			self.statusBar().showMessage('Arduino initialization complete', 5000)

			self.initializeArduinoButton.setEnabled(False)
		
		else:
			self.statusBar().showMessage('Arduino already initialized, relaunch 3D-MUSE-acquire if need to change values')

		
	# Open directory to store raw data
	def open_storage_dir(self):
		title = "Open Folder to save data"
		flags = QFileDialog.ShowDirsOnly
		path = QFileDialog.getExistingDirectory(self,
												title,
												os.path.expanduser("."),
												flags)

		self.storageDirEdit.setText(path)

		self.statusBar().showMessage('Storage folder location saved', 2000)

	# Open directory to store stitched data
	def open_stitched_dir(self):
		title = "Open Folder to save stitched data"
		flags = QFileDialog.ShowDirsOnly
		path = QFileDialog.getExistingDirectory(self,
												title,
												os.path.expanduser("."),
												flags)

		self.stitchDirEdit.setText(path)

		self.statusBar().showMessage('Stitched folder location saved', 2000)

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

		if "End of" in string:
			self.statusBar().showMessage(string, 2000)
		else:
			self.statusBar().showMessage(string)

	# Complete signal from the threads
	def acquisitionComplete(self, value):
		if value == 1:
			self.statusBar().showMessage("Imaging session complete")
			self.acquisitionThread.terminate_thread()
		if value == 2:
			self.statusBar().showMessage("Trimming session complete")
			self.trimmingThread.terminate_thread()

		self.progressBar.setValue(0)
		self.block_ui(False)

	# Open a dialog box with instructions
	def open_instructions(self):

		# Create an instance of the dialog to open the .ui file
		self.dialog = QDialog()
		# Load the .ui file into the dialog
		uic.loadUi("ui files\helpwindow.ui", self.dialog)
		# Show the dialog
		self.dialog.show()
				
	# Run the acquisition    
	def run_acquisition(self):

		# Set up logging
		logfile = str(self.storageDirEdit.text()) + '\\muse_application.log'
		logging.basicConfig(filename = logfile, filemode = 'a', level = logging.DEBUG, format = '%(asctime)s - %(levelname)s: %(message)s', datefmt = '%m/%d/%Y %I:%M:%S %p')


		if self.board is None:
			self.REGISTER_FLAG = False
			msgBox = QMessageBox()
			msgBox.setText("Arduino board is not initialized, press Initialize Arduino button first.")
			msgBox.exec()
			return None
					
		# Disable the UI so that user cannot edit line items during acq
		self.block_ui(True)
		
		# Number of cuts, trimming flag will not image
		num_cuts = int(self.numberCutsEdit.text())
		self.progressBar.setMinimum(0)
		self.progressBar.setMaximum(num_cuts)
		self.TRIMMING_FLAG = self.trimBlockCheckbox.isChecked()

		if int(self.skipEveryLineEdit.text()):
			num_images = len(range(0, num_cuts, int(self.skipEveryLineEdit.text())+1))
		else:
			num_images = num_cuts

		# If only trimming and not imaging
		if self.TRIMMING_FLAG:
			logging.info('----TRIMMING CYCLE----')
			logging.info('Trimming set to %s cuts', num_cuts)
			self.trimmingThread = trimmingClass(num_cuts, self.board, str(self.storageDirEdit.text()))
			self.trimmingThread.progressSignal.connect(self.progressUpdate)
			self.trimmingThread.progressMinimumSignal.connect(self.progressMinimum)
			self.trimmingThread.progressMaximumSignal.connect(self.progressMaximum)
			self.trimmingThread.completeSignal.connect(self.acquisitionComplete)
			self.trimmingThread.statusBarSignal.connect(self.statusBarMessage)
			self.trimmingThread.start()

		# Imaging
		else:
			# Hardcode these values in for now, get from UI as presets later
			# Use them to configure micromanager appropriately
			# self.PIXEL_SIZE = float(self.pixelSizeEdit.text())
			# self.TILE_SIZE_X = int(self.imageSizeXEdit.text())
			# self.TILE_SIZE_Y = int(self.imageSizeYEdit.text())

			self.PIXEL_SIZE = float(0.9)
			self.TILE_SIZE_X = int(4000)
			self.TILE_SIZE_Y = int(3000)

			# Set values from the UI
			self.STORAGE_DIRECTORY = str(self.storageDirEdit.text())

			prev_acqs = glob.glob(self.STORAGE_DIRECTORY + r'\\MUSE_acq_*')

			self.STITCHED_DIRECTORY = self.STORAGE_DIRECTORY + r'\\MUSE_stitched_acq_' + str(len(prev_acqs) + 1) + '.zarr'

			os.makedirs(self.STORAGE_DIRECTORY, exist_ok=True)
			os.makedirs(self.STITCHED_DIRECTORY, exist_ok=True)

			logging.info('---- ACQUISITION CYCLE ' + str(len(prev_acqs) + 1) + '----')
			logging.info('Imaging set to % s cuts', num_cuts)

			# Get XYZ positions for the tiles from MDA window, calculate number of tiles
			xy_positions, z_positions = self.get_xyz_positions()

			if xy_positions is None and z_positions is None:
				msgBox = QMessageBox()
				msgBox.setText("Could not retrieve positions, try running the acquisition again. Ensure MicroManager is open.")
				msgBox.exec()
				return

			xyz_positions = np.hstack((xy_positions, np.expand_dims(z_positions, axis=1)))
			self.NUM_TILES = xy_positions.shape[0]
			self.TILE_CONFIG_PATH = self.STORAGE_DIRECTORY + r'\\TileConfiguration_acq_' + str(len(prev_acqs) + 1) + '.txt'
			logging.info('Received XYZ positions from Micromanager')

			print('XY positions')
			print(xy_positions)

			print('Z positions')
			print(z_positions)

			logging.info('XY positions are: %s', xy_positions)
			logging.info('Z positions are: %s', z_positions)

			# Stitching and registration are needed if there is more than one tile
			self.STITCHING_FLAG = (self.NUM_TILES != 1)
			self.REGISTRATION_REQUIRED = (self.NUM_TILES != 1)

			# If registration is suggested but not required, we will not register
			self.REGISTRATION_SUGGESTED = self.registerImageCheckbox.isChecked()
			
			if self.REGISTRATION_REQUIRED and self.REGISTRATION_SUGGESTED:
				self.REGISTER_FLAG = True
			
			elif self.REGISTRATION_SUGGESTED and not self.REGISTRATION_REQUIRED:
				self.REGISTER_FLAG = False
				msgBox = QMessageBox()
				msgBox.setText("Since only one tile is acquired, registration is not required, skipping.")
				msgBox.exec()

			else:
				self.REGISTER_FLAG = False
			
			self.statusBar().showMessage('Registration flag set to ' + str(self.REGISTER_FLAG))
			
			# Find number of tiles
			num_tiles_x = len(np.unique(xy_positions[:,0]))
			num_tiles_y = len(np.unique(xy_positions[:,1]))

			if num_tiles_x == 0 and num_tiles_y == 0:
				msgBox = QMessageBox()
				msgBox.setText("Did not find tile set up in MicroManager. Please ensure tiles are specified using the MultiD Acq. window in MM.")
				msgBox.exec()

				self.block_ui(False)
				return None

			if self.NUM_TILES != (num_tiles_x * num_tiles_y):
				raise ValueError('Expected tile positions to be on a uniform grid')
			
			logging.info('Found %s tiles', self.NUM_TILES)	
			self.statusBar().showMessage('Found ' + str(num_tiles_x) + ' tiles in x and ' + str(num_tiles_y) + ' tiles in y')

			# Identify the correct sorting of the tiles, used to arrange tiles before sending to the stitching module
			self.SORTED_INDICES = None
			self.stitcher = None
			if self.STITCHING_FLAG:
				self.stitcher = Stitcher()
				self.SORTED_INDICES =self.stitcher.convert_xy_positions_to_tile_configuration(xy_positions, self.PIXEL_SIZE, self.TILE_CONFIG_PATH)

			# Imaging, pycro-manager acquisition
			time_interval_s = 0.001
			folder_created = True

			if self.STITCHING_FLAG:
				folder_created = self.stitcher.set_up_zarr_store_for_stitched_images(self.STITCHED_DIRECTORY, num_images, self.NUM_TILES, self.TILE_SIZE_X, self.TILE_SIZE_Y, num_tiles_x, num_tiles_y)
			
			if folder_created:
				self.core = Core()
				autoFocusEvery = int(self.autoFocusEveryLineEdit.text())				
				skipEvery = int(self.skipEveryLineEdit.text())

				logging.info('Skipping imaging every %s slices', skipEvery)
				logging.info('Autofocus set to occur every %s images', autoFocusEvery)
				logging.info('This will generate %s images', num_images)
				
				if self.core is None:					
					self.core = Core()	

				self.core.set_property('Core', 'TimeoutMs', '25000')
				self.core.set_exposure(int(self.exposureTimeLineEdit.text()))
				self.core.set_config('Startup', 'Initialization')

				if str(self.objectiveComboBox.currentText()) == '4x':
					self.core.set_config('Objective', 'Objective-A')
					
				if str(self.objectiveComboBox.currentText()) == '10x':
					self.core.set_config('Objective', 'Objective-B')

				self.acquisitionThread = acquisitionClass(self.STORAGE_DIRECTORY, xyz_positions, num_cuts, num_images, time_interval_s, self.board, self.studio,
														self.NUM_TILES, self.STITCHING_FLAG, self.SORTED_INDICES, self.stitcher,  self.TILE_SIZE_Y, self.TILE_SIZE_X, 
														self.PIXEL_SIZE, self.TILE_CONFIG_PATH, self.core, autoFocusEvery, skipEvery)
				
				self.acquisitionThread.progressSignal.connect(self.progressUpdate)
				self.acquisitionThread.progressMinimumSignal.connect(self.progressMinimum)
				self.acquisitionThread.progressMaximumSignal.connect(self.progressMaximum)
				self.acquisitionThread.completeSignal.connect(self.acquisitionComplete)
				self.acquisitionThread.statusBarSignal.connect(self.statusBarMessage)
				self.acquisitionThread.start()

		# TODO: Image registration with elastix

if __name__ == "__main__":
	app = QApplication([])
	window = Window()
	window.show()
	sys.exit(app.exec())