from PyQt5 import QtCore
import time
from tqdm import tqdm
import logging

# Create the class
class trimmingClass(QtCore.QThread):
	
	# Set up the signal data types
	progressSignal = QtCore.pyqtSignal(int)
	progressMinimumSignal = QtCore.pyqtSignal(int)
	progressMaximumSignal = QtCore.pyqtSignal(int)
	completeSignal = QtCore.pyqtSignal(int) 
	statusBarSignal = QtCore.pyqtSignal(str)
	
	def __init__(self, timepoints, board, storage_directory):
		
		# Get the arduino board, storage directory and time points
		super(trimmingClass, self).__init__(None)

		# Arduino board and number of cuts (timepoints)
		self.board = board
		self.timepoints = timepoints

		# Set up the progress bar minimum and maximum
		self.progressMinimumSignal.emit(0)
		self.progressMaximumSignal.emit(timepoints)

		# Thread active bool, checked in each iteration and exit if False
		self.threadActive = True				
		
	def stop(self):

		# If stop signal was sent, set the threadActive bool to false and wait for thread to finish
		self.threadActive = False
		self.wait()

	# Called automatically with thread.start()
	def run(self):
		print('Trimming block-face')

		for i in tqdm(range(self.timepoints)):

			# Send a cutting signal, mimic pressing and releasing the footswitch
			self.board.digital[9].write(0)
			time.sleep(3)
			self.board.digital[9].write(1)

			# Poll every second to see if cut complete signal is high
			while (not self.board.digital[12].read()):
				time.sleep(1)

			# Update status bar and progress bar
			self.statusBarSignal.emit('Trimming: End of section ' + str(i + 1) + ' out of ' + str(self.timepoints))
			self.progressSignal.emit(i + 1)
			
			# Break out of the for loop if user clicks stop acquisition button
			if not self.threadActive:				
				logging.info('Stopped trimming after %s cuts', (i+1))
				break

		if self.threadActive:
			logging.info('Completed trimming for %s cuts', self.timepoints)
			
		self.completeSignal.emit(2)

	# Stop the thread - called after the completeSignal is sent back to main and we are done with this thread
	def terminate_thread(self):
		
		self.quit()
		self.wait()