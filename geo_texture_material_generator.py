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

def scientific_inference_engine(raw_layer):
    """【真·12轨双重物理推理引擎】完全由网络抓回来的[岩石名]与[地质年龄]裁决层数与肥瘦厚度"""
    global GLOBAL_WIGGLE_INTENSITY
    
    if raw_layer:
        surf_name = raw_layer.get("name", "Unknown Bedrock").lower()
        surf_color = raw_layer.get("color", "#8A96A0")
        b_age = float(raw_layer.get("b_age", 100.0))
        t_age = float(raw_layer.get("t_age", 0.0))
        STATUS_INFO["msg"] = f"🌐 联网成功！成功抓取坐标 ({LATITUDE}, {LONGITUDE}) 的真实地表数据。"
    else:
        # 离线或未匹配时的自适应兜底（默认给一套砂岩高精层理）。
        surf_name, surf_color, b_age, t_age = "sandstone", "#C77D55", 320.0, 250.0
        reason = STATUS_INFO.get("net_error") or "未获取到联网数据"
        STATUS_INFO["msg"] = f"🔌 离线兜底已激活（{reason}），当前为默认砂岩参数，非该坐标真实地质。"

    age_span = max(0.1, b_age - t_age)
    STATUS_INFO["age_details"] = f"⏳ 原生岩性: {surf_name.upper()} | 寿命跨度: {age_span:.2f}Ma ({b_age}Ma - {t_age}Ma)"

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
    
    # ── 🛰️ 核心流程：读取控制台坐标 ➔ 联网刺探 ➔ 双重推理 ──
    raw_layer = fetch_by_coordinates(LATITUDE, LONGITUDE)
    chosen_layers = scientific_inference_engine(raw_layer)
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