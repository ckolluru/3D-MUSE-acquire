# This will take a stack of PNG images and segmentation labels
# And tractography data and bundle into the correct folders for upload to globus
import os
import zarr
import shutil
import glob
import numpy as np
from PIL import Image
from tqdm import tqdm

def copy_zattrs_file(pixel_size_xy, pixel_size_z, destination_folder, array_name):
    
    # This zattrs file is needed to view the Zarr dataset in a tool like BigDataViewer in Fiji
    shutil.copy('example.zattrs', destination_folder + '\\.zattrs')
    
    # Read the example .zattrs file in the stitched_directory folder
    # Read the list of lines into data
    with open(destination_folder + '\\.zattrs', 'r') as file:
        data = file.readlines()

    # Modify the x, y, z pixel spacing to the correct values
    data[25] = ' ' * 32 + str(pixel_size_z) + ',\n'
    data[26] = ' ' * 32 + str(pixel_size_xy) + ',\n'
    data[27] = ' ' * 32 + str(pixel_size_xy) + '\n'

    # Put in the correct array name, used in path by Zarr
    data[32] = ' ' * 20 + "path: \"muse/" + array_name + "\"" + '\n'

    # Write everything back
    with open(destination_folder + '\\.zattrs', 'w') as file:
        file.writelines(data)

def create_zarr_from_png_images(input_folder, output_folder, array_name, data_type):

    # Check how many images are in there
    filelist = glob.glob(input_folder + r'\\*.png')
    num_images = len(filelist)

    # Get image dimensions using the first image
    sample_image = Image.open(filelist[0])
    sample_image_array = np.array(sample_image)
    height = sample_image_array.shape[0]
    width = sample_image_array.shape[1]

    if data_type == 'int16':
        zarr_datatype = "i2"
        numpy_type = np.int16
    elif data_type == 'int8':
        zarr_datatype = "i1"
        numpy_type = np.uint8

    # Create new zarr folder and data structure
    store = zarr.DirectoryStore(output_folder, dimension_separator='/')
    root = zarr.group(store=store, overwrite=True)
    muse = root.create_group('muse')
    DS = muse.zeros(array_name, shape=(num_images, height, width), chunks=(16, height, width), dtype=zarr_datatype)

    # Write each file to the zarr file
    print('Converting images to zarr - ' + array_name)
    for k in tqdm(range(num_images)):
        image = Image.open(filelist[k])
        image_array = np.array(image)

        # Write to the zarr dataset, no need to close it like a tradiitional file pointer
        DS[int(k), :, :] = image_array.astype(numpy_type)

if __name__ == '__main__':

    # Folder paths to the data (in png files for image and segmentations, pkl for tractography)
    images_folder = r'D:\chaitanya\MUSE datasets SPIE\P11\annotations\images'
    segmentations_folder = r'D:\chaitanya\MUSE datasets SPIE\P11\annotations\labels'
    tractography_folder = r'D:\chaitanya\MUSE datasets SPIE\P11\tractography'

    output_folder = r'D:\chaitanya\MUSE datasets SPIE\P11\globus'

    subject_name = 'SRpilot'
    sample_name = 'CR1'
    grid_location = '01c05e'

    image_datatype = 'int16'
    segmentations_datatype = 'int8'

    # Image scale (needed for zarr)
    pixel_size_xy = 0.9
    pixel_size_z = 3 * 20

    # Make the required parent dirs
    os.makedirs(output_folder, exist_ok = True)

    primary_folder = output_folder + r'\\primary\\sub-' + subject_name + r'\\sam-' + subject_name + '-' + sample_name + '\\'
    derivative_folder = output_folder + r'\\derivative\\sub-' + subject_name + r'\\sam-' + subject_name + '-' + sample_name + '\\' + grid_location

    # Get the correct folder naming convention
    primary_output_folder = primary_folder + grid_location + '.zarr'
    segmentations_output_folder = derivative_folder + '\\segmentations.zarr'
    tractography_output_folder = derivative_folder + '\\tractography'

    # Make the required sub directories for this sample
    os.makedirs(primary_output_folder, exist_ok = True)
    os.makedirs(segmentations_output_folder, exist_ok = True)
    os.makedirs(tractography_output_folder, exist_ok = True)

    # Create zarr datasets for images and segmentations
    create_zarr_from_png_images(images_folder, primary_output_folder, array_name = 'stitched', data_type = image_datatype)
    create_zarr_from_png_images(segmentations_folder, segmentations_output_folder, array_name = 'segmentations', data_type = segmentations_datatype)

    # Copy zattrs file to the primary and segmentations folder
    copy_zattrs_file(pixel_size_xy, pixel_size_z, primary_output_folder, array_name = 'stitched')
    copy_zattrs_file(pixel_size_xy, pixel_size_z, segmentations_output_folder, array_name = 'segmentations')

    # Copy tractography results to tractography folder
    print('Copying tractography files')
    filelist = glob.glob(tractography_folder + r'\*.pkl')

    for k in range(len(filelist)):
        shutil.copy2(filelist[k], tractography_output_folder + '\\' + os.path.basename(filelist[k]))
