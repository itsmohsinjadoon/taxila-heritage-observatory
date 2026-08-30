import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const sharp = require("sharp");

const root = path.resolve(".");
const outDir = path.join(root, "analysis", "derived", "raw");
await fs.mkdir(outDir, { recursive: true });

const epochs = ["E2004", "E2009", "E2014", "E2019", "E2024"];
const landsatDir = path.join(root, "work", "landsat", "outputs", "composites");
const landcoverDir = path.join(
  root,
  "work",
  "landcover",
  "Taxila_PreserveX_Stage4_Batch2",
  "outputs",
);

async function readFloatRaster(file) {
  const { data, info } = await sharp(file, { unlimited: true })
    .raw({ depth: "float" })
    .toBuffer({ resolveWithObject: true });
  return {
    values: new Float32Array(data.buffer, data.byteOffset, data.byteLength / 4),
    info,
  };
}

async function readByteRaster(file) {
  const { data, info } = await sharp(file, { unlimited: true })
    .raw()
    .toBuffer({ resolveWithObject: true });
  return { values: data, info };
}

function selectFloatChannels(values, channels, selected) {
  const pixels = values.length / channels;
  const out = new Float32Array(pixels * selected.length);
  for (let i = 0; i < pixels; i += 1) {
    const src = i * channels;
    const dst = i * selected.length;
    for (let j = 0; j < selected.length; j += 1) {
      out[dst + j] = values[src + selected[j]];
    }
  }
  return out;
}

function selectByteChannel(values, channels, selected = 0) {
  const pixels = values.length / channels;
  const out = Buffer.allocUnsafe(pixels);
  for (let i = 0; i < pixels; i += 1) {
    out[i] = values[i * channels + selected];
  }
  return out;
}

const manifest = {
  schema_version: "1.0",
  generated_by: "analysis/extract_geotiff_raw.mjs",
  width: 616,
  height: 655,
  grid_transform_gdal: [292980.0, 30.0, 0.0, 3748620.0, 0.0, -30.0],
  crs: "EPSG:32643",
  files: [],
};

for (const epoch of epochs) {
  const indexFile = path.join(landsatDir, `${epoch}_oli_like_indices.tif`);
  const indexRaster = await readFloatRaster(indexFile);
  if (
    indexRaster.info.width !== manifest.width ||
    indexRaster.info.height !== manifest.height ||
    indexRaster.info.channels !== 6
  ) {
    throw new Error(`Unexpected index raster geometry for ${epoch}`);
  }
  // libvips exposes the first grayscale band as three identical channels,
  // followed by the remaining GeoTIFF bands. The source order is
  // NDVI, NDBI, MNDWI, BSI, so the required channel indices are 0,3,4,5.
  const selectedIndices = selectFloatChannels(
    indexRaster.values,
    indexRaster.info.channels,
    [0, 3, 4, 5],
  );
  const indexOut = path.join(outDir, `${epoch}_indices_ndvi_ndbi_mndwi_bsi.f32`);
  await fs.writeFile(
    indexOut,
    Buffer.from(
      selectedIndices.buffer,
      selectedIndices.byteOffset,
      selectedIndices.byteLength,
    ),
  );
  manifest.files.push({
    epoch,
    kind: "indices",
    source: path.relative(root, indexFile),
    output: path.relative(root, indexOut),
    dtype: "float32_le",
    layout: "row_major_pixel_interleaved",
    bands: ["NDVI", "NDBI", "MNDWI", "BSI"],
    nodata: -9999,
  });

  const obsFile = path.join(landsatDir, `${epoch}_valid_observation_count.tif`);
  const obsRaster = await readFloatRaster(obsFile);
  const obsSelected = selectFloatChannels(
    obsRaster.values,
    obsRaster.info.channels,
    [0],
  );
  const obsOut = path.join(outDir, `${epoch}_valid_observations.f32`);
  await fs.writeFile(
    obsOut,
    Buffer.from(obsSelected.buffer, obsSelected.byteOffset, obsSelected.byteLength),
  );
  manifest.files.push({
    epoch,
    kind: "valid_observations",
    source: path.relative(root, obsFile),
    output: path.relative(root, obsOut),
    dtype: "float32_le",
    layout: "row_major",
  });

  const lcFile = path.join(landcoverDir, `${epoch}_provisional_landcover.tif`);
  const lcRaster = await readByteRaster(lcFile);
  const lcSelected = selectByteChannel(lcRaster.values, lcRaster.info.channels, 0);
  const lcOut = path.join(outDir, `${epoch}_provisional_landcover.u8`);
  await fs.writeFile(lcOut, lcSelected);
  manifest.files.push({
    epoch,
    kind: "provisional_landcover",
    source: path.relative(root, lcFile),
    output: path.relative(root, lcOut),
    dtype: "uint8",
    layout: "row_major",
    nodata: 0,
  });
}

const reflectanceFile = path.join(
  landsatDir,
  "E2019_oli_like_surface_reflectance.tif",
);
const reflectanceRaster = await readFloatRaster(reflectanceFile);
if (reflectanceRaster.info.channels !== 8) {
  throw new Error("Unexpected E2019 reflectance channel layout");
}
const reflectanceSelected = selectFloatChannels(
  reflectanceRaster.values,
  reflectanceRaster.info.channels,
  [0, 3, 4, 5, 6, 7],
);
const reflectanceOut = path.join(outDir, "E2019_reflectance_6band.f32");
await fs.writeFile(
  reflectanceOut,
  Buffer.from(
    reflectanceSelected.buffer,
    reflectanceSelected.byteOffset,
    reflectanceSelected.byteLength,
  ),
);
manifest.files.push({
  epoch: "E2019",
  kind: "reflectance",
  source: path.relative(root, reflectanceFile),
  output: path.relative(root, reflectanceOut),
  dtype: "float32_le",
  layout: "row_major_pixel_interleaved",
  bands: ["blue", "green", "red", "nir08", "swir16", "swir22"],
  nodata: -9999,
});

await fs.writeFile(
  path.join(outDir, "raw_manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
  "utf8",
);

console.log(JSON.stringify({ status: "PASS", files: manifest.files.length }));
