# ruflora

## Project overview
This repository provides a lightweight toolkit for recreating a photo dataset of the vascular plants of Russia from the collaborative ["Flora of Russia" project on iNaturalist](https://www.inaturalist.org/projects/flora-of-russia). The project was organised by Russian botanists and amateur naturalists to document the country’s flora and is described in detail in the open-access Biodiversity Data Journal article, *Flora of Russia on iNaturalist: a dataset* (Kashirina et al., 2021). The article reports that more than 10,000 contributors uploaded over 750,000 georeferenced observations that collectively cover 6,853 plant species and form one of the largest open datasets on Russian biodiversity to date. You can read the full publication here: https://bdj.pensoft.net/article/59249/?utm_source.

## Repository contents
- `flora.csv` – a comma-separated list of image URLs and scientific names that serves as an example subset of the Flora of Russia observations. Each row includes two columns:
  1. `image_url`: a direct link to the medium-sized photo hosted on iNaturalist.
  2. `scientific_name`: the taxonomic label associated with the observation.
- `download.py` – a multithreaded downloader that converts the referenced images into consistently named JPEG files ready for downstream machine learning or archival workflows.

## Installation
1. Ensure you are using Python 3.10 or newer.
2. Create and activate a virtual environment if desired.
3. Install the required Python packages:
   ```bash
   pip install pillow requests tqdm
   ```

## Usage
1. Prepare a CSV file that follows the two-column format demonstrated in `flora.csv`.
2. Run the downloader, pointing it at your CSV and a destination folder:
   ```bash
   python download.py -i flora.csv -o data/images --workers 16
   ```
   Key command-line options:
   - `-i / --i`: path to the input CSV file.
   - `-o / --o`: directory where the normalised JPEG files will be written.
   - `--workers`: number of parallel download threads (defaults to 16).
3. The script prints a progress bar and a final summary indicating how many images were saved or skipped.

### How the downloader works
- **Robust HTTP handling**: a per-thread `requests` session with retry logic ensures resilience against transient network errors.
- **Format fallbacks**: each image is attempted with several common file extensions (`jpeg`, `jpg`, `png`, `webp`) to maximise successful downloads.
- **Thread-safe naming**: observations are slugified (lowercase ASCII, underscores) and assigned incremental indices per species, preventing race conditions in multi-threaded execution.
- **Atomic writes**: files are first saved to temporary `.part` paths and then atomically renamed to avoid partial or corrupted outputs.
- **JPEG normalisation**: all images are converted to JPEG (RGB) via Pillow so that downstream pipelines receive consistent file formats.

## Data provenance and licensing
All image URLs originate from observations shared on iNaturalist within the Flora of Russia project. According to the Biodiversity Data Journal article, approximately 85% of the material is distributed under open licences (CC0, CC-BY, or CC-BY-NC). When using the dataset, review the licence associated with each observation on iNaturalist and follow the citation guidelines recommended in the publication above. Cite both the iNaturalist project and the article by Kashirina et al. (2021) in any derivative work.

## Extending the dataset
- To add more observations, export additional records from iNaturalist in the same two-column format and append them to `flora.csv` (or point the script to your custom file).
- Consider segmenting large exports into multiple CSV files to simplify retries if a batch fails.
- If you need higher-resolution imagery, adjust the URLs to reference `large` or `original` image sizes, keeping in mind the increased bandwidth requirements.

## Support
Issues and pull requests are welcome for bug fixes or enhancements to the downloader. For broader questions about the Flora of Russia initiative, consult the project discussion on iNaturalist or the original Biodiversity Data Journal article.
