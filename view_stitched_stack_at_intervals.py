import zarr
import matplotlib.pyplot as plt
from skimage import exposure
import numpy as np
import cv2

plt.ion()

# Inputs
zarr_filename = r'C:\MUSE datasets\REVA\Polymerization Tests\P7\MUSE_stitched_acq_2.zarr'
skip = 100

gamma = 0.75
vmin = 0
vmax = 3000

# Visualization
# S1 - muse, S2 - muse, S3 - muse\stitched
zarr_file = zarr.open(zarr_filename)
muse_data = zarr_file['muse\stitched']

print('Dataset shape:')
print(muse_data.shape)

print('Imaging was set up for ' + str(muse_data.shape[0]) + ' slices.')

for k in range(0, muse_data.shape[0], skip):
    image = np.squeeze(muse_data[k, :, :])

    if np.sum(image) == 0:
        print('Found blank images at slice ' + str(k) + '. Stopping.')
        break

    image[image > vmax] = vmax
    image[image < vmin] = vmin

    image = cv2.normalize(image, None, alpha = 0, beta = 255, norm_type = cv2.NORM_MINMAX, dtype = cv2.CV_32F)

    image = exposure.adjust_gamma(image, gamma = gamma) 
    
    image = cv2.normalize(image, None, alpha = 0, beta = 255, norm_type = cv2.NORM_MINMAX, dtype = cv2.CV_32F)

    plt.imshow(image, cmap='gray')
    plt.show()
    plt.pause(1)
    plt.clf()

print('Only found about ' + str(k) + ' images in the zarr folder. Actual image count may be different based on the skip value that was set.')