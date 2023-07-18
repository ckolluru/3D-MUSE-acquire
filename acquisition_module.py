from PyQt5 import QtCore
from pycromanager import Acquisition, multi_d_acquisition_events
import time
import numpy as np
import FocusStack

import logging

class acquisitionClass(QtCore.QThread):
	
	progressSignal = QtCore.pyqtSignal(int)
	progressMinimumSignal = QtCore.pyqtSignal(int)
	progressMaximumSignal = QtCore.pyqtSignal(int)
	completeSignal = QtCore.pyqtSignal(int) 
	statusBarSignal = QtCore.pyqtSignal(str)
	
	def __init__(self, STORAGE_DIRECTORY, xyz_positions, num_cuts, num_images, time_interval_s, board, studio, NUM_TILES, STITCHING_FLAG, SORTED_INDICES, stitcher, TILE_SIZE_Y, TILE_SIZE_X, PIXEL_SIZE, TILE_CONFIG_PATH, core, autoFocusEvery, skipEvery, Z_STACK_STITCHING, z_start, z_stop, z_step):
		
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
		self.focus_stack_tile = []

		# Set progress bar limits
		self.progressMinimumSignal.emit(0)
		self.progressMaximumSignal.emit(self.num_cuts)
		
		# Indices that will keep track of index in image stack (image_index) and cut cycle (cut_index)
		self.current_image_index = 0
		self.current_cut_index = 0
		self.old_cut_index = 0

		# Z stack stitching
		self.Z_STACK_STITCHING_FLAG = Z_STACK_STITCHING
		self.z_start = z_start
		self.z_stop = z_stop
		self.z_step = z_step
		if self.Z_STACK_STITCHING_FLAG:
			self.num_focus_positions = len(range(int(z_start), int(z_stop), int(z_step)))
		else:
			self.num_focus_positions = 0

		# Used to store focused positions at each tile
		self.best_z_positions = np.zeros((self.NUM_TILES))

		# Flag to keep track of whether the user clicked on stop acquisition
		self.threadActive = True

		self.last_cutting_start_time = time.time()

	# Before any of the hardware (stages) state changes (moves)
	def pre_hardware_hook_fn(self, event):
		if not self.threadActive:
			return None

	# Switch on the light source and open the shutter before snapping a picture
	def post_hardware_hook_fn(self, event):		

		# Delete the events if the thread is no longer active (user clicked stop)
		if not self.threadActive:
			return None

		time.sleep(3)
		
		# If slices need to be skipped, run additional sectioning cycles here
		if self.skipEvery and self.current_cut_index != 0:
			
			logging.info('Post hardware hook function -  checking (current_cut_index, old_cut_index) - %s %s', self.current_cut_index, self.old_cut_index)
			if self.current_cut_index != self.old_cut_index:
				for i in range(self.skipEvery):

					# Poll once every second to see if the cut signal is complete
					while not self.board.digital[12].read():
						time.sleep(1)

						# If you don't get a cut complete signal within 18 seconds, try cutting again
						if time.time() - self.last_cutting_start_time > 18:
							break

					# Send a cutting signal
					self.last_cutting_start_time = time.time()
					self.current_cut_index = self.current_cut_index + 1
					self.board.digital[9].write(0)
					time.sleep(3)
					self.board.digital[9].write(1)

					self.progressSignal.emit(int(self.current_cut_index))
					self.statusBarSignal.emit('Post hardware hook function - End of cutting section #' + str(int(self.current_cut_index)))
					logging.info('Post hardware hook function - Skipped imaging %s cut', i)

					if not self.threadActive:
						break

				self.old_cut_index = self.current_cut_index
				logging.info('Post hardware hook function - Setting old_cut_index to current_cut_index %s', self.old_cut_index)

		if not self.threadActive:
			return None
		
		# Poll once every second to see if the cut signal is complete.
		while not self.board.digital[12].read():
			time.sleep(1)

			# If you don't get a cutting signal back, try cutting again
			if time.time() - self.last_cutting_start_time > 18:
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

		if not self.threadActive:
			return None
		
		# Return the event as is if there are no focus positions set (autofocusEvery was zero)
		if self.best_z_positions[int(event['axes']['position'])] == 0:
			return event
		
		# Change the event z positions if focus positions were collected
		else:
			event['z'] = self.best_z_positions[int(event['axes']['position'])]
			return event

	# After capturing an image, stitching if required, skip slices if specified
	def image_process_fn(self, image, metadata):

		# Accumulate individual tiles directy if not focus stitching
		if not self.Z_STACK_STITCHING_FLAG:
			self.tiles.append(np.reshape(image, (self.TILE_SIZE_Y, self.TILE_SIZE_X)))

		# If focus stitching, then collect all focus images at a tile
		else:
			self.focus_stack_tile.append(np.reshape(image, (self.TILE_SIZE_Y, self.TILE_SIZE_X)))
			
			if metadata['axes']['z'] == self.num_focus_positions:

				merged_image = FocusStack.focus_stack(self.focus_stack_tile)
		
				self.tiles.append(merged_image)

				# Reset the list container
				self.focus_stack_tile = []

		# If you have all the tiles for this image slice
		if len(self.tiles) == self.NUM_TILES:
			
			# Switch off the light source
			self.board.digital[10].write(1)

			# Send a cutting signal
			self.current_cut_index = self.current_cut_index + 1
			logging.info('Image process function - Setting current_cut_index %s', self.current_cut_index)

			self.last_cutting_start_time = time.time()
			self.board.digital[9].write(0)
			time.sleep(3)
			self.board.digital[9].write(1)

			# Get the current image index
			self.current_image_index  = metadata['Axes']['time'] + 1
			self.statusBarSignal.emit('End of imaging slice # ' + str(self.current_image_index))
			logging.info('Image process function - current_image_index - End of imaging slice # ' + str(self.current_image_index))
			self.progressSignal.emit(int(self.current_cut_index))

			# Pass array for stitching
			if self.STITCHING_FLAG:

				# Sort the tiles based on the sorting indices
				self.tiles = [self.tiles[i] for i in self.SORTED_INDICES]

				self.stitcher.stitch_tiles(self.tiles, self.TILE_CONFIG_PATH, self.PIXEL_SIZE, self.current_image_index - 1)
				self.statusBarSignal.emit('Image process function - Tile stitching complete for image slice # ' + str(self.current_image_index))
				
				logging.info('Image process function - current_image_index - Tile stitching complete for image slice # ' + str(self.current_image_index))

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