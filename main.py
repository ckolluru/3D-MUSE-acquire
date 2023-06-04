import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox
from PyQt5 import uic
import os
from pycromanager import Acquisition, Studio, multi_d_acquisition_events, Core
from stitch import *
import pyfirmata
import time

class Window(QMainWindow):
    def __init__(self):
        super(Window, self).__init__()
        uic.loadUi('mainwindow.ui', self)
        self.show() 

        self.board = None

    # Get XYZ positions from Micromanager
    def get_xyz_positions(self):

        studio = Studio()

        # Pull current MDA window positions
        acq_manager = studio.acquisitions()
        acq_settings = acq_manager.get_acquisition_settings()
        position_list_manager = studio.positions()
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
                    z_positions[idx] = stage_pos.z

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
                self.board.digital[11].write(0)
            else:
                self.board.digital[11].write(1)

    # Switch on the light source and open the shutter before snapping a picture
    def post_hardware_hook_fn(self, event):
        
        time.sleep(1)

        # Poll once every second to see if the cut signal is complete.
        while not self.board.digital[12].read():
            time.sleep(1)

        self.board.digital[10].write(0)
        self.core.set_config("Arduino-Switch", "Switch on light source")

        if self.autofocusCheckbox.isChecked():
            mmc = Core()
            mmc.full_focus()

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
            time.sleep(1)
            self.board.digital[9].write(1)

            # Get the time point index
            time_index = metadata['Axes']['time']
            self.progressBar.setValue(time_index)
            self.statusBar().showMessage('End of section ' + str(time_index))

            # Sort the tiles based on the sorting indices
            self.tiles = [self.tiles[i] for i in self.SORTED_INDICES]

            # ZYX array
            if self.STITCHING_FLAG:
                self.stitcher.stitch_tiles(self.tiles, self.TILE_CONFIG_PATH, self.PIXEL_SIZE, time_index-1)
                self.statusBar().showMessage('Tile stitching complete for section ' + str(time_index))

            # Reset the list container
            self.tiles = []

        return image, metadata

    # Initialize the arduino board
    def initialize_arduino(self):

        if self.board is None:

            # Define the arduino board
            self.board = pyfirmata.Arduino(str(self.arduinoPortEdit.text()))

            # Set input and output pins
            self.board.digital[8].mode = pyfirmata.OUTPUT
            self.board.digital[9].mode = pyfirmata.OUTPUT
            self.board.digital[10].mode = pyfirmata.OUTPUT        
            self.board.digital[12].mode = pyfirmata.INPUT

            # Start the iterator
            it = pyfirmata.util.Iterator(self.board)
            it.start()

            self.statusBar().showMessage('Arduino initialization complete', 5000)
        
        else:
            self.statusBar().showMessage('Arduino already initialized, relaunch 3D-MUSE-acquire if need to change values')

    # Run the acquisition    
    def run_acquisition(self):

        # Disable the UI so that user cannot edit line items during acq
        self.scrollAreaWidgetContents.setEnabled(False)

        # Switch off the emergency stop, cutting and light source, inverted logic
        self.board.digital[8].write(1)
        self.board.digital[9].write(1)
        self.board.digital[10].write(1)

        # Set values from the UI
        self.PIXEL_SIZE = float(self.pixelSizeEdit.text())
        self.STORAGE_DIRECTORY = str(self.storageDirEdit.text())
        self.STITCHED_DIRECTORY = str(self.stitchedDirEdit.text()) + r'\\stitched.zarr'
        self.TILE_SIZE_X = int(self.imageSizeXEdit.text())
        self.TILE_SIZE_Y = int(self.imageSizeYEdit.text())

        # Create directories if necessary
        os.makedirs(self.STORAGE_DIRECTORY, exist_ok=True)
        os.makedirs(self.STITCHED_DIRECTORY, exist_ok=True)

        # Get XYZ positions for the tiles from MDA window, calculate number of tiles
        xy_positions, z_positions = self.get_xyz_positions()
        xyz_positions = np.hstack((xy_positions, np.expand_dims(z_positions, axis=1)))
        self.NUM_TILES = xy_positions.shape[0]
        self.TILE_CONFIG_PATH = self.STORAGE_DIRECTORY / 'TileConfiguration.txt'
        self.statusBar().showMessage('Received XYZ positions from Micromanager')

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

        if self.NUM_TILES != (num_tiles_x * num_tiles_y):
            raise ValueError('Expected tile positions to be on a uniform grid')
        
        self.statusBar().showMessage('Found ' + str(num_tiles_x) + ' in x and ' + str(num_tiles_y) + ' in y')

        # Identify the correct sorting of the tiles, used to arrange tiles before sending to the stitching module
        if self.STITCHING_FLAG:
            self.stitcher = Stitcher()
            self.SORTED_INDICES =self.stitcher.convert_xy_positions_to_tile_configuration(xy_positions, self.PIXEL_SIZE, self.TILE_CONFIG_PATH)

        # Number of cuts, trimming flag will not image
        num_time_points = int(self.numberCutsEdit.text())
        self.progressBar.SetMinimum(0)
        self.progressBar.SetMaximum(num_time_points)
        self.TRIMMING_FLAG = self.trimBlockCheckbox.isChecked()

        # If only trimming and not imaging
        if self.TRIMMING_FLAG:
            for i in range(num_time_points):
                self.progressBar.setValue(i)
                self.board.digital[9].write(0)
                time.sleep(1)

                # Poll every second to see if cut complete signal is high
                while (not self.board.digital[12].read()):
                    time.sleep(1)

                self.statusBar().showMessage('End of section ' + str(i))

        # Imaging, pycro-manager acquisition
        else:
            time_interval_s = 1
            folder_created = True

            if self.STITCHING_FLAG:
                folder_created = self.stitcher.set_up_zarr_store_for_stitched_images(self.STITCHED_DIRECTORY, num_time_points, self.NUM_TILES, self.TILE_SIZE_X, self.TILE_SIZE_Y, num_tiles_x, num_tiles_y)
            
            if folder_created:
                self.core = Core()

                with Acquisition(directory=self.STORAGE_DIRECTORY, name='MUSE_acq', image_process_fn=self.image_process_fn, post_hardware_hook_fn=self.post_hardware_hook_fn) as acq:
                    events = multi_d_acquisition_events(xyz_positions=xyz_positions,  num_time_points=num_time_points, time_interval_s=time_interval_s)
                    acq.acquire(events)

        self.progressBar.setValue(0)
        self.statusBar().showMessage('Acquisition complete.')
        self.scrollAreaWidgetContents.setEnabled(True)

        # TODO: Image registration with elastix

if __name__ == "__main__":
    app = QApplication([])
    window = Window()
    window.show()
    sys.exit(app.exec())