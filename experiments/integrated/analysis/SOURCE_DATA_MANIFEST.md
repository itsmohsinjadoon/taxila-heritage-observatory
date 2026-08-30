# Source data manifest

## Frozen Taxila inputs

| Input bundle | SHA-256 |
|---|---|
| `Taxila_PreserveX_Stage3_M1_Spatial_Foundation_Bundle.zip` | `855d1677ea7a6ee4e2991ea3b37e3105e0a0aeb4c2e2e42f7050bf9f23c0ef24` |
| `Taxila_PreserveX_Stage4_Batch1_Landsat_Reproducibility_Bundle.zip` | `d31e807e03892a78c7ddccd8892320f0b573f0e08a7b6d08416e52811eb1ad9b` |
| `Taxila_PreserveX_Stage4_Batch2_Land_Cover_Reproducibility_Bundle.zip` | `3e306dfabdb38cac8d5e6fd0c45ccb8ee978ddf41ddd6d19158f997071236c3b` |
| `Taxila_PreserveX_Stage4_Batch3_Reproducibility_Bundle.zip` | `477aeb71ca315e6d3e3ec6bc1f46a5d456daee7c967b8cba39305cf6702eabd8` |
| `Taxila_PreserveX_Stage4_Batch4_Dual_AI_Screening_Reproducibility_Bundle.zip` | `1c3baa631be9c526dee4b47ab03c3800b605a6c550bfc357c8db2a54347fc028` |

## External forcing and susceptibility sources

| File | Source | SHA-256 | Analytical use |
|---|---|---|---|
| `nasa_power_taxila_1991_2025_daily.json` | NASA POWER Daily API, point 33.746° N, 72.835° E | `d1868aa2b5d39f523c13f87a4a3848fdf22e8222b15d089ce06d6da3db42a6ef` | Site-wide daily climate forcing and matched epoch extremes |
| `N33E072.hgt.gz` | AWS Terrain Tiles public bare-earth elevation collection | `3533552b896de675087a6cfbd6d758f44b1ef46397b1a277b195c1d760c9fbd0` | Elevation, slope, terrain roughness, D8 convergence, TWI proxy and high-flow distance |

## Authoritative documentation

- NASA POWER Daily API: <https://power.larc.nasa.gov/docs/services/api/temporal/daily/>
- NASA POWER resolution guidance: <https://power.larc.nasa.gov/docs/tutorials/service-data-request/api/>
- AWS Terrain Tiles: <https://registry.opendata.aws/terrain-tiles/>

NASA POWER meteorology is represented as site-wide temporal forcing. It is not
resampled and interpreted as independent 30 m rainfall measurements.

The raw 30 m Landsat and land-cover arrays are generated from the frozen input
bundles with `extract_geotiff_raw.mjs`; their derived-file inventory and hashes
are recorded in `raw_manifest.json`.
