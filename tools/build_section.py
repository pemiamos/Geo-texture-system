#!/usr/bin/env python3
"""生成长白山地质图预览 + 天池地质剖面 (自包含 HTML)"""
import json, math, os
import geopandas as gpd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data', 'changbaishan')

A, B = (127.55, 41.60), (128.45, 42.33)
KM = 110.3

# ---- 高程 (SRTM90, opentopodata, 93点, 与 ts 一一对应) ----
ELEV = [906,850,930,937,965,963,978,980,1014,1020,1115,1146,1230,1214,1296,
        1340,1368,1193,1376,1374,1284,1151,1302,1250,1120,1259,1280,1289,1318,1338,
        1383,1414,1436,1450,1476,1514,1538,1577,1628,1666,1704,1749,1842,1921,1999,
        2317,2472,2284,2188,2188,2188,2188,2375,2574,2300,2165,2036,1943,1878,1780,
        1739,1709,1681,1643,1590,1529,1477,1454,1438,1408,1378,1339,1325,1313,1286,
        1246,1219,1188,1190,1164,1195,1153,1244,1119,1022,975,1002,969,1098,1051,
        856,771,704]
ts = [i/29*0.42 for i in range(30)] + [0.42+i/44*0.30 for i in range(45)] + [0.72+i/19*0.28 for i in range(20)]
TS = sorted(set(round(t,5) for t in ts))
assert len(TS) == len(ELEV), (len(TS), len(ELEV))

# ---- 剖面分段 ----
from shapely.geometry import LineString, Point
g = gpd.read_file(os.path.join(DATA, 'changbaishan_geology.geojson'))
line = LineString([A, B])
L = line.length
segs = []
for _, row in g[g.intersects(line)].iterrows():
    inter = row.geometry.intersection(line)
    for s in getattr(inter, 'geoms', [inter]):
        if s.geom_type == 'LineString' and s.length > 1e-5:
            d0 = line.project(Point(s.coords[0])); d1 = line.project(Point(s.coords[-1]))
            segs.append([min(d0,d1)/L, max(d0,d1)/L, row['DSN'].strip(), (row['DSO_TXT'] or '').strip()])
segs.sort()
# 合并相邻同代号分段
merged = []
for s in segs:
    if merged and merged[-1][3] == s[3] and s[0] - merged[-1][1] < 0.004:
        merged[-1][1] = max(merged[-1][1], s[1])
    else:
        merged.append(list(s))
segs = merged

# ---- 地图用简化几何 ----
gs = g.copy()
gs['geometry'] = gs.geometry.simplify(0.0008, preserve_topology=True)
gs['DSN'] = gs['DSN'].str.strip()
gs['DSO_TXT'] = gs['DSO_TXT'].fillna('').str.strip()
gs = gs[['DSN', 'DSO_TXT', 'geometry']]
geo_json = gs.to_json(drop_id=True)
geo_json = json.dumps(json.loads(geo_json), ensure_ascii=False, separators=(',',':'))
# 坐标降精度
import re
geo_json = re.sub(r'(\d+\.\d{4})\d+', r'\1', geo_json)

f = gpd.read_file(os.path.join(DATA, 'changbaishan_faults.geojson'))
fs = f.copy()
fs['geometry'] = fs.geometry.simplify(0.0008, preserve_topology=True)
fault_json = fs[['geometry']].to_json(drop_id=True)
fault_json = re.sub(r'(\d+\.\d{4})\d+', r'\1', json.dumps(json.loads(fault_json), separators=(',',':')))

# ---- 岩层柱: 剖面单元按新老排序 ----
RANK = {  # 越小越新
    'Q4-3': 0, 'τQh': 1, 'τQ4': 2, 'τQp-2': 3, 'τQ2': 4,
    'βQ1': 5, 'βN2-Qp-1': 6, 'β-1+2': 6, 'β-2': 6, 'βN': 7,
}
EPOCH = {
    'Q4-3': '全新统', 'τQh': '全新统', 'τQ4': '全新统—晚更新统',
    'τQp-2': '中—晚更新统', 'τQ2': '中更新统', 'βQ1': '早更新统',
    'βN2-Qp-1': '上新统—早更新统', 'βN': '中新统—上新统',
}
LITH = {  # 岩性花纹类型
    'Q4-3': 'sed', 'τQh': 'ash', 'τQ4': 'tra', 'τQp-2': 'tra',
    'τQ2': 'tra', 'βQ1': 'bas', 'βN2-Qp-1': 'bas', 'βN': 'bas',
}
g['DSN'] = g['DSN'].str.strip()
g['DSO_TXT'] = g['DSO_TXT'].fillna('').str.strip()
g['QDFCF'] = g.get('QDFCF', '').astype(str).str.strip()
units = {}
for _, _, name, code in segs:
    if code in units:
        continue
    sub = g[g['DSO_TXT'] == code]
    ages = sorted(set(a for a in sub['QDFCF'] if a))
    units[code] = {
        'code': code, 'name': name,
        'age': ages[0] if ages else '',
        'epoch': EPOCH.get(code, ''), 'lith': LITH.get(code, 'sed'),
    }
unit_list = sorted(units.values(), key=lambda u: RANK.get(u['code'], 99))

payload = {
    'A': A, 'B': B, 'km': KM,
    'ts': TS, 'elev': ELEV,
    'segs': segs, 'units': unit_list,
}

html = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'section_template.html'), encoding='utf-8').read()
html = html.replace('/*__SECTION__*/', json.dumps(payload, ensure_ascii=False, separators=(',',':')))
html = html.replace('/*__GEOLOGY__*/', geo_json)
html = html.replace('/*__FAULTS__*/', fault_json)
out = os.path.join(DATA, 'changbaishan_section.html')
open(out, 'w', encoding='utf-8').write(html)
print('written', out, '%.1f KB' % (os.path.getsize(out)/1024))
