from flask import Flask, render_template, jsonify, request, send_from_directory
import json
import tweepy
import os
import secrets
from datetime import datetime, timedelta, timezone
import sqlite3
import logging
import threading
import time

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Twitter API配置
TWITTER_BEARER_TOKEN = os.environ.get('TWITTER_BEARER_TOKEN')

class TwitterAPI:
    def __init__(self):
        if TWITTER_BEARER_TOKEN:
            try:
                self.client = tweepy.Client(bearer_token=TWITTER_BEARER_TOKEN)
                logger.info("✅ Twitter API客户端初始化成功")
                self.test_connection()
            except Exception as e:
                logger.error(f"❌ Twitter API初始化失败: {e}")
                self.client = None
        else:
            self.client = None
            logger.warning("⚠️ Twitter Bearer Token未配置，将无法获取真实数据")
    
    def test_connection(self):
        """测试API连接"""
        try:
            if self.client:
                # 测试获取一个公开用户信息
                user = self.client.get_user(username='elonmusk')
                if user.data:
                    logger.info("🔗 Twitter API连接测试成功")
                    return True
        except Exception as e:
            logger.error(f"API连接测试失败: {e}")
        return False
    
    def get_user_tweets(self, username, max_results=10):
        """
        获取用户自2025年1月1日以来的推文。
        如果获取失败或没有新推文，则返回空列表。
        """
        if not self.client:
            logger.warning(f"Twitter客户端未配置，无法获取 {username} 的推文")
            return []
        
        try:
            # 移除@符号
            username = username.replace('@', '')
            
            # 获取用户信息
            user_response = self.client.get_user(username=username)
            if not user_response.data:
                logger.warning(f"Twitter用户 {username} 不存在")
                return []
            
            user_id = user_response.data.id
            
            # 设置起始时间为2025年1月1日
            start_date = datetime(2025, 1, 1, tzinfo=timezone.utc)
            
            # 获取推文
            tweets_response = self.client.get_users_tweets(
                id=user_id,
                max_results=min(max_results, 100),
                tweet_fields=['created_at', 'public_metrics', 'context_annotations'],
                exclude=['retweets', 'replies'],
                start_time=start_date
            )
            
            if not tweets_response.data:
                logger.info(f"✅ 未找到 {username} 自 {start_date.date()} 以来的新推文")
                return []
            
            result = []
            for tweet in tweets_response.data:
                result.append({
                    'id': str(tweet.id),
                    'content': tweet.text,
                    'created_at': tweet.created_at.isoformat() if tweet.created_at else None,
                    'likes': tweet.public_metrics.get('like_count', 0),
                    'retweets': tweet.public_metrics.get('retweet_count', 0),
                    'replies': tweet.public_metrics.get('reply_count', 0),
                    'author': username,
                    'type': 'text'
                })
            
            logger.info(f"✅ 成功获取 {username} 的 {len(result)} 条新推文")
            return result
            
        except Exception as e:
            logger.error(f"获取 {username} 推文时发生错误: {e}")
            return [] # 发生任何错误时，返回空列表

class ResearcherManager:
    def __init__(self):
        self.init_database()
        self.load_sample_data()
    
    def init_database(self):
        """初始化数据库 - 支持大规模数据存储"""
        conn = sqlite3.connect('research_platform.db')
        cursor = conn.cursor()
        
        # 开启外键约束和基本优化设置
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA synchronous = NORMAL;")  # 平衡性能和安全性

        # 研究者表 - 优化字段类型和索引
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS researchers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rank INTEGER,
                name TEXT NOT NULL,
                country TEXT,
                company TEXT,
                research_focus TEXT,
                x_account TEXT,
                followers_count TEXT DEFAULT '0',
                following_count TEXT DEFAULT '0',
                avatar_url TEXT DEFAULT '',
                is_monitoring BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 为高频查询字段创建索引
        try:
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_researchers_rank ON researchers(rank);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_researchers_name ON researchers(name);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_researchers_monitoring ON researchers(is_monitoring);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_researchers_account ON researchers(x_account);')
        except Exception as e:
            logger.warning(f"创建索引时遇到警告: {e}")
        
        # 内容表 - 优化存储和索引
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS x_content (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                researcher_id INTEGER,
                tweet_id TEXT UNIQUE,
                content TEXT,
                content_type TEXT DEFAULT 'text',
                likes_count INTEGER DEFAULT 0,
                retweets_count INTEGER DEFAULT 0,
                replies_count INTEGER DEFAULT 0,
                created_at DATETIME,
                collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (researcher_id) REFERENCES researchers (id) ON DELETE CASCADE
            )
        ''')
        
        # 内容表索引
        try:
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_content_researcher ON x_content(researcher_id);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_content_created ON x_content(created_at);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_content_tweet_id ON x_content(tweet_id);')
        except Exception as e:
            logger.warning(f"创建内容表索引时遇到警告: {e}")
        
        # 监控任务表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS monitoring_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                researcher_id INTEGER,
                status TEXT DEFAULT 'active',
                last_check DATETIME DEFAULT CURRENT_TIMESTAMP,
                check_interval INTEGER DEFAULT 3600,
                FOREIGN KEY (researcher_id) REFERENCES researchers (id) ON DELETE CASCADE
            )
        ''')
        
        # 监控任务表索引
        try:
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_monitoring_researcher ON monitoring_tasks(researcher_id);')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_monitoring_status ON monitoring_tasks(status);')
        except Exception as e:
            logger.warning(f"创建监控任务表索引时遇到警告: {e}")
        
        conn.commit()
        conn.close()
        logger.info("✅ 数据库初始化完成 - 已优化支持大规模数据")
    
    def load_sample_data(self):
        """加载研究者示例数据 (此为应用基础数据，非动态内容)"""
        researchers_data = [
            {
                'rank': 1, 'name': 'Ilya Sutskever', 'country': 'Canada', 'company': 'SSI',
                'research_focus': 'AlexNet、Seq2seq、深度学习', 'x_account': '@ilyasut',
                'followers_count': '127K', 'following_count': '89'
            },
            {
                'rank': 2, 'name': 'Noam Shazeer', 'country': 'USA', 'company': 'Google Deepmind',
                'research_focus': '注意力机制、混合专家模型、角色AI', 'x_account': '@noamshazeer',
                'followers_count': '45K', 'following_count': '156'
            },
            {
                'rank': 3, 'name': 'Geoffrey Hinton', 'country': 'UK', 'company': 'University of Toronto',
                'research_focus': '反向传播、玻尔兹曼机、深度学习', 'x_account': '@geoffreyhinton',
                'followers_count': '234K', 'following_count': '67'
            },
            {
                'rank': 4, 'name': 'Alec Radford', 'country': 'USA', 'company': 'Thinking Machines',
                'research_focus': '生成对抗网络、GPT、CLIP', 'x_account': '@alec_radford',
                'followers_count': '89K', 'following_count': '123'
            },
            {
                'rank': 5, 'name': 'Andrej Karpathy', 'country': 'Slovakia', 'company': 'Tesla',
                'research_focus': '计算机视觉、神经网络、自动驾驶', 'x_account': '@karpathy',
                'followers_count': '512K', 'following_count': '234'
            }
        ]
        
        conn = sqlite3.connect('research_platform.db')
        cursor = conn.cursor()
        
        for researcher in researchers_data:
            cursor.execute('''
                INSERT OR IGNORE INTO researchers 
                (rank, name, country, company, research_focus, x_account, followers_count, following_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                researcher['rank'], researcher['name'], researcher['country'],
                researcher['company'], researcher['research_focus'], researcher['x_account'],
                researcher['followers_count'], researcher['following_count']
            ))
        
        conn.commit()
        conn.close()

# 初始化
try:
    researcher_manager = ResearcherManager()
    logger.info("✅ 研究者管理器初始化成功")
except Exception as e:
    logger.error(f"❌ 研究者管理器初始化失败: {e}")
    researcher_manager = None

try:
    twitter_api = TwitterAPI()
    logger.info("✅ Twitter API初始化完成")
except Exception as e:
    logger.error(f"❌ Twitter API初始化失败: {e}")
    twitter_api = None

# 监控任务 - 优化支持大规模监控
class MonitoringService:
    def __init__(self):
        self.running = False
        self.thread = None
        self.max_concurrent_checks = 10  # 最大并发检查数
    
    def start_monitoring(self):
        """启动监控服务"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.thread.start()
            logger.info("🚀 监控服务已启动 - 支持大规模监控")
    
    def _monitoring_loop(self):
        """监控循环 - 优化处理大量研究者"""
        while self.running:
            try:
                self._check_researchers_batch()
                time.sleep(1800)  # 每30分钟检查一次
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
                time.sleep(60)
    
    def _check_researchers_batch(self):
        """批量检查正在监控的研究者"""
        conn = sqlite3.connect('research_platform.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, name, x_account FROM researchers WHERE is_monitoring = 1')
        researchers = cursor.fetchall()
        conn.close()
        
        logger.info(f"🔍 开始检查 {len(researchers)} 位研究者的内容")
        
        # 分批处理，避免同时处理过多研究者
        batch_size = 50  # 每批处理50个
        for i in range(0, len(researchers), batch_size):
            batch = researchers[i:i + batch_size]
            self._process_researcher_batch(batch)
            time.sleep(5)  # 批次间休息5秒
    
    def _process_researcher_batch(self, researchers_batch):
        """处理一批研究者"""
        for researcher_id, name, x_account in researchers_batch:
            try:
                tweets = twitter_api.get_user_tweets(x_account, max_results=5)
                
                if not tweets:
                    continue

                conn = sqlite3.connect('research_platform.db')
                cursor = conn.cursor()

                new_tweets_count = 0
                for tweet in tweets:
                    cursor.execute('''
                        INSERT OR IGNORE INTO x_content 
                        (researcher_id, tweet_id, content, likes_count, retweets_count, replies_count, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        researcher_id, tweet['id'], tweet['content'],
                        tweet['likes'], tweet['retweets'], tweet['replies'],
                        tweet['created_at']
                    ))
                    if cursor.rowcount > 0:
                        new_tweets_count += 1
                
                # 更新最后检查时间
                cursor.execute('''
                    UPDATE monitoring_tasks SET last_check = CURRENT_TIMESTAMP 
                    WHERE researcher_id = ?
                ''', (researcher_id,))
                
                conn.commit()
                conn.close()
                
                if new_tweets_count > 0:
                    logger.info(f"✅ {name} 更新了 {new_tweets_count} 条新内容")
                
            except Exception as e:
                logger.error(f"检查 {name} 时出错: {e}")
                time.sleep(1)  # 出错时稍作等待

# 初始化监控服务
try:
    monitoring_service = MonitoringService()
    logger.info("✅ 监控服务初始化成功")
except Exception as e:
    logger.error(f"❌ 监控服务初始化失败: {e}")
    monitoring_service = None

# API路由
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/researchers')
def get_researchers():
    """获取研究者列表 - 支持分页处理大量数据"""
    if not researcher_manager:
        return jsonify({'error': 'System not properly initialized'}), 500
        
    conn = sqlite3.connect('research_platform.db')
    cursor = conn.cursor()
    
    search_query = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)  # 默认每页50条
    
    # 限制每页最大数量
    per_page = min(per_page, 200)
    offset = (page - 1) * per_page
    
    if search_query:
        # 搜索查询
        count_query = '''
            SELECT COUNT(*) FROM researchers 
            WHERE name LIKE ? OR company LIKE ? OR research_focus LIKE ?
        '''
        cursor.execute(count_query, (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
        total_count = cursor.fetchone()[0]
        
        data_query = '''
            SELECT * FROM researchers 
            WHERE name LIKE ? OR company LIKE ? OR research_focus LIKE ?
            ORDER BY rank LIMIT ? OFFSET ?
        '''
        cursor.execute(data_query, (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%', per_page, offset))
    else:
        # 普通查询
        cursor.execute('SELECT COUNT(*) FROM researchers')
        total_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT * FROM researchers ORDER BY rank LIMIT ? OFFSET ?', (per_page, offset))
    
    researchers = []
    for row in cursor.fetchall():
        researchers.append({
            'id': row[0], 'rank': row[1], 'name': row[2], 'country': row[3],
            'company': row[4], 'research_focus': row[5], 'x_account': row[6],
            'followers_count': row[7], 'following_count': row[8],
            'is_monitoring': bool(row[10])
        })
    
    conn.close()
    
    return jsonify({
        'researchers': researchers,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total_count,
            'pages': (total_count + per_page - 1) // per_page
        }
    })

@app.route('/api/researcher/<int:researcher_id>')
def get_researcher_detail(researcher_id):
    """获取研究者详情"""
    conn = sqlite3.connect('research_platform.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM researchers WHERE id = ?', (researcher_id,))
    researcher_row = cursor.fetchone()
    
    if not researcher_row:
        conn.close()
        return jsonify({'error': 'Researcher not found'}), 404
    
    researcher = {
        'id': researcher_row[0], 'rank': researcher_row[1], 'name': researcher_row[2],
        'country': researcher_row[3], 'company': researcher_row[4], 
        'research_focus': researcher_row[5], 'x_account': researcher_row[6],
        'followers_count': researcher_row[7], 'following_count': researcher_row[8],
        'is_monitoring': bool(researcher_row[10])
    }
    
    # 获取最新内容
    cursor.execute('''
        SELECT * FROM x_content WHERE researcher_id = ? 
        ORDER BY created_at DESC LIMIT 10
    ''', (researcher_id,))
    content_rows = cursor.fetchall()
    
    conn.close()
    
    recent_content = [
        {
            'id': c[0], 'content': c[3], 'likes': c[5], 
            'retweets': c[6], 'replies': c[7], 'created_at': c[8]
        } for c in content_rows
    ]
    
    return jsonify({
        'researcher': researcher,
        'recent_content': recent_content
    })

@app.route('/api/researcher/<int:researcher_id>', methods=['DELETE'])
def delete_researcher(researcher_id):
    """删除指定的研究者及其所有相关数据"""
    try:
        conn = sqlite3.connect('research_platform.db')
        cursor = conn.cursor()

        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute('DELETE FROM researchers WHERE id = ?', (researcher_id,))
        
        conn.commit()

        if cursor.rowcount > 0:
            logger.info(f"✅ 成功删除研究者 ID: {researcher_id}")
            return jsonify({'message': f'成功删除研究者 ID: {researcher_id}'}), 200
        else:
            logger.warning(f"⚠️ 尝试删除一个不存在的研究者 ID: {researcher_id}")
            return jsonify({'error': 'Researcher not found'}), 404

    except Exception as e:
        logger.error(f"❌ 删除研究者 {researcher_id} 时发生错误: {e}")
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/api/content')
def get_content():
    """获取所有内容 - 支持分页"""
    conn = sqlite3.connect('research_platform.db')
    cursor = conn.cursor()
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    per_page = min(per_page, 100)  # 限制最大每页数量
    offset = (page - 1) * per_page
    
    # 获取总数
    cursor.execute('SELECT COUNT(*) FROM x_content')
    total_count = cursor.fetchone()[0]
    
    query = '''
        SELECT c.id, c.content, c.content_type, c.likes_count, c.retweets_count, 
               c.replies_count, c.created_at, c.collected_at, r.name, r.x_account 
        FROM x_content c
        JOIN researchers r ON c.researcher_id = r.id
        ORDER BY c.created_at DESC
        LIMIT ? OFFSET ?
    '''
    
    cursor.execute(query, (per_page, offset))
    content_list = []
    
    for row in cursor.fetchall():
        content_list.append({
            'id': row[0],
            'content': row[1],
            'content_type': row[2],
            'likes_count': row[3],
            'retweets_count': row[4],
            'replies_count': row[5],
            'created_at': row[6],
            'collected_at': row[7],
            'author_name': row[8] or 'Unknown',
            'author_handle': row[9] or '@unknown'
        })
    
    conn.close()
    return jsonify({
        'content': content_list,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total_count,
            'pages': (total_count + per_page - 1) // per_page
        }
    })

@app.route('/api/start_monitoring', methods=['POST'])
def start_monitoring_route():
    """开始监控指定研究者 - 支持批量操作"""
    data = request.get_json()
    researcher_ids = data.get('researcher_ids', [])
    
    if not researcher_ids:
        return jsonify({'error': 'No researchers selected'}), 400
    
    if len(researcher_ids) > 1000:  # 单次最多1000个
        return jsonify({'error': 'Too many researchers selected at once (max: 1000)'}), 400
    
    conn = sqlite3.connect('research_platform.db')
    cursor = conn.cursor()
    
    success_count = 0
    failed_ids = []
    
    # 开始事务
    cursor.execute('BEGIN TRANSACTION')
    
    try:
        for researcher_id in researcher_ids:
            try:
                # 更新研究者监控状态
                cursor.execute('UPDATE researchers SET is_monitoring = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (researcher_id,))
                
                # 创建监控任务
                cursor.execute('INSERT OR REPLACE INTO monitoring_tasks (researcher_id, status, last_check) VALUES (?, \'active\', CURRENT_TIMESTAMP)', (researcher_id,))
                
                success_count += 1
                
            except Exception as e:
                logger.error(f"启动监控研究者 {researcher_id} 失败: {e}")
                failed_ids.append(researcher_id)
        
        cursor.execute('COMMIT')
        
    except Exception as e:
        cursor.execute('ROLLBACK')
        logger.error(f"批量启动监控失败: {e}")
        return jsonify({'error': 'Failed to start monitoring'}), 500
    
    finally:
        conn.close()
    
    # 确保监控服务正在运行
    monitoring_service.start_monitoring()
    
    response_data = {
        'message': f'成功启动监控 {success_count} 位研究者',
        'monitoring_count': success_count
    }
    
    if failed_ids:
        response_data['failed_ids'] = failed_ids
        response_data['message'] += f', {len(failed_ids)} 位失败'
    
    return jsonify(response_data)

@app.route('/api/stop_monitoring', methods=['POST'])
def stop_monitoring_route():
    """停止监控指定研究者"""
    data = request.get_json()
    researcher_ids = data.get('researcher_ids', [])
    
    if len(researcher_ids) > 1000:
        return jsonify({'error': 'Too many researchers selected at once (max: 1000)'}), 400
    
    conn = sqlite3.connect('research_platform.db')
    cursor = conn.cursor()
    
    cursor.execute('BEGIN TRANSACTION')
    
    try:
        for researcher_id in researcher_ids:
            cursor.execute('UPDATE researchers SET is_monitoring = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (researcher_id,))
            cursor.execute('UPDATE monitoring_tasks SET status = \'inactive\' WHERE researcher_id = ?', (researcher_id,))
        
        cursor.execute('COMMIT')
        
    except Exception as e:
        cursor.execute('ROLLBACK')
        logger.error(f"批量停止监控失败: {e}")
        return jsonify({'error': 'Failed to stop monitoring'}), 500
    
    finally:
        conn.close()
    
    return jsonify({'message': f'已停止监控 {len(researcher_ids)} 位研究者'})

@app.route('/api/fetch_content/<int:researcher_id>', methods=['POST'])
def fetch_researcher_content(researcher_id):
    """立即获取指定研究者的最新内容"""
    conn = sqlite3.connect('research_platform.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT name, x_account FROM researchers WHERE id = ?', (researcher_id,))
    researcher = cursor.fetchone()
    
    if not researcher:
        conn.close()
        return jsonify({'error': 'Researcher not found'}), 404
    
    name, x_account = researcher
    
    try:
        # 获取最新推文
        tweets = twitter_api.get_user_tweets(x_account, max_results=10)
        
        new_content_count = 0
        if tweets:
            for tweet in tweets:
                cursor.execute('''
                    INSERT OR IGNORE INTO x_content 
                    (researcher_id, tweet_id, content, likes_count, retweets_count, replies_count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    researcher_id, tweet['id'], tweet['content'],
                    tweet['likes'], tweet['retweets'], tweet['replies'],
                    tweet['created_at']
                ))
                
                if cursor.rowcount > 0:
                    new_content_count += 1
            
            conn.commit()

        conn.close()
        
        message = f'成功获取 {name} 的内容。' if tweets else f'未找到 {name} 的新内容。'
        return jsonify({
            'message': message,
            'new_content_count': new_content_count,
            'total_fetched': len(tweets)
        })
        
    except Exception as e:
        conn.close()
        logger.error(f"获取 {name} 内容失败: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics')
def get_analytics():
    """获取平台分析数据"""
    conn = sqlite3.connect('research_platform.db')
    cursor = conn.cursor()
    
    # 基础统计
    cursor.execute('SELECT COUNT(*) FROM researchers')
    total_researchers = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM researchers WHERE is_monitoring = 1')
    monitoring_researchers = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM x_content')
    total_content = cursor.fetchone()[0]
    
    cursor.execute('SELECT SUM(likes_count + retweets_count + replies_count) FROM x_content')
    total_engagement = cursor.fetchone()[0] or 0
    
    # 国家分布
    cursor.execute('SELECT country, COUNT(*) FROM researchers GROUP BY country')
    country_distribution = {k: v for k, v in cursor.fetchall() if k}
    
    # 公司分布
    cursor.execute('SELECT company, COUNT(*) FROM researchers GROUP BY company')
    company_distribution = {k: v for k, v in cursor.fetchall() if k}
    
    # 最近7天的内容趋势
    cursor.execute('''
        SELECT DATE(created_at), COUNT(*) 
        FROM x_content 
        WHERE created_at >= date('now', '-7 days')
        GROUP BY DATE(created_at)
        ORDER BY DATE(created_at)
    ''')
    content_trend = dict(cursor.fetchall())
    
    # 监控能力状态
    cursor.execute('SELECT MAX(rank) FROM researchers')
    max_capacity = 5000  # 最大支持容量
    current_capacity = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return jsonify({
        'total_researchers': total_researchers,
        'monitoring_researchers': monitoring_researchers,
        'total_content': total_content,
        'total_engagement': total_engagement,
        'country_distribution': country_distribution,
        'company_distribution': company_distribution,
        'content_trend': content_trend,
        'api_status': 'connected' if twitter_api.client else 'disconnected',
        'monitoring_active': monitoring_service.running,
        'capacity': {
            'current': total_researchers,
            'monitoring': monitoring_researchers,
            'max_supported': max_capacity,
            'utilization': f"{(total_researchers/max_capacity)*100:.1f}%"
        }
    })

@app.route('/api/upload_excel', methods=['POST'])
def upload_excel():
    """上传Excel文件 - 增强错误处理和批量导入"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # 检查文件类型
    if not file.filename.lower().endswith(('.xlsx', '.xls')):
        return jsonify({'error': 'Please upload an Excel file (.xlsx or .xls)'}), 400
    
    try:
        import openpyxl
        workbook = openpyxl.load_workbook(file)
        worksheet = workbook.active
        
        logger.info(f"📊 开始处理Excel文件，共 {worksheet.max_row - 1} 行数据")
        
        conn = sqlite3.connect('research_platform.db')
        cursor = conn.cursor()
        
        # 开始事务
        cursor.execute('BEGIN TRANSACTION')
        
        added_count = 0
        error_count = 0
        skipped_count = 0
        error_details = []
        
        # 批量处理数据
        batch_size = 100
        batch_data = []
        
        for row_num, row in enumerate(worksheet.iter_rows(min_row=2, values_only=True), start=2):
            try:
                # 数据验证
                if not row or len(row) < 6:
                    skipped_count += 1
                    logger.warning(f"第 {row_num} 行：数据不完整，跳过")
                    continue
                
                if not row[1]:  # 名字不能为空
                    skipped_count += 1
                    logger.warning(f"第 {row_num} 行：研究者姓名为空，跳过")
                    continue
                
                # 清理和验证数据
                rank = row[0] if row[0] is not None else row_num - 1
                name = str(row[1]).strip() if row[1] else ''
                country = str(row[2]).strip() if row[2] else ''
                company = str(row[3]).strip() if row[3] else ''
                research_focus = str(row[4]).strip() if row[4] else ''
                x_account = str(row[5]).strip() if row[5] else ''
                
                # 确保 X 账号格式正确
                if x_account and not x_account.startswith('@'):
                    x_account = '@' + x_account
                
                batch_data.append((rank, name, country, company, research_focus, x_account))
                
                # 达到批量大小时执行插入
                if len(batch_data) >= batch_size:
                    added_count += insert_researcher_batch(cursor, batch_data, error_details)
                    batch_data = []
                
            except Exception as e:
                error_count += 1
                error_msg = f"第 {row_num} 行处理失败: {str(e)}"
                logger.error(error_msg)
                error_details.append(error_msg)
                
                if error_count > 50:  # 如果错误太多，停止处理
                    logger.error("错误过多，停止处理文件")
                    break
        
        # 处理剩余的批量数据
        if batch_data:
            added_count += insert_researcher_batch(cursor, batch_data, error_details)
        
        # 提交事务
        cursor.execute('COMMIT')
        conn.close()
        
        total_processed = worksheet.max_row - 1
        
        logger.info(f"✅ Excel导入完成: 成功 {added_count}, 跳过 {skipped_count}, 错误 {error_count}")
        
        response_data = {
            'message': f'Excel文件处理完成',
            'total_rows': total_processed,
            'imported': added_count,
            'skipped': skipped_count,
            'errors': error_count
        }
        
        if error_details and len(error_details) <= 20:  # 只返回前20个错误
            response_data['error_details'] = error_details[:20]
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"❌ Excel文件处理失败: {e}")
        return jsonify({
            'error': f'文件处理失败: {str(e)}',
            'suggestion': '请检查文件格式，确保包含必要的列：排名、姓名、国家、公司、研究领域、X账号'
        }), 500

def insert_researcher_batch(cursor, batch_data, error_details):
    """批量插入研究者数据"""
    added_count = 0
    
    for data in batch_data:
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO researchers 
                (rank, name, country, company, research_focus, x_account)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', data)
            added_count += 1
            
        except Exception as e:
            error_msg = f"插入数据失败 {data[1]}: {str(e)}"
            error_details.append(error_msg)
            logger.error(error_msg)
    
    return added_count

@app.route('/api/system_status')
def get_system_status():
    """获取系统状态信息"""
    conn = sqlite3.connect('research_platform.db')
    cursor = conn.cursor()
    
    # 数据库统计
    cursor.execute('SELECT COUNT(*) FROM researchers')
    total_researchers = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM researchers WHERE is_monitoring = 1')
    monitoring_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM x_content')
    total_content = cursor.fetchone()[0]
    
    # 最近24小时的活动
    cursor.execute('''
        SELECT COUNT(*) FROM x_content 
        WHERE collected_at >= datetime('now', '-1 day')
    ''')
    recent_content = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'system_capacity': {
            'max_researchers': 5000,
            'current_researchers': total_researchers,
            'available_slots': 5000 - total_researchers,
            'utilization_percentage': (total_researchers / 5000) * 100
        },
        'monitoring_status': {
            'active_monitoring': monitoring_count,
            'max_concurrent': 1000,
            'service_running': monitoring_service.running
        },
        'data_statistics': {
            'total_content': total_content,
            'recent_24h': recent_content
        },
        'api_status': {
            'twitter_connected': twitter_api.client is not None,
            'last_check': datetime.now().isoformat()
        }
    })

@app.route('/health')
def health_check():
    """健康检查"""
    return jsonify({
        'status': 'healthy' if researcher_manager else 'partial',
        'timestamp': datetime.now().isoformat(),
        'twitter_api': 'connected' if twitter_api and twitter_api.client else 'disconnected',
        'monitoring': 'active' if monitoring_service and monitoring_service.running else 'inactive',
        'capacity': '5000 researchers supported',
        'components': {
            'researcher_manager': 'ok' if researcher_manager else 'failed',
            'twitter_api': 'ok' if twitter_api else 'failed',
            'monitoring_service': 'ok' if monitoring_service else 'failed'
        }
    })

@app.route('/api/init_status')
def get_init_status():
    """获取初始化状态"""
    return jsonify({
        'initialized': bool(researcher_manager),
        'components': {
            'database': bool(researcher_manager),
            'twitter_api': bool(twitter_api),
            'monitoring': bool(monitoring_service)
        },
        'ready': bool(researcher_manager and twitter_api and monitoring_service)
    })

if __name__ == '__main__':
    logger.info("🚀 AI研究者X内容学习平台启动中...")
    logger.info(f"📊 系统容量: 最大支持 5000 位研究者监控")
    logger.info(f"Twitter API: {'✅ 已配置' if TWITTER_BEARER_TOKEN else '⚠️ 未配置，将无法获取真实数据'}")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
