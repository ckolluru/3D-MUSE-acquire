import os
import itk
from tqdm import tqdm
import numpy as np
import zarr
import shutil

# Pre-load ITKMontage components
itk.auto_progress(1)
itk.TileConfiguration.GetTypes()
itk.auto_progress(0)

# Set up the stitching class
class Stitcher():

    def __init__(self):

        # Zarr dataset specifications, storage variable, dataset variable, image shape in XY
        self.ZARR_STORE = None
        self.DS = None
        self.Y_SHAPE_ZARR = None
        self.X_SHAPE_ZARR = None

        # Pixel size in microns, XY and Z
        self.pixel_size = None
        self.z_thickness = None

    def convert_xy_positions_to_tile_configuration(self, xy_positions, pixel_size, tile_config_path, x_stage_max=25400, y_stage_max=20000):

        # Set the pixel size
        self.pixel_size = pixel_size

        # Convert the physical distance values in the positions to image space coordinates
        xy_positions = np.round(xy_positions / self.pixel_size)
        x_stage_max = np.round(x_stage_max / self.pixel_size)
        y_stage_max = np.round(y_stage_max / self.pixel_size)

        # Our stages are setup such that y is positive going up and x is positive going left
        # Instead we want our top left tile to be (0, 0) (needed for ITKMontage)
        # So we subtract xy_positions from max values
        for index in range(xy_positions.shape[0]):
            xy_positions[index, :] = [x_stage_max - xy_positions[index, 0], y_stage_max - xy_positions[index, 1]]

        # Tile positions in X, Y
        min_x = min(position[0] for position in xy_positions)
        min_y = min(position[1] for position in xy_positions)

        for index in range(xy_positions.shape[0]):
            xy_positions[index, :] = [xy_positions[index, 0] - min_x, xy_positions[index, 1] - min_y]

        # Sort the positions as desired by ITK montage 
        # See https://github.com/InsightSoftwareConsortium/ITKMontage/issues/190
        x_positions = xy_positions[:,0]
        y_positions = xy_positions[:,1]

        sorted_indices = np.lexsort((x_positions, y_positions))
        xy_positions_sorted = xy_positions.take(tuple(sorted_indices), axis=0)

        # Create tile config text string
        tile_config_str = f"# Tile coordinates are in index space, not physical space\ndim = 2\n"

        # If there is a tile config path with the same name, delete it
        # So this will keep track of the latest acquisition cycle's tile setup for simplicity
        if os.path.exists(tile_config_path):
            os.remove(tile_config_path)

        # Create output dir and save tile config, file names are dummy and not used
        with open(tile_config_path, 'w') as fp:
            fp.write(tile_config_str)

            for index in range(xy_positions_sorted.shape[0]):
                fp.write('img_' + str(index) + '.h5;;(' + str(xy_positions_sorted[index, 0]) + ', ' + str(xy_positions_sorted[index, 1]) + ')\n')

        # Return the sorted tile positions, used to arrange the tiles in a list when sending it to the stitching algorithm
        print('Sorted XY tile positions:\n ', xy_positions_sorted)
        print('Sorted indices: ', sorted_indices)

        return sorted_indices

    # Set up the Zarr store to save the stitched images
    def set_up_zarr_store_for_stitched_images(self, stitched_directory, num_time_points, num_tiles, tile_size_x, tile_size_y, num_tiles_x, num_tiles_y, z_thickness):
        
        # Add 5% extra than what is needed
        self.Y_SHAPE_ZARR = int(tile_size_y * num_tiles_y * 1.05)
        self.X_SHAPE_ZARR = int(tile_size_x * num_tiles_x * 1.05)

        # Create new zarr folder and data structure
        store = zarr.DirectoryStore(stitched_directory, dimension_separator='/')
        root = zarr.group(store=store, overwrite=True)
        muse = root.create_group('muse')

        # Try a large chunk size (16 slices). If it raises an exception that Zarr cannot compress it, go for a smaller chunk size
        # Smaller chunk size is needed if you do beyond 2x2 tiles
        # See https://github.com/zarr-developers/zarr-python/issues/487
        try:
            self.DS = muse.zeros('stitched', shape=(num_time_points, self.Y_SHAPE_ZARR, self.X_SHAPE_ZARR), chunks=(16, self.Y_SHAPE_ZARR, self.X_SHAPE_ZARR), dtype="i2" )
        except:
            self.DS = muse.zeros('stitched', shape=(num_time_points, self.Y_SHAPE_ZARR, self.X_SHAPE_ZARR), chunks=(4, self.Y_SHAPE_ZARR, self.X_SHAPE_ZARR), dtype="i2" )
 
        # This zattrs file is needed to view the Zarr dataset in a tool like BigDataViewer in Fiji
        shutil.copy('example.zattrs', stitched_directory + '\\.zattrs')
        
        # Read the example .zattrs file in the stitched_directory folder
        # Read the list of lines into data
        with open(stitched_directory + '\\.zattrs', 'r') as file:
            data = file.readlines()

        # Modify the x, y, z pixel spacing to the correct values
        data[25] = ' ' * 32 + str(z_thickness) + ',\n'
        data[26] = ' ' * 32 + str(self.pixel_size) + ',\n'
        data[27] = ' ' * 32 + str(self.pixel_size) + '\n'

        # Write everything back
        with open(stitched_directory + '\\.zattrs', 'w') as file:
            file.writelines(data)

    # Pad the arrays as needed
    def pad_array(self, a):
        y, x = a.shape
        y_pad = int(self.Y_SHAPE_ZARR-y)
        x_pad = int(self.X_SHAPE_ZARR-x)
        
        try:
            return np.pad(a,((y_pad//2, y_pad//2 + y_pad%2), 
                        (x_pad//2, x_pad//2 + x_pad%2)),
                    mode = 'constant') 
        
        except ValueError:
            
            # Pad in the dimension that is not an issue
            if x_pad < 0:
                x_pad = 0

            if y_pad < 0:
                y_pad = 0

            b = np.pad(a,((y_pad//2, y_pad//2 + y_pad%2), 
                        (x_pad//2, x_pad//2 + x_pad%2)),
                    mode = 'constant') 

            # Crop out the center portion
            if x_pad == 0:
                startx = x//2-(self.X_SHAPE_ZARR//2)
                return b[:,startx:startx+self.X_SHAPE_ZARR]      
            if y_pad == 0:
                starty = y//2-(self.Y_SHAPE_ZARR//2)
                return b[starty:starty+self.Y_SHAPE_ZARR,:]  

    # This is the function that performs the stitching
    # Images should be provided as a list of 2D numpy arrays
    def stitch_tiles(self, images, tile_configuration_path, pixel_size, time_index):

        # This code is taken from ITKMontage example jupyter notebooks
        dimension = 2
        stage_tiles = itk.TileConfiguration[dimension]()
        stage_tiles.Parse(str(tile_configuration_path))
        
        if len(images) != stage_tiles.LinearSize():
            raise ValueError("Images should have the same length as number of xy positions in the tile configuration file.")

        # For registration
        itk_images = []  
        for t in range(stage_tiles.LinearSize()):
            origin = stage_tiles.GetTile(t).GetPosition()
            image = itk.GetImageFromArray(np.ascontiguousarray(images[t]))
            image.SetSpacing((pixel_size, pixel_size))
            spacing = image.GetSpacing()

            # Tile configurations are in pixel (index) coordinates
            # So we convert them into physical ones
            for d in range(dimension):
                origin[d] *= spacing[d]

            image.SetOrigin(origin)
            itk_images.append(image)

        # Only float is wrapped as coordinate representation type in TileMontage
        montage = itk.TileMontage[type(itk_images[0]), itk.F].New()
        montage.SetMontageSize(stage_tiles.GetAxisSizes())
        for t in range(stage_tiles.LinearSize()):
            montage.SetInputTile(t, itk_images[t])

        montage.Update()

        resampleF = itk.TileMergeImageFilter[type(itk_images[0]), itk.D].New()
        resampleF.SetMontageSize(stage_tiles.GetAxisSizes())
        for t in range(stage_tiles.LinearSize()):
            resampleF.SetInputTile(t, itk_images[t])
            index = stage_tiles.LinearIndexToNDIndex(t)
            resampleF.SetTileTransform(index, montage.GetOutputTransform(index))
        resampleF.Update()

        # Pad the array as needed
        array = self.pad_array(np.array(resampleF.GetOutput()))
        
        # Write to the zarr dataset, no need to close it like a tradiitional file pointer
        self.DS[int(time_index), :, :] = np.round(array).astype(np.uint16)