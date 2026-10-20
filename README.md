# 多伦多大学数字孪生 · UofT St. George Digital Twin

A browser-based 3D model of the University of Toronto St. George campus and its
surroundings, built from OpenStreetMap data and rendered with Three.js.

**Live:** https://felixjiashengfu.github.io/uoft-digital-twin/

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
- **Smooth zoom**: every wheel notch, pinch or `+`/`-` key press eases out over about
  0.3 s (frame-rate independent) and zooms about the exact point under the cursor;
  dragging keeps the grabbed point under the pointer. `tools/qa.mjs` measures one notch
  frame by frame: 95% of it is done after 0.33 s, no frame carries more than 14% of it,
  and the point under the cursor does not move (0.00 px).
- **English / 中文**: the page always opens in English, whatever the browser language;
  the button next to the clock switches the whole interface to Chinese, and `?lang=zh`
  opens it in Chinese.

The occupancy, energy, indoor temperature and CO₂ values are simulated, not
sensor readings. Outdoor temperature uses Toronto climate normals.

## Layout

```
tools/fetch_osm.sh   download raw Overpass extracts into data/osm/
tools/process.py     project, clean and classify into data/campus.json
tools/build.mjs      inline the dataset into the viewer → dist/
tools/qa.mjs         automated browser checks (headless Chrome): language default, zoom
                     smoothness, pan/rotate/pinch, fly-to; writes qa/report.json and screenshots
src/index.html       viewer source (data placeholder: __TWIN_DATA__)
dist/index.html      standalone page — open directly in a browser
dist/uoft-twin.html  same page without a document skeleton (for publishing)
.github/workflows/   deploys dist/ to GitHub Pages on every push to main
```

## Rebuild

Processing the raw OSM data needs Python 3; building and checking the page run under
Deno (or Node 20+).

```sh
./tools/fetch_osm.sh                      # download raw OSM data (not stored in git)
python3 -I tools/process.py data/osm data/campus.json
deno run -A tools/build.mjs               # → dist/uoft-twin.html, dist/index.html
deno install                              # playwright-core, for the checks
deno run -A --unsafe-proto tools/qa.mjs   # 20 checks in headless Chrome; add a URL to check the live site
```

## Controls

Drag to pan · right-drag to rotate and tilt (or Ctrl-drag) · scroll, pinch, middle-drag or
double-click to zoom (Shift + double-click zooms out) · two fingers: pinch to zoom, twist to
rotate, move up or down together to tilt · arrow keys pan, `+` / `-` zoom, `Q` / `E` turn ·
`/` focuses search · `Esc` clears the selection.

Map data © OpenStreetMap contributors, available under the
[Open Database License](https://opendatacommons.org/licenses/odbl/). The derived
dataset in `data/campus.json` (and embedded in `dist/`) is likewise available under the ODbL.
Unofficial project, not affiliated with the University of Toronto.
