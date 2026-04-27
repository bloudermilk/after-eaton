# After Eaton

**After Eaton** is a living analysis of the impacts of the Eaton Fire of 2025 on the unincorporated town of Altadena. We use open data from LA County and other sources to compare rebuild efforts to pre-fire state of the community. Our site is free and publicly accessible and intended to be useful for community members, county agencies, and other stakeholders.

## Data Sources

* [EPIC-LA Fire Recovery Cases](https://lacounty.maps.arcgis.com/home/item.html?id=e87c8fcf5a2c4f7e87198b0c208d3d9f) ([API service](https://services.arcgis.com/RmCCgQtiZLDCtblq/arcgis/rest/services/EPICLA_Eaton_Palisades/FeatureServer)) - building plans, permits, rebuild progress
* [2025 Parcels with DINS data](https://data.lacounty.gov/datasets/lacounty::2025-parcels-with-dins-data/about) ([API service](https://services.arcgis.com/RmCCgQtiZLDCtblq/ArcGIS/rest/services/2025_Parcels_with_DINS_data/FeatureServer/5)) - pre-fire assessor parcel data, fire impact

## Parcel Analysis

For each parcel in the burn area, we calcuate the following:
* quantity and size of single family residence(s) before/after
* quantity and size of accessory dwelling unit(s) before/after
* quantity and size of multi-family residence(s) before/after
* whether or not the primary residence rebuild is like-for-like and if so, whether its size is smaller, identical, larger
* whether or not the rebuild adds an additional primary unit under SB-9
* whether or not additional ADUs are being added and if so, how many

We also carry over DINS and EPIC-LA data (damage status, permit status, rebuild progress, last-update timestamps, etc) from the respective sources.

## Aggregate Analysis

Parcel analysis is aggregated (counts, percentages) by the following geographical areas:
* Entire burn area
* Census tracts
* Census blocks
* Altagether zones

## Development

* MIT license
* See `ARCHITECTURE.md` for implementation details