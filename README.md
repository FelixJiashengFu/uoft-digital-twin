# 多伦多大学数字孪生 · UofT St. George Digital Twin

A browser-based 3D model of the University of Toronto St. George campus and its
surroundings, built from OpenStreetMap data and rendered with Three.js.

## What it does

- **Real geometry**: 3,532 building footprints (including 1,310 detailed 3D parts),
  heights, roof shapes (gabled, hipped, pyramidal, dome), facade colours, roads,
  green space, 1,724 mapped trees, TTC Line 1/2 and stations.
- **Real sun**: sun position computed for Toronto at any date and time, with
  shadows, sky colour, sunrise/sunset, and lit windows at night.
- **Seasonal trees**: foliage colour follows the chosen date (autumn colours in October).
- **Data layers**: realistic, building function, height, and two *simulated* layers
  (occupancy, energy) driven by a schedule model per building type.
- **Inspect & search**: click any building for its OSM attributes, landmark notes,
  and simulated live readings; search in English or Chinese; guided campus tour.
- **中文 / English**: the whole interface switches language from the button next to
  the clock. The first visit follows the browser language; the choice is remembered.

The occupancy, energy, indoor temperature and CO₂ values are simulated, not
sensor readings. Outdoor temperature uses Toronto climate normals.

## Layout

```
tools/fetch_osm.sh   download raw Overpass extracts into data/osm/
tools/process.py     project, clean and classify into data/campus.json
tools/build.py       inline the dataset into the viewer → dist/
src/index.html       viewer source (data placeholder: __TWIN_DATA__)
dist/index.html      standalone page — open directly in a browser
dist/uoft-twin.html  same page without a document skeleton (for publishing)
```

## Rebuild

```sh
./tools/fetch_osm.sh                      # download raw OSM data (not stored in git)
python3 -I tools/process.py data/osm data/campus.json
python3 -I tools/build.py src/index.html data/campus.json dist/uoft-twin.html
```

## Controls

Drag to pan · right-drag or two fingers to rotate · scroll or pinch to zoom ·
`/` focuses search · `Esc` clears the selection.

Map data © OpenStreetMap contributors, available under the ODbL.
Unofficial project, not affiliated with the University of Toronto.
