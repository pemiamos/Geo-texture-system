# GeoTexture System

GeoTexture System 是一个面向地质图件和剖面图制作的 Web 工具。项目当前包含一个 Next.js 应用、岩性纹理矢量库、从图例素材生成 React SVG pattern 的辅助脚本，以及一个用于 Blender 的地质材质生成脚本。

## 主要功能

- 本地 SVG 剖面填色：上传 Illustrator 导出的 SVG 线稿，点击地层面后应用地质年代色和岩性纹理。
- 岩性纹理库：内置 75 个岩性图例纹理，支持按沉积岩、变质岩、火成岩等类别浏览。
- 地质年代色卡：维护常用地质年代颜色数据，供剖面着色使用。
- 地图剖面推演：在 Mapbox 地图上绘制 A-B 剖面线，读取地形并尝试结合 Macrostrat 数据生成示意地质剖面。
- 3D 地形块渲染：在 Mapbox 地图上拖拽矩形范围，采样 DEM、贴合卫星地表影像，并用 Three.js 实时渲染地下岩层。
  - **真实地层柱**：优先调用 Macrostrat `/units` 接口，在北美等覆盖区生成真实的命名地层序列（地层名 · 岩性 · 年龄，最多 14 层）；无覆盖区（如中国）退回按地表岩性推断的层序。
  - **顶面贴图模式**：卫星 / 网格 / 混合 / **等高线**。等高线模式从 DEM 实时提取真实等值线（marching squares），自动按高差选取整数等高距、计曲线（每 5 条）加粗并标注海拔高程；底图可选「地形设色」（DEM 高程设色 + 山体阴影）或「真实地图」（Mapbox 静态图，样式可配）。
  - **统一水体着色**：网格 / 等高线模式下大型水体（湖泊等）按统一水体色填充。
  - 可拖动的上下视窗分隔条；2D 地图叠加 Mapbox Terrain v2 矢量等高线开关。
- Blender 地质材质脚本：按经纬度联网获取地质数据，在 Blender 中给 DEM 模型生成分层岩性程序化材质（详见下文）。

## 项目结构

```text
Geo-texture-system/
├── geo-texture-app/                    # Next.js 前端应用
│   ├── src/app/                        # App Router 页面入口
│   ├── src/components/                 # 主界面、侧栏、地图、剖面编辑、3D 地块组件
│   └── src/config/                     # 地质年代色卡与岩性纹理元数据
├── rock_legend_vectors/                # 岩性图例的 SVG/PNG 资源与 manifest
├── tools/                              # 图例提取与 PatternDefs 生成脚本
├── geo_texture_material_generator.py   # Blender 地质材质生成脚本
└── geology_pipeline_test.html          # 地层推演测试台（浏览器单文件，离线可开）
```

## 本地运行

```bash
cd geo-texture-app
npm install
npm run dev
```

然后打开 `http://localhost:3000`。

如需使用地图剖面推演，在 `geo-texture-app/.env.local` 中加入：

```bash
NEXT_PUBLIC_MAPBOX_TOKEN=你的_Mapbox_token
# 可选：等高线"真实地图"底图样式（Mapbox Studio 样式 ID，格式 用户名/样式ID）。
# 想"只显示地理信息"，可在 Studio 复制 outdoors 并隐藏地名/道路/行政界线图层后填入。不填则用代码默认值。
NEXT_PUBLIC_CONTOUR_MAP_STYLE=用户名/样式ID
```

> 注意：`NEXT_PUBLIC_*` 变量在启动时注入，修改 `.env.local` 后需重启 `npm run dev` 才生效。

## Blender 地质材质脚本

`geo_texture_material_generator.py` 在 Blender 中运行（脚本编辑器粘贴执行），为选中的 DEM 网格生成分层岩性程序化材质：

- 顶部填入经纬度即可联网刺探地质数据，数据源按优先级分级：① Macrostrat `/units` 真实地层柱 → ② 本地中国地质图 GeoJSON（可选）/ Macrostrat `/map` 地表种子 → 交由内置 12 轨道推理引擎生成层序；可选叠加 CRUST1.0 真实沉积/地壳厚度偏置。
- 默认直连外网（如需代理在 `HTTP_PROXY` 填写），联网失败会给出明确提示并转入离线兜底。
- 兼容 Blender 4.x；岩性匹配支持中文岩性名与「沉积/火成/变质」大类归一化。

## 常用命令

```bash
cd geo-texture-app
npm run lint
npm run build
```

重新生成岩性纹理定义：

```bash
python tools/build_pattern_defs.py
```

## 维护建议

- 岩性纹理资源以 `rock_legend_vectors/manifest.json` 为索引，更新素材后再运行生成脚本。
- `geo-texture-app/src/components/PatternDefs.tsx` 是生成文件，体积较大，修改纹理时优先改源 SVG 或生成脚本。
- 本地上传 SVG 当前直接注入页面，适合个人本地使用；如果部署给外部用户，应先加入 SVG 清洗和文件安全校验。
- 3D 地块中的 DEM 和地表影像来自 Mapbox 当前可查询数据。地下岩层在有 Macrostrat `/units` 覆盖处为真实命名地层柱，其余地区为基于地表单元的示意推断，均不等同于钻孔或地震解释成果。
- 等高线为从 DEM 实时计算的真实等值线；「真实地图」底图是否带地名/道路/行政界线由所配置的 Mapbox 样式决定，Static API 无法在请求时关闭这些图层。
- `.env.local`、`.DS_Store`、压缩包和本地工具目录不应提交到 GitHub。

## GitHub Desktop 后续管理

1. 用 GitHub Desktop 打开本仓库目录 `Geo-texture-system`。
2. 修改代码后先查看左侧 Changed Files，确认只包含本次要提交的文件。
3. 在 Summary 写简短提交说明，例如 `Update texture library`，点击 Commit to main。
4. 点击 Push origin 同步到 GitHub。
5. 如果多人协作，开始修改前先点 Fetch origin / Pull origin，避免和远端改动冲突。
6. 做较大功能时建议新建 branch，完成后用 Pull Request 合并回 `main`。
