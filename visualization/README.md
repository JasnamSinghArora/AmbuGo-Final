# Visualizations and simulator transfer

| Folder | Contents |
| --- | --- |
| `map_replay/` | Source for the 20-second map and graph animations, frozen replay data, and the optional SUMO reproduction workflow. |
| `simultaneous/` | Source for combining recorded graphs with either the supplied planning film or the synchronized map replay. |
| `vissim_transfer/` | OpenDRIVE geometry, source network and scenario data, a boundary-reference repair script, and native Vissim integration instructions. |

The repository includes source and numeric inputs. Videos, map-background images and preview images are supplied in the complete release archives. Use an extracted archive as a standalone package to reproduce the films; the Git-only map renderer does not have its required background images. Graph rendering and the SUMO workflow do not require those images.

## Download complete packages

Run these commands from the repository root. They use the GitHub CLI and Python 3.12, and extract the packages into a sibling directory outside the Git checkout.

```sh
mkdir -p ../AmbuGo-downloads
gh release download v1.0.0 --repo JasnamSinghArora/AmbuGo-Final \
  --pattern 'AmbuGo_20s_Reproducible.zip' \
  --pattern 'AmbuGo_Simultaneous.zip' \
  --pattern 'AmbuGo_Vissim_Transfer.zip' \
  --dir ../AmbuGo-downloads
cd ../AmbuGo-downloads
python3.12 -m zipfile -e AmbuGo_20s_Reproducible.zip .
python3.12 -m zipfile -e AmbuGo_Simultaneous.zip .
python3.12 -m zipfile -e AmbuGo_Vissim_Transfer.zip .
```

Alternatively, download the ZIPs from the [v1.0.0 release](https://github.com/JasnamSinghArora/AmbuGo-Final/releases/tag/v1.0.0) and extract them, preserving their folder structures. The original MP4s can be watched without installing Python.

## Reproduce the films

Continue from `AmbuGo-downloads/`. These macOS/Linux commands create a separate environment. Windows equivalents are in the extracted package's `README.txt`.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r AmbuGo_20s_Reproducible/requirements.txt
.venv/bin/python -m pip install -r AmbuGo_Simultaneous/requirements.txt

# Validate the complete map package and its supplied videos.
.venv/bin/python AmbuGo_20s_Reproducible/reproduce.py verify \
  --videos AmbuGo_20s_Reproducible/reference

# Rebuild both 20-second films into the package's generated/ folder.
.venv/bin/python AmbuGo_20s_Reproducible/reproduce.py all

# Rebuild the synchronized side-by-side film in its package folder.
.venv/bin/python AmbuGo_Simultaneous/reproduce.py --version synchronized

# Optionally rebuild the edit containing the supplied planning film.
.venv/bin/python AmbuGo_Simultaneous/reproduce.py --version teammate
```

The simultaneous renderer overwrites its existing composite outputs; its input films are preserved. The renderers use NumPy, Pillow, Matplotlib and imageio-ffmpeg. Initial installation needs internet access; rendering uses local assets. Font and encoder differences can change output pixels or bytes across machines.

To rerun the recorded traffic episodes, install `AmbuGo_20s_Reproducible/simulation/requirements.txt` and follow that folder's `README.txt`. It uses the pinned SUMO/libsumo 1.28.0 environment and checks the rerun against the frozen trajectories. This is separate from replaying the supplied data.

## Interpretation and third-party content

The 20-second synchronized map and graphs represent one recorded synthetic-traffic episode. The longer planning film and its accompanying graphs represent different examples with independent clocks and different priority-budget settings. Those graphs do not measure the maneuvers shown in the planning film. The compositor source is included; the supplied planning film's original animation project is not included.

The Vissim package is preparation only. It contains no completed native Vissim project or tested Vissim controller, and no Vissim execution or cross-simulator equivalence is claimed. Use its `README.txt` and `PTV_REQUIREMENTS_AND_INTEGRATION.txt` for the remaining native integration work.

Retain the Google and provider attribution in map images and films. Google imagery is not covered by a project-code license; see the packages' `THIRD_PARTY_NOTICES.txt` and [Google's geographic-content guidance](https://about.google/brand-resource-center/products-and-services/geo-guidelines/). The modeled road data derive from [OpenStreetMap contributors under ODbL](https://www.openstreetmap.org/copyright); the geometry notes also identify the imagery consulted for the local correction. Third-party dependencies are installed separately under their own licenses.
