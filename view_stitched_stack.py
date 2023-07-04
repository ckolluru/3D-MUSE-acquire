import zarr
import matplotlib.pyplot as plt
from skimage import exposure

plt.ion()

# Inputs
zarr_filename = r'C:\MUSE datasets\REVA\Polymerization Tests\S8\MUSE_stitched_acq_2.zarr'
slices = 1000
skip = 100

gamma = 0.6
vmin = 0
vmax = 2500

# Visualization
zarr_file = zarr.open(zarr_filename)
muse_data = zarr_file['muse/stitched']

for k in range(0, slices, skip):
    image = muse_data[k, :, :]
    image[image > vmax] = vmax

    image = exposure.adjust_gamma(image, gamma)

    plt.imshow(image, cmap='gray', vmin = vmin, vmax= vmax)
    plt.show()
    plt.pause(1)
    plt.clf()