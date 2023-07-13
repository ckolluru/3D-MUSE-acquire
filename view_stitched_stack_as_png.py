import zarr
import matplotlib.pyplot as plt
from skimage import exposure
import numpy as np
import cv2

plt.ion()

# Inputs
zarr_filename = r'C:\MUSE datasets\REVA\Polymerization Tests\P7\MUSE_stitched_acq_1.zarr'
skip = 5

gamma = 0.75
vmin = 0
vmax = 2500

# Visualization
zarr_file = zarr.open(zarr_filename)
muse_data = zarr_file['muse\stitched']

print('Dataset shape:')
print(muse_data.shape)

for k in range(0, muse_data.shape[0], skip):
    image = np.squeeze(muse_data[k, :, :])

    image[image > vmax] = vmax
    image[image < vmin] = vmin

    image = cv2.normalize(image, None, alpha = 0, beta = 255, norm_type = cv2.NORM_MINMAX, dtype = cv2.CV_32F)

    image = exposure.adjust_gamma(image, gamma = gamma) 
    
    image = cv2.normalize(image, None, alpha = 0, beta = 255, norm_type = cv2.NORM_MINMAX, dtype = cv2.CV_32F)

    plt.imshow(image, cmap='gray')
    plt.show()
    plt.pause(1)
    plt.clf()