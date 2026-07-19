import os
import requests
import json
import re
import subprocess
import time
from datetime import datetime, timezone, timedelta

# ================= 配置區 =================
BASE_DIR = "docs"
tz_utc_8 = timezone(timedelta(hours=8))
AUTO_PUSH_GITHUB = True  # 開啟 Python 端自動 Push 到 GitHub 的功能
# ==========================================

def get_user_tweet_ids(username, limit=10):
    """通過公開 Syndication API 或備用 RSS 獲取用戶最新推文 ID"""
    print(f"⏳ 正在解析 @{username} 的時間線...")
    url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', res.text)
        if match:
            data = json.loads(match.group(1))
            entries = data.get('props', {}).get('pageProps', {}).get('timeline', {}).get('entries', [])
            tweet_ids = []
            for entry in entries:
                tweet_id = entry.get('content', {}).get('tweet', {}).get('id_str')
                if tweet_id and tweet_id not in tweet_ids:
                    tweet_ids.append(tweet_id)
            if tweet_ids:
                return tweet_ids[:limit]
    except Exception as e:
        print(f"⚠️ 解析主節點失敗: {e}")
    
    print("⏳ 嘗試使用備用 RSS 節點解析...")
    rss_url = f"https://rsshub.rssforever.com/twitter/user/{username}/exclude_rts_replies"
    try:
        res = requests.get(rss_url, headers=headers, timeout=10)
        ids = re.findall(r'status/(\d+)', res.text)
        seen = set()
        tweet_ids = [x for x in ids if not (x in seen or seen.add(x))]
        return tweet_ids[:limit]
    except Exception as e:
        print(f"❌ 備用節點解析失敗: {e}")
    
    return []

def save_tweet_local(tweet_data, tweet_id, now_obj):
    """在本地生成極簡推文卡片 HTML"""
    year_str, month_str = str(now_obj.year), str(now_obj.month)
    target_dir = os.path.join(BASE_DIR, year_str, month_str)
    os.makedirs(target_dir, exist_ok=True)

    # 檔名加入秒數與推文ID防止批量處理時衝突
    time_hms = now_obj.strftime('%H%M%S')
    filename = f"{now_obj.year}_{now_obj.month}_{now_obj.day}_{time_hms}_{tweet_id}_x.html"
    html_path = os.path.join(target_dir, filename)
    now_str = now_obj.strftime("%Y-%m-%d %H:%M")

    # 提取數據
    author = tweet_data.get('user_name', 'Unknown')
    handle = tweet_data.get('user_screen_name', 'unknown')
    text = tweet_data.get('text', '')
    likes = tweet_data.get('likes', 0)
    retweets = tweet_data.get('retweets', 0)
    
    media_extended = tweet_data.get('media_extended', [])
    media_urls = tweet_data.get('mediaURLs', [])
    original_url = f"https://x.com/{handle}/status/{tweet_id}"

    # 處理媒體附件 (極簡還原版)
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

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="referrer" content="no-referrer">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Tweet by {author}</title>
    <style>
        :root {{ --bg: #f2f2f7; --card: #ffffff; --text: #0f1419; --muted: #536471; --border: #eff3f4; --x-blue: #1d9bf0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); margin: 0; padding: 0; -webkit-font-smoothing: antialiased; }}
        .nav-back {{ padding: 15px; text-align: center; background: var(--card); border-bottom: 1px solid #eee; position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
        .nav-back a {{ text-decoration: none; color: white; background: #000; padding: 8px 20px; border-radius: 20px; font-weight: bold; font-size: 0.9rem; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px 15px 50px 15px; }}
        .tweet-card {{ background: var(--card); border-radius: 16px; padding: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); }}
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
    </style>
</head>
<body>
    <div class="nav-back"><a href="../../index.html">🔙 返回日曆樞紐</a></div>
    <div class="container">
        <div class="time-stamp">歸檔時間: {now_str}</div>
        <div class="tweet-card">
            <div class="header">
                <div class="names">
                    <span class="name">{author}</span>
                    <span class="handle">@{handle}</span>
                </div>
            </div>
            <div class="content">{text}</div>
            {media_html}
            <div class="stats">
                <span>❤️ {likes:,} 喜歡</span>
                <span>🔁 {retweets:,} 轉發</span>
            </div>
            <a href="{original_url}" target="_blank" class="btn-link">🔗 前往 X 查看原文及評論</a>
        </div>
    </div>
</body>
</html>"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"✅ 語料已歸檔: {html_path}")

def process_tweet_id(tweet_id, d_time):
    """處理單個推文 ID"""
    api_url = f"https://api.vxtwitter.com/Twitter/status/{tweet_id}"
    try:
        res = requests.get(api_url, timeout=15).json()
        if 'error' in res:
            print(f"❌ 抓取失敗 [{tweet_id}]: {res.get('error')}")
            return False
        save_tweet_local(res, tweet_id, d_time)
        return True
    except Exception as e:
        print(f"❌ 網絡異常 [{tweet_id}]: {e}")
        return False

def generate_index():
    """日曆樞紐生成器 + 支援動態更新的 X 前端控制台"""
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
                            
                            # 全新標題格式
                            title = f"🐦 靈感推文：{time_str}"

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
                        
                        // 標題本身就包含了時間，不需要再額外添加時間標籤
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

        // X 推文前端抓取邏輯 (支援單個與批量)
        document.getElementById('xUrlInput').addEventListener('keypress', async function (e) {
            if (e.key === 'Enter') {
                const url = this.value.trim();
                
                // 判斷是否為單推文或帳號首頁
                const statusMatch = url.match(/status\\/(\\d+)/);
                const userMatch = url.match(/(?:x|twitter)\\.com\\/([A-Za-z0-9_]+)\\/?$/);
                
                let tweetIdsToProcess = [];
                let isBatch = false;

                if (statusMatch) {
                    tweetIdsToProcess.push(statusMatch[1]);
                } else if (userMatch && !['i', 'home', 'explore', 'notifications'].includes(userMatch[1].toLowerCase())) {
                    isBatch = true;
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
                    // 若為批量，前端使用代理拉取時間線
                    if (isBatch) {
                        const username = userMatch[1];
                        const proxyUrl = `https://api.allorigins.win/get?url=${encodeURIComponent('https://syndication.twitter.com/srv/timeline-profile/screen-name/' + username)}`;
                        const res = await fetch(proxyUrl);
                        const data = await res.json();
                        const match = data.contents.match(/<script id="__NEXT_DATA__" type="application\\/json">(.*?)<\\/script>/);
                        
                        if (match) {
                            const parsed = JSON.parse(match[1]);
                            const entries = parsed.props?.pageProps?.timeline?.entries || [];
                            entries.forEach(e => {
                                const tid = e.content?.tweet?.id_str;
                                if (tid && !tweetIdsToProcess.includes(tid)) tweetIdsToProcess.push(tid);
                            });
                            tweetIdsToProcess = tweetIdsToProcess.slice(0, 10);
                        }
                        
                        if (tweetIdsToProcess.length === 0) throw new Error("代理節點未能解析出推文");
                    }

                    // 處理搜集到的所有 IDs
                    const now = new Date();
                    const yearStr = AppState.year.toString();
                    const monthStr = AppState.month.toString();
                    const dayStr = AppState.day.toString();
                    const newItems = [];

                    for (let i = 0; i < tweetIdsToProcess.length; i++) {
                        loadingBar.style.width = `${10 + (80 / tweetIdsToProcess.length) * i}%`;
                        const tweetId = tweetIdsToProcess[i];
                        
                        const vRes = await fetch(`https://api.vxtwitter.com/Twitter/status/${tweetId}`);
                        const tweet = await vRes.json();
                        if (tweet.error) continue; // 略過錯誤的推文

                        // 製造微小的時間差(秒數)，防止檔名重複
                        const d = new Date(now.getTime() - i * 60000); 
                        const hhmmStr = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
                        const hhmmssFile = String(d.getHours()).padStart(2, '0') + String(d.getMinutes()).padStart(2, '0') + String(d.getSeconds()).padStart(2, '0');
                        
                        const filename = `${yearStr}_${monthStr}_${dayStr}_${hhmmssFile}_${tweetId}_x.html`;
                        const fileRelPath = `${yearStr}/${monthStr}/${filename}`;

                        const htmlOutput = generateBaseHTMLString(tweet, tweetId, AppState.year, AppState.month, AppState.day, hhmmStr);

                        await fetch(`https://api.github.com/repos/${ghOwner}/${ghRepo}/contents/docs/${fileRelPath}`, {
                            method: 'PUT',
                            headers: { 'Authorization': `Bearer ${ghToken}`, 'Content-Type': 'application/json' },
                            body: JSON.stringify({ message: `Add tweet by ${tweet.user_name}`, content: btoa(unescape(encodeURIComponent(htmlOutput))) })
                        });

                        newItems.push({ time: hhmmStr, path: fileRelPath, title: `🐦 靈感推文：${hhmmStr}` });
                    }

                    if (newItems.length === 0) throw new Error("API 節點阻擋，無法抓取到資料");

                    // 批量更新 index.html (防止連續提交導致 GitHub 報錯)
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
                    
                    // 將新抓取的資料加到陣列最前面
                    archiveObj[yearStr][monthStr][dayStr] = [...newItems, ...archiveObj[yearStr][monthStr][dayStr]];

                    const newIdxContent = idxContent.substring(0, dataStart) + JSON.stringify(archiveObj) + idxContent.substring(dataEnd);
                    
                    const putIdxRes = await fetch(`https://api.github.com/repos/${ghOwner}/${ghRepo}/contents/docs/index.html`, {
                        method: 'PUT',
                        headers: { 'Authorization': `Bearer ${ghToken}`, 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: `Batch update index.html`, content: btoa(unescape(encodeURIComponent(newIdxContent))), sha: idxData.sha })
                    });
                    
                    if (!putIdxRes.ok) throw new Error("更新 index.html 失敗！");

                    // 更新本地記憶體
                    if (!archiveData[yearStr]) archiveData[yearStr] = {};
                    if (!archiveData[yearStr][monthStr]) archiveData[yearStr][monthStr] = {};
                    if (!archiveData[yearStr][monthStr][dayStr]) archiveData[yearStr][monthStr][dayStr] = [];
                    archiveData[yearStr][monthStr][dayStr] = [...newItems, ...archiveData[yearStr][monthStr][dayStr]];

                    forceRender(); 
                    loadingBar.style.width = '100%';
                    alert(`🎉 抓取成功！共歸檔 ${newItems.length} 條推文。`);
                    this.value = '';
                    setTimeout(() => { loadingBar.style.width = '0%'; }, 1500);

                } catch (err) {
                    alert('❌ 操作失敗: ' + err.message + (isBatch ? ' (若代理節點失效，建議使用 Python 後台終端執行)' : ''));
                    loadingBar.style.width = '0%';
                } finally {
                    this.disabled = false;
                }
            }
        });

        // 模板：生成極簡版子頁面 HTML
        function generateBaseHTMLString(tweet, tweetId, sYear, sMonth, sDay, hhmmStr) {
            const author = tweet.user_name || 'Unknown';
            const handle = tweet.user_screen_name || 'unknown';
            const text = tweet.text || '';
            const likes = tweet.likes || 0;
            const retweets = tweet.retweets || 0;
            const mediaExtended = tweet.media_extended || [];
            const mediaUrls = tweet.mediaURLs || [];
            const original_url = `https://x.com/${handle}/status/${tweetId}`;
            
            const now_str = `${sYear}-${String(sMonth).padStart(2,'0')}-${String(sDay).padStart(2,'0')} ${hhmmStr}`;

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

            return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="referrer" content="no-referrer">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Tweet by ${author}</title>
    <style>
        :root { --bg: #f2f2f7; --card: #ffffff; --text: #0f1419; --muted: #536471; --border: #eff3f4; --x-blue: #1d9bf0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); margin: 0; padding: 0; -webkit-font-smoothing: antialiased; }
        .nav-back { padding: 15px; text-align: center; background: var(--card); border-bottom: 1px solid #eee; position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }
        .nav-back a { text-decoration: none; color: white; background: #000; padding: 8px 20px; border-radius: 20px; font-weight: bold; font-size: 0.9rem; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px 15px 50px 15px; }
        .tweet-card { background: var(--card); border-radius: 16px; padding: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.04); }
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
    </style>
</head>
<body>
    <div class="nav-back"><a href="../../index.html">🔙 返回日曆樞紐</a></div>
    <div class="container">
        <div class="time-stamp">歸檔時間: ${now_str}</div>
        <div class="tweet-card">
            <div class="header">
                <div class="names">
                    <span class="name">${author}</span>
                    <span class="handle">@${handle}</span>
                </div>
            </div>
            <div class="content">${text}</div>
            ${media_html}
            <div class="stats">
                <span>❤️ ${likes} 喜歡</span>
                <span>🔁 ${retweets} 轉發</span>
            </div>
            <a href="${original_url}" target="_blank" class="btn-link">🔗 前往 X 查看原文及評論</a>
        </div>
    </div>
</body>
</html>`;
        }
    </script>
</body>
</html>"""

    html_template = html_template.replace('REPLACEME_JSON_DATA', json_data)

    with open(os.path.join(BASE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_template)
    print("🚀 首頁日曆 WebApp 已生成更新！")

def git_push_to_github(msg="Auto-archive"):
    """自動調用本地系統的 Git 指令將更新推送到 GitHub"""
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
    print("提示1：粘貼 [單推文鏈接] 即可抓取該條推文")
    print("提示2：粘貼 [帳號首頁鏈接] 將自動抓取該帳號最新 10 條推文！")
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
            if process_tweet_id(tweet_id, now):
                generate_index()
                git_push_to_github(f"Archive single tweet {tweet_id}")
        
        elif user_match:
            username = user_match.group(1)
            if username.lower() in ['i', 'home', 'explore', 'notifications', 'messages']:
                print("❌ 鏈接無效，請輸入真實的帳號首頁")
                continue
            
            tweet_ids = get_user_tweet_ids(username, limit=10)
            if not tweet_ids:
                print("❌ 找不到該帳號的推文或解析時間線失敗。")
                continue
            
            print(f"✅ 成功獲取 {len(tweet_ids)} 條推文，準備依序歸檔...")
            success_count = 0
            for i, tid in enumerate(tweet_ids):
                # 人為製造秒級時間差，避免檔名與顯示時間重疊
                d_time = now - timedelta(minutes=i)
                if process_tweet_id(tid, d_time):
                    success_count += 1
                    time.sleep(0.5)
            
            if success_count > 0:
                generate_index()
                git_push_to_github(f"Batch archive {success_count} tweets from {username}")
        else:
            print("❌ 無法識別的鏈接格式。")

if __name__ == "__main__":
    main()
