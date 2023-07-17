from PyQt5 import QtCore
import time
from tqdm import tqdm
import logging

class trimmingClass(QtCore.QThread):
	
	progressSignal = QtCore.pyqtSignal(int)
	progressMinimumSignal = QtCore.pyqtSignal(int)
	progressMaximumSignal = QtCore.pyqtSignal(int)
	completeSignal = QtCore.pyqtSignal(int) 
	statusBarSignal = QtCore.pyqtSignal(str)
	
	def __init__(self, timepoints, board, storage_directory):
		
		super(trimmingClass, self).__init__(None)
		self.board = board
		self.timepoints = timepoints

		self.progressMinimumSignal.emit(0)
		self.progressMaximumSignal.emit(timepoints)

		self.threadActive = True				
		
		# Set up logging
		logfile = storage_directory + '\\muse_application.log'
		logging.basicConfig(filename = logfile, filemode = 'a', level = logging.DEBUG, format = '%(asctime)s - %(levelname)s: %(message)s', datefmt = '%m/%d/%Y %I:%M:%S %p')


	def stop(self):
		self.threadActive = False
		self.wait()

	def run(self):
		print('Trimming block-face')

		for i in tqdm(range(self.timepoints)):

			# Cutting signal
			last_cutting_time = time.time()
			self.board.digital[9].write(0)
			time.sleep(3)
			self.board.digital[9].write(1)

			# Poll every second to see if cut complete signal is high
			while (not self.board.digital[12].read()):
				time.sleep(1)

				if time.time() - last_cutting_time > 25:
					break

			self.statusBarSignal.emit('Trimming: End of section ' + str(i + 1) + ' out of ' + str(self.timepoints))
			self.progressSignal.emit(i + 1)
			
			# Break out of the for loop if user clicks stop acquisition button
			if not self.threadActive:
				
				logging.info('Stopped trimming after %s cuts', (i+1))
				break

		if self.threadActive:
			logging.info('Completed trimming after %s cuts', self.timepoints)
			
		self.completeSignal.emit(2)

	# Stop the thread
	def terminate_thread(self):
		
		self.quit()
		self.wait()