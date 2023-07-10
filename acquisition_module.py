from PyQt5 import QtCore
from pycromanager import Acquisition, multi_d_acquisition_events
import time
import numpy as np
from tqdm import tqdm

import humanize
import datetime as dt
import logging

from collections import deque

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
		self.num_cuts = num_cuts
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
		
		self.image_index = 0
		self.image_flag = [False] * self.num_cuts

		self.best_z_positions = np.zeros((self.NUM_TILES))

		self.threadActive = True

		# Set up logging
		logfile = self.STORAGE_DIRECTORY + '\\muse_application.log'
		logging.basicConfig(filename = logfile, filemode = 'a', level = logging.DEBUG, format = '%(asctime)s - %(levelname)s: %(message)s', datefmt = '%m/%d/%Y %I:%M:%S %p')

	# Switch on the light source before snapping a picture
	def post_hardware_hook_fn(self, event):
		
		time.sleep(1)

		# Poll once every second to see if the cut signal is complete.
		while not self.board.digital[12].read():
			time.sleep(1)

		# Switch on the light source
		self.board.digital[10].write(0)

		if self.autoFocusEvery:
			if ((self.image_index) % self.autoFocusEvery == 0):

				# Move the z-stage to the position in the stage position list
				self.core.set_position("Stage", event['z'])
				self.core.wait_for_device("Stage")

				afm = self.studio.get_autofocus_manager()
				afm_method = afm.get_autofocus_method()
				afm_method.full_focus()
				self.statusBarSignal.emit('Autofocus complete')

				# Update best z positions
				self.best_z_positions[int(event['axes']['position'])] = self.core.get_position()

		logging.info('Returning event back, image_index: %s', self.image_index)

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

			# ZYX array
			if self.STITCHING_FLAG:

				# Sort the tiles based on the sorting indices
				self.tiles = [self.tiles[i] for i in self.SORTED_INDICES]

				self.stitcher.stitch_tiles(self.tiles, self.TILE_CONFIG_PATH, self.PIXEL_SIZE, self.image_index)
				self.statusBarSignal.emit('Tile stitching complete for image number ' + str(self.image_index + 1))

			# Reset the list container
			self.tiles = []

			logging.info('Returning from image_process function: %s', self.image_index)

		return image, metadata

	def stop(self):
		self.threadActive = False
		self.wait()

	def run(self):
		print('Acquiring serial block-face images')
		self.image_flag = [False] * self.num_cuts

		# Find which indices we need to image
		for i in range(len(self.image_flag)):
			if i % (self.skipEvery + 1) == 0:
				self.image_flag[i] = True

		logging.info('Image flag list: %s', self.image_flag)

		# Ensure the number of images to be captured is consistent
		assert self.num_images == np.sum(self.image_flag)

		with Acquisition(directory=self.STORAGE_DIRECTORY, name='MUSE_acq', image_process_fn=self.image_process_fn, post_hardware_hook_fn=self.post_hardware_hook_fn) as acq:
			events = multi_d_acquisition_events(xyz_positions=self.xyz_positions,  num_time_points=self.num_images, time_interval_s=self.time_interval_s)

			current_index = 0 

			for event in events:
				if self.image_flag[current_index]:

					time.sleep(1)

					acq.acquire(event)

					current_index = current_index + 1	
					self.image_index = self.image_index + 1

					# Update progress bar and status bar
					self.statusBarSignal.emit('End of section ' + str(current_index+1))
					self.progressSignal.emit(int(current_index+1))
					logging.info('End of section ' + str(current_index+1))

					# Get out of loop if not active anymore (user clicks stop acquisition)
					if not self.threadActive:
						logging.info('Stopped acqusition cycle after %s cuts', current_index)
						break		

				else:
					# Any cutting flags, complete them here before the next image flag
					while current_index < self.num_cuts and not self.image_flag[current_index]:

						# Poll every 1 second to see if cut complete
						while not self.board.digital[12].read():
							time.sleep(1)

						# Send a cutting signal
						self.board.digital[9].write(0)
						time.sleep(3)
						self.board.digital[9].write(1)

						# Cutting cycle complete
						while not self.board.digital[12].read():
							time.sleep(1)

						current_index = current_index + 1
						# Update progress bar and status bar
						self.statusBarSignal.emit('End of section ' + str(current_index+1))
						self.progressSignal.emit(int(current_index+1))
						logging.info('End of section ' + str(current_index+1))

						# Get out of loop if not active anymore (user clicks stop acquisition)
						if not self.threadActive:
							logging.info('Stopped acqusition cycle after %s cuts', current_index)
							break		


				# Get out of loop if not active anymore (user clicks stop acquisition)
				if not self.threadActive:
					logging.info('Stopped acqusition cycle after %s cuts', current_index)
					break



			# event_queue = deque(events)				

			# for i in range(len(self.image_flag)):
			# 	if self.image_flag[i]:					
					
			# 		time.sleep(1)

			# 		# Acquire an image
			# 		acq.acquire(event_queue.popleft())
			# 		self.image_index = self.image_index + 1

			# 	else:
			# 		# Poll every 1 second to see if cut complete
			# 		while not self.board.digital[12].read():
			# 			time.sleep(1)

			# 		# Send a cutting signal
			# 		self.board.digital[9].write(0)
			# 		time.sleep(3)
			# 		self.board.digital[9].write(1)

			# 		# Cutting cycle complete
			# 		while not self.board.digital[12].read():
			# 			time.sleep(1)



				# # Update progress bar and status bar
				# self.statusBarSignal.emit('End of section ' + str(i+1))
				# self.progressSignal.emit(int(i+1))
				# logging.info('End of section ' + str(i+1))

		# If the thread is still active, that means finished all the cuts
		if self.threadActive:
			logging.info('Completed acquisition cycle, finished %s cuts', self.num_cuts)							

		self.completeSignal.emit(1)

	# Stop the thread
	def terminate_thread(self):
		
		self.quit()
		self.wait()