# Proxy benchmark split contract

The canonical proxy benchmark does **not** consume the `partition` column in
`proxy_model_feature_table.csv`. That field is retained inside the checksum-locked
historical feature table, but it describes an earlier sample partition and
disagrees with the final geographical split for 7,085 of 20,749 pixels.

The final benchmark derives the split deterministically from `spatial_block`:

- `block_row = spatial_block // 10`;
- `block_col = spatial_block % 10`;
- block columns 3–4: outer proxy test, 4,188 pixels in 20 blocks;
- block columns 2 and 5: excluded spatial buffer, 4,467 pixels in 20 blocks;
- remaining block columns: development, 12,094 pixels in 60 blocks.

This produces zero development/test block overlap and a minimum two-column
separation. The counts agree with the frozen enhanced buffered-model comparison.
Code, tests or secondary analyses must derive this split from `spatial_block` and
must not filter on the legacy `partition` field. The benchmark remains
WorldCover-derived proxy land-cover agreement, not independent heritage-condition
validation.
