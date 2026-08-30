#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { fromFile, writeArrayBuffer } from "geotiff";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const runRoot = path.resolve(scriptDir, "..");
const rasterDir = path.join(runRoot, "05_processed_rasters");
const validationDir = path.join(runRoot, "16_validation");
const spec = JSON.parse(await fs.readFile(path.join(rasterDir, "derived_raster_spec.json"), "utf8"));
const [xOrigin, pixelWidth, , yOrigin, , pixelHeight] = spec.transform_gdal;
const outputs = [];

for (const fileName of spec.float32_files) {
  const sourcePath = path.join(rasterDir, fileName);
  const raw = await fs.readFile(sourcePath);
  const values = new Float32Array(raw.buffer, raw.byteOffset, raw.byteLength / 4);
  if (values.length !== spec.width * spec.height) {
    throw new Error(`Unexpected float raster size for ${fileName}`);
  }
  const cleaned = new Float32Array(values.length);
  for (let index = 0; index < values.length; index += 1) {
    cleaned[index] = Number.isFinite(values[index]) ? values[index] : spec.nodata;
  }
  const metadata = {
    width: spec.width,
    height: spec.height,
    BitsPerSample: [32],
    SampleFormat: [3],
    SamplesPerPixel: [1],
    PlanarConfiguration: [1],
    Compression: [1],
    PhotometricInterpretation: [1],
    RowsPerStrip: [spec.height],
    StripByteCounts: [cleaned.byteLength],
    ModelPixelScale: [pixelWidth, Math.abs(pixelHeight), 0],
    ModelTiepoint: [0, 0, 0, xOrigin, yOrigin, 0],
    GTModelTypeGeoKey: 1,
    GTRasterTypeGeoKey: 1,
    ProjectedCSTypeGeoKey: 32643,
    GDAL_NODATA: `${spec.nodata}`,
    Software: "geotiff.js 2.1.3; Taxila PreserveX experiment-only pipeline",
  };
  const arrayBuffer = writeArrayBuffer(cleaned, metadata);
  const outputName = fileName.replace(/\.f32$/, ".tif");
  const outputPath = path.join(rasterDir, outputName);
  await fs.writeFile(outputPath, Buffer.from(arrayBuffer));

  const tiff = await fromFile(outputPath);
  const image = await tiff.getImage();
  const read = await image.readRasters({ interleave: true });
  const geoKeys = image.getGeoKeys();
  const boundingBox = image.getBoundingBox();
  let dataMin = Infinity;
  let dataMax = -Infinity;
  for (const value of read) {
    if (value !== spec.nodata && Number.isFinite(value)) {
      dataMin = Math.min(dataMin, value);
      dataMax = Math.max(dataMax, value);
    }
  }
  outputs.push({
    file: path.relative(runRoot, outputPath),
    width: image.getWidth(),
    height: image.getHeight(),
    projectedCSTypeGeoKey: geoKeys.ProjectedCSTypeGeoKey,
    boundingBox,
    nodata: image.getGDALNoData(),
    dataMin,
    dataMax,
    bytes: (await fs.stat(outputPath)).size,
    pass:
      image.getWidth() === spec.width &&
      image.getHeight() === spec.height &&
      geoKeys.ProjectedCSTypeGeoKey === 32643 &&
      boundingBox.every(Number.isFinite),
  });
}

const validation = {
  status: outputs.every((item) => item.pass) ? "PASS" : "FAIL",
  geotiffWriter: "geotiff.js 2.1.3",
  outputs,
};
await fs.writeFile(
  path.join(validationDir, "derived_geotiff_validation.json"),
  `${JSON.stringify(validation, null, 2)}\n`,
  "utf8",
);
if (validation.status !== "PASS") {
  throw new Error("Derived GeoTIFF validation failed");
}
console.log(JSON.stringify({ status: validation.status, files: outputs.length }));
