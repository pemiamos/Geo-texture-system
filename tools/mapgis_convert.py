#!/usr/bin/env python3
"""
MapGIS 6.x (.WP/.WL) -> GeoJSON (WGS84) 批量转换
数据源: 1:20万区域地质图空间数据库 (JWD 经纬度图层)
解析器: pymapgis (https://github.com/leecugb/pymapgis)

用法:
  python3 mapgis_convert.py <数据根目录> <输出目录> <图幅1> [图幅2 ...]

输出:
  <输出目录>/<区域>_geology.geojson  (D01D 地质体面, 合并)
  <输出目录>/<区域>_faults.geojson   (D08D 断层线, 合并)
"""
import sys, os, io, re, contextlib
import pandas as pd
import geopandas as gpd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pymapgis

WGS84 = "EPSG:4326"

# MapGIS 上下标记号 -> 纯文本 (Q↓4↑3 -> Q4-3)
def clean_code(s):
    if not isinstance(s, str):
        return s
    s = s.replace("→", "")
    s = re.sub(r"↓([^↑↓]*)", r"\1", s)
    s = re.sub(r"↑([^↑↓]*)", r"-\1", s)
    return s.strip().strip("-")


def read_layer(path):
    """解析单个 MapGIS 文件, 返回 WGS84 GeoDataFrame"""
    with contextlib.redirect_stdout(io.StringIO()):
        r = pymapgis.Reader(path)
    gdf = r.geodataframe.copy()
    sc = r.sc or 1.0
    gdf.geometry = gdf.geometry.affine_transform([1 / sc, 0, 0, 1 / sc, 0, 0])
    gdf = gdf.set_crs(r.crs, allow_override=True).to_crs(WGS84)
    # 修复自相交等无效几何; make_valid 可能产生 GeometryCollection, 只保留面部分
    bad = ~gdf.geometry.is_valid
    if bad.any():
        gdf.loc[bad, "geometry"] = gdf.loc[bad, "geometry"].make_valid()
    if r.shapeType == "POLYGON":
        import shapely
        def poly_only(geom):
            if geom.geom_type == "GeometryCollection":
                polys = [x for x in geom.geoms if "Polygon" in x.geom_type]
                return shapely.unary_union(polys) if polys else geom
            return geom
        gdf["geometry"] = gdf["geometry"].map(poly_only)
    return gdf


def convert(root, out_dir, sheets, prefix="area"):
    os.makedirs(out_dir, exist_ok=True)
    geo, flt = [], []
    for s in sheets:
        jwd = os.path.join(root, s, "MAPGIS", "JWD")
        wp = os.path.join(jwd, f"{s}D01D.WP")   # 地质体面
        wl = os.path.join(jwd, f"{s}D08D.WL")   # 断层线
        if os.path.exists(wp):
            g = read_layer(wp)
            g["SHEET"] = s
            geo.append(g)
            print(f"{s} 地质体面: {len(g)}")
        else:
            print(f"!! {s} 缺 D01D.WP")
        if os.path.exists(wl):
            f = read_layer(wl)
            f["SHEET"] = s
            flt.append(f)
            print(f"{s} 断层线: {len(f)}")

    if geo:
        g = pd.concat(geo, ignore_index=True)
        g = gpd.GeoDataFrame(g, crs=WGS84)
        g["DSO_TXT"] = g["DSO"].map(clean_code)
        keep = ["DSN", "DSO", "DSO_TXT", "GSAF", "QDFCF", "CHFCAC", "SHEET", "geometry"]
        g[[c for c in keep if c in g.columns]].to_file(
            os.path.join(out_dir, f"{prefix}_geology.geojson"), driver="GeoJSON")
        print(f"=> {prefix}_geology.geojson  {len(g)} 面, bounds={g.total_bounds.round(3)}")
    if flt:
        f = pd.concat(flt, ignore_index=True)
        f = gpd.GeoDataFrame(f, crs=WGS84)
        keep = ["CHFCAC", "GZEE", "SHEET", "geometry"]
        f[[c for c in keep if c in f.columns]].to_file(
            os.path.join(out_dir, f"{prefix}_faults.geojson"), driver="GeoJSON")
        print(f"=> {prefix}_faults.geojson  {len(f)} 线")


if __name__ == "__main__":
    root, out = sys.argv[1], sys.argv[2]
    sheets = sys.argv[3:]
    prefix = os.environ.get("PREFIX", "area")
    convert(root, out, sheets, prefix)
