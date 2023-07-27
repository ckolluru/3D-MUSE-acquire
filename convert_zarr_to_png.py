import zarr
from skimage import exposure
import numpy as np
import cv2
from tqdm import tqdm
from PIL import Image
import os

# Inputs, if saveEvery is 1, all images are saved
acq_cycle = 4
zarr_filename = r'F:\P11\MUSE_stitched_acq_' + str(acq_cycle) + '.zarr'
saveEvery = 1

# Output folder
output_folder = r'F:\P11\PNG images acq ' + str(acq_cycle) 

# Gamma contrast adjustments, the structures we are intersted in (fibers) are dark
# Gamma helps increase their brightness
gamma = 0.75

# ---------
# Algorithm
# ---------
# Make the output directory if needed
os.makedirs(output_folder, exist_ok=True)

# Pull array from the zarr dataset
zarr_file = zarr.open(zarr_filename)
muse_data = zarr_file['muse\stitched']

print('Dataset shape:')
print(muse_data.shape)

# Calculate minimum and maximum limits, min and max is 1%  percentile
sample_image = np.squeeze(muse_data[0, :, :])

vmin = np.percentile(sample_image, 0.01)
vmax = np.percentile(sample_image, 99.99)

print('Considering ' + str(vmin) + ' ' + str(vmax) + ' as the minimum and maximum intensity limits, the final pngs will be rescaled to 0-255 in this min-max range.')

# Loop through the slices
for k in tqdm(range(0, muse_data.shape[0], saveEvery)):
    image = np.squeeze(muse_data[k, :, :])

    if np.sum(image) == 0:
        print('\n Found empty image, stopping at ' + str(k) + 'images')
        break

    # Equivalent to setting the min max values on the histogram
    image[image > vmax] = vmax
    image[image < vmin] = vmin

    image = cv2.normalize(image, None, alpha = 0, beta = 255, norm_type = cv2.NORM_MINMAX, dtype = cv2.CV_32F)
    
    image[image > 255] = 255
    image[image < 0] = 0

    # Setting the gamma
    image = exposure.adjust_gamma(image, gamma = gamma) 

    # Normalizing this back to 0-255
    image = np.floor(cv2.normalize(image, None, alpha = 0, beta = 255, norm_type = cv2.NORM_MINMAX, dtype = cv2.CV_32F)).astype('uint8')

    # Save the image as png
    pillow_image = Image.fromarray(image)
    pillow_image.save(output_folder + r'\\Image_' + str(k).zfill(5) + '.png')