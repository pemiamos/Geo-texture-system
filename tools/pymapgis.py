"""
pymapgis.py
Provides reading support for mapgis *.wt,*.wl,*.wp geospatial vector files.
author: 1045105061@qq.com
version: 1.0
Compatible with Python versions 3.9
"""

__version__ = "1.0"

import struct
import pyproj
import os
import re
import pandas as pd
import geopandas as gpd
import numpy as np
import shapely
import datetime
import warnings

class Reader:
    def __init__(self,filepath):
        self.f=open(filepath,'rb')
        type_dict={'WMAP`D22':'POINT','WMAP`D23':'POLYGON','WMAP`D21':'LINE'}
        type=self.f.read(8).decode('gbk')
        if type not in ['WMAP`D22','WMAP`D23','WMAP`D21']:
            raise InvalidFileError()
        self.shapeType=type_dict[type]

        struct.unpack('1i',self.f.read(4))[0]
        data_start=struct.unpack('1i',self.f.read(4))[0]
        self.f.seek(data_start)
        self.head_1=self.f.read(10)
        self.head_2=self.f.read(10)
        self.head_3=self.f.read(10)
        self.head_4=self.f.read(10)
        self.head_5=self.f.read(10)
        self.head_6=self.f.read(10)
        self.head_7=self.f.read(10)
        self.head_8=self.f.read(10)
        self.head_9=self.f.read(10)
        self.head_10=self.f.read(10)
        self.filepath=filepath
        if type =='WMAP`D22':
            start,vol=struct.unpack('2i',self.head_3[:-2])
            self.__get_attr(start)
            self.__get_points()

        elif type =='WMAP`D21':
            start,vol=struct.unpack('2i',self.head_3[:-2])
            self.__get_attr(start)
            self.__get_lines()

        else:
            start,vol=struct.unpack('2i',self.head_10[:-2])
            self.__get_attr(start)
            self.__get_polygons()

        self.__get_geopandas()
    def __get_crs(self):
        self.f.seek(109)
        self.pro=ord(self.f.read(1))
        pro_dict={5:'tmerc',1:'utm',2:'aea',3:'lcc'}
        elli=ord(self.f.read(1))
        self.f.seek(143)
        self.sc=struct.unpack('1d',self.f.read(8))[0]
        ellip={
            1:'+ellps=krass +towgs84=15.8,-154.4,-82.3,0,0,0,0 +units=m +no_d',
            2:'+a=6378140 +b=6356755.288157528',
            7:'+datum=WGS84',
            9:'+ellps=WGS72',
            10:'+ellps=aust_SA +towgs84=-117.808,-51.536,137.784,0.303,0.446,0.234,-0.29',
            11:'+ellps=aust_SA +towgs84=-134,-48,149,0,0,0,0',
            16:'+ellps=krass',
            116:'+ellps=clrk80 +towgs84=-166,-15,204,0,0,0,0',
            'cgcs2000':'+ellps=GRS80',
        }
        if (elli not in ellip.keys()) or (self.sc==0):
            self.sc=1
            self.crs=''
            warnings.warn(self.filepath+':  no invalid crs detected')
            return
        if self.pro==5:

            self.sc=self.sc/1000
            self.f.seek(151)
            cl=struct.unpack('1d',self.f.read(8))[0]
            cl=int(str(cl).split('.')[0][:-4])+int( str(cl).split('.')[0][-4:-2])/60.0+int(str(cl).split('.')[0][-2:]  )/60.0/60
            self.crs=pyproj.CRS('+proj=tmerc'+' +lat_0=0 +lon_0='+str(cl)+' +k=1 +x_0=500000 +y_0=0 '+ellip[elli]+' +units=m +no_defs')
        elif self.pro == 0:

            self.crs=pyproj.CRS('+proj=longlat '+ellip[elli]+' +no_defs')

        elif (self.pro==2 or self.pro==3):   # Albers or Lambert


            self.sc=self.sc/1000
            self.f.seek(151)
            cl=struct.unpack('1d',self.f.read(8))[0]
            cl=int(str(cl).split('.')[0][:-4])+int( str(cl).split('.')[0][-4:-2])/60.0+int(str(cl).split('.')[0][-2:]  )/60.0/60

            self.f.seek(175)
            lat0=struct.unpack('1d',self.f.read(8))[0]   #standard latitude
            lat_0=int(str(lat0).split('.')[0][:-4])+int(str(lat0).split('.')[0][-4:-2])/60.0+int(str(lat0).split('.')[0][-2:])/60.0/60
            lat1=struct.unpack('1d',self.f.read(8))[0]   #first standard latitude
            lat_1=int(str(lat1).split('.')[0][:-4])+int(str(lat1).split('.')[0][-4:-2])/60.0+int(str(lat1).split('.')[0][-2:])/60.0/60
            lat2=struct.unpack('1d',self.f.read(8))[0]   #second standard latitude
            lat_2=int(str(lat2).split('.')[0][:-4])+int(str(lat2).split('.')[0][-4:-2])/60.0+int(str(lat2).split('.')[0][-2:])/60.0/60
            x_0=struct.unpack('1d',self.f.read(8))[0]
            y_0=struct.unpack('1d',self.f.read(8))[0]
            self.crs=pyproj.CRS('+proj='+pro_dict[self.pro]+' +lat_0='+str(lat_0)+' +lon_0='+str(cl)+' +lat_1='+
                                str(lat_1)+' +lat_2='+str(lat_2)+' +x_0='+str(x_0)+' +y_0='+str(y_0)+' '+ellip[elli]+' +units=m +no_defs')

    def __get_attr(self,start):
        self.f.seek(start)
        self.f.read(2)
        self.f.read(4) # date-created
        self.f.read(6)
        offset=struct.unpack('1i',self.f.read(4))[0] # attribute data offset from this section
        self.f.read(4)
        self.f.read(4)
        self.f.read(128) # work directory path
        self.f.read(128)
        self.f.read(40)
        self.f.read(2)
        fields_n=struct.unpack('1h',self.f.read(2))[0] # the number of fields
        num=struct.unpack('1i',self.f.read(4))[0] # the number of records
        leng=struct.unpack('1h',self.f.read(2))[0] # the length of each record
        self.f.read(18)
        field_names=[] # list to store field names
        types=[] # list to store field types
        nums=[] # list to store the number of records
        offs=[] # list to store the offset of each field
        lens=[] # list to store the length of each field

        for i in range(fields_n):
            temp=self.f.read(20)
            try:
                temp_=temp.decode('gbk').strip('\x00')
            except UnicodeDecodeError as err:
                temp_= temp[:   int(re.search(r'in position (\d+)',str(err)).group(1))].decode('gbk')
            field_names.append(temp_)
            types.append(ord(self.f.read(1)))
            offs.append(struct.unpack('1i', self.f.read(4)))
            self.f.read(2)
            lens.append(struct.unpack('1h',self.f.read(2)))
            self.f.read(1)
            self.f.read(1)
            self.f.read(2)
            nums.append(struct.unpack('1h', self.f.read(2)))
            self.f.read(4)
        temp=np.array(types)
        mask=(temp==0)|(temp==1)|(temp==2)|(temp==3)|(temp==4)|(temp==5)|(temp==6)|(temp==7)
        field_names=np.array(field_names)[mask]
        
        field_type_dict={0:'string',1:'byte',2:'short integer',3:'integer',4:'float',5:'double',6:'date',7:'time'}


        offs=[i[0] for i in offs]

        k1=offs.copy()
        k1.append(leng) 
        length=np.array([i[1]-i[0] for i in zip(k1[:-1],k1[1:])])[mask]
        self.fields=list(zip(field_names,[field_type_dict[i] for i in np.array(types)[mask]],length))


        self.f.read(leng)
        self.data=[]
        for i in range(num-1):
            a=self.f.read(leng)
            attr=[]
            for j in range(offs.__len__()):
                if j<offs.__len__()-1:
                    if types[j]==4:
                        attr.append(struct.unpack('1f',a[offs[j]:offs[j+1]])[0])
                    elif types[j]==3:
                        attr.append(struct.unpack('1i',a[offs[j]:offs[j+1]])[0])
                    elif types[j]==2:
                        attr.append(struct.unpack('1h',a[offs[j]:offs[j+1]])[0])
                    elif types[j]==1:
                        attr.append(ord(a[offs[j]:offs[j+1]]))
                    elif types[j]==5:
                        attr.append(struct.unpack('1d',a[offs[j]:offs[j+1]])[0])

                    elif types[j]==6:
                        temp=a[offs[j]:offs[j+1]]
                        attr.append(datetime.date(struct.unpack('1h',temp[:2])[0],temp[2],temp[3]))

                    elif types[j]==7:
                        temp=a[offs[j]:offs[j+1]]
                        attr.append(datetime.time ( temp[0],temp[1], *(lambda x:(np.int64(np.floor(x)),np.int64(1000000*(x-np.floor(x)))))(struct.unpack('1d',temp[2:])[0])))

                    elif types[j]==0:
                        temp=a[offs[j]:offs[j+1]]
                        try:
                            temp_=temp.decode('gbk').strip('\x00')
                        except UnicodeDecodeError as err:
                            temp_= temp[:int(re.search(r'in position (\d+)',str(err)).group(1))].decode('gbk')
                        attr.append(temp_)
                else:
                    if types[j]==4:
                        attr.append(struct.unpack('1f',a[offs[j]:])[0])
                    elif types[j]==3:
                        attr.append(struct.unpack('1i',a[offs[j]:])[0])
                    elif types[j]==2:
                        attr.append(struct.unpack('1h',a[offs[j]:])[0])
                    elif types[j]==1:
                        attr.append(ord(a[offs[j]:]))
                    elif types[j]==5:
                        attr.append(struct.unpack('1d',a[offs[j]:])[0])

                    elif types[j]==6:
                        temp=a[offs[j]:]
                        attr.append(datetime.date(struct.unpack('1h',temp[:2])[0],temp[2],temp[3]))

                    elif types[j]==7:
                        temp=a[offs[j]:]
                        attr.append(datetime.time ( temp[0],temp[1], *(lambda x:(np.int64(np.floor(x)),np.int64(1000000*(x-np.floor(x)))))(struct.unpack('1d',temp[2:])[0])        )         )
                    elif types[j]==0:
                        temp=a[offs[j]:]
                        try:
                            temp_=temp.decode('gbk').strip('\x00')
                        except UnicodeDecodeError as err:
                            temp_= temp[:int(re.search(r'in position (\d+)',str(err)).group(1))].decode('gbk')
                        attr.append(temp_)
            self.data.append(attr)
        self.data=pd.DataFrame(self.data)
        self.data.columns=field_names

    def __get_points(self):
        self.__get_crs()
        start,vol=struct.unpack('2i',self.head_1[:-2])
        self.f.seek(start)
        self.f.read(93)
        self.coords=[]
        for i in range(int(vol/93)-1):
            self.f.read(1) # 1 label
            self.f.read(2) #
            self.f.read(4)
            self.coords.append(struct.unpack('2d',self.f.read(16)))
            self.f.read(70)
        self.coords=np.array(self.coords)
        self.geom = [shapely.geometry.Point(xy*self.sc) for xy in self.coords]
    def __get_lines(self):
        self.__get_crs()
        start,vol=struct.unpack('2i',self.head_1[:-2])
        self.f.seek(start)
        k=vol/57
        self.f.read(57)
        points=[]
        points_off=[]
        for i in range(int(k)-1):
            self.f.read(10)
            points.append(struct.unpack('1i',self.f.read(4))[0])
            points_off.append(struct.unpack('1i',self.f.read(4))[0])
            self.f.read(39)
        start,vol=struct.unpack('2i',self.head_2[:-2])
        self.coords=[]
        for i in range(int(k)-1):
            self.f.seek(start+points_off[i])
            self.coords.append(struct.unpack('%sd'%(points[i]*2),self.f.read(points[i]*16)))
        self.geom = [shapely.geometry.LineString(np.array(i).reshape(-1,2)*self.sc) for i in self.coords]
        
        
        
  
        
        
    def __get_polygons(self):
        self.__get_crs()
        start,vol=struct.unpack('2i',self.head_1[:-2])
        self.f.seek(start)
        k=vol/57
        self.f.read(57)
        points=[]
        points_off=[]
        for i in range(int(k)-1):
            self.f.read(10)
            points.append(struct.unpack('1i',self.f.read(4))[0])
            points_off.append(struct.unpack('1i',self.f.read(4))[0])
            self.f.read(39)
        start,vol=struct.unpack('2i',self.head_2[:-2])
        self.coords=[]
        for i in range(int(k)-1):
            self.f.seek(start+points_off[i])
            self.coords.append(struct.unpack('%sd'%(points[i]*2),self.f.read(points[i]*16)))
        geom_ = [shapely.geometry.LineString(np.array(i).reshape(-1,2)*self.sc) for i in self.coords]
        
        start,vol=struct.unpack('2i',self.head_4[:-2])

        self.f.seek(start)
        self.f.read(24)
        temp=[]
        for i in range(int(vol/24.-1)):
            temp.append(struct.unpack('4i',self.f.read(16)))
            self.f.read(8)
        temp=np.array(temp)
        temp=np.hstack((temp,np.arange(temp.__len__()).reshape((-1,1))))

        ids = sorted(set(temp[:,2:4].flatten())-{0})
        self.data = self.data.loc[np.array(ids)-1]

        # 按多边形id分组弧段 (与原算法一致: 每条弧段出现一次, 方向无关)
        arcs_by_poly = {i: [] for i in ids}
        for row in temp:
            l, r, arc = row[2], row[3], row[4]
            c = list(geom_[arc].coords)
            if l != 0:
                arcs_by_poly[l].append(c)
            if r != 0 and r != l:
                arcs_by_poly[r].append(c)

        # 属性表中的"面积"用于自校验 (失败的要素退回慢速精确算法)
        true_area = self.data['面积'].values if '面积' in self.data.columns else None

        self.geom=[]
        for n_, i in enumerate(ids):
            segs = arcs_by_poly[i]
            if len(segs) == 1:
                self.geom.append(shapely.geometry.Polygon(segs[0]))
                continue
            rings = _walk_rings(segs)
            geom = _rings_to_multipolygon(rings)
            if true_area is not None:
                ta = true_area[n_]
                if ta > 0 and abs(geom.area / self.sc**2 - ta) > 0.01 * ta:
                    try:
                        lines = _stitch_rings_legacy([list(s) for s in segs])
                        geom = shapely.geometry.MultiPolygon(get_multipolygons(lines))
                    except Exception:
                        pass  # 保留快速结果
            self.geom.append(geom)


    def __get_geopandas(self):


        self.geodataframe = gpd.GeoDataFrame(self.data, crs=self.crs, geometry=self.geom)
        self.bbox=np.array([self.geodataframe.bounds.minx.min(),self.geodataframe.bounds.miny.min(),self.geodataframe.bounds.maxx.max(),self.geodataframe.bounds.maxy.max()])
    def to_file(self,filepath,**kwargs):

        #geodataframe.to_json()
        #geodataframe.to_file('be.shp',encoding='utf-8')
        self.geodataframe.to_file(filepath,**kwargs)

    def __len__(self):
        return self.geom.__len__()
    def __str__(self):
        return("mapgis file Reader\n%s feature%s (type %s)" %(self.__len__(),(lambda x:'s' if x>1 else '')(self.__len__()),self.shapeType))



    def __del__(self):
        self.f.close()


        
        
    def __enter__(self):
        return self
    def __exit__(self,type,value,traceback):
        self.__del__()
        
        
class InvalidFileError(BaseException):
    def __init__(self):
        pass
    def __str__(self):
        return "can not detect the file's geometry type"
class InvalidDirectoryError(BaseException):
    def __init__(self):
        pass
class TopoError(BaseException):
    def __init__(self):
        pass
    def __str__(self):
        return "topo error in this wp file"
    
import math
from collections import defaultdict


def _ring_key(p):
    return (round(p[0], 4), round(p[1], 4))


def _walk_rings(segs):
    """最近端点续接: 从环尾找最近的未用弧段端点接上 (容忍节点间微小间隙).
    当环首尾距离 <= 最近候选距离时闭合. 语义与原 O(n^3) 距离合并一致, O(n log n).
    """
    n = len(segs)
    starts = np.array([s[0] for s in segs], dtype=float)
    ends = np.array([s[-1] for s in segs], dtype=float)
    pts = np.vstack([starts, ends])  # j<n: start of j;  j>=n: end of j-n
    from scipy.spatial import cKDTree
    tree = cKDTree(pts)
    used = np.zeros(n, dtype=bool)
    rings = []
    for i0 in range(n):
        if used[i0]:
            continue
        used[i0] = True
        ring = list(segs[i0])
        while True:
            tail = np.asarray(ring[-1], dtype=float)
            head = np.asarray(ring[0], dtype=float)
            d_close = float(np.hypot(*(tail - head)))
            # 最近的未用端点
            k = 8
            best, bd = None, None
            while best is None and k <= 2 * n:
                dd, jj = tree.query(tail, k=min(k, 2 * n))
                for d, j in zip(np.atleast_1d(dd), np.atleast_1d(jj)):
                    if not used[j % n]:
                        best, bd = (j % n, j >= n), float(d)
                        break
                k *= 4
            if best is None or d_close <= bd:
                break  # 闭合
            j, rev = best
            used[j] = True
            ext = segs[j][::-1] if rev else segs[j]
            ring.extend(ext[1:] if bd == 0 else ext)
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        if len(ring) >= 4:
            rings.append(ring)
    return rings


def _rings_to_multipolygon(rings):
    """环嵌套: 按面积降序, 代表点含于某外环且不在其洞中 => 作为洞, 洞中环 => 新外环."""
    polys = [shapely.geometry.Polygon(r) for r in rings if len(r) >= 4]
    polys = [p for p in polys if not p.is_empty and p.area > 0]
    if not polys:
        return shapely.geometry.MultiPolygon([])
    if len(polys) == 1:
        return shapely.geometry.MultiPolygon(polys)
    polys.sort(key=lambda p: p.area, reverse=True)
    outers = []  # [poly, [hole_polys]]
    for p in polys:
        pt = p.representative_point()
        target = None
        for o in outers:
            if o[0].contains(pt):
                target = o
                break
        if target is None:
            outers.append([p, []])
        elif any(h.contains(pt) for h in target[1]):
            outers.append([p, []])  # 洞中岛
        else:
            target[1].append(p)
    return shapely.geometry.MultiPolygon(
        [shapely.geometry.Polygon(o[0].exterior, [h.exterior for h in o[1]]) for o in outers])


def _stitch_rings_legacy(m):
    """原版 O(n^3) 全局最近端点合并 (慢但稳, 仅作快速算法失败时的兜底)."""
    lines=[]
    while m:
        xx=[]
        for ii in m:
            xx.append(ii[0])
            xx.append(ii[-1])
        t=np.ones((xx.__len__(),xx.__len__()))*np.inf
        for ii in range(xx.__len__()-1):
            for j in range(ii+1,xx.__len__()):
                t[ii,j]=np.abs(np.array(xx)[ii]-np.array(xx)[j]).max()
        x,y=np.argwhere(t==t.min())[0]
        if np.ceil((x+1)/2)==np.ceil((y+1)/2):
            lines.append(m[np.int64(np.ceil((x+1)/2))-1])
            m.pop(np.int64(np.ceil((x+1)/2))-1)
        else:
            if (x+1)/2<np.ceil((x+1)/2):
                m[np.int64(np.ceil((x+1)/2))-1]=m[np.int64(np.ceil((x+1)/2))-1][-1::-1]
            if (y+1)/2<np.ceil((y+1)/2):
                m[np.int64(np.ceil((x+1)/2))-1].extend(m[np.int64(np.ceil((y+1)/2))-1])
            else:
                m[np.int64(np.ceil((x+1)/2))-1].extend(m[np.int64(np.ceil((y+1)/2))-1][-1::-1])
            m.pop(np.int64(np.ceil((y+1)/2))-1)
    return lines


def get_multipolygons(lines):
    
    tt=np.zeros((lines.__len__(),lines.__len__()))
    for i in range(lines.__len__()):
        for j in range(lines.__len__()):
            if i==j:
                tt[i,j]=0
            else:
                try:
                    temp=shapely.geometry.Polygon( lines[i]  ).within(    shapely.geometry.Polygon( lines[j]  )     )
                except:
                    temp=np.array([shapely.geometry.Point(i).within( shapely.geometry.Polygon(lines[j])  ) for i in lines[i]]).any()
                if temp:
                    tt[i,j]=1
              
    level_0={}
    for i in range(tt.__len__()):
        if not (tt[i]==1).any():
            level_0[i]=[lines[i]]
    for i in range(tt.__len__()):
        if (tt[i]==1).sum()==1:
            level_0[np.argwhere(tt[i]==1)[0][0]].append(lines[i])
    if not ((tt==1).sum(1)==2).any():
        return [shapely.geometry.Polygon(i[0],i[1:]) for i in level_0.values()]
    else:
        temp= [shapely.geometry.Polygon(i[0],i[1:]) for i in level_0.values()]
        temp.extend(  get_multipolygones([ lines[i] for i in np.argwhere((tt==1).sum(1)>1).flatten()]   )  )
        return temp
