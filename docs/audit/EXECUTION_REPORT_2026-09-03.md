# ProjectTaxila fresh execution report

**Execution date:** 3 September 2026  
**Platform:** Windows 11, Python 3.12.13  
**Seed:** 311  
**Environment:** exact versions in `requirements-reproduction.txt`

## Outcome

The canonical analysis was executed locally rather than inferred from stored
tables. A reduced validation run completed first, followed by the complete
publication profile and a final validation run through the new receipt-producing
runner.

| Run | Result | Duration | Evidence locks |
| --- | --- | ---: | ---: |
| Initial validation profile | PASS | approximately 2 min | 19/19 |
| Publication profile | REVIEW | approximately 24 min 36 s | 24/27 |
| Final runner validation | PASS | 129.362 s | 19/19 |
| Scientific data audit | PASS | — | 30/30 |

The publication run produced 65 files (90,429,748 bytes), including vector and
raster figures, tables, fitted-model artifacts, validation records, an output
manifest and SHA-256 list. The final validation runner produced an executed
notebook, output manifest, data-quality report and `execution_receipt.json` in a
separate run directory.

## Independently observed results

- E2004–E2024 common spectral support: **386,280 cells (95.7371%)**.
- Cells meeting at least two adverse endpoint criteria: **65,391 (16.93%)**.
- Cells meeting all three adverse endpoint criteria: **5,493 (1.42%)**.
- Highest fixed 500 m priority: **Giri complex of monuments, 0.591176**.
- Annual precipitation Theil–Sen slope: **−10.303704 mm yr⁻¹** in the declared frozen analysis.
- Annual mean-temperature Theil–Sen slope: **+0.041753 °C yr⁻¹** in the declared frozen analysis.
- Development-selected MLP point estimates on the 4,188-pixel outer proxy test: macro-F1 **0.830072**, overall agreement **0.828080**, and top-label ECE **0.015117**.
- Fixed-six-class block-bootstrap macro-F1 interval: **0.701423–0.850954**.

The full joint analysis used 500 independent spatial states crossed with ten
decision settings (5,000 score vectors). The largest top-three probabilities
were Giri complex **0.7324**, Buddhist remains around Bhallar stupa **0.5260**,
Giri Mosque and tombs **0.4626**, and Jaulian **0.4096**. Wide rank intervals
remain material and should accompany the fixed ordering.

## Failed publication locks

| Lock | Observed | Frozen target | Absolute difference | Tolerance |
| --- | ---: | ---: | ---: | ---: |
| Primary proxy macro-F1 | 0.830072 | 0.830795 | 0.000723 | 0.000005 |
| Primary proxy overall agreement | 0.828080 | 0.833095 | 0.005015 | 0.000005 |
| Primary proxy top-label ECE | 0.015117 | 0.014280 | 0.000837 | 0.000005 |

These are the same three platform-sensitive failures found in the 2 September
audit. The fresh run therefore confirms that the repository must not state that
all publication evidence locks reproduce on Windows. The fixed-six-class
bootstrap correction reproduces the rounded manuscript interval but does not
resolve the point-metric discrepancy.

## Data-quality evidence

The fresh scientific audit verified all 157 files in the frozen SHA-256 manifest,
the 18-record component inventory and explicit unresolved Saraikala geometry,
17 mapped components at every declared radius/epoch grain, a complete 12,784-day
climate sequence from 1991 through 2025, 20,749 unique proxy pixels, the final
12,094/4,467/4,188 development-buffer-test split, and alignment of all 21
GeoTIFFs on the 616 × 655, 30 m, EPSG:32643 grid.

The feature table's historical `partition` field disagrees with the final
block-derived geographical split for 7,085 pixels. The field is retained only
because the evidence package is checksum-locked. The canonical notebook now
drops it explicitly and derives the split from `spatial_block`; see
[`PROXY_SPLIT_CONTRACT.md`](PROXY_SPLIT_CONTRACT.md).

## Traceability hashes

| Artifact | SHA-256 |
| --- | --- |
| Executed publication notebook | `4256DA4A2CF4D43930FB5E91BAF19961466DE0A2495E7DF2F1245236BED0CC44` |
| Publication headline evidence lock | `E7AACD5FCE8369DB63C37396F3D288C68F03FD9608C4F05B715D38B04D0D0D2C` |
| Publication proxy comparison | `4D55174EE245FD56C4CB5D9231C24A0272B85802B1AF25ECF71AEC50B5C63B88` |
| Publication output manifest | `82EADD6A2708DA3862B8070A9B020F6FFA132F999CCD5742795B691A2F52AF40` |
| Final validation execution receipt | `C06DFBDCA03D2E064092D580F12D49B7436658816D57AC4CE0368240E7EFDBCB` |

Executed notebooks and generated outputs remain outside Git because they are
large run artifacts. This report, the committed clean notebooks, runner,
data-quality report and hashes provide the reviewable repository record.

## Validation decision

**Share with caveats / needs manuscript correction before submission.** The
data package, deterministic scores, uncertainty experiments and engineering
pipeline are internally reproducible. The all-lock clean-reproduction claim is
not supported by the fresh publication run, and the proxy benchmark remains a
land-cover proxy rather than independent heritage-condition accuracy.
