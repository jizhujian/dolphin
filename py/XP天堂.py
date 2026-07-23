#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XP天堂 全量爬虫（完整移植自 xp天堂.js）
自动保存至手机根目录：/sdcard/videos.json, /sdcard/playlist.m3u, /sdcard/videos.db
"""

import os
import re
import time
import json
import sqlite3
import base64
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from Crypto.Cipher import AES

# ==================== 配置（输出目录为手机根目录） ====================
OUTPUT_DIR = '/sdcard/'                     # 手机根目录（也可改为 '/storage/emulated/0/'）
OUTPUT_JSON = os.path.join(OUTPUT_DIR, 'videos.json')
OUTPUT_M3U = os.path.join(OUTPUT_DIR, 'playlist.m3u')
OUTPUT_DB = os.path.join(OUTPUT_DIR, 'videos.db')

# 原 JS 中的站点列表（保持完全一致）
sites = [
    'https://dzsx5k01kgm6y.cloudfront.net',   # 可直连
    'https://attack.bjidvlyog.com',
    'https://agency.bjidvlyog.com/'
]
baseUrl = sites[0]                           # 默认使用第一个
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ==================== 全局缓存（与原 JS 完全一致） ====================
cachedClasses = []
cachedFilters = {}
hasParsed = False

# ==================== 辅助函数 ====================
def mylog(*args):
    print("[xp天堂18+]", *args)

def req(url, options=None):
    """模拟原 JS 的 req 函数，返回 { content: ... }"""
    if options is None:
        options = {}
    method = options.get('method', 'get').lower()
    headers = options.get('headers', {})
    buffer_mode = options.get('buffer') == 2  # 若为 2 则表示返回二进制数据

    # 默认头
    headers.setdefault('User-Agent', UA)
    headers.setdefault('Referer', baseUrl)

    try:
        if method == 'get':
            resp = requests.get(url, headers=headers, timeout=15)
        elif method == 'post':
            resp = requests.post(url, headers=headers, timeout=15)
        else:
            raise ValueError(f"Unsupported method: {method}")
        resp.raise_for_status()
        if buffer_mode:
            # 返回 base64 编码的二进制内容（原 JS 中 buffer:2 返回 base64）
            content = base64.b64encode(resp.content).decode('utf-8')
        else:
            content = resp.text
        return {'content': content}
    except Exception as e:
        mylog("req error:", e)
        raise

def aesX(algorithm, isEncrypt, data, isBase64, key, iv, outputBase64):
    """
    完整模拟原 JS 的 aesX 函数（仅实现解密模式）
    algorithm: "AES/CBC/No" -> 实际使用 AES-128-CBC
    """
    if isEncrypt:
        raise NotImplementedError("加密模式未实现，仅用于解密")
    # 密钥和 IV 必须是 16 字节
    key_bytes = key.encode('utf-8')
    iv_bytes = iv.encode('utf-8')
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv_bytes)
    if isBase64:
        encrypted_data = base64.b64decode(data)
    else:
        encrypted_data = data.encode('utf-8')  # 假设是字符串
    decrypted = cipher.decrypt(encrypted_data)
    # 去除 PKCS7 填充
    pad_len = decrypted[-1]
    decrypted = decrypted[:-pad_len]
    if outputBase64:
        return base64.b64encode(decrypted).decode('utf-8')
    else:
        return decrypted.decode('utf-8', errors='ignore')

def getRealImgurl(imgurl):
    """完全模拟原 JS 的 getRealImgurl 函数"""
    try:
        if not imgurl:
            return ""
        res = req(imgurl, {
            'method': 'get',
            'headers': {
                'User-Agent': UA,
                'Referer': 'https://wuabeza.gyqspl.cn/'
            },
            'buffer': 2
        })
        encryptedBase64 = res['content']
        if not encryptedBase64:
            return ""
        realImageBase64 = aesX(
            "AES/CBC/No",
            False,
            encryptedBase64,
            True,
            "f5d965df75336270",
            "97b60394abc2fbe1",
            True
        )
        if not realImageBase64:
            return ""
        ext = "jpeg"
        if ".gif" in imgurl.lower():
            ext = "gif"
        elif ".png" in imgurl.lower():
            ext = "png"
        return "data:image/" + ext + ";base64," + realImageBase64
    except Exception as e:
        mylog("getRealImgurl error:", e)
        return ""

def fixVodName(name=""):
    """完全模拟原 JS 的 fixVodName"""
    name = name.strip()
    parts = name.split(" ")
    if len(parts) >= 3:
        return "".join(parts[1:-1])
    return name

# ==================== 核心函数（与原 JS 完全一致） ====================
def home(filter_param=None):
    """模拟原 home 函数，返回 JSON 字符串"""
    global cachedClasses, cachedFilters, hasParsed
    try:
        html = req(baseUrl)['content']
        soup = BeautifulSoup(html, 'html.parser')
        classes = []
        filters = {}

        # 标准排序规则
        sortFilter = [
            {
                "key": "sort",
                "name": "排序",
                "value": [
                    {"n": "最近更新", "v": "update"},
                    {"n": "最高收藏", "v": "favorite"},
                    {"n": "近期最佳", "v": "hot"},
                    {"n": "最多观看", "v": "watch"}
                ]
            }
        ]

        # 解析 .app-nav .container 区块
        containers = soup.select('.app-nav .container')
        for container in containers:
            title_box = container.select_one('.title-box h2')
            blockTitle = title_box.text.strip() if title_box else ""

            # 选片主题块
            if "选片" in blockTitle or "主题" in blockTitle:
                for a in container.select('a.tjtagmanager'):
                    name = a.text.strip()
                    href = a.get('href', '')
                    # 去掉末尾的排序后缀
                    href = re.sub(r'/(favorite|update|hot|watch)/?$', '', href)
                    if href and name:
                        classes.append({"type_id": href, "type_name": name})
                        filters[href] = sortFilter

            # 标签块
            if container.select('a.tag'):
                for a in container.select('a.tag'):
                    name = a.text.strip()
                    href = a.get('href', '')
                    href = re.sub(r'/(favorite|update|hot|watch)/?$', '', href)
                    if href and name:
                        classes.append({"type_id": href, "type_name": "🏷️ " + name})
                        filters[href] = sortFilter

        # 过滤资讯和回家
        cachedClasses = [item for item in classes if "资讯" not in item['type_name'] and "回家" not in item['type_name']]
        cachedFilters = filters
        hasParsed = True

        # 返回 JSON 字符串（与原 JS 一致）
        return json.dumps({
            "class": cachedClasses,
            "filters": homeFilter()
        }, ensure_ascii=False)
    except Exception as e:
        mylog("❌ 全自动解析 class 失败: ", e)
        return json.dumps({"class": []}, ensure_ascii=False)

def homeFilter():
    """模拟原 homeFilter 函数"""
    if hasParsed:
        return cachedFilters
    return {}

def category(tid, pg, filter_param=None, extend=None):
    """模拟原 category 函数，返回 JSON 字符串"""
    try:
        if not tid:
            return json.dumps({"list": []}, ensure_ascii=False)
        pg = pg or 1
        if extend is None:
            extend = {}
        sort = extend.get('sort', '')

        url = f"{baseUrl}{tid}/{sort}/{pg}/"
        mylog(f"🚀 正在请求分类URL: {url}")

        html = req(url)['content']
        soup = BeautifulSoup(html, 'html.parser')
        video_elements = soup.select('.col-6.col-sm-4.col-lg-3')

        # 由于 Python 不支持 async，我们采用同步循环，但保持逻辑与 JS 一致
        list_data = []
        for el in video_elements:
            a_tag = el.select_one('.video-img-box a')
            if not a_tag:
                continue
            href = a_tag.get('href', '')
            if '/videos/' in href:
                vod_id = href
                title_el = el.select_one('.title a')
                vod_name = fixVodName(title_el.text.strip() if title_el else "")
                watch_span = el.select_one('span[class^="interaction_watch_count_"]')
                watch_count = watch_span.text.strip() if watch_span else ""
                vod_remarks = watch_count + "播放" if watch_count else ""
                year_el = el.select_one('.label')
                vod_year = year_el.text.strip() if year_el else ""
                img_el = el.select_one('img.zximg')
                img_url = img_el.get('z-image-loader-url', '') if img_el else ""
                vod_pic = getRealImgurl(img_url)

                list_data.append({
                    "vod_id": vod_id,
                    "vod_name": vod_name,
                    "vod_pic": vod_pic,
                    "vod_year": vod_year,
                    "vod_remarks": vod_remarks,
                    "land": 1,
                    "ratio": 1.78
                })

        # 分页信息
        pager = soup.select_one('ul.dx-pager')
        total = int(pager.get('data-rec-total', 0)) if pager else 0
        perPage = int(pager.get('data-rec-per-page', 20)) if pager else 20
        pagecount = (total + perPage - 1) // perPage if total > 0 else 1

        mylog(f"category 成功获取视频数: {len(list_data)}")
        return json.dumps({"list": list_data, "pagecount": pagecount}, ensure_ascii=False)
    except Exception as e:
        mylog(e)
        return json.dumps({"list": []}, ensure_ascii=False)

def detail(vid):
    """模拟原 detail 函数，返回 JSON 字符串"""
    try:
        url = baseUrl + vid
        html = req(url)['content']
        soup = BeautifulSoup(html, 'html.parser')

        vod_name_el = soup.select_one('h1.my-foldable-content')
        vod_name = vod_name_el.text.strip() if vod_name_el else ""

        player = soup.select_one('#player')
        vod_pic = player.get('data-src', '') if player else ""
        vod_pic = getRealImgurl(vod_pic)

        # 提取标签
        tags = []
        for a in soup.select('h5.tags a'):
            tag = a.text.strip()
            if tag:
                tags.append(tag)
        vod_actor = '/'.join(tags)
        vod_class = ' '.join(tags)

        # 构造简介（含标签快捷搜索）
        vod_content = "(todo)标签快捷搜索：\n"
        for tag in tags:
            vod_content += f'[a=cr:{{"action":"category","key":"{tag}"}}/]【{tag}】[/a]   '

        # 提取 m3u8
        pattern = r'https?://[^\s"\'`]+\.m3u8(?:\?[^\s"\'`]*)?'
        match = re.search(pattern, html)
        hlsUrl = match.group(0) if match else ""

        lines = ["hls线路"]
        vod_play_from = "$$$".join(lines)
        playlistArray = [f"正片${hlsUrl}"]
        vod_play_url = "$$$".join(playlistArray)

        watch_span = soup.select_one('.video-info span[class^="interaction_watch_count_"]')
        watch_count = watch_span.text.strip().upper() if watch_span else ""
        fav_span = soup.select_one('#bind_collect_count')
        fav_count = fav_span.text.strip().upper() if fav_span else ""
        vod_remarks = watch_count + "播放" if watch_count else ""
        if fav_count:
            vod_remarks += " | " + fav_count + "收藏"

        back = {
            "vod_id": vid,
            "vod_remarks": vod_remarks,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_content": vod_content,
            "vod_actor": vod_actor,
            "vod_class": vod_class,
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url,
            "play_url": hlsUrl   # 额外字段，方便生成 M3U
        }

        return json.dumps({"list": [back]}, ensure_ascii=False)
    except Exception as e:
        mylog(e)
        return json.dumps({"list": []}, ensure_ascii=False)

def play(flag, id, vipFlags):
    """模拟原 play 函数，返回 JSON 字符串"""
    return json.dumps({
        "parse": 0,
        "url": id,
        "header": {"User-Agent": UA, "Referer": baseUrl}
    }, ensure_ascii=False)

def search(key, quick, page):
    """模拟原 search 函数（保留，但爬虫主流程不使用）"""
    try:
        page = page or 1
        url = f"{baseUrl}/search/{key}/{page}/"
        mylog(f"正在搜索: {url}")
        html = req(url)['content']
        soup = BeautifulSoup(html, 'html.parser')
        search_elements = soup.select('.video-img-box')
        list_data = []
        for el in search_elements:
            a_tag = el.select_one('.img-box > a')
            if not a_tag:
                continue
            vod_id = a_tag.get('href', '')
            img_el = a_tag.select_one('img')
            vod_name = img_el.get('alt', '') if img_el else ''
            img_url = img_el.get('z-image-loader-url', '') if img_el else ''
            vod_pic = getRealImgurl(img_url)
            remarks_el = el.select_one('.absolute-bottom-right .label')
            vod_remarks = remarks_el.text.strip() if remarks_el else ''
            list_data.append({
                "vod_id": vod_id,
                "vod_name": fixVodName(vod_name),
                "vod_pic": vod_pic,
                "vod_remarks": vod_remarks
            })
        pager = soup.select_one('ul.dx-pager')
        total = int(pager.get('data-rec-total', 0)) if pager else 0
        perPage = int(pager.get('data-rec-per-page', 20)) if pager else 20
        pagecount = (total + perPage - 1) // perPage if total > 0 else 1
        return json.dumps({"list": list_data, "pagecount": pagecount}, ensure_ascii=False)
    except Exception as e:
        mylog(e)
        return json.dumps({"list": []}, ensure_ascii=False)

# ==================== 爬虫主流程（自动实时保存） ====================
def crawl_all():
    # 确保输出目录存在（手机根目录通常存在，但为了安全）
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 初始化文件（清空）
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump([], f, ensure_ascii=False, indent=2)
    with open(OUTPUT_M3U, 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')

    # 初始化 SQLite 数据库
    conn = sqlite3.connect(OUTPUT_DB)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS videos (
            id TEXT PRIMARY KEY,
            name TEXT,
            pic TEXT,
            content TEXT,
            actor TEXT,
            class TEXT,
            play_from TEXT,
            play_url TEXT,
            play_m3u8 TEXT,
            category_name TEXT,
            category_id TEXT,
            crawl_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

    # 1. 获取分类
    home_result = home()
    parsed = json.loads(home_result)
    classes = parsed.get('class', [])
    if not classes:
        mylog("❌ 未获取到分类，退出")
        return
    mylog(f"✅ 获取到 {len(classes)} 个分类")

    total = 0
    failed = []

    # 2. 遍历分类
    for cls in classes:
        tid = cls['type_id']
        name = cls['type_name']
        mylog(f"\n📂 处理分类: {name} ({tid})")

        page = 1
        while True:
            mylog(f"   📄 请求第 {page} 页...")
            cat_result = category(tid, page, None, {})
            cat_data = json.loads(cat_result)
            video_list = cat_data.get('list', [])
            pagecount = cat_data.get('pagecount', 0)

            if not video_list:
                break

            for video in video_list:
                vid = video['vod_id']
                try:
                    # 获取详情
                    detail_result = detail(vid)
                    detail_data = json.loads(detail_result)
                    detail_list = detail_data.get('list', [])
                    if not detail_list:
                        failed.append(vid)
                        continue
                    full_info = detail_list[0]
                    # 补充分类信息
                    full_info['category_name'] = name
                    full_info['category_id'] = tid

                    # ---- 实时保存 JSON ----
                    with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
                        current = json.load(f)
                    current.append(full_info)
                    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
                        json.dump(current, f, ensure_ascii=False, indent=2)

                    # ---- 实时保存 M3U ----
                    if full_info.get('play_url'):
                        with open(OUTPUT_M3U, 'a', encoding='utf-8') as f:
                            f.write(f"#EXTINF:-1,{full_info['vod_name']}\n")
                            f.write(f"{full_info['play_url']}\n")

                    # ---- 实时保存 SQLite ----
                    c.execute('''
                        INSERT OR REPLACE INTO videos (
                            id, name, pic, content, actor, class,
                            play_from, play_url, play_m3u8,
                            category_name, category_id
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    ''', (
                        full_info['vod_id'],
                        full_info['vod_name'],
                        full_info['vod_pic'],
                        full_info['vod_content'],
                        full_info['vod_actor'],
                        full_info['vod_class'],
                        full_info['vod_play_from'],
                        full_info['vod_play_url'],
                        full_info.get('play_url', ''),
                        full_info['category_name'],
                        full_info['category_id']
                    ))
                    conn.commit()

                    total += 1
                    mylog(f"   ✅ 已保存: {full_info['vod_name']} (累计 {total})")
                except Exception as e:
                    mylog(f"   ❌ 处理视频 {vid} 失败: {e}")
                    failed.append(vid)

                # 请求间隔（避免过快）
                time.sleep(0.3)

            if page >= pagecount:
                break
            page += 1

    conn.close()
    mylog(f"\n🎉 爬取完成！共 {total} 个视频。")
    if failed:
        mylog(f"⚠️ 以下视频详情获取失败: {failed[:10]} ...")
        with open(os.path.join(OUTPUT_DIR, 'failed_ids.json'), 'w', encoding='utf-8') as f:
            json.dump(failed, f, ensure_ascii=False, indent=2)
    mylog(f"📁 数据已保存至:\n  {OUTPUT_JSON}\n  {OUTPUT_M3U}\n  {OUTPUT_DB}")

# ==================== 入口 ====================
if __name__ == '__main__':
    crawl_all()