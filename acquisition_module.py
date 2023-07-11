from PyQt5 import QtCore
from pycromanager import Acquisition, multi_d_acquisition_events
import time
import numpy as np

import logging

class acquisitionClass(QtCore.QThread):
	
	progressSignal = QtCore.pyqtSignal(int)
	progressMinimumSignal = QtCore.pyqtSignal(int)
	progressMaximumSignal = QtCore.pyqtSignal(int)
	completeSignal = QtCore.pyqtSignal(int) 
	statusBarSignal = QtCore.pyqtSignal(str)
	
	def __init__(self, STORAGE_DIRECTORY, xyz_positions, num_cuts, num_images, time_interval_s, board, studio, NUM_TILES, STITCHING_FLAG, SORTED_INDICES, stitcher, TILE_SIZE_Y, TILE_SIZE_X, PIXEL_SIZE, TILE_CONFIG_PATH, core, autoFocusEvery, skipEvery):
		
		super(acquisitionClass, self).__init__(None)
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

		# List to store tile images, refreshed after each image slice
		self.tiles = []

		# Set progress bar limits
		self.progressMinimumSignal.emit(0)
		self.progressMaximumSignal.emit(self.num_cuts)
		
		# Indices that will keep track of index in image stack (image_index) and cut cycle (cut_index)
		self.current_image_index = 0
		self.current_cut_index = 0

		# Used to store focused positions at each tile
		self.best_z_positions = np.zeros((self.NUM_TILES))

		# Flag to keep track of whether the user clicked on stop acquisition
		self.threadActive = True

	# Switch on the light source and open the shutter before snapping a picture
	def post_hardware_hook_fn(self, event):

		time.sleep(3)

		# Delete the events if the thread is no longer active (user clicked stop)
		if not self.threadActive:
			return None
		
		# If slices need to be skipped, run additional sectioning cycles here
		if self.skipEvery and self.current_cut_index != 0:
			for i in range(self.skipEvery):

				# Poll once every second to see if the cut signal is complete
				while not self.board.digital[12].read():
					time.sleep(1)

				# Send a cutting signal
				self.current_cut_index = self.current_cut_index + 1
				self.board.digital[9].write(0)
				time.sleep(3)
				self.board.digital[9].write(1)

				self.progressSignal.emit(int(self.current_cut_index))
				self.statusBarSignal.emit('End of cutting section # %s', int(self.current_cut_index))
				logging.info('Image process function - Skipped imaging %s cut', i)

				if not self.threadActive:
					break

		# Poll once every second to see if the cut signal is complete.
		while not self.board.digital[12].read():
			time.sleep(1)

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

		logging.info('Returning from post hardware hook function %s', self.current_image_index)

		# Return the event as is if there are no focus positions set (autofocusEvery was zero)
		if self.best_z_positions[int(event['axes']['position'])] == 0:
			return event
		
		# Change the event z positions if focus positions were collected
		else:
			event['z'] = self.best_z_positions[int(event['axes']['position'])]
			return event

	# After capturing an image, stitching if required, skip slices if specified
	def image_process_fn(self, image, metadata):

		# Accumulate individual tiles
		self.tiles.append(np.reshape(image, (self.TILE_SIZE_Y, self.TILE_SIZE_X)))

		# If you have all the tiles for this image slice
		if len(self.tiles) == self.NUM_TILES:
			
			# Switch off the light source
			self.board.digital[10].write(1)

			# Send a cutting signal
			self.current_cut_index = self.current_cut_index + 1
			self.board.digital[9].write(0)
			time.sleep(3)
			self.board.digital[9].write(1)

			# Get the current image index
			self.current_image_index  = metadata['Axes']['time']
			self.statusBarSignal.emit('End of imaging slice # ' + str(self.current_image_index + 1))
			logging.info('Image process function - End of imaging slice # ' + str(self.current_image_index + 1))
			self.progressSignal.emit(int(self.current_cut_index))

			# Pass array for stitching
			if self.STITCHING_FLAG:

				# Sort the tiles based on the sorting indices
				self.tiles = [self.tiles[i] for i in self.SORTED_INDICES]

				self.stitcher.stitch_tiles(self.tiles, self.TILE_CONFIG_PATH, self.PIXEL_SIZE, self.current_image_index)
				self.statusBarSignal.emit('Tile stitching complete for image slice # ' + str(self.current_image_index + 1))
				
				logging.info('Image process function - Tile stitching complete for image slice # ' + str(self.current_image_index + 1))

			# Reset the list container
			self.tiles = []

		return image, metadata

	def stop(self):
		self.threadActive = False
		self.wait()

	def run(self):

		with Acquisition(directory=self.STORAGE_DIRECTORY, name='MUSE_acq', image_process_fn=self.image_process_fn, post_hardware_hook_fn=self.post_hardware_hook_fn) as acq:
			events = multi_d_acquisition_events(xyz_positions=self.xyz_positions,  num_time_points=self.num_images, time_interval_s=self.time_interval_s)

			for event in events:	
				acq.acquire(event)

				if not self.threadActive:
					break

			# TODO - is this needed?
			# acq.await_completion()

		if self.threadActive:
			logging.info('Completed acquisition cycle, finished %s cuts', self.num_cuts)

		else:
			logging.info('Acquisition cycle stopped after %s cuts', self.current_cut_index)

		self.completeSignal.emit(1)

	# Stop the thread
	def terminate_thread(self):
		
		self.quit()
		self.wait()