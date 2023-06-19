from PyQt5 import QtCore
from pycromanager import Acquisition, multi_d_acquisition_events
import time
import numpy as np
from tqdm import tqdm

class acquisitionClass(QtCore.QThread):
	
	progressSignal = QtCore.pyqtSignal(int)
	progressMinimumSignal = QtCore.pyqtSignal(int)
	progressMaximumSignal = QtCore.pyqtSignal(int)
	completeSignal = QtCore.pyqtSignal(int) 
	statusBarSignal = QtCore.pyqtSignal(str)
	
	def __init__(self, STORAGE_DIRECTORY, xyz_positions, num_time_points, time_interval_s, board, autoFocus, studio, NUM_TILES, STITCHING_FLAG, SORTED_INDICES, stitcher, TILE_SIZE_Y, TILE_SIZE_X, PIXEL_SIZE, TILE_CONFIG_PATH, core):
		
		super(acquisitionClass, self).__init__(None)
		self.STORAGE_DIRECTORY = STORAGE_DIRECTORY
		self.xyz_positions = xyz_positions
		self.num_time_points = num_time_points
		self.time_interval_s= time_interval_s
		self.board = board
		self.autoFocus = autoFocus
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
		self.progressMaximumSignal.emit(self.num_time_points)
		
		self.current_time_index = None

		self.best_z_positions = np.zeros((self.NUM_TILES))

		self.threadActive = True

	# Switch on the light source and open the shutter before snapping a picture
	def post_hardware_hook_fn(self, event):
		
		time.sleep(1)

		# Poll once every second to see if the cut signal is complete.
		while not self.board.digital[12].read():
			time.sleep(1)

		# Wait for a few seconds to ensure that the block-face is cleared.
		time.sleep(3)

		# Switch on the light source
		self.board.digital[10].write(0)

		if self.current_time_index is not None: 
			if self.current_time_index % 10 == 0 and self.current_time_index != 0:
				if self.autoFocus:
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
			self.statusBarSignal.emit('End of section ' + str(time_index + 1))
			self.progressSignal.emit(int(time_index))
			self.current_time_index = time_index

			# ZYX array
			if self.STITCHING_FLAG:

				# Sort the tiles based on the sorting indices
				self.tiles = [self.tiles[i] for i in self.SORTED_INDICES]

				self.stitcher.stitch_tiles(self.tiles, self.TILE_CONFIG_PATH, self.PIXEL_SIZE, time_index)
				self.statusBarSignal.emit('Tile stitching complete for section ' + str(time_index))

			# Reset the list container
			self.tiles = []

		return image, metadata

	def stop(self):
		self.threadActive = False
		self.wait()

	def run(self):
		print('Acquiring serial block-face images')
		self.threadActive = True

		with Acquisition(directory=self.STORAGE_DIRECTORY, name='MUSE_acq', image_process_fn=self.image_process_fn, post_hardware_hook_fn=self.post_hardware_hook_fn) as acq:
			events = multi_d_acquisition_events(xyz_positions=self.xyz_positions,  num_time_points=self.num_time_points, time_interval_s=self.time_interval_s)

			for event in tqdm(events):		
				acq.acquire(event)

				# Break out of the for loop if user clicks stop acquisition button
				if not self.threadActive:
					break

		self.completeSignal.emit(1)

	# Stop the thread
	def terminate_thread(self):
		
		self.quit()
		self.wait()