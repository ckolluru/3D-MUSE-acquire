from PyQt5 import QtCore
from pycromanager import Acquisition, multi_d_acquisition_events
import time
import numpy as np

# TODO - choose one or better eventually
import focus_stacking_module
import focus_stacking_module_2

import logging

# Set up the imaging class
class imagingClass(QtCore.QThread):
	
	# Signals that we need to update from this thread
	progressSignal = QtCore.pyqtSignal(int)
	progressMinimumSignal = QtCore.pyqtSignal(int)
	progressMaximumSignal = QtCore.pyqtSignal(int)
	completeSignal = QtCore.pyqtSignal(int) 
	statusBarSignal = QtCore.pyqtSignal(str)
	
	def __init__(self, STORAGE_DIRECTORY, xyz_positions, num_cuts, num_images, time_interval_s, board, studio, NUM_TILES, STITCHING_FLAG, SORTED_INDICES, stitcher, TILE_SIZE_Y, TILE_SIZE_X, PIXEL_SIZE, TILE_CONFIG_PATH, core, autoFocusEvery, skipEvery, Z_STACK_STITCHING, z_start, z_stop, z_step):
		
		super(imagingClass, self).__init__(None)

		# Copy over all the variables that we need from main.py, kept the variable names the same for ease of use
		self.STORAGE_DIRECTORY = STORAGE_DIRECTORY
		self.xyz_positions = xyz_positions
		self.num_cuts = num_cuts
		self.num_images = num_images
		self.time_interval_s= time_interval_s
		self.board = board
		self.studio = studio
		self.NUM_TILES = NUM_TILES
		self.STITCHING_FLAG = STITCHING_FLAG
		self.SORTED_INDICES = SORTED_INDICES
		self.stitcher  = stitcher
		self.core = core
		self.autoFocusEvery = autoFocusEvery
		self.skipEvery = skipEvery

		# Imaging parameters for stitching
		self.TILE_SIZE_Y = TILE_SIZE_Y
		self.TILE_SIZE_X = TILE_SIZE_X
		self.PIXEL_SIZE = PIXEL_SIZE
		self.TILE_CONFIG_PATH = TILE_CONFIG_PATH

		# List to store tile images, reset after each image slice and after stitching is complete
		self.tiles = []

		# List to store focus stack images, needs to be reset after each tile
		self.focus_stack_tile = []

		# Set progress bar limits
		self.progressMinimumSignal.emit(0)
		self.progressMaximumSignal.emit(self.num_cuts)
		
		# Indices that will keep track of index in image stack (image_index) and cut cycle (cut_index)
		self.current_image_index = 0
		self.current_cut_index = 0
		self.old_cut_index = 0

		# Z stack stitching
		self.Z_STACK_STITCHING = Z_STACK_STITCHING

		# Get the number of focus positions
		if self.Z_STACK_STITCHING:
			self.num_focus_positions = len(range(int(z_start), int(z_stop), int(z_step)))
			self.z_start = int(z_start)
			self.z_stop = int(z_stop)
			self.z_step = int(z_step)

			self.focusstacker = focus_stacking_module_2.FocusStacker()

		else:
			self.num_focus_positions = 0
			self.z_start = None
			self.z_stop = None
			self.z_step = None

		# Flag to indicate to post hardware hook function that we are merging slices from a tile and it needs to wait
		self.focus_stacking_in_progress = False

		# Use this variable to store the best focus positions at each tile - set after autofocus
		# If focus stacking is set up, it will be done relative to this position
		self.best_z_positions = np.zeros((self.NUM_TILES))

		# Flag to keep track of whether the user clicked on stop acquisition
		self.threadActive = True

		# Debugging - used to check how long it has been since a cut signal was sent
		# Using it to break out of waiting for the cut complete to be set right now
		# Should not be required in the future
		self.last_cutting_time = time.time()

	# If user clicked on stop acquisition
	def stop(self):
		# Set the thread active bool to False
		self.threadActive = False
		self.wait()

	# Setup the autofocus parameters
	def setup_autofocus_params(self):
		   
		# Autofocusing method
		afm = self.studio.get_autofocus_manager()
		afm.set_autofocus_method_by_name("JAF(TB)")  

		# Autofocusing parameters
		afm_method = afm.get_autofocus_method()
		afm_method.set_property_value("Threshold", "0.1")  
		afm_method.set_property_value("1st step size", "3")
		afm_method.set_property_value("1st setp number", "1")
		afm_method.set_property_value("2nd step size", "0.3")
		afm_method.set_property_value("2nd step number", "2")
		afm_method.set_property_value("Threshold", "0.1")
		afm_method.set_property_value("Crop ratio", "0.5")

		# Apply these settings
		afm_method.apply_settings()
		afm_method.save_settings()

	# Called before any of the hardware (stages) state changes (moves)
	# Hook functions are blocking, so if there is a sleep here, it will wait before going to the next event
	def pre_hardware_hook_fn(self, event):

		# Return none for the event if thread is no longer active
		if not self.threadActive:
			return None
		
		return event

	# Switch on the light source before snapping a picture
	# Blocking call
	def post_hardware_hook_fn(self, event):		

		# Return none for the event if thread is no longer active
		if not self.threadActive:
			return None

		time.sleep(3)
		
		# Check whether focus stacking is in progress and if so, wait here
		while self.Z_STACK_STITCHING and self.focus_stacking_in_progress:
			time.sleep(1)

		# If slices need to be skipped, run additional sectioning cycles here
		if self.skipEvery and self.current_cut_index != 0:
			
			logging.info('Post hardware hook function -  checking (current_cut_index, old_cut_index) - %s %s', self.current_cut_index, self.old_cut_index)

			if self.current_cut_index != self.old_cut_index:

				# Loop through the number of skip cycles needed
				for i in range(1, self.skipEvery + 1):

					# Poll once every second to see if the cut signal is complete
					while not self.board.digital[12].read():
						time.sleep(1)

						# If you don't get cut complete signal from the microtome in 25 seconds, assume cut was complete
						# Do not want to get stuck in an infinite loop
						if time.time() - self.last_cutting_time > 25:
							break

					# Send a cutting signal, increment cut index
					self.last_cutting_time = time.time()
					self.current_cut_index = self.current_cut_index + 1
					self.board.digital[9].write(0)
					time.sleep(3)
					self.board.digital[9].write(1)

					# Update progress bars, status bar, logging
					self.progressSignal.emit(int(self.current_cut_index))
					self.statusBarSignal.emit('Post hardware hook function - End of cutting section #' + str(int(self.current_cut_index)))
					logging.info('Post hardware hook function - Skipped imaging %s cut', i)

					# Break out of loop if user clicked on stop acquisition button
					if not self.threadActive:
						break
				
				# Set a variable to check whether a cut signal was sent from image processing function
				self.old_cut_index = self.current_cut_index
				logging.info('Post hardware hook function - Setting old_cut_index to current_cut_index %s', self.old_cut_index)

		# Return none for the event if thread is no longer active
		if not self.threadActive:
			return None
		
		# Poll once every second to see if the cut signal is complete.
		while not self.board.digital[12].read():
			time.sleep(1)

			# If you don't get cut complete signal from the microtome in 25 seconds, assume cut was complete
			# Do not want to get stuck in an infinite loop
			if time.time() - self.last_cutting_time > 25:
				break

		logging.info('Post hardware hook function - received cut complete, imaging')

		# Switch on the light source
		self.board.digital[10].write(0)

		# Run an autofocus if needed
		if self.autoFocusEvery: 
			if ((self.current_image_index + 1) % self.autoFocusEvery == 0) and self.current_image_index != 0:

				# Move the z-stage to the position in the stage position list
				self.core.set_position("Stage", event['z'])
				self.core.wait_for_device("Stage")

				# Run the autofocus
				afm = self.studio.get_autofocus_manager()
				afm_method = afm.get_autofocus_method()
				afm_method.full_focus()
				self.statusBarSignal.emit('Autofocus complete')

				# Update best z positions
				self.best_z_positions[int(event['axes']['position'])] = self.core.get_position()

		logging.info('Post hardware hook function - returning, current_image_index %s', self.current_image_index)

		# Return none for the event if thread is no longer active
		if not self.threadActive:
			return None
		
		# Return the event as is if there are no focus positions set (autofocusEvery was zero)
		if self.best_z_positions[int(event['axes']['position'])] == 0:
			return event
		
		# Change the event z positions if focus positions were collected and then return it
		else:
			event['z'] = self.best_z_positions[int(event['axes']['position'])]
			return event

	# Called after capturing an image, perform z-stack focusing and stitching if required
	# Non blocking call
	def image_process_fn(self, image, metadata):

		# Accumulate individual tiles directly if not focus stitching
		if not self.Z_STACK_STITCHING:
			self.tiles.append(np.reshape(image, (self.TILE_SIZE_Y, self.TILE_SIZE_X)))

		# If focus stitching, then collect all focus images at a tile
		# TODO - need a fast algorithm here
		else:
			self.focus_stack_tile.append(np.reshape(image, (self.TILE_SIZE_Y, self.TILE_SIZE_X)))
			
			# If you have all the positions at a tile for focus stacking
			if metadata['axes']['z'] == self.num_focus_positions:
				
				# Set a flag that informs the post hardware hook function that we are focus stacking
				self.focus_stacking_in_progress = True

				# Perform focus stacking
				# Needs a 3 channel uint8 dataset to work
				# Probably want to quickly normalize data between 1 and 99 percentile to 0-255
				# numpy repeat across third axis
				# get best focus index for each pixel
				# recon image at 16 bit pixelstar
				merged_image = self.focusstacker.focus_stack(self.focus_stack_tile)
				#merged_image = focus_stacking_module.focus_stack(self.focus_stack_tile)
		
				# Append the merged image into the tiles container
				self.tiles.append(merged_image)

				# Reset the list container
				self.focus_stack_tile = []

				# Reset the focus stacking progress flag
				self.focus_stacking_in_progress = False

		# If you have all the tiles for this image slice
		if len(self.tiles) == self.NUM_TILES:
			
			# Switch off the light source
			self.board.digital[10].write(1)

			# Send a cutting signal			
			self.last_cutting_time = time.time()
			self.current_cut_index = self.current_cut_index + 1
			logging.info('Image process function - Setting current_cut_index %s', self.current_cut_index)

			self.board.digital[9].write(0)
			time.sleep(3)
			self.board.digital[9].write(1)

			# Get the current image index from the metadata
			self.current_image_index  = metadata['Axes']['time'] + 1

			# Update progress bar, logging and status bar
			self.statusBarSignal.emit('End of imaging slice # ' + str(self.current_image_index))
			logging.info('Image process function - current_image_index - End of imaging slice # ' + str(self.current_image_index))
			self.progressSignal.emit(int(self.current_cut_index))

			# Pass list of image tiles for stitching
			if self.STITCHING_FLAG:

				# Sort the tiles based on the sorting indices
				self.tiles = [self.tiles[i] for i in self.SORTED_INDICES]

				# Call the stitching function
				self.stitcher.stitch_tiles(self.tiles, self.TILE_CONFIG_PATH, self.PIXEL_SIZE, self.current_image_index - 1)
				
				# Update status bar and log file
				self.statusBarSignal.emit('Image process function - Tile stitching complete for image slice # ' + str(self.current_image_index))
				logging.info('Image process function - current_image_index - Tile stitching complete for image slice # ' + str(self.current_image_index))

			# Reset the list container
			self.tiles = []

		return image, metadata

	# Called when thread.start() is called
	def run(self):

		# Set up the autofocusing parameters first
		self.setup_autofocus_params()

		# Set up the acquisition parameters, add function callbacks
		with Acquisition(directory=self.STORAGE_DIRECTORY, name='MUSE_acq', image_process_fn=self.image_process_fn, post_hardware_hook_fn=self.post_hardware_hook_fn, pre_hardware_hook_fn=self.pre_hardware_hook_fn) as acq:
			
			# Set up the event list, xyz positions, number of images to collect (timepoints) and time interval (will be ignored because we wait in our hook functions)
			events = multi_d_acquisition_events(xyz_positions=self.xyz_positions,  num_time_points=self.num_images, time_interval_s=self.time_interval_s, z_start = self.z_start, z_step = self.z_step, z_end=self.z_stop)

			for event in events:	
				acq.acquire(event)

				# Check whether the user clicked the stop acquisition button
				if not self.threadActive:
					break
				
				# Check if additional cuts are needed
				while self.current_cut_index < self.num_cuts and self.threadActive:

						# Poll once every second to see if the cut signal is complete
						while not self.board.digital[12].read():
								time.sleep(1)

								# If you don't get cut complete signal from the microtome in 25 seconds, assume cut was complete
								# Do not want to get stuck in an infinite loop
								if time.time() - self.last_cutting_time > 25:
										break

						if not self.threadActive:
							break
						
						# Send cut signal
						self.last_cutting_time = time.time()
						self.current_cut_index = self.current_cut_index + 1
						self.board.digital[0].write(0)
						time.sleep(3)
						self.board.digital[0].write(1)

						logging.info('Additional cuts - End of cutting section %s', self.current_cut_index)
						


		# Log appropriately
		if self.threadActive:
			logging.info('Completed acquisition cycle, finished %s cuts', self.num_cuts)

		else:
			logging.info('Acquisition cycle stopped after %s cuts', self.current_cut_index)

		# Send the complete signal
		self.completeSignal.emit(1)

	# Stop the thread, coming from the function that receives the complete signal in main.py
	def terminate_thread(self):
		
		self.quit()
		self.wait()
