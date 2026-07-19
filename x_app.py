import os
import requests
import json
import re
import subprocess
from datetime import datetime, timezone, timedelta

# ================= 配置區 =================
BASE_DIR = "docs"
tz_utc_8 = timezone(timedelta(hours=8))
AUTO_PUSH_GITHUB = True  # 開啟 Python 端自動 Push 到 GitHub 的功能
# ==========================================

def get_user_tweet_ids(username, limit=10):
    """通過公開 Syndication API 或備用 RSS 獲取用戶最新原創推文 ID"""
    print(f"⏳ 正在解析 @{username} 的時間線...")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}"
        res = requests.get(url, headers=headers, timeout=10)
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', res.text)
        if match:
            data = json.loads(match.group(1))
            entries = data.get('props', {}).get('pageProps', {}).get('timeline', {}).get('entries', [])
            tweet_ids = []
            for entry in entries:
                tweet = entry.get('content', {}).get('tweet', {})
                tweet_id = tweet.get('id_str')
                screen_name = tweet.get('user', {}).get('screen_name', '')
                if tweet_id and screen_name.lower() == username.lower() and tweet_id not in tweet_ids:
                    tweet_ids.append(tweet_id)
            if tweet_ids:
                return tweet_ids[:limit]
    except Exception as e:
        print(f"⚠️ 解析主節點失敗: {e}")
    
    print("⏳ 嘗試使用備用 RSS 節點解析...")
    try:
        rss_url = f"https://rsshub.rssforever.com/twitter/user/{username}/exclude_rts_replies"
        res = requests.get(rss_url, headers=headers, timeout=10)
        ids = re.findall(r'status/(\d+)', res.text)
        seen = set()
        tweet_ids = [x for x in ids if not (x in seen or seen.add(x))]
        return tweet_ids[:limit]
    except Exception as e:
        print(f"❌ 備用節點解析失敗: {e}")
    
    return []

def generate_tweet_card(tweet_data, tweet_id):
    """生成單個推文卡片的 HTML 結構 (包含批注區)"""
    author = tweet_data.get('user_name', 'Unknown')
    handle = tweet_data.get('user_screen_name', 'unknown')
    text = tweet_data.get('text', '')
    likes = tweet_data.get('likes', 0)
    retweets = tweet_data.get('retweets', 0)
    
    media_extended = tweet_data.get('media_extended', [])
    media_urls = tweet_data.get('mediaURLs', [])
    original_url = f"https://x.com/{handle}/status/{tweet_id}"

    media_html = ""
    if media_extended:
        for media in media_extended:
            m_type = media.get('type')
            m_url = media.get('url', '')
            if m_type in ['video', 'gif']:
                poster = media.get('thumbnail_url', '')
                media_html += f'<div class="media-container"><video controls src="{m_url}" poster="{poster}" class="media-item" preload="metadata" playsinline></video></div>'
            else:
                media_html += f'<div class="media-container"><img src="{m_url}" class="media-item" loading="lazy"></div>'
    elif media_urls:
        for m_url in media_urls:
            if '.mp4' in m_url:
                media_html += f'<div class="media-container"><video controls src="{m_url}" class="media-item" preload="metadata" playsinline></video></div>'
            else:
                media_html += f'<div class="media-container"><img src="{m_url}" class="media-item" loading="lazy"></div>'

    return f"""
        <div class="tweet-card">
            <div class="header">
                <div class="names">
                    <span class="name">{author}</span>
                    <span class="handle">@{handle}</span>
                </div>
            </div>
            <div class="content">{text}</div>
            {media_html}
            <div class="anno-section para-wrap">
                <span class="anno-toggle"></span>
                <span class="sync-status">📡 同步中...</span>
                <div class="anno-box">
                    <div class="anno-view markdown-body"></div>
                    <textarea class="anno-edit" placeholder="支援 Markdown，雙擊預覽區或點擊空白處保存..."></textarea>
                </div>
            </div>
            <div class="stats">
                <span>❤️ {likes:,} 喜歡</span>
                <span>🔁 {retweets:,} 轉發</span>
            </div>
            <a href="{original_url}" target="_blank" class="btn-link">🔗 前往 X 查看原文及評論</a>
        </div>"""

def generate_page_wrapper(content_html, page_title, now_str):
    """生成完整 HTML 頁面外殼 (集成翻譯與批注引擎)"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="referrer" content="no-referrer">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{page_title}</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        :root {{ --bg: #f2f2f7; --card: #ffffff; --text: #0f1419; --muted: #536471; --border: #eff3f4; --x-blue: #1d9bf0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); margin: 0; padding: 0; -webkit-font-smoothing: antialiased; }}
        .nav-back {{ display: flex; justify-content: space-between; align-items: center; padding: 15px 20px; background: var(--card); border-bottom: 1px solid #eee; position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
        .nav-back a {{ text-decoration: none; color: white; background: #000; padding: 8px 20px; border-radius: 20px; font-weight: bold; font-size: 0.9rem; flex-shrink: 0; }}
        .translate-btn {{ background: #f2f2f7; color: #0f1419; border: 1px solid #ccc; padding: 8px 15px; border-radius: 20px; font-weight: bold; font-size: 0.9rem; cursor: pointer; transition: 0.2s; flex-shrink: 0; outline: none; }}
        .translate-btn:active {{ background: #e5e5ea; transform: scale(0.95); }}
        .translate-btn[disabled] {{ opacity: 0.8; cursor: not-allowed; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px 15px 50px 15px; }}
        .tweet-card {{ background: var(--card); border-radius: 16px; padding: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); margin-bottom: 25px; }}
        .header {{ display: flex; align-items: center; margin-bottom: 12px; }}
        .names {{ display: flex; flex-direction: column; }}
        .name {{ font-weight: 700; font-size: 1.1rem; color: var(--text); }}
        .handle {{ color: var(--muted); font-size: 0.95rem; margin-top: 2px; }}
        .content {{ font-size: 1.1rem; color: var(--text); line-height: 1.5; white-space: pre-wrap; word-wrap: break-word; margin-bottom: 15px; }}
        .media-container {{ margin-top: 10px; border-radius: 16px; overflow: hidden; border: 1px solid var(--border); margin-bottom: 10px; background: #000; }}
        .media-item {{ width: 100%; height: auto; display: block; max-height: 500px; object-fit: contain; }}
        .stats {{ margin-top: 15px; color: var(--muted); font-size: 0.95rem; border-top: 1px solid var(--border); padding-top: 15px; display: flex; gap: 20px; font-weight: 500; margin-bottom: 15px; }}
        .btn-link {{ display: block; background: var(--x-blue); color: #fff; text-align: center; padding: 12px; border-radius: 24px; text-decoration: none; font-weight: 700; font-size: 1rem; transition: transform 0.2s; }}
        .btn-link:active {{ transform: scale(0.98); background: #1a8cd8; }}
        .time-stamp {{ text-align: center; color: var(--muted); font-size: 0.85rem; margin-bottom: 15px; font-weight: 600; }}
        
        /* 批注區樣式 */
        .anno-section {{ margin-top: 15px; border-top: 1px dashed var(--border); padding-top: 12px; }}
        .anno-toggle {{ display: inline-block; cursor: pointer; color: var(--muted); font-size: 0.9rem; font-weight: bold; user-select: none; transition: 0.2s; }}
        .anno-toggle:hover {{ color: var(--x-blue); }}
        .anno-toggle.has-anno {{ color: var(--x-blue); }}
        .anno-toggle::before {{ content: "📝 寫筆記 / 批注"; }}
        .anno-toggle.has-anno::before {{ content: "📝 查看批注"; }}
        .sync-status {{ display: none; margin-left: 10px; font-size: 0.8rem; padding: 2px 8px; border-radius: 10px; color: white; background: #f39c12; vertical-align: middle; box-shadow: 0 2px 6px rgba(0,0,0,0.1); }}
        .anno-box {{ display: none; margin-top: 10px; background: #f8f9fa; border-left: 4px solid var(--x-blue); padding: 12px; border-radius: 0 8px 8px 0; }}
        .anno-view {{ font-size: 1rem; color: #333; line-height: 1.5; min-height: 24px; cursor: pointer; }}
        .anno-edit {{ width: 100%; min-height: 100px; padding: 10px; font-family: monospace; font-size: 0.95rem; border: 1px dashed var(--x-blue); border-radius: 6px; box-sizing: border-box; resize: vertical; display: none; outline: none; }}
        .anno-edit:focus {{ border-style: solid; box-shadow: 0 0 0 2px rgba(29,155,240,0.1); }}
        
        /* Markdown 渲染優化 */
        .markdown-body p {{ margin: 0 0 8px 0; }}
        .markdown-body p:last-child {{ margin-bottom: 0; }}
        .markdown-body a {{ color: var(--x-blue); text-decoration: none; }}
        .markdown-body a:hover {{ text-decoration: underline; }}
        .markdown-body blockquote {{ margin: 0 0 10px 0; padding: 10px 15px; background: rgba(29,155,240,0.05); border-left: 4px solid var(--x-blue); color: #555; }}
    </style>
</head>
<body>
    <div class="nav-back">
        <a href="../../index.html">🔙 返回</a>
        <button class="translate-btn" id="translate-btn" onclick="translateAll()">🌐 翻譯</button>
    </div>
    <div class="container">
        <div class="time-stamp">歸檔時間: {now_str}</div>
        {content_html}
    </div>
    
    <script>
        // ---------------- 翻譯邏輯 ----------------
        async function translateAll() {{
            const btn = document.getElementById('translate-btn');
            if(btn.hasAttribute('disabled')) return;
            btn.innerText = '⏳ 處理中...';
            btn.setAttribute('disabled', 'true');

            let translatedCount = 0;
            const contents = document.querySelectorAll('.content');
            
            for (let i = 0; i < contents.length; i++) {{
                const content = contents[i];
                if (content.getAttribute('data-translated') === 'true') continue;
                
                const originalText = content.innerText;
                if (!originalText.trim()) continue;

                let lines = originalText.split('\\n');
                let cleanedLines = [];
                for(let j=0; j<lines.length; j++) {{
                    let words = lines[j].split(' ');
                    let cleanWords = [];
                    for(let k=0; k<words.length; k++) {{
                        if(words[k].indexOf('http') !== 0) {{
                            cleanWords.push(words[k]);
                        }}
                    }}
                    cleanedLines.push(cleanWords.join(' '));
                }}
                let textToTranslate = cleanedLines.join('\\n');

                textToTranslate = textToTranslate.replace(/[\\uD800-\\uDBFF][\\uDC00-\\uDFFF]/g, '').trim();
                const hasWords = /[a-zA-Z0-9\\u4E00-\\u9FA5\\u3040-\\u30FF\\u0400-\\u04FF]/.test(textToTranslate);

                if (!textToTranslate || !hasWords) {{
                    content.setAttribute('data-translated', 'true');
                    continue; 
                }}

                try {{
                    const url = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-CN&dt=t&q=' + encodeURIComponent(textToTranslate);
                    const res = await fetch(url);
                    const data = await res.json();
                    let translatedText = '';
                    if (data && data[0]) {{
                        data[0].forEach(item => {{ if (item[0]) translatedText += item[0]; }});
                    }}

                    if (translatedText.trim()) {{
                        const transDiv = document.createElement('div');
                        transDiv.className = 'translated-content';
                        transDiv.style.cssText = 'color: #0f1419; font-size: 1.1rem; margin-top: 10px; padding-top: 10px; border-top: 1px solid #eff3f4; white-space: pre-wrap; word-wrap: break-word;';
                        transDiv.innerText = translatedText.trim();
                        
                        content.parentNode.insertBefore(transDiv, content.nextSibling);
                        content.setAttribute('data-translated', 'true');
                        translatedCount++;
                    }}
                }} catch (e) {{
                    console.error('翻譯失敗:', e);
                }}
            }}
            
            if (translatedCount === 0) {{
                btn.innerText = '✅ 已全部翻譯';
                return;
            }}

            btn.innerText = '⏳ 固化至雲端...';
            await snapshotAndSync(btn, '✅ 翻譯已固化', '⚠️ 僅本地翻譯');
        }}

        // ---------------- 批注與同步邏輯 ----------------
        function escapeHTML(str) {{
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
        }}

        let syncTimeout = null;

        function initAnnotations() {{
            document.querySelectorAll('.para-wrap').forEach(wrap => {{
                const view = wrap.querySelector('.anno-view');
                const edit = wrap.querySelector('.anno-edit');
                const toggle = wrap.querySelector('.anno-toggle');
                const box = wrap.querySelector('.anno-box');
                const status = wrap.querySelector('.sync-status');

                const rawText = edit.value.trim();
                if (rawText) {{
                    toggle.classList.add('has-anno');
                    if (typeof marked !== 'undefined') view.innerHTML = marked.parse(rawText);
                }}

                toggle.onclick = () => {{
                    if (box.style.display === 'block') {{
                        box.style.display = 'none';
                    }} else {{
                        box.style.display = 'block';
                        if (!edit.value.trim()) {{
                            view.style.display = 'none';
                            edit.style.display = 'block';
                            edit.focus();
                        }} else {{
                            view.style.display = 'block';
                            edit.style.display = 'none';
                        }}
                    }}
                }};

                const triggerEdit = () => {{
                    view.style.display = 'none';
                    edit.style.display = 'block';
                    edit.focus();
                }};

                view.addEventListener('dblclick', triggerEdit);
                
                let lastTap = 0;
                view.addEventListener('touchstart', e => {{
                    const currentTime = new Date().getTime();
                    const tapLength = currentTime - lastTap;
                    if (tapLength < 500 && tapLength > 0) {{
                        triggerEdit();
                        e.preventDefault();
                    }}
                    lastTap = currentTime;
                }}, {{passive: false}});

                edit.onblur = () => {{
                    const newVal = edit.value.trim();
                    edit.innerHTML = escapeHTML(newVal); 

                    try {{ view.innerHTML = newVal ? marked.parse(newVal) : ''; }} catch(e){{}}
                    edit.style.display = 'none';

                    if (newVal) {{
                        view.style.display = 'block';
                        toggle.classList.add('has-anno');
                    }} else {{
                        view.style.display = 'none';
                        box.style.display = 'none';
                        toggle.classList.remove('has-anno');
                    }}

                    if (edit.getAttribute('data-old-val') !== newVal) {{
                        edit.setAttribute('data-old-val', newVal);
                        scheduleAnnoSync(status);
                    }}
                }};
                edit.setAttribute('data-old-val', rawText);
            }});
        }}
        
        window.addEventListener('DOMContentLoaded', initAnnotations);

        function scheduleAnnoSync(statusEl) {{
            statusEl.style.display = 'inline-block';
            statusEl.style.backgroundColor = '#f39c12';
            statusEl.innerText = '⏳ 5秒後同步...';

            if (syncTimeout) clearTimeout(syncTimeout);
            syncTimeout = setTimeout(() => {{
                snapshotAndSync(statusEl, '✅ 已同步', '❌ 同步失敗', true);
            }}, 5000);
        }}

        // ---------------- 共用 DOM 快照與上傳函數 ----------------
        async function snapshotAndSync(uiElement, successText, failText, isStatusLabel = false) {{
            const ghToken = localStorage.getItem('GH_TOKEN');
            const ghOwner = localStorage.getItem('GH_OWNER');
            const ghRepo = localStorage.getItem('GH_REPO');
            
            if (!ghToken || !ghOwner || !ghRepo) {{
                uiElement.innerText = '❌ 缺Token';
                if(isStatusLabel) uiElement.style.backgroundColor = '#e74c3c';
                return;
            }}

            if (isStatusLabel) {{
                uiElement.style.backgroundColor = '#2ea44f';
                uiElement.innerText = '📡 同步中...';
            }}

            try {{
                const pathParts = window.location.pathname.split('/');
                const fileName = pathParts.pop();
                const month = pathParts.pop();
                const year = pathParts.pop();
                const fileRelPath = year + '/' + month + '/' + fileName;

                if (!isStatusLabel) {{
                    uiElement.innerText = successText;
                    uiElement.style.cssText = 'background: #e8f5fd; color: #1d9bf0; border: 1px solid #1d9bf0;';
                }}
                
                const htmlSnapshot = '<!DOCTYPE html><html lang="zh-CN">' + document.documentElement.innerHTML + '</html>';

                const fileRes = await fetch('https://api.github.com/repos/' + ghOwner + '/' + ghRepo + '/contents/docs/' + fileRelPath + '?t=' + Date.now(), {{ headers: {{ 'Authorization': 'Bearer ' + ghToken }}, cache: 'no-store' }});
                if (fileRes.ok) {{
                    const fileData = await fileRes.json();
                    await fetch('https://api.github.com/repos/' + ghOwner + '/' + ghRepo + '/contents/docs/' + fileRelPath, {{
                        method: 'PUT',
                        headers: {{ 'Authorization': 'Bearer ' + ghToken, 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ 
                            message: 'Auto-solidify DOM snapshot for ' + fileName, 
                            content: btoa(unescape(encodeURIComponent(htmlSnapshot))),
                            sha: fileData.sha
                        }})
                    }});
                }}

                if (isStatusLabel) {{
                    uiElement.innerText = successText;
                    setTimeout(() => {{ if(uiElement.innerText === successText) uiElement.style.display = 'none'; }}, 3000);
                }}

            }} catch(e) {{
                console.error('固化失敗', e);
                uiElement.innerText = failText;
                if (isStatusLabel) {{
                    uiElement.style.backgroundColor = '#e74c3c';
                    uiElement.style.cursor = 'pointer';
                    uiElement.onclick = () => snapshotAndSync(uiElement, successText, failText, true);
                }}
            }}
        }}
    </script>
</body>
</html>"""

def save_single_tweet_local(tweet_id, now_obj):
    api_url = f"https://api.vxtwitter.com/Twitter/status/{tweet_id}"
    try:
        res = requests.get(api_url, timeout=15).json()
        if 'error' in res:
            return False
        
        year_str, month_str = str(now_obj.year), str(now_obj.month)
        target_dir = os.path.join(BASE_DIR, year_str, month_str)
        os.makedirs(target_dir, exist_ok=True)

        time_hms = now_obj.strftime('%H%M%S')
        filename = f"{now_obj.year}_{now_obj.month}_{now_obj.day}_{time_hms}_{tweet_id}_x.html"
        html_path = os.path.join(target_dir, filename)
        now_str = now_obj.strftime("%Y-%m-%d %H:%M")

        card_html = generate_tweet_card(res, tweet_id)
        page_html = generate_page_wrapper(card_html, f"Tweet by {res.get('user_name', 'Unknown')}", now_str)

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(page_html)
        return True
    except Exception:
        return False

def save_batch_tweets_local(username, tweet_ids, now_obj):
    year_str, month_str = str(now_obj.year), str(now_obj.month)
    target_dir = os.path.join(BASE_DIR, year_str, month_str)
    os.makedirs(target_dir, exist_ok=True)

    time_hms = now_obj.strftime('%H%M%S')
    filename = f"{now_obj.year}_{now_obj.month}_{now_obj.day}_{time_hms}_batch_{username}_x.html"
    html_path = os.path.join(target_dir, filename)
    now_str = now_obj.strftime("%Y-%m-%d %H:%M")

    cards_html = ""
    success_count = 0

    for tid in tweet_ids:
        api_url = f"https://api.vxtwitter.com/Twitter/status/{tid}"
        try:
            res = requests.get(api_url, timeout=10).json()
            if 'error' not in res:
                cards_html += generate_tweet_card(res, tid)
                success_count += 1
        except Exception:
            pass

    if success_count == 0:
        return False

    page_html = generate_page_wrapper(cards_html, f"Tweets by @{username}", now_str)

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(page_html)
    return True


def generate_index():
    archive_data = {}
    if os.path.exists(BASE_DIR):
        years = [d for d in os.listdir(BASE_DIR) if d.isdigit()]
        for year in years:
            months = [d for d in os.listdir(os.path.join(BASE_DIR, year)) if d.isdigit()]
            for month in months:
                files = sorted([f for f in os.listdir(os.path.join(BASE_DIR, year, month)) if f.endswith('.html')], reverse=True)
                for file in files:
                    try:
                        parts = file.replace(".html", "").split('_')
                        if len(parts) >= 4:
                            f_year = str(int(parts[0]))
                            f_month = str(int(parts[1]))
                            f_day = str(int(parts[2]))
                            time_str = f"{parts[3][:2]}:{parts[3][2:4]}"
                            file_path = f"{year}/{month}/{file}"
                            
                            if "batch" in file:
                                username = file.split('_batch_')[1].replace('_x.html', '')
                                title = f"🐦 {time_str} 推文集：@{username}"
                            else:
                                title = f"🐦 {time_str} 靈感推文"

                            if f_year not in archive_data: archive_data[f_year] = {}
                            if f_month not in archive_data[f_year]: archive_data[f_year][f_month] = {}
                            if f_day not in archive_data[f_year][f_month]: archive_data[f_year][f_month][f_day] = []

                            archive_data[f_year][f_month][f_day].append({
                                "time": time_str,
                                "path": file_path,
                                "title": title
                            })
                    except Exception:
                        pass

    json_data = json.dumps(archive_data)

    html_template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>X 語料日曆樞紐</title>
    <style>
        :root { --bg: #f5f5f7; --text: #333; --muted: #888; --primary: #1d9bf0; --border: #e0e0e0; --card: #fff; }
        body, html { font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif; -webkit-font-smoothing: antialiased; background: var(--bg); margin: 0; padding: 0; color: var(--text); }
        .container { max-width: 600px; margin: 0 auto; padding-bottom: 20px; }
        
        .manual-fetch-bar { background: var(--card); padding: 12px 15px; display: flex; gap: 10px; align-items: center; border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 20; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        .fetch-input { flex: 1; padding: 10px 15px; border: 1px solid #ccc; border-radius: 20px; font-size: 14px; outline: none; background: #f9f9f9; transition: border 0.2s; }
        .fetch-input:focus { border-color: var(--primary); background: #fff; }
        .settings-btn { background: none; border: none; font-size: 20px; cursor: pointer; padding: 5px; }
        
        .modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 100; justify-content: center; align-items: center; padding: 20px; }
        .modal-content { background: var(--card); border-radius: 16px; padding: 20px; width: 100%; max-width: 400px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
        .modal-title { margin: 0 0 15px 0; font-size: 18px; font-weight: bold; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 5px; font-weight: bold; }
        .form-group input { width: 100%; box-sizing: border-box; padding: 10px; border: 1px solid #ddd; border-radius: 8px; font-size: 14px; outline: none; }
        .modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
        .btn { padding: 8px 16px; border-radius: 8px; border: none; font-size: 14px; font-weight: bold; cursor: pointer; }
        .btn-cancel { background: #eee; color: #333; }
        .btn-save { background: var(--primary); color: #fff; }
        
        .controls { background: var(--bg); padding: 15px 20px; display: flex; justify-content: center; align-items: center; gap: 8px; border-bottom: 1px solid var(--border); }
        .control-btn { background: var(--primary); color: #fff; border: none; border-radius: 6px; padding: 8px 12px; font-size: 14px; cursor: pointer; font-weight: bold; transition: all 0.2s; }
        .control-btn:active { opacity: 0.8; transform: scale(0.95); }
        .select-box { padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px; font-size: 15px; background: #fff; outline: none; font-weight: bold; cursor: pointer; }
        .calendar-wrapper { background: var(--card); padding: 15px; margin-bottom: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.02); }
        .weekdays { display: grid; grid-template-columns: repeat(7, 1fr); text-align: center; font-weight: bold; font-size: 13px; color: var(--muted); margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid #f0f0f0; }
        .days-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 5px; }
        .day-cell { aspect-ratio: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; font-size: 16px; font-weight: 600; border-radius: 10px; cursor: pointer; position: relative; transition: all 0.2s; }
        .day-cell.empty { visibility: hidden; }
        .day-cell.has-news { color: var(--text); }
        .day-cell.no-news { color: #ccc; }
        .day-cell.selected { background: #e8f5fd; border: 1px solid var(--primary); color: var(--primary); font-weight: bold; }
        .day-cell.today { background: #f0f0f0; color: #333; }
        .dot { width: 5px; height: 5px; background-color: var(--primary); border-radius: 50%; position: absolute; bottom: 6px; display: none; }
        .day-cell.has-news .dot { display: block; }
        .news-section { padding: 0 15px; }
        
        .news-item-wrapper { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
        .news-item { flex: 1; background: var(--card); border-radius: 14px; padding: 18px 16px; margin-bottom: 0; display: flex; justify-content: space-between; align-items: center; text-decoration: none; color: var(--text); box-shadow: 0 2px 8px rgba(0,0,0,0.03); border-left: 4px solid var(--primary); transition: all 0.2s; overflow: hidden; }
        .news-item:active { transform: scale(0.98); background: #fafafa; }
        .news-title { font-size: 15px; color: #333; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: left; font-weight: bold; flex: 1; }
        .delete-btn { background: #ff3b30; color: white; border: none; border-radius: 10px; padding: 0 15px; height: 54px; font-size: 16px; cursor: pointer; display: none; transition: all 0.2s; flex-shrink: 0; }
        
        .empty-state { text-align: center; padding: 40px 20px; color: var(--muted); font-size: 14px; background: var(--card); border-radius: 14px; }
        
        #loadingBar { height: 3px; background: var(--primary); width: 0%; transition: width 0.3s; position: absolute; top: 0; left: 0; z-index: 30; }
    </style>
</head>
<body>
    <div id="loadingBar"></div>
    <div class="manual-fetch-bar">
        <input type="text" id="xUrlInput" class="fetch-input" placeholder="粘貼推文或帳號鏈接，回車歸檔..." autocomplete="off">
        <button class="settings-btn" id="openSettingsBtn">⚙️</button>
    </div>

    <div class="modal-overlay" id="settingsModal">
        <div class="modal-content">
            <h3 class="modal-title">GitHub 雲端同步配置</h3>
            <p style="font-size:12px; color:#888; margin-top:-10px; margin-bottom:15px;">只需填寫 GitHub Token，即可在網頁端直接同步推文。</p>
            <div class="form-group"><label>GitHub Personal Access Token</label><input type="password" id="cfgGhToken" placeholder="ghp_..."></div>
            <div class="form-group"><label>GitHub 用戶名</label><input type="text" id="cfgGhOwner" value="moodHappy" placeholder="例如: moodHappy"></div>
            <div class="form-group"><label>GitHub 倉庫名</label><input type="text" id="cfgGhRepo" placeholder="例如: x-vibe"></div>
            <div class="modal-actions">
                <button class="btn btn-cancel" id="closeSettingsBtn">取消</button>
                <button class="btn btn-save" id="saveSettingsBtn">保存配置</button>
            </div>
        </div>
    </div>

    <div class="container">
        <div class="controls">
            <button class="control-btn" id="prevBtn">&lt;</button>
            <select class="select-box" id="yearSelect"></select>
            <select class="select-box" id="monthSelect">
                <option value="1">01月</option><option value="2">02月</option><option value="3">03月</option>
                <option value="4">04月</option><option value="5">05月</option><option value="6">06月</option>
                <option value="7">07月</option><option value="8">08月</option><option value="9">09月</option>
                <option value="10">10月</option><option value="11">11月</option><option value="12">12月</option>
            </select>
            <button class="control-btn" id="nextBtn">&gt;</button>
            <button class="control-btn" id="todayBtn">今天</button>
        </div>
        <div class="calendar-wrapper">
            <div class="weekdays"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div>
            <div class="days-grid" id="daysGrid"></div>
        </div>
        <div class="news-section"><div id="newsList"></div></div>
    </div>

    <script>
        const archiveData = /*DATA_START*/REPLACEME_JSON_DATA/*DATA_END*/;
        const today = new Date();
        
        const AppState = {
            year: today.getFullYear(),
            month: today.getMonth() + 1,
            day: today.getDate(),
            deleteMode: false
        };

        function initSelects() {
            const yearSelect = document.getElementById('yearSelect');
            yearSelect.innerHTML = '';
            const allYears = new Set(Object.keys(archiveData).map(Number));
            for(let i = -5; i <= 50; i++) allYears.add(today.getFullYear() + i);
            
            Array.from(allYears).sort((a, b) => b - a).forEach(y => { 
                const opt = document.createElement('option'); 
                opt.value = y; opt.textContent = y + ' 年'; yearSelect.appendChild(opt); 
            });
        }

        function forceRender() {
            const maxDay = new Date(AppState.year, AppState.month, 0).getDate();
            if (AppState.day > maxDay) AppState.day = maxDay;

            document.getElementById('yearSelect').value = AppState.year;
            document.getElementById('monthSelect').value = AppState.month;

            const daysGrid = document.getElementById('daysGrid');
            const newsList = document.getElementById('newsList');

            daysGrid.innerHTML = ''; newsList.innerHTML = '';

            try {
                const firstDay = new Date(AppState.year, AppState.month - 1, 1).getDay() || 7;
                for (let i = 1; i < firstDay; i++) { 
                    const emptyCell = document.createElement('div'); 
                    emptyCell.className = 'day-cell empty'; daysGrid.appendChild(emptyCell); 
                }
                
                const monthData = (archiveData[AppState.year] && archiveData[AppState.year][AppState.month]) || {};
                
                for (let day = 1; day <= maxDay; day++) {
                    const cell = document.createElement('div'); cell.className = 'day-cell'; cell.textContent = day;
                    const dot = document.createElement('div'); dot.className = 'dot'; cell.appendChild(dot);
                    
                    if (monthData[day] && monthData[day].length > 0) cell.classList.add('has-news'); else cell.classList.add('no-news');
                    if (AppState.year === today.getFullYear() && AppState.month === today.getMonth() + 1 && day === today.getDate()) cell.classList.add('today');
                    if (day === AppState.day) cell.classList.add('selected');
                    
                    cell.onclick = () => { AppState.day = day; forceRender(); };
                    daysGrid.appendChild(cell);
                }
            } catch (err) { console.error(err); }

            try {
                let dayData = null;
                if (archiveData[AppState.year] && archiveData[AppState.year][AppState.month] && archiveData[AppState.year][AppState.month][AppState.day]) {
                    dayData = archiveData[AppState.year][AppState.month][AppState.day];
                }
                
                if (dayData && Array.isArray(dayData) && dayData.length > 0) {
                    dayData.forEach((news, index) => {
                        const wrapper = document.createElement('div'); wrapper.className = 'news-item-wrapper';
                        const a = document.createElement('a'); a.href = news.path; a.className = 'news-item';
                        
                        a.innerHTML = `<span class="news-title">${news.title}</span>`;
                        wrapper.appendChild(a);

                        const delBtn = document.createElement('button'); delBtn.className = 'delete-btn'; delBtn.innerHTML = '🗑️';
                        if (AppState.deleteMode) delBtn.style.display = 'block';
                        
                        delBtn.onclick = async (e) => {
                            e.preventDefault();
                            if(confirm('確認刪除此條目並同步刪除雲端文件嗎？')) {
                                const pathToDelete = news.path;
                                dayData.splice(index, 1);
                                if (dayData.length === 0) delete archiveData[AppState.year][AppState.month][AppState.day];
                                forceRender();
                                await syncDeleteToGithub(pathToDelete);
                            }
                        };
                        wrapper.appendChild(delBtn); newsList.appendChild(wrapper);
                    });
                } else {
                    newsList.innerHTML = '<div class="empty-state">當日暫無推文歸檔 🕊️</div>';
                }
            } catch (err) { console.error(err); }
        }

        document.getElementById('yearSelect').addEventListener('change', (e) => { AppState.year = parseInt(e.target.value, 10); forceRender(); });
        document.getElementById('monthSelect').addEventListener('change', (e) => { AppState.month = parseInt(e.target.value, 10); forceRender(); });
        document.getElementById('prevBtn').addEventListener('click', () => { AppState.month--; if (AppState.month < 1) { AppState.month = 12; AppState.year--; } forceRender(); });
        document.getElementById('nextBtn').addEventListener('click', () => { AppState.month++; if (AppState.month > 12) { AppState.month = 1; AppState.year++; } forceRender(); });
        document.getElementById('todayBtn').addEventListener('click', () => { AppState.year = today.getFullYear(); AppState.month = today.getMonth() + 1; AppState.day = today.getDate(); forceRender(); });

        let lastTap = 0;
        document.querySelector('.calendar-wrapper').addEventListener('click', (e) => {
            const tapLength = new Date().getTime() - lastTap;
            if (tapLength < 500 && tapLength > 0) {
                AppState.deleteMode = !AppState.deleteMode;
                document.querySelectorAll('.delete-btn').forEach(btn => btn.style.display = AppState.deleteMode ? 'block' : 'none');
                e.preventDefault();
            }
            lastTap = new Date().getTime();
        });

        initSelects(); forceRender();

        document.getElementById('openSettingsBtn').addEventListener('click', () => {
            document.getElementById('cfgGhToken').value = localStorage.getItem('GH_TOKEN') || '';
            document.getElementById('cfgGhOwner').value = localStorage.getItem('GH_OWNER') || 'moodHappy';
            document.getElementById('cfgGhRepo').value = localStorage.getItem('GH_REPO') || '';
            document.getElementById('settingsModal').style.display = 'flex';
        });
        document.getElementById('closeSettingsBtn').addEventListener('click', () => { document.getElementById('settingsModal').style.display = 'none'; });
        document.getElementById('saveSettingsBtn').addEventListener('click', () => {
            localStorage.setItem('GH_TOKEN', document.getElementById('cfgGhToken').value.trim());
            localStorage.setItem('GH_OWNER', document.getElementById('cfgGhOwner').value.trim());
            localStorage.setItem('GH_REPO', document.getElementById('cfgGhRepo').value.trim());
            document.getElementById('settingsModal').style.display = 'none';
            alert('配置已本地保存！');
        });

        async function syncDeleteToGithub(fileRelPath) {
            const ghToken = localStorage.getItem('GH_TOKEN');
            const ghOwner = localStorage.getItem('GH_OWNER');
            const ghRepo = localStorage.getItem('GH_REPO');
            if (!ghToken || !ghOwner || !ghRepo) return alert('本地已刪除，但未配置 GitHub Token，遠端不會變更。');
            try {
                const loadingBar = document.getElementById('loadingBar'); loadingBar.style.width = '20%';
                const targetFilePath = `docs/${fileRelPath}`;
                const fileRes = await fetch(`https://api.github.com/repos/${ghOwner}/${ghRepo}/contents/${targetFilePath}`, { headers: { 'Authorization': `Bearer ${ghToken}` } });
                if (fileRes.ok) {
                    const fileData = await fileRes.json();
                    await fetch(`https://api.github.com/repos/${ghOwner}/${ghRepo}/contents/${targetFilePath}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${ghToken}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ message: `Delete tweet html: ${fileRelPath}`, sha: fileData.sha }) });
                }
                loadingBar.style.width = '60%';
                const idxRes = await fetch(`https://api.github.com/repos/${ghOwner}/${ghRepo}/contents/docs/index.html`, { headers: { 'Authorization': `Bearer ${ghToken}` } });
                const idxData = await idxRes.json();
                const idxContent = decodeURIComponent(escape(atob(idxData.content.replace(/\\n/g, ''))));
                
                const dataStart = idxContent.indexOf('/*DATA_START*/') + 14;
                const dataEnd = idxContent.indexOf('/*DATA_END*/');
                const newIdxContent = idxContent.substring(0, dataStart) + JSON.stringify(archiveData) + idxContent.substring(dataEnd);
                
                loadingBar.style.width = '90%';
                await fetch(`https://api.github.com/repos/${ghOwner}/${ghRepo}/contents/docs/index.html`, { method: 'PUT', headers: { 'Authorization': `Bearer ${ghToken}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ message: `Update index.html after deletion`, content: btoa(unescape(encodeURIComponent(newIdxContent))), sha: idxData.sha }) });
                loadingBar.style.width = '100%'; setTimeout(() => { loadingBar.style.width = '0%'; }, 1000);
            } catch(e) { console.error(e); alert('刪除同步失敗: ' + e.message); document.getElementById('loadingBar').style.width = '0%'; }
        }

        // --- 核心：HTML 模板組裝函數 (前端) ---
        function generateTweetCard(tweet, tweetId) {
            const author = tweet.user_name || 'Unknown';
            const handle = tweet.user_screen_name || 'unknown';
            const text = tweet.text || '';
            const likes = tweet.likes || 0;
            const retweets = tweet.retweets || 0;
            const mediaExtended = tweet.media_extended || [];
            const mediaUrls = tweet.mediaURLs || [];
            const original_url = `https://x.com/${handle}/status/${tweetId}`;
            
            let media_html = "";
            if (mediaExtended.length > 0) {
                mediaExtended.forEach(media => {
                    if (media.type === 'video' || media.type === 'gif') {
                        media_html += `<div class="media-container"><video controls src="${media.url}" poster="${media.thumbnail_url || ''}" class="media-item" preload="metadata" playsinline></video></div>`;
                    } else {
                        media_html += `<div class="media-container"><img src="${media.url}" class="media-item" loading="lazy"></div>`;
                    }
                });
            } else if (mediaUrls.length > 0) {
                mediaUrls.forEach(url => {
                    if (url.includes('.mp4')) {
                        media_html += `<div class="media-container"><video controls src="${url}" class="media-item" preload="metadata" playsinline></video></div>`;
                    } else {
                        media_html += `<div class="media-container"><img src="${url}" class="media-item" loading="lazy"></div>`;
                    }
                });
            }

            return `
        <div class="tweet-card">
            <div class="header">
                <div class="names">
                    <span class="name">${author}</span>
                    <span class="handle">@${handle}</span>
                </div>
            </div>
            <div class="content">${text}</div>
            ${media_html}
            <div class="anno-section para-wrap">
                <span class="anno-toggle"></span>
                <span class="sync-status">📡 同步中...</span>
                <div class="anno-box">
                    <div class="anno-view markdown-body"></div>
                    <textarea class="anno-edit" placeholder="支援 Markdown，雙擊預覽區或點擊空白處保存..."></textarea>
                </div>
            </div>
            <div class="stats">
                <span>❤️ ${likes} 喜歡</span>
                <span>🔁 ${retweets} 轉發</span>
            </div>
            <a href="${original_url}" target="_blank" class="btn-link">🔗 前往 X 查看原文及評論</a>
        </div>`;
        }

        function generatePageWrapper(contentHtml, pageTitle, now_str) {
            return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="referrer" content="no-referrer">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>${pageTitle}</title>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"><\\/script>
    <style>
        :root { --bg: #f2f2f7; --card: #ffffff; --text: #0f1419; --muted: #536471; --border: #eff3f4; --x-blue: #1d9bf0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); margin: 0; padding: 0; -webkit-font-smoothing: antialiased; }
        .nav-back { display: flex; justify-content: space-between; align-items: center; padding: 15px 20px; background: var(--card); border-bottom: 1px solid #eee; position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        .nav-back a { text-decoration: none; color: white; background: #000; padding: 8px 20px; border-radius: 20px; font-weight: bold; font-size: 0.9rem; flex-shrink: 0; }
        .translate-btn { background: #f2f2f7; color: #0f1419; border: 1px solid #ccc; padding: 8px 15px; border-radius: 20px; font-weight: bold; font-size: 0.9rem; cursor: pointer; transition: 0.2s; flex-shrink: 0; outline: none; }
        .translate-btn:active { background: #e5e5ea; transform: scale(0.95); }
        .translate-btn[disabled] { opacity: 0.8; cursor: not-allowed; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px 15px 50px 15px; }
        .tweet-card { background: var(--card); border-radius: 16px; padding: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); margin-bottom: 25px; }
        .header { display: flex; align-items: center; margin-bottom: 12px; }
        .names { display: flex; flex-direction: column; }
        .name { font-weight: 700; font-size: 1.1rem; color: var(--text); }
        .handle { color: var(--muted); font-size: 0.95rem; margin-top: 2px; }
        .content { font-size: 1.1rem; color: var(--text); line-height: 1.5; white-space: pre-wrap; word-wrap: break-word; margin-bottom: 15px; }
        .media-container { margin-top: 10px; border-radius: 16px; overflow: hidden; border: 1px solid var(--border); margin-bottom: 10px; background: #000; }
        .media-item { width: 100%; height: auto; display: block; max-height: 500px; object-fit: contain; }
        .stats { margin-top: 15px; color: var(--muted); font-size: 0.95rem; border-top: 1px solid var(--border); padding-top: 15px; display: flex; gap: 20px; font-weight: 500; margin-bottom: 15px; }
        .btn-link { display: block; background: var(--x-blue); color: #fff; text-align: center; padding: 12px; border-radius: 24px; text-decoration: none; font-weight: 700; font-size: 1rem; transition: transform 0.2s; }
        .btn-link:active { transform: scale(0.98); background: #1a8cd8; }
        .time-stamp { text-align: center; color: var(--muted); font-size: 0.85rem; margin-bottom: 15px; font-weight: 600; }
        
        /* 批注區樣式 */
        .anno-section { margin-top: 15px; border-top: 1px dashed var(--border); padding-top: 12px; }
        .anno-toggle { display: inline-block; cursor: pointer; color: var(--muted); font-size: 0.9rem; font-weight: bold; user-select: none; transition: 0.2s; }
        .anno-toggle:hover { color: var(--x-blue); }
        .anno-toggle.has-anno { color: var(--x-blue); }
        .anno-toggle::before { content: "📝 寫筆記 / 批注"; }
        .anno-toggle.has-anno::before { content: "📝 查看批注"; }
        .sync-status { display: none; margin-left: 10px; font-size: 0.8rem; padding: 2px 8px; border-radius: 10px; color: white; background: #f39c12; vertical-align: middle; box-shadow: 0 2px 6px rgba(0,0,0,0.1); }
        .anno-box { display: none; margin-top: 10px; background: #f8f9fa; border-left: 4px solid var(--x-blue); padding: 12px; border-radius: 0 8px 8px 0; }
        .anno-view { font-size: 1rem; color: #333; line-height: 1.5; min-height: 24px; cursor: pointer; }
        .anno-edit { width: 100%; min-height: 100px; padding: 10px; font-family: monospace; font-size: 0.95rem; border: 1px dashed var(--x-blue); border-radius: 6px; box-sizing: border-box; resize: vertical; display: none; outline: none; }
        .anno-edit:focus { border-style: solid; box-shadow: 0 0 0 2px rgba(29,155,240,0.1); }
        
        /* Markdown 渲染優化 */
        .markdown-body p { margin: 0 0 8px 0; }
        .markdown-body p:last-child { margin-bottom: 0; }
        .markdown-body a { color: var(--x-blue); text-decoration: none; }
        .markdown-body a:hover { text-decoration: underline; }
        .markdown-body blockquote { margin: 0 0 10px 0; padding: 10px 15px; background: rgba(29,155,240,0.05); border-left: 4px solid var(--x-blue); color: #555; }
    </style>
</head>
<body>
    <div class="nav-back">
        <a href="../../index.html">🔙 返回</a>
        <button class="translate-btn" id="translate-btn" onclick="translateAll()">🌐 翻譯</button>
    </div>
    <div class="container">
        <div class="time-stamp">歸檔時間: ${now_str}</div>
        ${contentHtml}
    </div>
    
    <script>
        // ---------------- 翻譯邏輯 ----------------
        async function translateAll() {
            const btn = document.getElementById('translate-btn');
            if(btn.hasAttribute('disabled')) return;
            btn.innerText = '⏳ 處理中...';
            btn.setAttribute('disabled', 'true');

            let translatedCount = 0;
            const contents = document.querySelectorAll('.content');
            
            for (let i = 0; i < contents.length; i++) {
                const content = contents[i];
                if (content.getAttribute('data-translated') === 'true') continue;
                
                const originalText = content.innerText;
                if (!originalText.trim()) continue;

                let lines = originalText.split('\\n');
                let cleanedLines = [];
                for(let j=0; j<lines.length; j++) {
                    let words = lines[j].split(' ');
                    let cleanWords = [];
                    for(let k=0; k<words.length; k++) {
                        if(words[k].indexOf('http') !== 0) {
                            cleanWords.push(words[k]);
                        }
                    }
                    cleanedLines.push(cleanWords.join(' '));
                }
                let textToTranslate = cleanedLines.join('\\n');

                textToTranslate = textToTranslate.replace(/[\\uD800-\\uDBFF][\\uDC00-\\uDFFF]/g, '').trim();
                const hasWords = /[a-zA-Z0-9\\u4E00-\\u9FA5\\u3040-\\u30FF\\u0400-\\u04FF]/.test(textToTranslate);

                if (!textToTranslate || !hasWords) {
                    content.setAttribute('data-translated', 'true');
                    continue; 
                }

                try {
                    const url = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-CN&dt=t&q=' + encodeURIComponent(textToTranslate);
                    const res = await fetch(url);
                    const data = await res.json();
                    let translatedText = '';
                    if (data && data[0]) {
                        data[0].forEach(item => { if (item[0]) translatedText += item[0]; });
                    }

                    if (translatedText.trim()) {
                        const transDiv = document.createElement('div');
                        transDiv.className = 'translated-content';
                        transDiv.style.cssText = 'color: #0f1419; font-size: 1.1rem; margin-top: 10px; padding-top: 10px; border-top: 1px solid #eff3f4; white-space: pre-wrap; word-wrap: break-word;';
                        transDiv.innerText = translatedText.trim();
                        
                        content.parentNode.insertBefore(transDiv, content.nextSibling);
                        content.setAttribute('data-translated', 'true');
                        translatedCount++;
                    }
                } catch (e) {
                    console.error('翻譯失敗:', e);
                }
            }
            
            if (translatedCount === 0) {
                btn.innerText = '✅ 已全部翻譯';
                return;
            }

            btn.innerText = '⏳ 固化至雲端...';
            await snapshotAndSync(btn, '✅ 翻譯已固化', '⚠️ 僅本地翻譯');
        }

        // ---------------- 批注與同步邏輯 ----------------
        function escapeHTML(str) {
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
        }

        let syncTimeout = null;

        function initAnnotations() {
            document.querySelectorAll('.para-wrap').forEach(wrap => {
                const view = wrap.querySelector('.anno-view');
                const edit = wrap.querySelector('.anno-edit');
                const toggle = wrap.querySelector('.anno-toggle');
                const box = wrap.querySelector('.anno-box');
                const status = wrap.querySelector('.sync-status');

                const rawText = edit.value.trim();
                if (rawText) {
                    toggle.classList.add('has-anno');
                    if (typeof marked !== 'undefined') view.innerHTML = marked.parse(rawText);
                }

                toggle.onclick = () => {
                    if (box.style.display === 'block') {
                        box.style.display = 'none';
                    } else {
                        box.style.display = 'block';
                        if (!edit.value.trim()) {
                            view.style.display = 'none';
                            edit.style.display = 'block';
                            edit.focus();
                        } else {
                            view.style.display = 'block';
                            edit.style.display = 'none';
                        }
                    }
                };

                const triggerEdit = () => {
                    view.style.display = 'none';
                    edit.style.display = 'block';
                    edit.focus();
                };

                view.addEventListener('dblclick', triggerEdit);
                
                let lastTap = 0;
                view.addEventListener('touchstart', e => {
                    const currentTime = new Date().getTime();
                    const tapLength = currentTime - lastTap;
                    if (tapLength < 500 && tapLength > 0) {
                        triggerEdit();
                        e.preventDefault();
                    }
                    lastTap = currentTime;
                }, {passive: false});

                edit.onblur = () => {
                    const newVal = edit.value.trim();
                    edit.innerHTML = escapeHTML(newVal); 

                    try { view.innerHTML = newVal ? marked.parse(newVal) : ''; } catch(e){}
                    edit.style.display = 'none';

                    if (newVal) {
                        view.style.display = 'block';
                        toggle.classList.add('has-anno');
                    } else {
                        view.style.display = 'none';
                        box.style.display = 'none';
                        toggle.classList.remove('has-anno');
                    }

                    if (edit.getAttribute('data-old-val') !== newVal) {
                        edit.setAttribute('data-old-val', newVal);
                        scheduleAnnoSync(status);
                    }
                };
                edit.setAttribute('data-old-val', rawText);
            });
        }
        
        window.addEventListener('DOMContentLoaded', initAnnotations);

        function scheduleAnnoSync(statusEl) {
            statusEl.style.display = 'inline-block';
            statusEl.style.backgroundColor = '#f39c12';
            statusEl.innerText = '⏳ 5秒後同步...';

            if (syncTimeout) clearTimeout(syncTimeout);
            syncTimeout = setTimeout(() => {
                snapshotAndSync(statusEl, '✅ 已同步', '❌ 同步失敗', true);
            }, 5000);
        }

        // ---------------- 共用 DOM 快照與上傳函數 ----------------
        async function snapshotAndSync(uiElement, successText, failText, isStatusLabel = false) {
            const ghToken = localStorage.getItem('GH_TOKEN');
            const ghOwner = localStorage.getItem('GH_OWNER');
            const ghRepo = localStorage.getItem('GH_REPO');
            
            if (!ghToken || !ghOwner || !ghRepo) {
                uiElement.innerText = '❌ 缺Token';
                if(isStatusLabel) uiElement.style.backgroundColor = '#e74c3c';
                return;
            }

            if (isStatusLabel) {
                uiElement.style.backgroundColor = '#2ea44f';
                uiElement.innerText = '📡 同步中...';
            }

            try {
                const pathParts = window.location.pathname.split('/');
                const fileName = pathParts.pop();
                const month = pathParts.pop();
                const year = pathParts.pop();
                const fileRelPath = year + '/' + month + '/' + fileName;

                if (!isStatusLabel) {
                    uiElement.innerText = successText;
                    uiElement.style.cssText = 'background: #e8f5fd; color: #1d9bf0; border: 1px solid #1d9bf0;';
                }
                
                const htmlSnapshot = '<!DOCTYPE html><html lang="zh-CN">' + document.documentElement.innerHTML + '</html>';

                const fileRes = await fetch('https://api.github.com/repos/' + ghOwner + '/' + ghRepo + '/contents/docs/' + fileRelPath + '?t=' + Date.now(), { headers: { 'Authorization': 'Bearer ' + ghToken }, cache: 'no-store' });
                if (fileRes.ok) {
                    const fileData = await fileRes.json();
                    await fetch('https://api.github.com/repos/' + ghOwner + '/' + ghRepo + '/contents/docs/' + fileRelPath, {
                        method: 'PUT',
                        headers: { 'Authorization': 'Bearer ' + ghToken, 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            message: 'Auto-solidify DOM snapshot for ' + fileName, 
                            content: btoa(unescape(encodeURIComponent(htmlSnapshot))),
                            sha: fileData.sha
                        })
                    });
                }

                if (isStatusLabel) {
                    uiElement.innerText = successText;
                    setTimeout(() => { if(uiElement.innerText === successText) uiElement.style.display = 'none'; }, 3000);
                }

            } catch(e) {
                console.error('固化失敗', e);
                uiElement.innerText = failText;
                if (isStatusLabel) {
                    uiElement.style.backgroundColor = '#e74c3c';
                    uiElement.style.cursor = 'pointer';
                    uiElement.onclick = () => snapshotAndSync(uiElement, successText, failText, true);
                }
            }
        }
    \\x3C/script>
</body>
</html>`;
        }
        // ------------------------------------

        // X 推文前端抓取邏輯
        document.getElementById('xUrlInput').addEventListener('keypress', async function (e) {
            if (e.key === 'Enter') {
                const url = this.value.trim();
                
                const statusMatch = url.match(/status\\/(\\d+)/);
                const userMatch = url.match(/(?:x|twitter)\\.com\\/([A-Za-z0-9_]+)\\/?$/);
                
                let tweetIdsToProcess = [];
                let isBatch = false;
                let username = "";

                if (statusMatch) {
                    tweetIdsToProcess.push(statusMatch[1]);
                } else if (userMatch && !['i', 'home', 'explore', 'notifications'].includes(userMatch[1].toLowerCase())) {
                    isBatch = true;
                    username = userMatch[1];
                } else {
                    return alert('❌ 無法識別的 X (Twitter) 鏈接或格式不正確');
                }

                const ghToken = localStorage.getItem('GH_TOKEN');
                const ghOwner = localStorage.getItem('GH_OWNER');
                const ghRepo = localStorage.getItem('GH_REPO');
                if (!ghToken || !ghOwner || !ghRepo) {
                    alert('請先點擊齒輪⚙️配置 GitHub 信息！');
                    document.getElementById('settingsModal').style.display = 'flex';
                    return;
                }

                const loadingBar = document.getElementById('loadingBar');
                loadingBar.style.width = '5%';
                this.disabled = true;

                try {
                    if (isBatch) {
                        loadingBar.style.width = '15%';
                        try {
                            const rssUrl = `https://rsshub.rssforever.com/twitter/user/${username}/exclude_rts_replies`;
                            const rssRes = await fetch(rssUrl);
                            if (rssRes.ok) {
                                const rssText = await rssRes.text();
                                const matches = [...rssText.matchAll(/status\\/(\\d+)/g)];
                                matches.forEach(m => {
                                    if (!tweetIdsToProcess.includes(m[1])) tweetIdsToProcess.push(m[1]);
                                });
                            }
                        } catch(err) { console.warn("RSSHub fetch failed"); }

                        loadingBar.style.width = '25%';

                        if (tweetIdsToProcess.length === 0) {
                            const synUrl = encodeURIComponent(`https://syndication.twitter.com/srv/timeline-profile/screen-name/${username}`);
                            const proxies = [
                                `https://api.allorigins.win/raw?url=${synUrl}`,
                                `https://corsproxy.io/?url=${synUrl}`,
                                `https://api.codetabs.com/v1/proxy?quest=${decodeURIComponent(synUrl)}`
                            ];

                            for (let proxy of proxies) {
                                try {
                                    const res = await fetch(proxy);
                                    if (!res.ok) continue;
                                    const text = await res.text();
                                    const match = text.match(/<script id="__NEXT_DATA__" type="application\\/json">(.*?)<\\/script>/);
                                    if (match) {
                                        const parsed = JSON.parse(match[1]);
                                        const timelineEntries = parsed.props?.pageProps?.timeline?.entries || [];
                                        timelineEntries.forEach(entry => {
                                            const tweet = entry.content?.tweet;
                                            const tid = tweet?.id_str;
                                            const screenName = tweet?.user?.screen_name;
                                            
                                            if (tid && screenName && screenName.toLowerCase() === username.toLowerCase() && !tweetIdsToProcess.includes(tid)) {
                                                tweetIdsToProcess.push(tid);
                                            }
                                        });
                                        if (tweetIdsToProcess.length > 0) break;
                                    }
                                } catch(err) { console.warn(`Proxy failed:`, proxy); }
                            }
                        }

                        tweetIdsToProcess = tweetIdsToProcess.slice(0, 10);
                        if (tweetIdsToProcess.length === 0) {
                            throw new Error("前端代理節點全數遭瀏覽器攔截，請關閉廣告攔截器/防追蹤護盾，或更換網路後重試。");
                        }
                    }

                    const now = new Date();
                    const yearStr = AppState.year.toString();
                    const monthStr = AppState.month.toString();
                    const dayStr = AppState.day.toString();
                    const hhmmStr = String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0');
                    const hhmmssFile = String(now.getHours()).padStart(2, '0') + String(now.getMinutes()).padStart(2, '0') + String(now.getSeconds()).padStart(2, '0');
                    
                    let filename = "";
                    let fileRelPath = "";
                    let finalHtmlOutput = "";
                    let indexTitle = "";
                    
                    if (isBatch) {
                        let combinedCardsHtml = "";
                        let validCount = 0;
                        
                        for (let i = 0; i < tweetIdsToProcess.length; i++) {
                            loadingBar.style.width = `${30 + (50 / tweetIdsToProcess.length) * i}%`;
                            const tweetId = tweetIdsToProcess[i];
                            const vRes = await fetch(`https://api.vxtwitter.com/Twitter/status/${tweetId}`);
                            const tweet = await vRes.json();
                            if (tweet.error) continue;
                            
                            combinedCardsHtml += generateTweetCard(tweet, tweetId);
                            validCount++;
                        }
                        
                        if (validCount === 0) throw new Error("所有推文數據抓取失敗");
                        
                        finalHtmlOutput = generatePageWrapper(combinedCardsHtml, `Tweets by @${username}`, hhmmStr);
                        filename = `${yearStr}_${monthStr}_${dayStr}_${hhmmssFile}_batch_${username}_x.html`;
                        fileRelPath = `${yearStr}/${monthStr}/${filename}`;
                        indexTitle = `🐦 ${hhmmStr} 推文集：@${username}`;
                        
                    } else {
                        loadingBar.style.width = '60%';
                        const tweetId = tweetIdsToProcess[0];
                        const vRes = await fetch(`https://api.vxtwitter.com/Twitter/status/${tweetId}`);
                        const tweet = await vRes.json();
                        if (tweet.error) throw new Error(tweet.error);
                        
                        const singleCardHtml = generateTweetCard(tweet, tweetId);
                        finalHtmlOutput = generatePageWrapper(singleCardHtml, `Tweet by ${tweet.user_name}`, hhmmStr);
                        filename = `${yearStr}_${monthStr}_${dayStr}_${hhmmssFile}_${tweetId}_x.html`;
                        fileRelPath = `${yearStr}/${monthStr}/${filename}`;
                        indexTitle = `🐦 ${hhmmStr} 靈感推文`;
                    }

                    loadingBar.style.width = '85%';
                    const putHtmlRes = await fetch(`https://api.github.com/repos/${ghOwner}/${ghRepo}/contents/docs/${fileRelPath}`, {
                        method: 'PUT',
                        headers: { 'Authorization': `Bearer ${ghToken}`, 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: `Add ${isBatch ? 'batch' : 'single'} tweet HTML`, content: btoa(unescape(encodeURIComponent(finalHtmlOutput))) })
                    });
                    
                    if (!putHtmlRes.ok) throw new Error("HTML 文件上傳 GitHub 失敗");

                    loadingBar.style.width = '95%';
                    const idxRes = await fetch(`https://api.github.com/repos/${ghOwner}/${ghRepo}/contents/docs/index.html`, { headers: { 'Authorization': `Bearer ${ghToken}` } });
                    const idxData = await idxRes.json();
                    const idxContent = decodeURIComponent(escape(atob(idxData.content.replace(/\\n/g, ''))));

                    const dataStart = idxContent.indexOf('/*DATA_START*/') + 14;
                    const dataEnd = idxContent.indexOf('/*DATA_END*/');
                    const archiveObj = JSON.parse(idxContent.substring(dataStart, dataEnd));

                    if (!archiveObj[yearStr]) archiveObj[yearStr] = {};
                    if (!archiveObj[yearStr][monthStr]) archiveObj[yearStr][monthStr] = {};
                    if (!archiveObj[yearStr][monthStr][dayStr]) archiveObj[yearStr][monthStr][dayStr] = [];
                    
                    const newItem = { time: hhmmStr, path: fileRelPath, title: indexTitle };
                    archiveObj[yearStr][monthStr][dayStr].unshift(newItem);

                    const newIdxContent = idxContent.substring(0, dataStart) + JSON.stringify(archiveObj) + idxContent.substring(dataEnd);
                    
                    const putIdxRes = await fetch(`https://api.github.com/repos/${ghOwner}/${ghRepo}/contents/docs/index.html`, {
                        method: 'PUT',
                        headers: { 'Authorization': `Bearer ${ghToken}`, 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: `Update index.html with new ${isBatch ? 'batch' : 'single'} entry`, content: btoa(unescape(encodeURIComponent(newIdxContent))), sha: idxData.sha })
                    });
                    
                    if (!putIdxRes.ok) throw new Error("更新 index.html 失敗！");

                    if (!archiveData[yearStr]) archiveData[yearStr] = {};
                    if (!archiveData[yearStr][monthStr]) archiveData[yearStr][monthStr] = {};
                    if (!archiveData[yearStr][monthStr][dayStr]) archiveData[yearStr][monthStr][dayStr] = [];
                    archiveData[yearStr][monthStr][dayStr].unshift(newItem);

                    forceRender(); 
                    loadingBar.style.width = '100%';
                    alert(`🎉 成功！已為您歸檔最新的原創 ${isBatch ? '帳號瀑布流' : '單條推文'}。`);
                    this.value = '';
                    setTimeout(() => { loadingBar.style.width = '0%'; }, 1500);

                } catch (err) {
                    alert('❌ 操作失敗: ' + err.message);
                    loadingBar.style.width = '0%';
                } finally {
                    this.disabled = false;
                }
            }
        });
    </script>
</body>
</html>"""

    html_template = html_template.replace('REPLACEME_JSON_DATA', json_data)

    with open(os.path.join(BASE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_template)
    print("🚀 首頁日曆 WebApp (批注功能 + 翻譯優化版) 已生成更新！")

def git_push_to_github(msg="Auto-archive"):
    if not AUTO_PUSH_GITHUB:
        return
    print("\n⏳ 正在自動推送變更到 GitHub...")
    if not os.path.exists(".git"):
        print("⚠️ 當前目錄並非 Git 倉庫，跳過自動同步。")
        return
    try:
        subprocess.run(["git", "add", "docs/"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if not status.stdout.strip():
            print("ℹ️ 沒有需要推播的更新。")
            return

        subprocess.run(["git", "commit", "-m", msg], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "push"], check=True)
        print("✅ 成功同步到 GitHub！網頁版約在 1~3 分鐘後刷新可見。")
    except subprocess.CalledProcessError as e:
        print(f"❌ Git 執行失敗，錯誤碼: {e.returncode}")
    except FileNotFoundError:
        print("❌ 系統找不到 Git，請確認您已安裝 Git 並將其加入環境變數中。")

def main():
    os.makedirs(BASE_DIR, exist_ok=True)
    generate_index()

    print("\n=======================================")
    print("🐦 X (Twitter) 語料日曆 - 後台錄入")
    print("提示1：粘貼 [單推文鏈接] 即可抓取單條推文")
    print("提示2：粘貼 [帳號首頁鏈接] 將為您生成該帳號最新 10 條原創推文的瀑布流網頁！")
    print("=======================================")

    while True:
        url = input("\n👉 粘貼 X 推文或帳號鏈接 (輸入 q 退出): ").strip()
        if url.lower() == 'q':
            break
        if not url:
            continue

        status_match = re.search(r'status/(\d+)', url)
        user_match = re.search(r'(?:x|twitter)\.com/([A-Za-z0-9_]+)', url)

        now = datetime.now(tz_utc_8)

        if status_match:
            tweet_id = status_match.group(1)
            if save_single_tweet_local(tweet_id, now):
                generate_index()
                git_push_to_github(f"Archive single tweet {tweet_id}")
        
        elif user_match:
            username = user_match.group(1)
            if username.lower() in ['i', 'home', 'explore', 'notifications', 'messages']:
                print("❌ 鏈接無效，請輸入真實的帳號首頁")
                continue
            
            tweet_ids = get_user_tweet_ids(username, limit=10)
            if not tweet_ids:
                print("❌ 找不到該帳號的原創推文或解析時間線失敗。")
                continue
            
            if save_batch_tweets_local(username, tweet_ids, now):
                generate_index()
                git_push_to_github(f"Batch archive {len(tweet_ids)} tweets from {username}")
        else:
            print("❌ 無法識別的鏈接格式。")

if __name__ == "__main__":
    main()
