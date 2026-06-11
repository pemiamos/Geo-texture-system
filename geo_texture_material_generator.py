import sys
import os
import urllib.request
import urllib.parse
import json
import ssl
import bpy
import mathutils

# ============================================================
# ⚙️ 全球经纬度无线控制台（在地球上任意找一个坐标，输进来！）
# ============================================================
# 🗺️ 示例坐标供你测试：
# 1. 美国大峡谷沉积岩: 36.100, -112.100
# 2. 四川龙马溪长寿页岩: 29.500, 105.200
# 3. 长白山突发爆发流纹岩: 42.002, 128.058
# 4. 泰山太古代片麻岩: 36.255, 117.102

LATITUDE = 42.002    # 👈 自由输入全球任意纬度 (Latitude)
LONGITUDE = 128.058 # 👈 自由输入全球任意经度 (Longitude)

# 🏷️ 这个名字现在纯粹是用来给材质节点做排版、打标签用的，写啥都行！
LOCATION_LABEL = "作品集案例地形01" 

GLOBAL_NOISE_SCALE = 4.5
GLOBAL_WIGGLE_INTENSITY = 0.08

# 🌐 可选：仅当你本机需要走代理才能访问外网时填写，例如 "http://127.0.0.1:10808"。
#    默认 None = 直连（使用系统默认网络设置）。绝大多数用户保持 None 即可。
HTTP_PROXY = None
# 联网请求超时（秒）。Macrostrat 偶尔较慢，给足时间，超时即转入离线兜底。
REQUEST_TIMEOUT = 10.0

# ──────────────── 数据源分级（思路：真实优先，推断兜底）────────────────
# ① Macrostrat /units：北美等地有真实"命名地层柱"，命中即直接按真实层序/年龄/厚度建层。
# ② Macrostrat /map：全球粗覆盖的地表单元，作为推理引擎的"种子"。
#    可选 OneGeology 中国 1:100万 WMS：中国地表岩性比 Macrostrat 世界图细。
#    ⚠️ 注意：该服务端在本机实测未稳定响应，端点/图层名需你自行用浏览器确认后填入，默认关闭。
ONEGEOLOGY_WMS = None      # 例如 "http://onegeologychina.cgs.gov.cn:8080/.../wms"
ONEGEOLOGY_LAYER = None    # GetCapabilities 里查到的可查询图层名
# ③ CRUST1.0：1°×1° 全球地壳模型，给真实的"沉积层/结晶地壳"厚度（粗，公里级）。
#    用法：去 https://igppweb.ucsd.edu/~gabi/crust1.html 下载并解压，把含 crust1.bnds
#    的目录路径填到下面；填了才启用，用于给地块的"沉积盖层 vs 基底"比例沾一点真实。
CRUST1_DIR = None
# ④ 中国地质图离线 GeoJSON（最准的中国地表岩性来源）：把 1:20万/1:100万 公开版的面
#    导出为 EPSG:4326(WGS84 经纬度) 的 GeoJSON，路径填这里；填了且坐标落在某要素内，
#    就作为中国坐标的最高优先种子。CHINA_GEOMAP_FIELDS 配置从属性里取岩性/年代/名称的字段名。
CHINA_GEOMAP_GEOJSON = None
CHINA_GEOMAP_FIELDS = {
    "lith": ["岩性", "lithology", "lith", "rock", "rock_type"],
    "age": ["年代", "时代", "age", "period", "era"],
    "name": ["地层", "代号", "unit_name", "name", "符号"],
}
# ============================================================

API_BASE = "https://macrostrat.org/api/v2"
ERROR_MESSAGE = None
STATUS_INFO = {"msg": "", "science_track": "", "layer_count": 0, "age_details": "", "net_error": ""}

def fetch_by_coordinates(lat, lng):
    """【全自动管道】用经纬度联网请求 Macrostrat 地表地质单元。

    成功返回地表单元 dict；任何失败（无网络 / 超时 / 该坐标无数据）返回 None，
    调用方会据此转入离线兜底。失败原因记录到 STATUS_INFO['net_error'] 便于排查。
    """
    params = urllib.parse.urlencode({"lat": lat, "lng": lng, "response": "long"})
    url = f"{API_BASE}/geologic_units/map?{params}"
    try:
        # 默认走系统网络设置（直连）；仅当用户显式配置 HTTP_PROXY 时才挂代理。
        handlers = []
        if HTTP_PROXY:
            handlers.append(urllib.request.ProxyHandler({"http": HTTP_PROXY, "https": HTTP_PROXY}))
        else:
            handlers.append(urllib.request.ProxyHandler({}))  # 显式忽略环境里的异常代理变量
        # 正常情况下使用校验过的 TLS；个别系统证书缺失时降级为不校验，避免直接连不上。
        try:
            handlers.append(urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        except Exception:
            handlers.append(urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
        opener = urllib.request.build_opener(*handlers)
        req = urllib.request.Request(url, headers={"User-Agent": "GeoBlender/Ultimate"})
        with opener.open(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
            units = data.get("success", {}).get("data", [])
            if units:
                return units[0]
            STATUS_INFO["net_error"] = "联网成功，但该坐标在 Macrostrat 没有匹配的地表单元。"
    except Exception as exc:
        STATUS_INFO["net_error"] = f"联网失败：{type(exc).__name__}: {exc}"
    return None


def _http_get(url, timeout=None):
    """通用 GET，复用代理 / TLS 策略，返回原始字节；失败抛异常由调用方处理。"""
    handlers = []
    if HTTP_PROXY:
        handlers.append(urllib.request.ProxyHandler({"http": HTTP_PROXY, "https": HTTP_PROXY}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))
    if url.lower().startswith("https"):
        try:
            handlers.append(urllib.request.HTTPSHandler(context=ssl.create_default_context()))
        except Exception:
            handlers.append(urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={"User-Agent": "GeoBlender/Ultimate"})
    with opener.open(req, timeout=timeout or REQUEST_TIMEOUT) as resp:
        return resp.read()


# 岩性名 → 代表色（用于真实地层柱，因为 /units 不一定带 color）。
_LITH_COLOR = {
    "sandstone": "#C8A165", "sand": "#D8C18A", "shale": "#6B7B6B", "mudstone": "#7A7A6E",
    "siltstone": "#B59E78", "claystone": "#7A7466", "clay": "#7A7466",
    "limestone": "#8FB6C9", "dolomite": "#C9B79B", "carbonate": "#9FC0CF", "chalk": "#E6E6DA",
    "conglomerate": "#A98B6B", "breccia": "#9C7E63", "coal": "#23211F", "evaporite": "#E2D7C0",
    "basalt": "#46464E", "andesite": "#8A7A6A", "rhyolite": "#C9B6A0", "tuff": "#BDB29C",
    "volcanic": "#6A5A55", "granite": "#D8B0A0", "granodiorite": "#CBA694", "gabbro": "#3E4248",
    "diorite": "#9A8E84", "gneiss": "#B0A0B8", "schist": "#8C8C7A", "marble": "#E0E0E0",
    "quartzite": "#D8D2C0", "slate": "#4A4F58", "phyllite": "#7C8070",
}
_CLASS_COLOR = {"sedimentary": "#B0A080", "igneous": "#6A5F5A", "metamorphic": "#8A8A92"}


def _unit_color(unit):
    """从 Macrostrat /units 的 lith 数组推一个代表色。"""
    liths = unit.get("lith") or []
    blob = " ".join((l.get("name", "") + " " + l.get("type", "")) for l in liths).lower()
    for key, col in _LITH_COLOR.items():
        if key in blob:
            return col
    for l in liths:
        col = _CLASS_COLOR.get((l.get("class") or "").lower())
        if col:
            return col
    return "#8A96A0"


def fetch_macrostrat_units(lat, lng):
    """① 拉取 Macrostrat 真实地层柱（/units）。无覆盖（如中国）会返回空列表。"""
    params = urllib.parse.urlencode({"lat": lat, "lng": lng, "response": "long"})
    url = f"{API_BASE}/units?{params}"
    try:
        data = json.loads(_http_get(url).decode())
        return data.get("success", {}).get("data", []) or []
    except Exception as exc:
        STATUS_INFO["net_error"] = f"/units 请求失败：{type(exc).__name__}: {exc}"
        return []


def build_layers_from_units(units):
    """把真实地层柱转成 [{name,color,bot,top}]。按 t_age 由新到老排序：
    最年轻(地表)放在与模板 🔝 同一槽位(index 0)，与推断路径的纵向约定保持一致。
    层厚优先用 max_thick，缺失时退化为年龄跨度，再退化为等分。"""
    units = [u for u in units if u]
    if not units:
        return None
    units.sort(key=lambda u: float(u.get("t_age") or 0.0))   # 年轻 → 老

    def weight(u):
        mt = float(u.get("max_thick") or 0.0)
        if mt > 0:
            return mt
        span = abs(float(u.get("b_age") or 0.0) - float(u.get("t_age") or 0.0))
        return span if span > 0 else 1.0

    raw_w = [weight(u) for u in units]
    total = sum(raw_w) or 1.0
    layers, bot = [], 0.0
    n = len(units)
    for i, u in enumerate(units):
        top = 0.999 if i == n - 1 else bot + raw_w[i] / total * 0.999
        nm = u.get("unit_name") or u.get("Fm") or u.get("Gp") or "未命名单元"
        liths = u.get("lith") or []
        lith_txt = liths[0].get("name", "") if liths else ""
        b_age, t_age = u.get("b_age"), u.get("t_age")
        mark = "🔝" if i == 0 else ("🧱" if i == n - 1 else "📄")
        label = f"[{LOCATION_LABEL}] {mark} {nm}"
        if lith_txt:
            label += f"·{lith_txt}"
        if b_age is not None and t_age is not None:
            label += f" ({t_age}-{b_age}Ma)"
        layers.append({"name": label, "color": _unit_color(u), "bot": round(bot, 4), "top": round(min(top, 0.999), 4)})
        bot = top
    STATUS_INFO["msg"] = f"🌐 命中 Macrostrat 真实地层柱：{n} 个地层单元（坐标 {LATITUDE}, {LONGITUDE}）。"
    STATUS_INFO["science_track"] = "🔬 数据来源：Macrostrat /units 真实命名地层序列（非推断）。"
    ages = [float(u.get("b_age") or 0) for u in units] + [float(u.get("t_age") or 0) for u in units]
    STATUS_INFO["age_details"] = f"⏳ 真实地层柱 {n} 层 | 年龄跨度 {min(ages):.1f}-{max(ages):.1f}Ma"
    return layers


def fetch_onegeology_seed(lat, lng):
    """② 可选：OneGeology 中国 1:100万 WMS GetFeatureInfo → 返回 raw_layer 风格的种子。
    端点/图层名需在 ONEGEOLOGY_WMS / ONEGEOLOGY_LAYER 配好；解析尽量宽松。"""
    if not (ONEGEOLOGY_WMS and ONEGEOLOGY_LAYER):
        return None
    # 用一个极小的 bbox 包住目标点，请求 1x1 像素的 GetFeatureInfo（JSON 优先）。
    d = 0.01
    bbox = f"{lng - d},{lat - d},{lng + d},{lat + d}"
    q = urllib.parse.urlencode({
        "service": "WMS", "version": "1.1.1", "request": "GetFeatureInfo",
        "layers": ONEGEOLOGY_LAYER, "query_layers": ONEGEOLOGY_LAYER,
        "srs": "EPSG:4326", "bbox": bbox, "width": "3", "height": "3",
        "x": "1", "y": "1", "info_format": "application/json",
    })
    try:
        raw = _http_get(f"{ONEGEOLOGY_WMS}?{q}").decode("utf-8", "ignore")
        props = {}
        try:
            feats = json.loads(raw).get("features") or []
            if feats:
                props = feats[0].get("properties", {}) or {}
        except Exception:
            return None
        # 字段名各服务不一，挑常见的兜底取。
        def pick(*keys):
            for k in props:
                if k.lower() in keys:
                    return props[k]
            return None
        name = pick("lith", "lithology", "rock_type", "description", "rxml") or "rock"
        return {"name": str(name), "lith": str(pick("lith", "lithology") or ""),
                "color": pick("color") or "#8A96A0", "b_age": 200.0, "t_age": 0.0}
    except Exception as exc:
        STATUS_INFO["net_error"] = f"OneGeology 请求失败：{type(exc).__name__}: {exc}"
        return None


def read_crust1_profile(lat, lng):
    """③ 可选：从本地 CRUST1.0 模型读该点真实的沉积层 / 结晶地壳总厚度（km）。
    返回 (sediment_km, crust_km) 或 None。纯 Python，不依赖 numpy。"""
    if not CRUST1_DIR:
        return None
    try:
        path = os.path.join(CRUST1_DIR, "crust1.bnds")
        from math import floor
        lon = lng - 360 if lng > 180 else (lng + 360 if lng < -180 else lng)
        ilat = int(floor(90.0 - lat)); ilon = int(floor(180.0 + lon))
        ilat = min(179, max(0, ilat)); ilon = min(359, max(0, ilon))
        target = ilat * 360 + ilon
        with open(path, "r") as f:
            for idx, line in enumerate(f):
                if idx == target:
                    b = [float(x) for x in line.split()]   # 9 个边界顶面高程(km)
                    th = [abs(b[i] - b[i + 1]) for i in range(len(b) - 1)]
                    # 顺序：water, ice, 3×sediment, 3×crust, (mantle)
                    sediment = sum(th[2:5]) if len(th) >= 5 else 0.0
                    crust = sum(th[5:8]) if len(th) >= 8 else 0.0
                    return sediment, crust
    except Exception as exc:
        STATUS_INFO["net_error"] = f"CRUST1.0 读取失败：{type(exc).__name__}: {exc}"
    return None


def apply_crust1_cover_bias(layers, lat, lng):
    """用 CRUST1.0 的沉积/地壳比，温和地调整地块"沉积盖层 vs 基底"的厚度占比。
    沉积占比越大 → 顶部各层整体更厚、底部基底更薄；反之亦然。clamp 防止视觉崩坏。"""
    prof = read_crust1_profile(lat, lng)
    if not prof or len(layers) < 2:
        return layers
    sediment, crust = prof
    denom = sediment + crust
    if denom <= 0:
        return layers
    cover_frac = max(0.15, min(0.85, sediment / denom))   # 真实沉积占比，夹在 15%~85%
    bodies, base = layers[:-1], layers[-1]                 # 最后一层视为基底
    body_span = cover_frac * 0.999
    bot, new = 0.0, []
    spans = [(l["top"] - l["bot"]) for l in bodies]
    tot = sum(spans) or 1.0
    for l, s in zip(bodies, spans):
        top = bot + s / tot * body_span
        nl = dict(l); nl["bot"] = round(bot, 4); nl["top"] = round(top, 4); new.append(nl)
        bot = top
    nb = dict(base); nb["bot"] = round(bot, 4); nb["top"] = 0.999; new.append(nb)
    STATUS_INFO["age_details"] += f" | CRUST1.0 沉积{sediment:.1f}km/地壳{crust:.1f}km→盖层占比{cover_frac:.0%}"
    return new


def _point_in_polygon(lng, lat, rings):
    """射线法判断点是否在 GeoJSON Polygon 内（rings[0]=外环，其余=洞）。纯 Python。"""
    def in_ring(ring):
        inside = False
        n = len(ring)
        j = n - 1
        for i in range(n):
            xi, yi = ring[i][0], ring[i][1]
            xj, yj = ring[j][0], ring[j][1]
            if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi):
                inside = not inside
            j = i
        return inside
    if not rings:
        return False
    if not in_ring(rings[0]):
        return False
    return not any(in_ring(hole) for hole in rings[1:])   # 落在洞里则不算命中


def fetch_china_geomap_seed(lat, lng):
    """④ 从本地中国地质图 GeoJSON 做离线点查，返回 raw_layer 风格的种子（最准的中国来源）。"""
    if not CHINA_GEOMAP_GEOJSON:
        return None
    try:
        with open(CHINA_GEOMAP_GEOJSON, "r", encoding="utf-8") as f:
            gj = json.load(f)
        for feat in gj.get("features", []):
            geom = feat.get("geometry") or {}
            gtype, coords = geom.get("type"), geom.get("coordinates")
            hit = False
            if gtype == "Polygon":
                hit = _point_in_polygon(lng, lat, coords)
            elif gtype == "MultiPolygon":
                hit = any(_point_in_polygon(lng, lat, poly) for poly in coords)
            if not hit:
                continue
            props = feat.get("properties", {}) or {}

            def grab(keys):
                low = {k.lower(): v for k, v in props.items()}
                for key in keys:
                    if key in props:
                        return props[key]
                    if key.lower() in low:
                        return low[key.lower()]
                return None

            lith = grab(CHINA_GEOMAP_FIELDS["lith"]) or grab(CHINA_GEOMAP_FIELDS["name"]) or "rock"
            STATUS_INFO["msg"] = f"🗺️ 命中本地中国地质图要素：{lith}（坐标 {lat}, {lng}）。"
            return {"name": str(lith), "lith": str(grab(CHINA_GEOMAP_FIELDS["lith"]) or ""),
                    "color": grab(["color", "颜色"]) or "#8A96A0", "b_age": 200.0, "t_age": 0.0}
        STATUS_INFO["net_error"] = "本地中国地质图已加载，但该坐标不在任何要素范围内。"
    except Exception as exc:
        STATUS_INFO["net_error"] = f"中国地质图读取失败：{type(exc).__name__}: {exc}"
    return None


def acquire_geology(lat, lng):
    """数据获取总调度：返回 (real_layers 或 None, seed 或 None)。
    ① 先试 Macrostrat 真实地层柱；拿不到则按优先级取地表种子交给推理引擎：
       ④ 本地中国地质图 → ② Macrostrat /map → ② OneGeology。"""
    try:
        real = build_layers_from_units(fetch_macrostrat_units(lat, lng))
        if real:
            return real, None
    except Exception as exc:
        STATUS_INFO["net_error"] = f"真实地层柱处理失败，已回退推断：{type(exc).__name__}: {exc}"
    seed = (fetch_china_geomap_seed(lat, lng)
            or fetch_by_coordinates(lat, lng)
            or fetch_onegeology_seed(lat, lng))
    return None, seed

def scientific_inference_engine(raw_layer):
    """【真·12轨双重物理推理引擎】完全由网络抓回来的[岩石名]与[地质年龄]裁决层数与肥瘦厚度"""
    global GLOBAL_WIGGLE_INTENSITY
    
    if raw_layer:
        raw_name = (raw_layer.get("name") or "Unknown Bedrock").lower()
        raw_lith = (raw_layer.get("lith") or "").lower()
        surf_color = raw_layer.get("color", "#8A96A0")
        b_age = float(raw_layer.get("b_age", 100.0))
        t_age = float(raw_layer.get("t_age", 0.0))
        STATUS_INFO["msg"] = f"🌐 联网成功！成功抓取坐标 ({LATITUDE}, {LONGITUDE}) 的真实地表数据。"
    else:
        # 离线或未匹配时的自适应兜底（默认给一套砂岩高精层理）。
        raw_name, raw_lith, surf_color, b_age, t_age = "sandstone", "", "#C77D55", 320.0, 250.0
        reason = STATUS_INFO.get("net_error") or "未获取到联网数据"
        STATUS_INFO["msg"] = f"🔌 离线兜底已激活（{reason}），当前为默认砂岩参数，非该坐标真实地质。"

    age_span = max(0.1, b_age - t_age)

    # 岩性名归一化（针对中国等地常见的笼统返回值）：
    # Macrostrat 在覆盖较粗的地区(如中国)往往只返回 "sedimentary rocks" /
    # "igneous rocks" / "metamorphic rocks" 这类大类名，匹配不到任何具体岩石轨道，
    # 旧逻辑会一律掉进默认片岩轨道。这里先尝试具体岩石名；匹配不到时，
    # 再按沉积 / 碳酸盐 / 火山 / 侵入 / 变质大类，路由到一条代表性轨道。
    # name 与 lith 字段一起参与匹配，提高命中率。
    # 另外把常见中文岩性名翻成英文关键字追加进来，让本地中国地质图(中文属性)也能正确分轨。
    search_text = f"{raw_name} {raw_lith}"
    _zh_map = {
        "石灰岩": "limestone", "灰岩": "limestone", "白云岩": "dolomite", "碳酸盐": "carbonate",
        "砂岩": "sandstone", "粉砂岩": "siltstone", "页岩": "shale", "泥岩": "shale",
        "砾岩": "conglomerate", "角砾岩": "breccia", "玄武岩": "basalt", "安山岩": "andesite",
        "流纹岩": "rhyolite", "凝灰岩": "tuff", "花岗岩": "granite", "闪长岩": "diorite",
        "辉长岩": "gabbro", "片麻岩": "gneiss", "片岩": "schist", "板岩": "slate",
        "石英岩": "quartzite", "大理岩": "marble", "千枚岩": "phyllite", "煤": "coal",
        "火山岩": "volcanic", "沉积岩": "sediment", "变质岩": "metamorph",
        "岩浆岩": "igneous", "火成岩": "igneous", "侵入岩": "intrusive",
    }
    search_text += " " + " ".join(en for zh, en in _zh_map.items() if zh in search_text)
    specific_keywords = [
        "shale", "siltstone", "sandstone", "conglomerate", "breccia", "arkose",
        "limestone", "dolomite", "basalt", "andesite", "rhyolite", "trachyte",
        "tuff", "volcanic", "pyroclastic", "pumice", "granite", "granodiorite",
        "diorite", "gabbro", "plutonic", "gneiss", "migmatite", "schist",
        "slate", "quartzite", "marble", "phyllite",
    ]
    coarse_note = ""
    if any(k in search_text for k in specific_keywords):
        surf_name = search_text                       # 命中具体岩石名，按原逻辑分轨
    elif any(k in search_text for k in ["carbonate", "calcareous"]):
        surf_name, coarse_note = "limestone", "（按碳酸盐岩大类推断）"
    elif "metamorph" in search_text:
        surf_name, coarse_note = "gneiss", "（按变质岩大类推断）"
    elif any(k in search_text for k in ["volcan", "extrusive", "lava", "pyroclast"]):
        surf_name, coarse_note = "basalt", "（按火山岩大类推断）"
    elif any(k in search_text for k in ["igneous", "intrusive", "plutonic", "magmat"]):
        surf_name, coarse_note = "granite", "（按侵入岩大类推断）"
    elif "sediment" in search_text:
        surf_name, coarse_note = "sandstone", "（按沉积岩大类推断）"
    else:
        surf_name = search_text                       # 实在认不出，落入默认片岩轨道

    STATUS_INFO["age_details"] = f"⏳ 原生岩性: {raw_name.upper()}{coarse_note} | 寿命跨度: {age_span:.2f}Ma ({b_age}Ma - {t_age}Ma)"

    # 解码基础设计色彩基因并创建高档同色系明暗调色链
    h = surf_color.lstrip("#")
    base_rgb = [int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4)]
    
    def make_colors(count, base, intensity=0.28):
        return [f"#{int(max(0.01, min(0.99, base[0] * (1.0 + ((i / max(1, count - 1)) * 2.0 - 1.0) * intensity)))*255):02X}{int(max(0.01, min(0.99, base[1] * (1.0 + ((i / max(1, count - 1)) * 2.0 - 1.0) * intensity)))*255):02X}{int(max(0.01, min(0.99, base[2] * (1.0 + ((i / max(1, count - 1)) * 2.0 - 1.0) * intensity)))*255):02X}" for i in range(count)]

    # 1️⃣ 📄 轨道一：页岩 (Shale)
    if "shale" in surf_name:
        if age_span > 15.0: # 长寿页岩 ➔ 12层极限超频微页理
            STATUS_INFO["science_track"] = "🔬 物理推理：【长寿型深海静水页岩】➔ 12层精密微页理"
            w = [0.03, 0.12, 0.02, 0.15, 0.02, 0.18, 0.02, 0.14, 0.02, 0.13, 0.12, 0.05]
            names = ["🔝 风化碎屑覆土", "📄 顶层富碳质页岩", "⚡ 高有机质炭质线 A", "📄 硅质致密页岩", "⚡ 粉砂质水平层理线 B", "📄 纹层状微细页岩", "⚡ 黄铁矿化金属标志线 C", "📄 优质页岩储层核心段", "⚡ 泥质黏土岩剪切线 D", "📄 下部致密粉砂质页岩", "📄 深层高压流体异常带", "🧱 底座硬化生物灰岩"]
        else:
            STATUS_INFO["science_track"] = "🔬 物理推理：【突发期浅海泥岩】➔ 6层非对称泥质相"
            w = [0.06, 0.42, 0.03, 0.25, 0.14, 0.10]
            names = ["🔝 表层泥质粗沙土", "📄 浅海绿泥石砂质块", "⚡ 泥质不连续面界线", "📄 中部致密泥岩厚层", "📄 下部致密水平层理岩", "🧱 古生代硬化粗碎屑底"]
        c = make_colors(len(w), base_rgb, 0.3)

    # 2️⃣ 📄 轨道二：粉砂岩 (Siltstone)
    elif "siltstone" in surf_name:
        STATUS_INFO["science_track"] = "🔬 物理推理：【浅海陆棚粉砂岩】➔ 9层细粒海洋韵律"
        w = [0.05, 0.22, 0.03, 0.23, 0.03, 0.21, 0.13, 0.03, 0.07]
        names = ["🔝 现代表土风化沙质土", "📄 钙质粉砂岩主体盘", "⚡ 铁质浸润红褐色细界线", "📄 块状致密长石粉砂岩", "⚡ 泥质水平层理深色极薄层", "📄 互层状细粒海相碎屑岩", "📄 下部含海绿石绿调层", "⚡ 密集海相微体生物化石线", "🧱 坚硬基底碎屑沉积封底"]
        c = make_colors(9, base_rgb, 0.25)

    # 3️⃣ 🏖️ 轨道三：砂岩 (Sandstone)
    elif "sandstone" in surf_name:
        if age_span > 20.0: # 历史演化久 ➔ 叠复冲断韵律
            STATUS_INFO["science_track"] = "🔬 物理推理：【多阶长寿河流砂岩】➔ 8层高反差洪积韵律"
            w = [0.04, 0.36, 0.12, 0.02, 0.22, 0.02, 0.14, 0.08]
            names = ["🔝 河床坡积粗沙覆土", "📄 石英砂岩巨厚沙盘", "📄 泥质交错层理粉砂岩", "⚡ 强风化铁质高红界线", "📄 粗粒长石碎屑重力流", "⚡ 钙质硬化极其致密细白线", "📄 下部致密红层低能泥岩", "🧱 前寒武纪不整合坚硬底"]
        else:
            STATUS_INFO["science_track"] = "🔬 物理推理：【短期陆相河流砂岩】➔ 5层浑厚沉积相"
            w = [0.08, 0.52, 0.20, 0.12, 0.08]
            names = ["🔝 现代沙质冲积层", "📄 河道单一巨厚粉砂岩", "📄 泥质条带交错层", "📄 下部红色铁质致密层", "🧱 基底岩体剥蚀不整合面"]
        c = make_colors(len(w), base_rgb, 0.35)

    # 4️⃣ 🧱 轨道四：角砾岩/砾岩 (Conglomerate/Breccia)
    elif any(k in surf_name for k in ["conglomerate", "breccia", "arkose"]):
        STATUS_INFO["science_track"] = "🔬 物理推理：【山麓突发性滑塌】➔ 6层粗粒角砾岩相"
        w = [0.08, 0.44, 0.03, 0.29, 0.07, 0.09]
        names = ["🔝 现代群集基性粗砾土", "📄 巨型磨圆鹅卵砾岩大盘", "⚡ 突发洪水期细泥冲刷面", "📄 尖棱角状基性角砾流体", "📄 砂质胶结高强度致密砾岩", "🧱 古老剥蚀基底变质岩床"]
        c = make_colors(6, base_rgb, 0.22)

    # 5️⃣ 🐚 轨道五：石灰岩 (Limestone)
    elif "limestone" in surf_name:
        STATUS_INFO["science_track"] = "🔬 物理推理：【碳酸盐岩生物建造】➔ 10层海相骨感层序"
        w = [0.06, 0.26, 0.02, 0.14, 0.12, 0.02, 0.14, 0.12, 0.02, 0.10]
        names = ["🔝 喀斯特溶蚀残余红土", "📄 纯净鲕状灰岩大盘", "⚡ 极其锐利的黑色燧石条带", "📄 泥质豹皮状白云质灰岩", "📄 密集微体腕足类化石带", "⚡ 碳酸盐溶解缝合线标志层", "📄 竹叶状碎屑页相灰岩", "📄 深水微晶致密泥质页岩", "⚡ 泥质夹层强烈风化软化带", "🧱 深部寒武纪重结晶白云岩"]
        c = make_colors(10, base_rgb, 0.26)

    # 6️⃣ 🧂 轨道六：白云岩 (Dolomite)
    elif "dolomite" in surf_name:
        STATUS_INFO["science_track"] = "🔬 物理推理：【泻湖潮坪蒸发相】➔ 7层致密白云岩层序"
        w = [0.06, 0.36, 0.02, 0.24, 0.03, 0.19, 0.10]
        names = ["🔝 白云岩刀砍状溶蚀表土", "📄 砂糖状重结晶白云岩主体", "⚡ 石膏质晶斑蒸发极薄线", "📄 含泥质层理薄层白云岩", "⚡ 黑色硅质针状交代不连续面", "📄 深层致密微晶泥质白云岩", "🧱 震旦纪硬化高强度硅质岩"]
        c = make_colors(7, base_rgb, 0.2)

    # 7️⃣ 🪨 轨道七：玄武岩 (Basalt)
    elif "basalt" in surf_name:
        STATUS_INFO["science_track"] = "🔬 物理推理：【基性溢流火成岩】➔ 9层多期次溢流岩盘"
        w = [0.05, 0.17, 0.02, 0.34, 0.03, 0.17, 0.03, 0.11, 0.08]
        names = ["🔝 玄武岩红土化富铁表土", "📄 晚期致密玄武熔岩体", "⚡ 顶部快速骤冷多孔杏仁体", "📄 巨厚垂直柱状节理玄武岩柱", "⚡ 喷发间歇期夹砂砾风化层", "📄 中期隐晶质玄武岩盘", "⚡ 早期粗粒熔岩流前缘线", "📄 早期斑状玄武侵入岩盘", "🧱 断裂带深海沉积托底面"]
        c = make_colors(9, base_rgb, 0.24)

    # 8️⃣ ☄️ 轨道八：安山岩 (Andesite)
    elif "andesite" in surf_name:
        STATUS_INFO["science_track"] = "🔬 物理推理：【中性斑状熔岩锥】➔ 8层斑状过渡熔岩"
        w = [0.06, 0.29, 0.02, 0.25, 0.03, 0.17, 0.10, 0.08]
        names = ["🔝 风化安山质粘土角砾土", "📄 斜长石斑岩熔岩流主体", "⚡ 角闪石定向排列极薄流线", "📄 块状致密辉石安山岩", "⚡ 火山碎屑集块岩不连续夹层", "📄 早期隐晶质英安岩交代带", "⏳ 火山颈多期次剪切复合带", "🧱 地壳深部基底硬化托底"]
        c = make_colors(8, base_rgb, 0.25)

    # 9️⃣ 🌋 轨道九：流纹岩/凝灰岩 (Rhyolite/Tuff)
    elif any(k in surf_name for k in ["rhyolite", "trachyte", "tuff", "volcanic", "pyroclastic", "pumice"]):
        if age_span < 5.0: # 突发灾变喷发 ➔ 坍缩为 4层 刚性超级大肥块
            STATUS_INFO["science_track"] = "🔬 物理推理：【灾变骤发型火成碎屑】➔ 4层刚性爆裂熔岩体"
            w = [0.05, 0.73, 0.03, 0.19]
            c = ["#EBE4D8", surf_color, "#141414", "#24201D"] # 锁定黑曜岩玻璃线
            names = ["🔝 松散落碎风化火山灰", "📄 灾变熔结凝灰岩巨厚岩盘", "⚡ 骤冷流纹质晶质黑曜岩线", "🧱 古老深部地壳刚性结晶底"]
        else:
            STATUS_INFO["science_track"] = "🔬 物理推理：【演化期酸性火山岩】➔ 7层流纹相构造"
            w = [0.07, 0.38, 0.02, 0.25, 0.03, 0.16, 0.09]
            names = ["🔝 空落浮石层", "📄 流纹岩多期次岩体", "⚡ 黑色晶质黑曜岩标志线", "📄 粗面质刚性角砾熔岩", "⚡ 气孔状流纹斑岩气腔线", "⏳ 早期火山口集块岩带", "🧱 前陆断裂刚性盾底"]
            c = make_colors(7, base_rgb, 0.3)

    # 🔟 💎 轨道十：花岗岩 (Granite)
    elif any(k in surf_name for k in ["granite", "granodiorite", "diorite", "gabbro", "plutonic"]):
        STATUS_INFO["science_track"] = "🔬 物理推理：【深成岩浆岩基】➔ 4层极端极简浑厚块面"
        w = [0.08, 0.75, 0.03, 0.14] 
        names = ["🔝 节理球状风化残积沙土带", "📄 巨型结晶斑状花岗岩基体", "⚡ 晚期伟晶岩热液充填高亮脉", "🧱 同源基性包裹体深部底层"]
        c = ["#CCAFA4", surf_color, "#EADCD6", "#3D3431"]

    # 1️⃣1️⃣ 🌀 轨道十一：片麻岩 (Gneiss)
    elif any(k in surf_name for k in ["gneiss", "migmatite", "complex"]):
        if b_age > 1000.0: GLOBAL_WIGGLE_INTENSITY *= 1.8
        STATUS_INFO["science_track"] = "🔬 物理推理：【太古代高压深部变质】➔ 6层强力揉皱剪切带"
        w = [0.06, 0.30, 0.03, 0.34, 0.03, 0.24]
        names = ["🔝 山麓变质风化崩积粗碎土", "📄 条带状黑云斜长片麻岩", "⚡ 暗色斜长角闪岩剪切挤压带", "📄 富长英质交代重结晶混合岩", "⚡ 强烈长石化浅色交代微流线", "🧱 深部基性辉绿岩脉穿插底"]
        c = make_colors(6, base_rgb, 0.3)

    # 1️⃣2️⃣ 🪵 轨道十二：片岩/千枚岩 (Schist/Default)
    else:
        STATUS_INFO["science_track"] = "🔬 物理推理：【区域动力中阶变质】➔ 5层丝绢光泽定向片理"
        w = [0.05, 0.41, 0.03, 0.33, 0.18]
        names = ["🔝 绢云母风化残积薄表土", "📄 绢云母片岩片理面核心", "⚡ 挤压熔融后期高亮纯白石英脉", "📄 绿泥石千枚岩强烈揉皱带", "🧱 深部未变质泥质原岩刚性核"]
        c = make_colors(5, base_rgb, 0.28)

    # 区间归一化拼装
    layers = []
    current_bot = 0.0
    for i in range(len(w)):
        current_top = current_bot + w[i]
        if i == len(w) - 1: current_top = 0.999 
        layers.append({
            "name": f"[{LOCATION_LABEL}] " + names[i],
            "color": c[i],
            "bot": round(current_bot, 4),
            "top": round(current_top, 4)
        })
        current_bot = current_top
    return layers

def build_foolproof_engine():
    global ERROR_MESSAGE
    
    # ── 🛰️ 核心流程：分级数据获取 ➔ 真实优先/推断兜底 ➔ (可选)CRUST1.0 层厚偏置 ──
    real_layers, seed = acquire_geology(LATITUDE, LONGITUDE)
    if real_layers:
        chosen_layers = real_layers                          # ① 真实地层柱
    else:
        chosen_layers = scientific_inference_engine(seed)    # ②→推理引擎（含离线兜底）
    chosen_layers = apply_crust1_cover_bias(chosen_layers, LATITUDE, LONGITUDE)  # ③ 可选
    STATUS_INFO["layer_count"] = len(chosen_layers)

    obj = bpy.context.active_object
    if not obj or obj.type != "MESH":
        if "天池DEM2" in bpy.data.objects: 
            obj = bpy.data.objects["天池DEM2"]
            bpy.context.view_layer.objects.active = obj
        else:
            ERROR_MESSAGE = "❌ 终极拦截：未在 3D 视图中鼠标点击选中任何大山模型！"
            return False
            
    mat = obj.active_material
    if not mat:
        if len(obj.data.materials) > 0 and obj.data.materials[0] is not None:
            mat = obj.data.materials[0]
            obj.active_material = mat
        else:
            mat = bpy.data.materials.new(name="Geo_Coordinate_Engine_Material")
            obj.data.materials.append(mat)
            obj.active_material = mat
            
    mat.use_nodes = True
    nodes = mat.node_tree.nodes; links = mat.node_tree.links
    for n in list(nodes):
        if n.name.startswith("geo__"): nodes.remove(n)
        
    bbox = [obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box]
    min_z, max_z = min(v.z for v in bbox), max(v.z for v in bbox)
    height = max_z - min_z if (max_z - min_z) > 0 else 1.0
    
    # 波纹总线搭建
    tc = nodes.new("ShaderNodeTexCoord"); tc.name = "geo__tc"; tc.location = (-1600, 0)
    mapping = nodes.new("ShaderNodeMapping"); mapping.name = "geo__map"; mapping.location = (-1350, 0)
    mapping.inputs["Location"].default_value[2] = -min_z / height
    mapping.inputs["Scale"].default_value[2] = 1.0 / height
    
    noise = nodes.new("ShaderNodeTexNoise"); noise.name = "geo__noise"; noise.location = (-1100, -200)
    noise.inputs["Scale"].default_value = GLOBAL_NOISE_SCALE
    noise.inputs["Detail"].default_value = 6.0       
    noise.inputs["Roughness"].default_value = 0.52   
    
    vec_mix = nodes.new("ShaderNodeMix"); vec_mix.name = "geo__mix_vec"; vec_mix.location = (-850, 0)
    vec_mix.data_type = 'VECTOR'; vec_mix.inputs["Factor"].default_value = GLOBAL_WIGGLE_INTENSITY
    
    sep = nodes.new("ShaderNodeSeparateXYZ"); sep.name = "geo__sep"; sep.location = (-600, 0)
    
    links.new(tc.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(mapping.outputs["Vector"], vec_mix.inputs["A"])
    links.new(noise.outputs["Color"], vec_mix.inputs["B"])
    links.new(vec_mix.outputs["Result"], sep.inputs["Vector"])
    
    base = nodes.new("ShaderNodeBsdfPrincipled"); base.name = "geo__base"; base.location = (-450, 250)
    base.inputs["Base Color"].default_value = (0.005, 0.004, 0.003, 1.0)
    prev_socket = base.outputs["BSDF"]
    
    # 级联线铺设
    for i, layer in enumerate(chosen_layers):
        y_offset = -i * 370
        ramp = nodes.new("ShaderNodeValToRGB"); ramp.name = f"geo__ramp_{i}"; ramp.location = (-450, y_offset + 120)
        ramp.color_ramp.interpolation = "CONSTANT"
        cr = ramp.color_ramp
        cr.elements[0].position = 0.0; cr.elements[0].color = (0,0,0,1)
        cr.elements[1].position = 0.999; cr.elements[1].color = (0,0,0,1)
        cr.elements.new(layer["bot"]).color = (1,1,1,1)
        cr.elements.new(min(layer["top"], 0.998)).color = (0,0,0,1)
        
        links.new(sep.outputs["Z"], ramp.inputs["Fac"])
        
        bsdf = nodes.new("ShaderNodeBsdfPrincipled"); bsdf.name = f"geo__bsdf_{i}"; bsdf.location = (-450, y_offset - 60)
        bsdf.label = layer["name"]
        
        rgb = [((int(layer["color"].lstrip("#")[idx:idx+2], 16)/255.0)/12.92 if (int(layer["color"].lstrip("#")[idx:idx+2], 16)/255.0)<=0.04045 else ((int(layer["color"].lstrip("#")[idx:idx+2], 16)/255.0+0.055)/1.055)**2.4) for idx in (0, 2, 4)]
        bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.15 if "⚡" in layer["name"] else 0.93
        
        mix = nodes.new("ShaderNodeMixShader"); mix.name = f"geo__mix_{i}"; mix.location = (-50, y_offset + 60)
        links.new(ramp.outputs["Color"], mix.inputs[0])
        links.new(prev_socket, mix.inputs[1])
        links.new(bsdf.outputs["BSDF"], mix.inputs[2])
        prev_socket = mix.outputs["Shader"]
        
    out = next((n for n in nodes if n.type == "OUTPUT_MATERIAL"), None) or nodes.new("ShaderNodeOutputMaterial")
    out.location = (350, 0); links.new(prev_socket, out.inputs["Surface"])

    # 自动缩放节点编辑器视图。Blender 4.x 用 temp_override；
    # 旧版回退到 2.9x 的 dict 覆盖写法。失败也不影响材质本身已经建好。
    try:
        screen = getattr(bpy.context, "screen", None)
        for area in (screen.areas if screen else []):
            if area.type == "NODE_EDITOR":
                if hasattr(bpy.context, "temp_override"):
                    with bpy.context.temp_override(area=area):
                        bpy.ops.node.view_all()
                else:
                    ctx = bpy.context.copy(); ctx["area"] = area; bpy.ops.node.view_all(ctx)
                break
    except Exception:
        pass
    return True

def draw_success_popup(self, context):
    self.layout.label(text=STATUS_INFO["msg"], icon="WORLD")
    self.layout.label(text=STATUS_INFO["age_details"], icon="TIME")
    self.layout.label(text=STATUS_INFO["science_track"], icon="COLOR")
    self.layout.label(text=f"🔥 坐标全动态驱动：节点树已重组 ➔ {STATUS_INFO['layer_count']} 层 bespoke 切片 🔍", icon="LAYERS")

def draw_error_popup(self, context):
    self.layout.label(text=ERROR_MESSAGE, icon="ERROR")

# 启动卫星
success = build_foolproof_engine()
if success:
    bpy.context.window_manager.popup_menu(draw_success_popup, title="真·全动态坐标材质总线", icon="INFO")
else:
    bpy.context.window_manager.popup_menu(draw_error_popup, title="系统拦截器通知", icon="CANCEL")