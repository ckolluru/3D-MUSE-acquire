import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QFileDialog
from PyQt5 import uic
import os
from pycromanager import Studio, Core
from stitch import *
import pyfirmata
import time
import glob

from acquisition_module import acquisitionClass
from trimming_module import trimmingClass

class Window(QMainWindow):
	def __init__(self):
		super(Window, self).__init__()
		uic.loadUi('mainwindow.ui', self)
		self.show() 

		helpWindow = uic.loadUi('helpwindow.ui', self)
		self.addDockWidget(1, helpWindow)
		helpWindow.setFloating(True)

		self.board = None
		self.studio = None

	# Get XYZ positions from Micromanager
	def get_xyz_positions(self):

		self.studio = Studio()

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

	# Initialize the arduino board
	def initialize_arduino(self):

		if self.board is None:

			self.initializeArduinoButton.setEnabled(False)

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

			# Let the cut complete
			time.sleep(10)

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
		self.scrollAreaWidgetContents.setEnabled(True)
				
	# Run the acquisition    
	def run_acquisition(self):

		if self.board is None:
			self.REGISTER_FLAG = False
			msgBox = QMessageBox()
			msgBox.setText("Arduino board is not initialized, press Initialize Arduino button first.")
			msgBox.exec()
			return None
					
		# Disable the UI so that user cannot edit line items during acq
		self.scrollAreaWidgetContents.setEnabled(False)
		
		# Number of cuts, trimming flag will not image
		num_time_points = int(self.numberCutsEdit.text())
		self.progressBar.setMinimum(0)
		self.progressBar.setMaximum(num_time_points)
		self.TRIMMING_FLAG = self.trimBlockCheckbox.isChecked()

		# If only trimming and not imaging
		if self.TRIMMING_FLAG:
			self.trimmingThread = trimmingClass(num_time_points, self.board)
			self.trimmingThread.progressSignal.connect(self.progressUpdate)
			self.trimmingThread.progressMinimumSignal.connect(self.progressMinimum)
			self.trimmingThread.progressMaximumSignal.connect(self.progressMaximum)
			self.trimmingThread.completeSignal.connect(self.acquisitionComplete)
			self.trimmingThread.statusBarSignal.connect(self.statusBarMessage)
			self.trimmingThread.start()

		# Imaging
		else:
			# Hardcode these values in for now, get from UI as presets later
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

			# Create if directories exist, return if you don't want to overwrite
			if os.path.exists(self.STITCHED_DIRECTORY):
				msgBox = QMessageBox()
				msgBox.setText("Found a directory with the expected stitched folder name in the provided storage directory. Overwrite? If No is selected, acquisition will not start.")
				msgBox.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
				x = msgBox.exec()

				if x == QMessageBox.StandardButton.No:
					self.scrollAreaWidgetContents.setEnabled(True)
					return None

			os.makedirs(self.STORAGE_DIRECTORY, exist_ok=True)
			os.makedirs(self.STITCHED_DIRECTORY, exist_ok=True)

			# Get XYZ positions for the tiles from MDA window, calculate number of tiles
			xy_positions, z_positions = self.get_xyz_positions()
			xyz_positions = np.hstack((xy_positions, np.expand_dims(z_positions, axis=1)))
			self.NUM_TILES = xy_positions.shape[0]
			self.TILE_CONFIG_PATH = self.STORAGE_DIRECTORY + r'\\TileConfiguration_acq_' + str(len(prev_acqs) + 1) + '.txt'
			self.statusBar().showMessage('Received XYZ positions from Micromanager')

			print('XY positions')
			print(xy_positions)

			print('Z positions')
			print(z_positions)

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

				self.scrollAreaWidgetContents.setEnabled(True)
				return None

			if self.NUM_TILES != (num_tiles_x * num_tiles_y):
				raise ValueError('Expected tile positions to be on a uniform grid')
			
			self.statusBar().showMessage('Found ' + str(num_tiles_x) + ' tiles in x and ' + str(num_tiles_y) + ' tiles in y')

			# Identify the correct sorting of the tiles, used to arrange tiles before sending to the stitching module
			if self.STITCHING_FLAG:
				self.stitcher = Stitcher()
				self.SORTED_INDICES =self.stitcher.convert_xy_positions_to_tile_configuration(xy_positions, self.PIXEL_SIZE, self.TILE_CONFIG_PATH)

			# Imaging, pycro-manager acquisition
			time_interval_s = 1
			folder_created = True

			if self.STITCHING_FLAG:
				folder_created = self.stitcher.set_up_zarr_store_for_stitched_images(self.STITCHED_DIRECTORY, num_time_points, self.NUM_TILES, self.TILE_SIZE_X, self.TILE_SIZE_Y, num_tiles_x, num_tiles_y)
			
			if folder_created:
				self.core = Core()
				autoFocus = self.autofocusCheckbox.isChecked()

				self.acquisitionThread = acquisitionClass(self.STORAGE_DIRECTORY, xyz_positions, num_time_points, time_interval_s, self.board, autoFocus, self.studio,
														self.NUM_TILES, self.STITCHING_FLAG, self.SORTED_INDICES, self.stitcher,  self.TILE_SIZE_Y, self.TILE_SIZE_X, 
														self.PIXEL_SIZE, self.TILE_CONFIG_PATH, self.core)
				
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