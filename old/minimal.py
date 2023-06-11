import numpy as np
import time
from pycromanager import Acquisition, Studio, multi_d_acquisition_events, Core
import os

class acquisition():
    def __init__(self):
        self.core = None
        self.studio = None

        self.NUM_TILES = 1
        self.PIXEL_SIZE = 0
        self.STORAGE_DIRECTORY = None
        self.TILE_SIZE_X = None
        self.TILE_SIZE_Y = None

    # Get XY positions, set in MDA window in MM
    def get_xyz_positions(self):

        self.studio = Studio()

        # pull current MDA window positions
        acq_manager = self.studio.acquisitions()
        acq_settings = acq_manager.get_acquisition_settings()
        position_list_manager = self.studio.positions()
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

        return xy_positions, z_positions

    # Just before capturing an image
    def post_hardware_hook_fn(self, event):

        afm = self.studio.get_autofocus_manager()
        afm_method = afm.get_autofocus_method()
        print(afm_method)
        afm_method.full_focus()

        # mmc = Core()
        # mmc.full_focus()
        print('Focusing complete')

        return event

    # After capturing an image
    def image_process_fn(self, image, metadata):

        return image, metadata

    def run_acquisition(self):
        
        self.PIXEL_SIZE = 1
        self.STORAGE_DIRECTORY = r'D:\\data\\sample2'

        self.TILE_SIZE_X = 512
        self.TILE_SIZE_Y = 512

        os.makedirs(self.STORAGE_DIRECTORY, exist_ok=True)

        xy_positions, z_positions = self.get_xyz_positions()
        xyz_positions = np.hstack((xy_positions, np.expand_dims(z_positions, axis=1)))
        self.NUM_TILES = xy_positions.shape[0]
        assert self.NUM_TILES == 1

        num_time_points = 4
        time_interval_s = [0]
        time_per_slice = (0 + 3 * self.NUM_TILES)
        time_interval_s = time_interval_s + [time_per_slice] * (num_time_points-1)

        with Acquisition(directory=self.STORAGE_DIRECTORY, name='pycromanager_acq', image_process_fn=self.image_process_fn, post_hardware_hook_fn=self.post_hardware_hook_fn) as acq:
            events = multi_d_acquisition_events(xyz_positions=xyz_positions, num_time_points=num_time_points, time_interval_s=time_interval_s)
            for event in events:
                acq.acquire(event)

if __name__ == '__main__':
    acquisition = acquisition()
    acquisition.run_acquisition()