from PyQt5 import QtCore
from pycromanager import Acquisition, multi_d_acquisition_events
import time
import numpy as np
from tqdm import tqdm

import humanize
import datetime as dt

class acquisitionClass(QtCore.QThread):
	
	progressSignal = QtCore.pyqtSignal(int)
	progressMinimumSignal = QtCore.pyqtSignal(int)
	progressMaximumSignal = QtCore.pyqtSignal(int)
	completeSignal = QtCore.pyqtSignal(int) 
	statusBarSignal = QtCore.pyqtSignal(str)
	
	def __init__(self, STORAGE_DIRECTORY, xyz_positions, num_cuts, num_images, time_interval_s, board, autoFocusEvery, skipEvery, studio, NUM_TILES, STITCHING_FLAG, SORTED_INDICES, stitcher, TILE_SIZE_Y, TILE_SIZE_X, PIXEL_SIZE, TILE_CONFIG_PATH, core):
		
		super(acquisitionClass, self).__init__(None)
		self.STORAGE_DIRECTORY = STORAGE_DIRECTORY
		self.xyz_positions = xyz_positions
		self.num_images = num_images
		self.time_interval_s= time_interval_s
		self.board = board
		self.autoFocusEvery = autoFocusEvery
		self.skipEvery = skipEvery
		self.studio = studio
		self.NUM_TILES = NUM_TILES
		self.STITCHING_FLAG = STITCHING_FLAG
		self.SORTED_INDICES = SORTED_INDICES
		self.stitcher  = stitcher
		self.core = core

		self.TILE_SIZE_Y = TILE_SIZE_Y
		self.TILE_SIZE_X = TILE_SIZE_X
		self.PIXEL_SIZE = PIXEL_SIZE
		self.TILE_CONFIG_PATH = TILE_CONFIG_PATH

		self.tiles = []

		self.progressMinimumSignal.emit(0)
		self.progressMaximumSignal.emit(num_cuts)
		
		self.current_time_index = None

		self.best_z_positions = np.zeros((self.NUM_TILES))

		self.threadActive = True

	# Switch on the light source and open the shutter before snapping a picture
	def post_hardware_hook_fn(self, event):
		
		time.sleep(1)

		# Poll once every second to see if the cut signal is complete.
		while not self.board.digital[12].read():
			time.sleep(1)

		# Switch on the light source
		self.board.digital[10].write(0)

		if self.current_time_index is not None: 
			if self.autoFocusEvery:
				if self.current_time_index % self.autoFocusEvery == 0 and self.current_time_index != 0:

					# Move the z-stage to the position in the stage position list
					self.core.set_position("Stage", event['z'])
					self.core.wait_for_device("Stage")

					afm = self.studio.get_autofocus_manager()
					afm_method = afm.get_autofocus_method()
					afm_method.full_focus()
					self.statusBarSignal.emit('Autofocus complete')

					# Update best z positions
					self.best_z_positions[int(event['axes']['position'])] = self.core.get_position()

		if self.best_z_positions[int(event['axes']['position'])] == 0:
			return event
		
		else:
			event['z'] = self.best_z_positions[int(event['axes']['position'])]
			return event

	# After capturing an image
	def image_process_fn(self, image, metadata):

		# Accumulate individual tiles
		self.tiles.append(np.reshape(image, (self.TILE_SIZE_Y, self.TILE_SIZE_X)))

		if len(self.tiles) == self.NUM_TILES:
			
			# Switch off the light source
			self.board.digital[10].write(1)

			# Send a cutting signal
			self.board.digital[9].write(0)
			time.sleep(3)
			self.board.digital[9].write(1)

			# Get the time point index
			time_index = metadata['Axes']['time']
			self.statusBarSignal.emit('End of section ' + str(time_index + 1 + (self.skipEvery*time_index)))
			self.progressSignal.emit(int(time_index + 1) + int(self.skipEvery*time_index))
			self.current_time_index = time_index

			# ZYX array
			if self.STITCHING_FLAG:

				# Sort the tiles based on the sorting indices
				self.tiles = [self.tiles[i] for i in self.SORTED_INDICES]

				self.stitcher.stitch_tiles(self.tiles, self.TILE_CONFIG_PATH, self.PIXEL_SIZE, self.current_time_index)
				self.statusBarSignal.emit('Tile stitching complete for section ' + str(time_index))

			# Reset the list container
			self.tiles = []

		return image, metadata

	def stop(self):
		self.threadActive = False
		self.wait()

	def run(self):
		print('Acquiring serial block-face images')

		with Acquisition(directory=self.STORAGE_DIRECTORY, name='MUSE_acq', image_process_fn=self.image_process_fn, post_hardware_hook_fn=self.post_hardware_hook_fn) as acq:
			events = multi_d_acquisition_events(xyz_positions=self.xyz_positions,  num_time_points=self.num_images, time_interval_s=self.time_interval_s)

			for event in events:	
				# Get out of loop if not active anymore (user clicks stop acquisition)
				if not self.threadActive:
					break				
				
				# Acquire an image
				acq.acquire(event)

				# Skip imaging every N slices
				if self.skipEvery:
					for i in range(self.skipEvery):

						# Send a cutting signal
						self.board.digital[9].write(0)
						time.sleep(3)
						self.board.digital[9].write(1)

						# Poll every 1 second to see if cut complete
						while not self.board.digital[12].read():
							time.sleep(1)

						self.statusBarSignal.emit('End of section ' + str(self.current_time_index + 1 + (i*self.current_time_index)))
						self.progressSignal.emit(int(self.current_time_index + 1) + int(i*self.current_time_index))

						if not self.threadActive:
							break

		self.completeSignal.emit(1)

	# Stop the thread
	def terminate_thread(self):
		
		self.quit()
		self.wait()