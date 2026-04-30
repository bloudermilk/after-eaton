# Design Plan

The web interface for After Eaton is an interactive single-page application designed with the following goals in mind:
* Intuitive and usable by non-technical and technical people alike
* Accessible to people with disabilities or impairments
* Simple design and aesthetically refined
* Clear/concise copy and structure for quick interpretability
* Responsively designed to work equally well on desktop and mobile devices

## Aesthetics

* Built for and by Altadenans, the vibe is refined and relaxed
* The color pallette reflects the natural colors of our place (Poppy, Lupin, alluvial fan, live oak, cedrus deodara, etc.)
* Mid-century modern aesthetics overall, with splashes of muted color tones over lightly textured background

## Homepage

The homepage acts like a dashboard, reporting statistics of rebuilding in Altadena

### Statistics

* Each statistic is large and easy to read
* Each statistic is clearly labeled and has an "information" affordance aiding in interpretation by explaining the statistic and methodology
* Statistics outline
  * Relative Size
    * Visualizes the distribution of relative before/after size in buckets: +10% or smaller, 10-20% larger, more than 20% larger
  * Like-for-like
    * Pie chart of LFL claims in 3 categories: like-for-like, not like-for-like, not specified
    * For the purposes of visualization, not like-for-like and not specified are semantically similar, though not the same
  * Accessory Dwellings
    * Bar chart with distribution of ADU permits in buckets: +1 ADU, +2 ADUs, +3 or more ADUs
  * SB-9
    * Simple count of properties with permits filed per SB9

### Footer

* Explains free and open source nature of project
* Date of dataset generation
* Link to methodology page
* Link to Quality Control page
* Link to download the parcels CSV (see below)

## Pipeline updates

The pipline should be updated to accommodate affordances on the frontend

* Updates to summary.json necessary to populate all the aggregate statistics found on the homepage (e.g. LFL buckets, others)
* Update the architecture such that the website is deployed to GitHub pages using the latest assets in Releases (use actions/upload-pages-artifact)
* The addition of a parcels.csv artifact in the Release bundle, for easy downloading by end-users on the website