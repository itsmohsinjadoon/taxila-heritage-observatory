# Licences and attribution

The manuscript text and original workflow diagram are supplied for author review and scholarly submission. Copyright and licensing remain subject to the authors' final decision and any later publisher agreement.

The analytical figures and tables were generated from the study's verified outputs. Underlying third-party datasets retain their original terms and must be cited and accessed through the providers identified in Table 1, `references.bib` and `source_traceability/source_manifest.csv`. Principal providers include UNESCO World Heritage Centre, United States Geological Survey, European Space Agency WorldCover, Open-Meteo, NASA POWER and the Shuttle Radar Topography Mission data provider.

Bibliographic metadata are factual records. The included references do not transfer publisher rights in the cited works.

The package does not redistribute original third-party raster archives. Selected derived records are included for traceability and manuscript compilation only.

## Figure 1 source package

The canonical Figure 1 under `figures/main/` preserves the author-approved cartography as a checksum-locked archival render. `figures/source/figure_01/restore_author_approved_figure1.py` embeds that render without restyling it in the 260 x 175 mm manuscript PDF. The source bundle also retains a reproducible, non-canonical open-data QGIS variant for audit and comparison.

- Esri World Imagery: contextual basemap only; imagery sources credited as Esri, Maxar, Earthstar Geographics and the GIS User Community. The basemap is not redistributed as a standalone dataset and is not an analytical input.
- OpenStreetMap: road and museum data © OpenStreetMap contributors, Open Database Licence; see <https://www.openstreetmap.org/copyright>.
- Sentinel-2, Natural Earth and geoBoundaries files in the same directory support the clearly labelled open-data comparison variant; they are not represented as the basemap of the canonical manuscript figure.

The analytical circles in the figure are sampling neighbourhoods and are not UNESCO or legal boundaries.
