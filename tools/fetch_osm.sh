#!/bin/sh
# Download the raw OpenStreetMap extract for the St. George campus into data/osm/.
set -e
cd "$(dirname "$0")/.."
OUT=data/osm
mkdir -p "$OUT"
API=https://overpass-api.de/api/interpreter
UA="uoft-digital-twin/1.0"
B='43.6545,-79.4060,43.6715,-79.3855'

curl -sf -m 180 -A "$UA" -o "$OUT/buildings.json" --data-urlencode "data=[out:json][timeout:120];
( way[\"building\"]($B); relation[\"building\"]($B); way[\"building:part\"]($B); );
out body geom;" "$API"

curl -sf -m 180 -A "$UA" -o "$OUT/landscape.json" --data-urlencode "data=[out:json][timeout:120];
( way[\"highway\"]($B);
  way[\"leisure\"~\"park|garden|pitch|sports_centre|stadium|track\"]($B);
  relation[\"leisure\"~\"park|garden\"]($B);
  way[\"landuse\"~\"grass|recreation_ground|village_green\"]($B);
  way[\"natural\"~\"water|wood|scrub\"]($B);
  way[\"amenity\"=\"parking\"]($B);
  way[\"railway\"~\"subway|rail\"]($B);
  node[\"railway\"=\"station\"]($B);
  node[\"station\"=\"subway\"]($B); );
out body geom;" "$API"

curl -sf -m 180 -A "$UA" -o "$OUT/campus.json" --data-urlencode "data=[out:json][timeout:120];
( way[\"amenity\"=\"university\"](43.640,-79.420,43.680,-79.370);
  relation[\"amenity\"=\"university\"](43.640,-79.420,43.680,-79.370);
  way[\"amenity\"=\"college\"](43.640,-79.420,43.680,-79.370);
  relation[\"amenity\"=\"college\"](43.640,-79.420,43.680,-79.370); );
out body geom;" "$API"

curl -sf -m 120 -A "$UA" -o "$OUT/trees.json" --data-urlencode "data=[out:json][timeout:60];
( node[\"natural\"=\"tree\"]($B); );
out body;" "$API"

ls -la "$OUT"
