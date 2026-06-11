"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import styles from "./MapSelector.module.css";
import { PenTool, Map as MapIcon, RefreshCw, Download, Square } from "lucide-react";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import MapboxDraw from "@mapbox/mapbox-gl-draw";
import "@mapbox/mapbox-gl-draw/dist/mapbox-gl-draw.css";
import * as d3 from "d3";
import type { Feature, Polygon } from "geojson";
import TerrainBlock3D, {
  type SurfaceTextureOption,
  type TerrainBlockData,
  type TerrainLayer,
  type TerrainWaterFeature,
} from "./TerrainBlock3D";

interface MacrostratUnit {
  best_int_name?: string;
  lith?: string;
  color?: string;
}

interface OverpassCoordinate {
  lat: number;
  lon: number;
}

interface OverpassElement {
  type: "way" | "relation";
  id: number;
  tags?: Record<string, string>;
  geometry?: OverpassCoordinate[];
}

interface OverpassResponse {
  elements?: OverpassElement[];
}

const fallbackAgeColors = {
  quaternary: "#FFFF4D",
  cretaceous: "#80FF4D",
  jurassic: "#66FF99",
  triassic: "#66FFCC",
};

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function setMapCursor(mapInstance: mapboxgl.Map, cursor: string) {
  const canvas = mapInstance.getCanvas();
  if (canvas) canvas.style.cursor = cursor;
}

const selectionSourceId = "terrain-block-selection-source";
const selectionFillLayerId = "terrain-block-selection-fill";
const selectionOutlineLayerId = "terrain-block-selection-outline";
const esriImageryTileUrl = "https://server.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const maxSatelliteTextureSize = 768;
const minSatelliteTextureSize = 320;
const maxEsriTextureZoom = 16;
const minEsriTextureZoom = 8;
const esriTileSize = 256;
const defaultSurfaceTextureStyle = "bag326/cluwjr06f002o01pphuck9mrm";
const defaultGridBaseTextureStyle = "mapbox/outdoors-v12";
const chinaStartCenters: Array<[number, number]> = [
  [116.4074, 39.9042],
  [121.4737, 31.2304],
  [113.2644, 23.1291],
  [104.0665, 30.5728],
  [108.9398, 34.3416],
  [114.3055, 30.5928],
  [120.1551, 30.2741],
  [118.7969, 32.0603],
  [106.5516, 29.563],
  [102.8329, 24.8801],
  [87.6168, 43.8256],
  [91.1322, 29.6604],
  [126.6424, 45.7567],
  [111.751, 40.8415],
  [117.1201, 36.6512],
  [112.9388, 28.2282],
  [119.2965, 26.0745],
  [101.7782, 36.6171],
];

const defaultTerrainLayers: TerrainLayer[] = [
  { name: "第四纪覆盖层", color: "#d8c074", textureFile: "legend_01_soil_silt_or_alluvium.png" },
  { name: "砂岩层", color: "#b87943", textureFile: "legend_08_massive_sandstone.png" },
  { name: "灰岩层", color: "#8ca7a0", textureFile: "legend_15_massively_bedded_limestone.png" },
  { name: "结晶基底", color: "#6f5f7f", textureFile: "legend_45_gneiss.png" },
];

// Macrostrat /units（真实地层柱）单元结构
interface MacrostratColumnUnit {
  unit_name?: string;
  Fm?: string;
  Gp?: string;
  t_age?: number;
  b_age?: number;
  max_thick?: number;
  color?: string;
  lith?: Array<{ name?: string; type?: string; class?: string }>;
}

// 岩性关键字 → 图例贴图 / 中文名 / 颜色
const lithTextureTable: Array<[string, { file: string; name: string; color: string }]> = [
  ["limestone", { file: "legend_15_massively_bedded_limestone.png", name: "灰岩", color: "#8fb6c9" }],
  ["carbonate", { file: "legend_15_massively_bedded_limestone.png", name: "碳酸盐岩", color: "#9fc0cf" }],
  ["dolomite", { file: "legend_19_dolomite.png", name: "白云岩", color: "#c9b79b" }],
  ["chalk", { file: "legend_22_chalk.png", name: "白垩", color: "#e6e6da" }],
  ["sandstone", { file: "legend_08_massive_sandstone.png", name: "砂岩", color: "#c8a165" }],
  ["siltstone", { file: "legend_12_thin_bedded_or_shaly_sandstone.png", name: "粉砂岩", color: "#b59e78" }],
  ["conglomerate", { file: "legend_07_conglomerate.png", name: "砾岩", color: "#a98b6b" }],
  ["breccia", { file: "legend_40_breccia.png", name: "角砾岩", color: "#9c7e63" }],
  ["shale", { file: "legend_25_shale.png", name: "页岩", color: "#6b7b6b" }],
  ["mudstone", { file: "legend_25_shale.png", name: "泥岩", color: "#7a7a6e" }],
  ["claystone", { file: "legend_28_clay.png", name: "黏土岩", color: "#7a7466" }],
  ["clay", { file: "legend_28_clay.png", name: "黏土", color: "#7a7466" }],
  ["coal", { file: "legend_31_coal.png", name: "煤", color: "#23211f" }],
  ["chert", { file: "legend_18_bedded_chert.png", name: "燧石", color: "#9aa0a6" }],
  ["gypsum", { file: "legend_37_gypsum.png", name: "石膏", color: "#e2d7c0" }],
  ["salt", { file: "legend_38_salt.png", name: "盐岩", color: "#e8e2d2" }],
  ["sand", { file: "legend_02_sand.png", name: "砂", color: "#e0c48a" }],
  ["gravel", { file: "legend_03_gravel_and_stratified_drift.png", name: "砂砾", color: "#c9b08a" }],
  ["basalt", { file: "legend_52_basaltic_flows.png", name: "玄武岩", color: "#46464e" }],
  ["andesite", { file: "legend_53_bedded_lava_andesitic.png", name: "安山岩", color: "#8a7a6a" }],
  ["rhyolite", { file: "legend_50_volcanic_breccia_and_tuff.png", name: "流纹岩", color: "#c9b6a0" }],
  ["tuff", { file: "legend_50_volcanic_breccia_and_tuff.png", name: "凝灰岩", color: "#bdb29c" }],
  ["volcanic", { file: "legend_52_basaltic_flows.png", name: "火山岩", color: "#6a5a55" }],
  ["granite", { file: "legend_55_granite.png", name: "花岗岩", color: "#d8b0a0" }],
  ["granodiorite", { file: "legend_55_granite.png", name: "花岗闪长岩", color: "#cba694" }],
  ["diorite", { file: "legend_55_granite.png", name: "闪长岩", color: "#9a8e84" }],
  ["gabbro", { file: "legend_57_massive_igneous_rock_57.png", name: "辉长岩", color: "#3e4248" }],
  ["gneiss", { file: "legend_45_gneiss.png", name: "片麻岩", color: "#b0a0b8" }],
  ["schist", { file: "legend_48_schist.png", name: "片岩", color: "#8c8c7a" }],
  ["slate", { file: "legend_27_slate.png", name: "板岩", color: "#4a4f58" }],
  ["quartzite", { file: "legend_11_quartzite.png", name: "石英岩", color: "#d8d2c0" }],
  ["marble", { file: "legend_20_marble.png", name: "大理岩", color: "#e0e0e0" }],
];

const lithClassDefault: Record<string, { file: string; name: string; color: string }> = {
  sedimentary: { file: "legend_08_massive_sandstone.png", name: "沉积岩", color: "#b0a080" },
  igneous: { file: "legend_55_granite.png", name: "火成岩", color: "#6a5f5a" },
  metamorphic: { file: "legend_45_gneiss.png", name: "变质岩", color: "#8a8a92" },
};

function lithInfoForUnit(unit: MacrostratColumnUnit) {
  const liths = unit.lith ?? [];
  const blob = liths.map((l) => `${l.name ?? ""} ${l.type ?? ""}`).join(" ").toLowerCase();
  for (const [keyword, info] of lithTextureTable) {
    if (blob.includes(keyword)) return info;
  }
  const cls = (liths[0]?.class ?? "").toLowerCase();
  if (cls.includes("igneous")) return lithClassDefault.igneous;
  if (cls.includes("metamorphic")) return lithClassDefault.metamorphic;
  return lithClassDefault.sedimentary;
}

// 把 Macrostrat 真实地层柱转成自顶向下的 TerrainLayer[]（年轻在上、最老在下）。
const maxRealLayers = 14;
function buildLayersFromUnits(units: MacrostratColumnUnit[]): TerrainLayer[] | null {
  let list = units.filter(Boolean);
  if (list.length < 3) return null; // 太少没必要，交回模板
  list = list.slice().sort((a, b) => (Number(a.t_age) || 0) - (Number(b.t_age) || 0));
  if (list.length > maxRealLayers) {
    const sampled: MacrostratColumnUnit[] = [];
    for (let i = 0; i < maxRealLayers; i++) {
      sampled.push(list[Math.round((i * (list.length - 1)) / (maxRealLayers - 1))]);
    }
    list = sampled;
  }
  return list.map((unit) => {
    const info = lithInfoForUnit(unit);
    const baseName = unit.unit_name || unit.Fm || unit.Gp || info.name;
    const age = unit.t_age != null && unit.b_age != null ? ` ${unit.t_age}-${unit.b_age}Ma` : "";
    return {
      name: `${baseName}·${info.name}${age}`,
      color: unit.color || info.color,
      textureFile: info.file,
    };
  });
}

const geologicAgeNames: Record<string, string> = {
  "holocene": "全新世",
  "pleistocene": "更新世",
  "pliocene": "上新世",
  "miocene": "中新世",
  "oligocene": "渐新世",
  "eocene": "始新世",
  "paleocene": "古新世",
  "quaternary": "第四纪",
  "neogene": "新近纪",
  "paleogene": "古近纪",
  "tertiary": "第三纪",
  "cretaceous": "白垩纪",
  "jurassic": "侏罗纪",
  "triassic": "三叠纪",
  "permian": "二叠纪",
  "carboniferous": "石炭纪",
  "pennsylvanian": "宾夕法尼亚亚纪",
  "mississippian": "密西西比亚纪",
  "devonian": "泥盆纪",
  "silurian": "志留纪",
  "ordovician": "奥陶纪",
  "cambrian": "寒武纪",
  "proterozoic": "元古宙",
  "archean": "太古宙",
  "hadean": "冥古宙",
  "precambrian": "前寒武纪",
  "cenozoic": "新生代",
  "mesozoic": "中生代",
  "paleozoic": "古生代",
};

const geologicAgeModifiers: Record<string, string> = {
  "early": "早",
  "middle": "中",
  "late": "晚",
  "lower": "下",
  "upper": "上",
};

function asStageName(name: string, modifier: string) {
  if (modifier === "lower" || modifier === "middle" || modifier === "upper") {
    if (name.endsWith("纪")) return `${name.slice(0, -1)}统`;
    if (name.endsWith("世")) return `${name.slice(0, -1)}统`;
  }

  if (name.endsWith("纪")) return `${name.slice(0, -1)}世`;
  return name;
}

function localizeGeologicPart(part: string) {
  const trimmed = part.trim();
  const lower = trimmed.toLowerCase();
  if (geologicAgeNames[lower]) return geologicAgeNames[lower];

  const modifierMatch = lower.match(/^(early|middle|late|lower|upper)\s+(.+)$/);
  if (modifierMatch) {
    const [, modifier, baseName] = modifierMatch;
    const localizedBase = geologicAgeNames[baseName];
    if (localizedBase) return `${geologicAgeModifiers[modifier]}${asStageName(localizedBase, modifier)}`;
  }

  return trimmed;
}

function localizeGeologicName(name?: string) {
  if (!name) return "地表单元";

  return name
    .split(/\s*[/,;]\s*|\s+-\s+/)
    .map(localizeGeologicPart)
    .filter(Boolean)
    .join(" / ");
}

const createSelectionFeature = (start: mapboxgl.LngLat, end: mapboxgl.LngLat): Feature<Polygon> => {
  const west = Math.min(start.lng, end.lng);
  const east = Math.max(start.lng, end.lng);
  const south = Math.min(start.lat, end.lat);
  const north = Math.max(start.lat, end.lat);

  return {
    type: "Feature",
    properties: {},
    geometry: {
      type: "Polygon",
      coordinates: [[
        [west, south],
        [east, south],
        [east, north],
        [west, north],
        [west, south],
      ]],
    },
  };
};

function mercatorY(lat: number) {
  const clampedLat = Math.min(Math.max(lat, -85.05112878), 85.05112878);
  return Math.log(Math.tan(Math.PI / 4 + (clampedLat * Math.PI) / 360));
}

function getSatelliteTextureSize(bounds: TerrainBlockData["bounds"]) {
  const xSpan = Math.max(Math.abs(((bounds.east - bounds.west) * Math.PI) / 180), 0.000001);
  const ySpan = Math.max(Math.abs(mercatorY(bounds.north) - mercatorY(bounds.south)), 0.000001);
  const aspect = xSpan / ySpan;

  if (aspect >= 1) {
    return {
      width: maxSatelliteTextureSize,
      height: Math.round(Math.min(Math.max(maxSatelliteTextureSize / aspect, minSatelliteTextureSize), maxSatelliteTextureSize)),
    };
  }

  return {
    width: Math.round(Math.min(Math.max(maxSatelliteTextureSize * aspect, minSatelliteTextureSize), maxSatelliteTextureSize)),
    height: maxSatelliteTextureSize,
  };
}

function buildMapboxStaticTextureUrl(bounds: TerrainBlockData["bounds"], token?: string, stylePath = defaultSurfaceTextureStyle) {
  if (!token) return undefined;

  const { width, height } = getSatelliteTextureSize(bounds);
  const bbox = `[${bounds.west},${bounds.south},${bounds.east},${bounds.north}]`;
  const normalizedStylePath = stylePath.replace(/^mapbox:\/\/styles\//, "").replace(/^\/+|\/+$/g, "");
  const params = new URLSearchParams({
    access_token: token,
    attribution: "false",
    logo: "false",
  });

  return `https://api.mapbox.com/styles/v1/${normalizedStylePath}/static/${bbox}/${width}x${height}@2x?${params.toString()}`;
}

function normalizedMercatorX(lng: number) {
  return (lng + 180) / 360;
}

function normalizedMercatorYForTexture(lat: number) {
  const clampedLat = Math.min(Math.max(lat, -85.05112878), 85.05112878);
  return (1 - Math.log(Math.tan(Math.PI / 4 + (clampedLat * Math.PI) / 360)) / Math.PI) / 2;
}

function chooseEsriTextureZoom(bounds: TerrainBlockData["bounds"], targetWidth: number, targetHeight: number) {
  const westX = normalizedMercatorX(bounds.west);
  const eastX = normalizedMercatorX(bounds.east);
  const northY = normalizedMercatorYForTexture(bounds.north);
  const southY = normalizedMercatorYForTexture(bounds.south);
  const xSpan = Math.max(eastX - westX, 0.000001);
  const ySpan = Math.max(southY - northY, 0.000001);
  const requiredScale = Math.max(targetWidth / xSpan, targetHeight / ySpan);
  return clamp(Math.ceil(Math.log2(requiredScale / 256)), minEsriTextureZoom, maxEsriTextureZoom);
}

function loadImage(url: string) {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = url;
  });
}

async function buildEsriImageryTextureDataUrl(bounds: TerrainBlockData["bounds"]) {
  const { width, height } = getSatelliteTextureSize(bounds);
  const zoom = chooseEsriTextureZoom(bounds, width, height);
  const tileCount = 2 ** zoom;
  const westWorld = normalizedMercatorX(bounds.west) * tileCount;
  const eastWorld = normalizedMercatorX(bounds.east) * tileCount;
  const northWorld = normalizedMercatorYForTexture(bounds.north) * tileCount;
  const southWorld = normalizedMercatorYForTexture(bounds.south) * tileCount;
  const minTileX = Math.floor(westWorld);
  const maxTileX = Math.ceil(eastWorld) - 1;
  const minTileY = Math.floor(northWorld);
  const maxTileY = Math.ceil(southWorld) - 1;
  const mosaicWidth = Math.max((maxTileX - minTileX + 1) * esriTileSize, esriTileSize);
  const mosaicHeight = Math.max((maxTileY - minTileY + 1) * esriTileSize, esriTileSize);
  const mosaicCanvas = document.createElement("canvas");
  mosaicCanvas.width = mosaicWidth;
  mosaicCanvas.height = mosaicHeight;
  const mosaicContext = mosaicCanvas.getContext("2d");
  if (!mosaicContext) return undefined;

  mosaicContext.fillStyle = "#d8e0d2";
  mosaicContext.fillRect(0, 0, mosaicWidth, mosaicHeight);
  mosaicContext.imageSmoothingEnabled = false;

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return undefined;

  context.fillStyle = "#d8e0d2";
  context.fillRect(0, 0, width, height);

  const tileJobs: Promise<void>[] = [];

  for (let tileX = minTileX; tileX <= maxTileX; tileX++) {
    for (let tileY = minTileY; tileY <= maxTileY; tileY++) {
      const wrappedX = ((tileX % tileCount) + tileCount) % tileCount;
      if (tileY < 0 || tileY >= tileCount) continue;

      const url = esriImageryTileUrl
        .replace("{z}", String(zoom))
        .replace("{y}", String(tileY))
        .replace("{x}", String(wrappedX));

      tileJobs.push(loadImage(url).then((image) => {
        const left = (tileX - minTileX) * esriTileSize;
        const top = (tileY - minTileY) * esriTileSize;
        mosaicContext.drawImage(image, left, top, esriTileSize, esriTileSize);
      }).catch(() => undefined));
    }
  }

  await Promise.all(tileJobs);

  const sourceX = (westWorld - minTileX) * esriTileSize;
  const sourceY = (northWorld - minTileY) * esriTileSize;
  const sourceWidth = Math.min(Math.max((eastWorld - westWorld) * esriTileSize, 1), mosaicWidth - sourceX);
  const sourceHeight = Math.min(Math.max((southWorld - northWorld) * esriTileSize, 1), mosaicHeight - sourceY);
  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.drawImage(
    mosaicCanvas,
    sourceX,
    sourceY,
    sourceWidth,
    sourceHeight,
    0,
    0,
    width,
    height,
  );

  try {
    return canvas.toDataURL("image/png");
  } catch {
    return undefined;
  }
}

function getRandomChinaStartView() {
  const [lng, lat] = chinaStartCenters[Math.floor(Math.random() * chinaStartCenters.length)];
  const lngJitter = (Math.random() - 0.5) * 0.7;
  const latJitter = (Math.random() - 0.5) * 0.5;

  return {
    center: [lng + lngJitter, lat + latJitter] as [number, number],
    zoom: 8.8 + Math.random() * 2.2,
  };
}

function toLngLatLine(geometry?: OverpassCoordinate[]) {
  return geometry
    ?.filter((point) => Number.isFinite(point.lon) && Number.isFinite(point.lat))
    .map((point): [number, number] => [point.lon, point.lat]) ?? [];
}

function closeRing(line: Array<[number, number]>) {
  if (line.length < 3) return line;
  const first = line[0];
  const last = line[line.length - 1];
  if (first[0] === last[0] && first[1] === last[1]) return line;
  return [...line, first];
}

function isClosedLine(line: Array<[number, number]>) {
  if (line.length < 4) return false;
  const first = line[0];
  const last = line[line.length - 1];
  return first[0] === last[0] && first[1] === last[1];
}

function overpassElementToWaterFeature(element: OverpassElement): TerrainWaterFeature | null {
  if (element.type !== "way") return null;

  const line = toLngLatLine(element.geometry);
  if (line.length < 2) return null;

  if (isClosedLine(line)) {
    const ring = closeRing(line);
    return ring.length >= 4
      ? { source: "osm", geometry: { type: "Polygon", coordinates: [ring] } }
      : null;
  }

  return { source: "osm", geometry: { type: "LineString", coordinates: line } };
}

async function fetchOsmWaterFeatures(bounds: TerrainBlockData["bounds"]): Promise<TerrainWaterFeature[]> {
  const bbox = `${bounds.south},${bounds.west},${bounds.north},${bounds.east}`;
  const query = `
    [out:json][timeout:18];
    (
      way["natural"="water"](${bbox});
      way["landuse"="reservoir"](${bbox});
      way["landuse"="basin"](${bbox});
      way["water"](${bbox});
      way["waterway"~"river|stream|canal|ditch"](${bbox});
    );
    out geom;
  `;
  const endpoints = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
  ];

  for (const endpoint of endpoints) {
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "text/plain;charset=UTF-8" },
        body: query,
      });
      if (!response.ok) continue;

      const data = await response.json() as OverpassResponse;
      const seen = new Set<string>();
      return (data.elements ?? []).reduce<TerrainWaterFeature[]>((features, element) => {
        const feature = overpassElementToWaterFeature(element);
        if (!feature) return features;

        const key = `${element.type}:${element.id}`;
        if (seen.has(key)) return features;
        seen.add(key);
        features.push(feature);
        return features;
      }, []);
    } catch {
      // Try the next public Overpass mirror.
    }
  }

  return [];
}

export default function MapSelector() {
  const [isDrawing, setIsDrawing] = useState(false);
  const [isSelectingBlock, setIsSelectingBlock] = useState(false);
  const [hasDrawnLine, setHasDrawnLine] = useState(false);
  const [hasProfile, setHasProfile] = useState(false);
  const [isEstimating, setIsEstimating] = useState(false);
  const [isRenderingBlock, setIsRenderingBlock] = useState(false);
  const [terrainBlock, setTerrainBlock] = useState<TerrainBlockData | null>(null);
  const [profileHeight, setProfileHeight] = useState<number | null>(null);
  const [showContours, setShowContours] = useState(false);
  const d3Container = useRef<SVGSVGElement>(null);
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<mapboxgl.Map | null>(null);
  const draw = useRef<MapboxDraw | null>(null);
  const rectangleStart = useRef<mapboxgl.LngLat | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const draggingDivider = useRef(false);

  useEffect(() => {
    const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;
    if (!token || !mapContainer.current || map.current) return;

    mapboxgl.accessToken = token;
    const startView = getRandomChinaStartView();

    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: "mapbox://styles/mapbox/outdoors-v12",
      center: startView.center,
      zoom: startView.zoom,
    });

    map.current.addControl(new mapboxgl.NavigationControl(), "top-right");

    draw.current = new MapboxDraw({
      displayControlsDefault: false,
      controls: {
        line_string: true,
        trash: true
      },
      defaultMode: 'simple_select',
      styles: [
        {
          id: 'gl-draw-line',
          type: 'line',
          filter: ['all', ['==', '$type', 'LineString'], ['!=', 'mode', 'static']],
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': '#003153', 'line-dasharray': [0.2, 2], 'line-width': 4 }
        },
        {
          id: 'gl-draw-line-static',
          type: 'line',
          filter: ['all', ['==', '$type', 'LineString'], ['==', 'mode', 'static']],
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': '#003153', 'line-width': 4 }
        },
        {
          id: 'gl-draw-point',
          type: 'circle',
          filter: ['all', ['==', '$type', 'Point'], ['!=', 'meta', 'midpoint']],
          paint: { 'circle-radius': 6, 'circle-color': '#003153', 'circle-stroke-width': 2, 'circle-stroke-color': '#fff' }
        },
        {
          id: 'gl-draw-polygon-and-line-vertex-halo-active',
          type: 'circle',
          filter: ['all', ['==', 'meta', 'vertex'], ['==', '$type', 'Point'], ['!=', 'mode', 'static']],
          paint: { 'circle-radius': 8, 'circle-color': '#FFF' }
        },
        {
          id: 'gl-draw-polygon-and-line-vertex-active',
          type: 'circle',
          filter: ['all', ['==', 'meta', 'vertex'], ['==', '$type', 'Point'], ['!=', 'mode', 'static']],
          paint: { 'circle-radius': 6, 'circle-color': '#003153' }
        }
      ]
    });

    map.current.addControl(draw.current);

    map.current.on('load', () => {
      const mapInstance = map.current!;
      mapInstance.addSource('mapbox-dem', {
        'type': 'raster-dem',
        'url': 'mapbox://mapbox.mapbox-terrain-dem-v1',
        'tileSize': 512,
        'maxzoom': 14
      });
      mapInstance.setTerrain({ 'source': 'mapbox-dem', 'exaggeration': 1 });

      // Mapbox Terrain v2 矢量等高线（默认隐藏，由「等高线」开关控制）
      mapInstance.addSource('contour-terrain', {
        type: 'vector',
        url: 'mapbox://mapbox.mapbox-terrain-v2',
      });
      // 首曲线（全部等高线）
      mapInstance.addLayer({
        id: 'contour-lines',
        type: 'line',
        source: 'contour-terrain',
        'source-layer': 'contour',
        layout: { visibility: 'none', 'line-join': 'round', 'line-cap': 'round' },
        paint: {
          'line-color': '#8a5a2b',
          'line-width': ['interpolate', ['linear'], ['zoom'], 11, 0.4, 16, 1.0],
          'line-opacity': 0.5,
        },
      });
      // 计曲线（每 5 条加粗：index >= 5）
      mapInstance.addLayer({
        id: 'contour-index',
        type: 'line',
        source: 'contour-terrain',
        'source-layer': 'contour',
        filter: ['>=', ['get', 'index'], 5],
        layout: { visibility: 'none', 'line-join': 'round', 'line-cap': 'round' },
        paint: {
          'line-color': '#6b3f1d',
          'line-width': ['interpolate', ['linear'], ['zoom'], 11, 0.9, 16, 2.0],
          'line-opacity': 0.85,
        },
      });
      // 计曲线上的高程标注（ele 字段，米）
      mapInstance.addLayer({
        id: 'contour-labels',
        type: 'symbol',
        source: 'contour-terrain',
        'source-layer': 'contour',
        filter: ['>=', ['get', 'index'], 5],
        layout: {
          visibility: 'none',
          'symbol-placement': 'line',
          'text-field': ['concat', ['to-string', ['get', 'ele']], ' m'],
          'text-size': 11,
          'text-font': ['DIN Offc Pro Medium', 'Arial Unicode MS Regular'],
          'symbol-spacing': 300,
        },
        paint: {
          'text-color': '#5a3416',
          'text-halo-color': '#ffffff',
          'text-halo-width': 1.4,
        },
      });
    });

    return () => {
      if (map.current) {
        map.current.remove();
        map.current = null;
      }
    };
  }, []);

  // 切换 Mapbox 矢量等高线图层的显隐
  useEffect(() => {
    const mapInstance = map.current;
    if (!mapInstance) return;
    const apply = () => {
      const visibility = showContours ? "visible" : "none";
      ["contour-lines", "contour-index", "contour-labels"].forEach((id) => {
        if (mapInstance.getLayer(id)) mapInstance.setLayoutProperty(id, "visibility", visibility);
      });
    };
    if (mapInstance.isStyleLoaded() && mapInstance.getLayer("contour-lines")) {
      apply();
    } else {
      mapInstance.once("idle", apply);
    }
  }, [showContours]);

  useEffect(() => {
    if (!draw.current || !map.current) return;

    if (isDrawing) {
      draw.current.deleteAll(); // Clear previous line
      draw.current.changeMode("draw_line_string");
    } else {
      draw.current.changeMode("simple_select");
    }

    const handleMapClick = () => {
      if (!isDrawing || !draw.current) return;
      const features = draw.current.getAll().features;
      if (features.length > 0) {
        const activeFeature = features[0];
        if (activeFeature.geometry.type === 'LineString') {
          // In draw_line_string mode, the array contains clicked points + cursor position.
          // When user clicks the 2nd point, the array has [start, end, cursor].
          if (activeFeature.geometry.coordinates.length >= 3) {
            const coords = activeFeature.geometry.coordinates.slice(0, 2);
            activeFeature.geometry.coordinates = coords;
            draw.current.add(activeFeature);
            draw.current.changeMode('simple_select');
            setIsDrawing(false);
            setHasDrawnLine(true);
          }
        }
      }
    };

    map.current.on('click', handleMapClick);

    return () => {
      if (map.current) {
        map.current.off('click', handleMapClick);
      }
    };
  }, [isDrawing]);

  const ensureSelectionLayers = useCallback(() => {
    if (!map.current || !map.current.isStyleLoaded()) return false;

    if (!map.current.getSource(selectionSourceId)) {
      map.current.addSource(selectionSourceId, {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: [],
        },
      });
    }

    if (!map.current.getLayer(selectionFillLayerId)) {
      map.current.addLayer({
        id: selectionFillLayerId,
        type: "fill",
        source: selectionSourceId,
        paint: {
          "fill-color": "#38bdf8",
          "fill-opacity": 0.22,
        },
      });
    }

    if (!map.current.getLayer(selectionOutlineLayerId)) {
      map.current.addLayer({
        id: selectionOutlineLayerId,
        type: "line",
        source: selectionSourceId,
        paint: {
          "line-color": "#0f172a",
          "line-width": 2,
          "line-dasharray": [1.5, 1],
        },
      });
    }

    return true;
  }, []);

  const updateSelectionRectangle = useCallback((feature: Feature<Polygon>) => {
    if (!map.current) return;
    const source = map.current.getSource(selectionSourceId) as mapboxgl.GeoJSONSource | undefined;
    source?.setData(feature);
  }, []);

  const inferTerrainLayers = useCallback(async (lat: number, lng: number): Promise<TerrainLayer[]> => {
    // ① 优先取 Macrostrat 真实地层柱（/units）——北美等覆盖区会得到详细的命名地层序列
    try {
      const columnResponse = await fetch(
        `https://macrostrat.org/api/v2/units?lat=${lat}&lng=${lng}&response=long`,
      );
      const columnData = await columnResponse.json();
      const columnUnits = columnData?.success?.data as MacrostratColumnUnit[] | undefined;
      const realLayers = buildLayersFromUnits(columnUnits ?? []);
      if (realLayers) return realLayers;
    } catch {
      // 忽略，转入 /map 推断兜底
    }
    // ② 无真实地层柱（如中国）→ 用地表单元推断 4 层模板
    try {
      const response = await fetch(`https://macrostrat.org/api/v2/geologic_units/map?lat=${lat}&lng=${lng}`);
      const data = await response.json();
      const units = data?.success?.data as MacrostratUnit[] | undefined;
      const unit = units?.[0];
      if (!unit) return defaultTerrainLayers;

      const lith = (unit.lith || "").toLowerCase();
      if (lith.includes("limestone") || lith.includes("carbonate")) {
        return [
          { name: "碳酸盐盖层", color: unit.color || "#a9c2b8", textureFile: "legend_23_clayey_or_argillaceous_limestone.png" },
          { name: "厚层灰岩", color: "#8ca7a0", textureFile: "legend_15_massively_bedded_limestone.png" },
          { name: "泥质夹层", color: "#7c6f62", textureFile: "legend_24_calcareous_shale_or_shaly_limestone.png" },
          { name: "结晶基底", color: "#6f5f7f", textureFile: "legend_45_gneiss.png" },
        ];
      }
      if (lith.includes("granite") || lith.includes("intrusive") || lith.includes("plutonic")) {
        return [
          { name: "风化壳", color: "#c7a76f", textureFile: "legend_01_soil_silt_or_alluvium.png" },
          { name: "花岗质侵入体", color: unit.color || "#c77878", textureFile: "legend_55_granite.png" },
          { name: "接触变质带", color: "#815f75", textureFile: "legend_43_metamorphism.png" },
          { name: "深部基底", color: "#51475f", textureFile: "legend_45_gneiss.png" },
        ];
      }
      if (lith.includes("shale")) {
        return [
          { name: "松散覆盖层", color: "#d8c074", textureFile: "legend_01_soil_silt_or_alluvium.png" },
          { name: "页岩层", color: unit.color || "#6f756c", textureFile: "legend_25_shale.png" },
          { name: "砂岩夹层", color: "#b87943", textureFile: "legend_12_thin_bedded_or_shaly_sandstone.png" },
          { name: "老地层基底", color: "#6f5f7f", textureFile: "legend_45_gneiss.png" },
        ];
      }
      return [
        { name: localizeGeologicName(unit.best_int_name), color: unit.color || "#d8c074", textureFile: "legend_01_soil_silt_or_alluvium.png" },
        ...defaultTerrainLayers.slice(1),
      ];
    } catch {
      return defaultTerrainLayers;
    }
  }, []);

  const buildTerrainBlock = useCallback(async (start: mapboxgl.LngLat, end: mapboxgl.LngLat) => {
    if (!map.current) return;

    setIsRenderingBlock(true);
    setHasProfile(false);
    setTerrainBlock(null);

    const west = Math.min(start.lng, end.lng);
    const east = Math.max(start.lng, end.lng);
    const south = Math.min(start.lat, end.lat);
    const north = Math.max(start.lat, end.lat);
    const bounds = { west, south, east, north };
    const rows = 34;
    const cols = 34;
    const elevations: number[][] = [];
    let minElevation = Number.POSITIVE_INFINITY;
    let maxElevation = Number.NEGATIVE_INFINITY;

    for (let row = 0; row < rows; row++) {
      const lat = north - ((north - south) * row) / (rows - 1);
      const line: number[] = [];
      for (let col = 0; col < cols; col++) {
        const lng = west + ((east - west) * col) / (cols - 1);
        const queriedElevation = map.current.queryTerrainElevation([lng, lat]);
        const fallbackRelief = Math.sin(row * 0.35) * 60 + Math.cos(col * 0.27) * 45;
        const elevation = typeof queriedElevation === "number" ? queriedElevation : fallbackRelief;
        line.push(elevation);
        minElevation = Math.min(minElevation, elevation);
        maxElevation = Math.max(maxElevation, elevation);
      }
      elevations.push(line);
    }

    if (maxElevation - minElevation < 1) {
      elevations.forEach((line, row) => {
        line.forEach((_, col) => {
          const relief = Math.sin(row * 0.35) * 60 + Math.cos(col * 0.27) * 45;
          elevations[row][col] = relief;
          minElevation = Math.min(minElevation, relief);
          maxElevation = Math.max(maxElevation, relief);
        });
      });
    }

    const midLat = (south + north) / 2;
    const midLng = (west + east) / 2;
    const [layers, waterFeatures] = await Promise.all([
      inferTerrainLayers(midLat, midLng),
      fetchOsmWaterFeatures(bounds),
    ]);
    const mapboxSurfaceTextureUrl = buildMapboxStaticTextureUrl(
      bounds,
      process.env.NEXT_PUBLIC_MAPBOX_TOKEN,
      process.env.NEXT_PUBLIC_MAPBOX_SURFACE_STYLE,
    );
    const gridBaseTextureUrl = buildMapboxStaticTextureUrl(
      bounds,
      process.env.NEXT_PUBLIC_MAPBOX_TOKEN,
      defaultGridBaseTextureStyle,
    );
    const esriSurfaceTextureUrl = await buildEsriImageryTextureDataUrl(bounds);
    const gridBaseTexture = gridBaseTextureUrl ? {
      id: "mapbox-outdoors-grid-base",
      label: "Mapbox 地图",
      url: gridBaseTextureUrl,
      attribution: "© Mapbox © OpenStreetMap",
      provider: "mapbox" as const,
    } : undefined;
    const surfaceTextures: SurfaceTextureOption[] = [
      ...(esriSurfaceTextureUrl ? [{
        id: "esri",
        label: "Esri",
        url: esriSurfaceTextureUrl,
        attribution: "Esri, Maxar, Earthstar Geographics, and the GIS User Community",
        provider: "esri" as const,
      }] : []),
      ...(mapboxSurfaceTextureUrl ? [{
        id: "mapbox",
        label: "Mapbox",
        url: mapboxSurfaceTextureUrl,
        attribution: "© Mapbox © OpenStreetMap © Maxar",
        provider: "mapbox" as const,
      }] : []),
    ];
    const defaultSurfaceTexture = surfaceTextures[0];

    setTerrainBlock({
      elevations,
      bounds,
      minElevation,
      maxElevation,
      layers,
      surfaceTextureUrl: defaultSurfaceTexture?.url,
      surfaceTextureLabel: defaultSurfaceTexture ? "地表卫星贴图" : undefined,
      surfaceAttribution: defaultSurfaceTexture?.attribution,
      surfaceTextures,
      gridBaseTexture,
      waterFeatures,
    });
    setIsRenderingBlock(false);
  }, [inferTerrainLayers]);

  useEffect(() => {
    if (!map.current) return;
    const currentMap = map.current;

    if (!isSelectingBlock) {
      setMapCursor(currentMap, "");
      return;
    }

    draw.current?.changeMode("simple_select");
    setMapCursor(currentMap, "crosshair");

    const handleMouseDown = (event: mapboxgl.MapMouseEvent) => {
      if (!ensureSelectionLayers()) return;
      rectangleStart.current = event.lngLat;
      currentMap.dragPan.disable();
      updateSelectionRectangle(createSelectionFeature(event.lngLat, event.lngLat));
    };

    const handleMouseMove = (event: mapboxgl.MapMouseEvent) => {
      if (!rectangleStart.current) return;
      updateSelectionRectangle(createSelectionFeature(rectangleStart.current, event.lngLat));
    };

    const handleMouseUp = (event: mapboxgl.MapMouseEvent) => {
      if (!rectangleStart.current) return;
      const start = rectangleStart.current;
      rectangleStart.current = null;
      currentMap.dragPan.enable();
      setMapCursor(currentMap, "");
      setIsSelectingBlock(false);
      updateSelectionRectangle(createSelectionFeature(start, event.lngLat));
      void buildTerrainBlock(start, event.lngLat);
    };

    currentMap.on("mousedown", handleMouseDown);
    currentMap.on("mousemove", handleMouseMove);
    currentMap.on("mouseup", handleMouseUp);

    return () => {
      currentMap.off("mousedown", handleMouseDown);
      currentMap.off("mousemove", handleMouseMove);
      currentMap.off("mouseup", handleMouseUp);
      currentMap.dragPan.enable();
      setMapCursor(currentMap, "");
    };
  }, [buildTerrainBlock, ensureSelectionLayers, isSelectingBlock, updateSelectionRectangle]);

  const generateProfile = async () => {
    setIsDrawing(false);
    setTerrainBlock(null);
    setIsEstimating(true);

    const elevationData: number[] = [];
    let geologicUnits: MacrostratUnit[] = [];

    if (draw.current && map.current) {
      const features = draw.current.getAll().features;
      if (features.length > 0 && features[0].geometry.type === 'LineString') {
        const coords = features[0].geometry.coordinates;
        const start = coords[0];
        const end = coords[coords.length - 1];

        const numPoints = 60;
        for (let i = 0; i <= numPoints; i++) {
          const t = i / numPoints;
          const lng = start[0] + (end[0] - start[0]) * t;
          const lat = start[1] + (end[1] - start[1]) * t;
          const elevation = map.current.queryTerrainElevation([lng, lat]) || 0;
          elevationData.push(elevation);
        }

        try {
          const midLng = (start[0] + end[0]) / 2;
          const midLat = (start[1] + end[1]) / 2;
          const response = await fetch(`https://macrostrat.org/api/v2/geologic_units/map?lat=${midLat}&lng=${midLng}`);
          const data = await response.json();
          if (data && data.success && data.success.data) {
            geologicUnits = data.success.data;
          }
        } catch (e) {
          console.error("Failed to fetch macrostrat data", e);
        }
      }
    }

    setTimeout(() => {
      setIsEstimating(false);
      setHasProfile(true);
      renderD3Profile(elevationData, geologicUnits);
    }, 500); // Shorter timeout since fetch already took time
  };

  const renderD3Profile = (elevations: number[] = [], geologicUnits: MacrostratUnit[] = []) => {
    if (!d3Container.current) return;

    const svg = d3.select(d3Container.current);
    svg.selectAll("*").remove();

    const width = 800;
    const height = 350;

    svg.attr("viewBox", `0 0 ${width} ${height}`);

    // Create a beautiful border/background
    svg.append("rect")
      .attr("width", width)
      .attr("height", height)
      .attr("fill", "#f8f9fa")
      .attr("stroke", "#333")
      .attr("stroke-width", 2);

    // Dynamic Geological structural data points
    let topoPoints: { x: number, y: number }[] = [];

    if (elevations && elevations.length > 0) {
      const validElevs = elevations.filter(e => e > 0);
      const minElev = validElevs.length > 0 ? Math.min(...validElevs) : 0;
      const maxElev = validElevs.length > 0 ? Math.max(...validElevs) : 100;
      const elevRange = Math.max(maxElev - minElev, 1);

      topoPoints = elevations.map((elev, i) => {
        const x = (i / (elevations.length - 1)) * width;
        // Project elevation to Y coordinates (SVG y goes down, so max elev is smaller y)
        // Ensure minimum elevation maps to y=140, maximum to y=40
        const y = elev > 0 ? 140 - ((elev - minElev) / elevRange) * 100 : 100;
        return { x, y };
      });
    } else {
      const pts = [0, 100, 250, 400, 550, 700, 800];
      const topo = [70, 50, 110, 80, 130, 70, 80];
      topoPoints = pts.map((x, i) => ({ x, y: topo[i] }));
    }

    // Generate layers that follow topography with tectonic folding
    const layer1Data = topoPoints.map(p => {
      const foldOffset = Math.sin(p.x / 100) * 20;
      return { x: p.x, y0: p.y + 70 + foldOffset, y1: p.y };
    });

    const layer2Data = topoPoints.map(p => {
      const foldOffset = Math.sin(p.x / 100) * 20;
      const foldOffset2 = Math.sin(p.x / 130 + 1) * 35;
      return { x: p.x, y0: p.y + 150 + foldOffset2, y1: p.y + 70 + foldOffset };
    });

    const layer3Data = topoPoints.map(p => {
      const foldOffset2 = Math.sin(p.x / 130 + 1) * 35;
      const foldOffset3 = Math.sin(p.x / 160 + 2) * 50;
      return { x: p.x, y0: p.y + 240 + foldOffset3, y1: p.y + 150 + foldOffset2 };
    });

    const layer4Data = topoPoints.map(p => {
      const foldOffset3 = Math.sin(p.x / 160 + 2) * 50;
      return { x: p.x, y0: height + 50, y1: p.y + 240 + foldOffset3 };
    });

    const areaGen = d3.area<{ x: number, y0: number, y1: number }>()
      .x(d => d.x)
      .y0(d => d.y0)
      .y1(d => d.y1)
      .curve(d3.curveCatmullRom.alpha(0.5));

    const drawLayer = (data: { x: number, y0: number, y1: number }[], color: string, pattern: string) => {
      const g = svg.append("g");

      // Color fill
      g.append("path")
        .datum(data)
        .attr("d", areaGen)
        .attr("fill", color)
        .attr("stroke", "#222")
        .attr("stroke-width", 1.5);

      // Pattern overlay
      g.append("path")
        .datum(data)
        .attr("d", areaGen)
        .attr("fill", `url(#${pattern})`)
        .style("mix-blend-mode", "multiply")
        .style("opacity", 0.7);
    };

    const getLayerInfo = (index: number) => {
      // Top layer from real API data
      if (geologicUnits && geologicUnits.length > 0 && index === 0) {
        const unit = geologicUnits[0];
        const ageName = localizeGeologicName(unit.best_int_name);
        const lith = (unit.lith || "").toLowerCase();
        let lithName = "岩层";
        let pattern = "pattern-1";

        if (lith.includes("metamorphic") || lith.includes("gneiss") || lith.includes("schist")) {
          lithName = "变质岩/片麻岩"; pattern = "pattern-73"; // Metamorphic
        } else if (lith.includes("granite") || lith.includes("intrusive") || lith.includes("plutonic")) {
          lithName = "侵入花岗岩"; pattern = "pattern-61";
        } else if (lith.includes("limestone") || lith.includes("carbonate")) {
          lithName = "灰岩"; pattern = "pattern-15";
        } else if (lith.includes("sandstone")) {
          lithName = "砂岩"; pattern = "pattern-8";
        } else if (lith.includes("shale")) {
          lithName = "页岩"; pattern = "pattern-25";
        } else if (lith.includes("volcanic") || lith.includes("basalt")) {
          lithName = "火山岩"; pattern = "pattern-63";
        }

        return { name: `${ageName} (${lithName})`, color: unit.color || "#999966", pattern };
      }

      // If we used the API for layer 0, generate logical older layers below it
      if (geologicUnits && geologicUnits.length > 0) {
        if (index === 1) return { name: "太古代 (混合岩带)", color: "#FF8099", pattern: "pattern-71" };
        if (index === 2) return { name: "前寒武纪 (结晶基底)", color: "#999966", pattern: "pattern-73" };
        if (index === 3) return { name: "深部侵入岩体", color: "#FF6666", pattern: "pattern-61" };
      }

      // Fallback mock data
      const defaults = [
        { name: "第四纪 (土壤、粉砂或冲积物)", color: fallbackAgeColors.quaternary, pattern: "pattern-1" },
        { name: "白垩纪 (厚层灰岩)", color: fallbackAgeColors.cretaceous, pattern: "pattern-15" },
        { name: "侏罗纪 (页岩)", color: fallbackAgeColors.jurassic, pattern: "pattern-25" },
        { name: "三叠纪 (块状砂岩)", color: fallbackAgeColors.triassic, pattern: "pattern-8" }
      ];
      return defaults[index] || defaults[0];
    };

    const l1Info = getLayerInfo(0);
    const l2Info = getLayerInfo(1);
    const l3Info = getLayerInfo(2);
    const l4Info = getLayerInfo(3);

    // Draw layers
    drawLayer(layer1Data, l1Info.color, l1Info.pattern);
    drawLayer(layer2Data, l2Info.color, l2Info.pattern);
    drawLayer(layer3Data, l3Info.color, l3Info.pattern);
    drawLayer(layer4Data, l4Info.color, l4Info.pattern);


    // Helper for labels with backgrounds
    const addLabel = (x: number, y: number, text: string) => {
      const g = svg.append("g").attr("transform", `translate(${x}, ${y})`);
      const estWidth = text.length * 13 * 0.8 + 16;

      g.append("rect")
        .attr("x", -estWidth / 2)
        .attr("y", -14)
        .attr("width", estWidth)
        .attr("height", 28)
        .attr("fill", "rgba(255, 255, 255, 0.85)")
        .attr("rx", 14)
        .attr("ry", 14)
        .attr("stroke", "rgba(0,0,0,0.15)")
        .attr("stroke-width", 1);

      g.append("text")
        .text(text)
        .attr("fill", "#111")
        .attr("font-size", 13)
        .attr("font-weight", 600)
        .attr("text-anchor", "middle")
        .attr("dominant-baseline", "middle")
        .attr("y", 1);
    };

    // Add Labels using dynamic names
    addLabel(500, 90, l1Info.name);
    addLabel(500, 180, l2Info.name);
    addLabel(500, 260, l3Info.name);
    addLabel(500, 320, l4Info.name);
  };

  const profileOpen = hasProfile || isEstimating || Boolean(terrainBlock) || isRenderingBlock;

  const handleDividerDown = useCallback((event: React.PointerEvent) => {
    event.preventDefault();
    draggingDivider.current = true;
    document.body.style.userSelect = "none";
    document.body.style.cursor = "row-resize";

    function onMove(e: PointerEvent) {
      if (!draggingDivider.current || !containerRef.current) return;
      // 距底部高度 = 下视窗高度；夹在合理范围，避免拖到看不见
      const rect = containerRef.current.getBoundingClientRect();
      const next = clamp(rect.bottom - e.clientY, 160, rect.height - 140);
      setProfileHeight(next);
      map.current?.resize();
    }
    function onUp() {
      draggingDivider.current = false;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      map.current?.resize();
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }, []);

  return (
    <div className={styles.container} ref={containerRef}>
      {/* Top Map Section */}
      <div className={styles.mapArea}>
        <div className={styles.mapOverlay}>
          <div className={styles.mapControls}>
            <button
              className={`${styles.controlBtn} ${isDrawing ? styles.active : ""}`}
              onClick={() => {
                setIsSelectingBlock(false);
                setIsDrawing(!isDrawing);
                if (!isDrawing) setHasDrawnLine(false);
              }}
            >
              <PenTool size={16} /> 绘制剖面线
            </button>
            <button
              className={`${styles.controlBtn} ${isSelectingBlock ? styles.active : ""}`}
              onClick={() => {
                setIsDrawing(false);
                setIsSelectingBlock(!isSelectingBlock);
              }}
            >
              <Square size={16} /> 框选 3D 地块
            </button>
            <button
              className={`${styles.controlBtn} ${showContours ? styles.active : ""}`}
              onClick={() => setShowContours((v) => !v)}
            >
              <MapIcon size={16} /> 等高线
            </button>
            {(isDrawing || hasDrawnLine) && (
              <button className={styles.actionBtn} onClick={generateProfile}>
                生成地质剖面
              </button>
            )}
          </div>

          {!process.env.NEXT_PUBLIC_MAPBOX_TOKEN && (
            <div className={styles.mapPlaceholder}>
              <MapIcon size={48} className={styles.mapIcon} />
              <h3>Mapbox GL JS 模块</h3>
              <p>请在 .env.local 中配置 NEXT_PUBLIC_MAPBOX_TOKEN</p>
              {isDrawing && <div className={styles.drawingHint}>在地图上点击绘制 A-B 剖面线...</div>}
              {isSelectingBlock && <div className={styles.drawingHint}>按住鼠标拖出 3D 地块范围...</div>}
            </div>
          )}
        </div>

        {/* Actual Map Container */}
        <div ref={mapContainer} style={{ width: "100%", height: "100%" }} />
      </div>

      {/* Draggable divider between the map and the profile/3D viewport */}
      {profileOpen && (
        <div
          className={styles.dragDivider}
          role="separator"
          aria-orientation="horizontal"
          title="拖动调整上下视窗大小"
          onPointerDown={handleDividerDown}
          onDoubleClick={() => setProfileHeight(null)}
        />
      )}

      {/* Bottom Profile Section */}
      <div
        className={`${styles.profileArea} ${profileOpen ? styles.open : ""}`}
        style={profileOpen && profileHeight != null ? { height: profileHeight, transition: "none" } : undefined}
      >
        <div className={styles.profileHeader}>
          <h3>{terrainBlock || isRenderingBlock ? "DEM + 地下岩层 3D 地块" : "AI 生成的地下地质剖面"}</h3>
          {hasProfile && (
            <button className={styles.exportBtn}>
              <Download size={14} /> 导出 SVG
            </button>
          )}
        </div>

        <div className={styles.profileContent}>
          {(isEstimating || isRenderingBlock) && (
            <div className={styles.loader}>
              <RefreshCw size={24} className={styles.spin} />
              {isRenderingBlock ? (
                <>
                  <span>正在采样 Mapbox DEM...</span>
                  <span>正在构建 3D 地形块和地下岩层...</span>
                </>
              ) : (
                <>
                  <span>正在获取 Macrostrat 地层柱状数据...</span>
                  <span>正在运行 AI 地下结构推演...</span>
                </>
              )}
            </div>
          )}

          {terrainBlock && !isRenderingBlock && (
            <TerrainBlock3D data={terrainBlock} />
          )}

          <svg
            ref={d3Container}
            className={styles.d3Svg}
            style={{ display: hasProfile && !isEstimating && !terrainBlock ? "block" : "none" }}
          />
        </div>
      </div>
    </div>
  );
}
