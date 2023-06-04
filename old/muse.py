import numpy as np
import time
from pycromanager import Acquisition, Studio, multi_d_acquisition_events, Core
import os

from stitch import *

class muse():
    def __init__(self):
        self.core = None
        self.stitcher = None

        self.NUM_TILES = 1
        self.PIXEL_SIZE = 0
        self.TILE_CONFIG_PATH = None
        self.STORAGE_DIRECTORY = None
        self.STITCHED_DIRECTORY = None
        self.TILE_SIZE_X = None
        self.TILE_SIZE_Y = None
        self.SORTED_INDICES = None
        self.tiles = []

    # Get XY positions, set in MDA window in MM
    def get_xyz_positions(self):

        studio = Studio()

        # pull current MDA window positions
        acq_manager = studio.acquisitions()
        acq_settings = acq_manager.get_acquisition_settings()
        position_list_manager = studio.positions()
        position_list = position_list_manager.get_position_list()
        number_positions = position_list.get_number_of_positions()
        xy_positions = np.empty((number_positions,2))
        z_positions = np.empty((number_positions))

        # iterate through position list to extract XY positions    
        for idx in range(number_positions):
            pos = position_list.get_position(idx)
            for ipos in range(pos.size()):
                stage_pos = pos.get(ipos)
                if (stage_pos.get_stage_device_label() == 'XYStage'):
                    xy_positions[idx,:] = [stage_pos.x, stage_pos.y]
                if (stage_pos.get_stage_device_label() == 'Stage'):
                    z_positions[idx] = stage_pos.z

    # Switch on the light source and open the shutter before snapping a picture
    def post_hardware_hook_fn(self, event):
        
        # Check here whether the cut signal is high
        # Else stay here
        self.core.set_config("Arduino-Switch", "Switch on light source")

        mmc = Core()
        mmc.full_focus()

        return event

    # After capturing an image
    def image_process_fn(self, image, metadata):

        # accumulate individual tiles
        self.tiles.append(np.reshape(image, (self.TILE_SIZE_Y, self.TILE_SIZE_X)))

        if len(self.tiles) == self.NUM_TILES:
            
            # core.set_config("Arduino-Switch", "Start cutting")
            # time.sleep(1)
            # core.set_config("Arduino-Switch", "Switch off all")

            # get the time point index
            time_index = metadata['Axes']['time']
            print('End of time point ' + str(time_index))

            # sort the tiles
            self.tiles = [self.tiles[i] for i in self.SORTED_INDICES]

            # ZYX array
            if self.STITCHING_FLAG:
                self.stitcher.stitch_tiles(self.tiles, self.TILE_CONFIG_PATH, self.PIXEL_SIZE, time_index-1)

            # Reset the list container
            self.tiles = []

        return image, metadata

    def run_acquisition(self):
        
        self.PIXEL_SIZE = 0.9
        self.STORAGE_DIRECTORY = r'D:\\MUSE_data\\sample'
        self.STITCHED_DIRECTORY = self.STORAGE_DIRECTORY + r'\\stitched.zarr'

        self.TILE_SIZE_X = 4000
        self.TILE_SIZE_Y = 3000

        os.makedirs(self.STORAGE_DIRECTORY, exist_ok=True)
        os.makedirs(self.STITCHED_DIRECTORY, exist_ok=True)

        xy_positions, z_positions = self.get_xyz_positions()
        xyz_positions = np.hstack((xy_positions, np.expand_dims(z_positions, axis=1)))
        self.NUM_TILES = xy_positions.shape[0]
        parent_dir = Path(os.getcwd())
        self.TILE_CONFIG_PATH = parent_dir / 'TileConfigurationTest.txt'

        self.STITCHING_FLAG = (self.NUM_TILES != 1)

        num_tiles_x = len(np.unique(xy_positions[:,0]))
        num_tiles_y = len(np.unique(xy_positions[:,1]))

        assert self.NUM_TILES == num_tiles_x * num_tiles_y

        if self.STITCHING_FLAG:
            self.stitcher = Stitcher()
            self.SORTED_INDICES =self. stitcher.convert_xy_positions_to_tile_configuration(xy_positions, self.PIXEL_SIZE, self.TILE_CONFIG_PATH)

        num_time_points = 3
        time_per_slice = float(21 + 3*xy_positions.shape[0]) 
        time_interval_s = [0.0]
        time_interval_s = time_interval_s + [time_per_slice]* (num_time_points - 1)
        folder_created = True

        if self.STITCHING_FLAG:
            folder_created = self.stitcher.set_up_zarr_store_for_stitched_images(self.STITCHED_DIRECTORY, num_time_points, self.NUM_TILES, self.TILE_SIZE_X, self.TILE_SIZE_Y, num_tiles_x, num_tiles_y)
        
        if folder_created:
            self.core = Core()

            with Acquisition(directory=self.STORAGE_DIRECTORY, name='pycromanager_acq', image_process_fn=self.image_process_fn, post_hardware_hook_fn=self.post_hardware_hook_fn) as acq:
                events = multi_d_acquisition_events(xyz_positions=xyz_positions,  num_time_points=num_time_points, time_interval_s=time_interval_s)
                acq.acquire(events)

if __name__ == '__main__':
    muse = muse()
    muse.run_acquisition()