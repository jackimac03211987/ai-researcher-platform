from flask import Flask, render_template, jsonify, request, send_from_directory
import json
import tweepy
import os
import secrets
from datetime import datetime, timedelta
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
                logger.info("✅ Twitter API连接成功")
                self.test_connection()
            except Exception as e:
                logger.error(f"❌ Twitter API初始化失败: {e}")
                self.client = None
        else:
            self.client = None
            logger.warning("⚠️ Twitter Bearer Token未配置")
    
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
        """获取用户推文"""
        if not self.client:
            return self.get_mock_tweets(username)
        
        try:
            # 移除@符号
            username = username.replace('@', '')
            
            # 获取用户信息
            user = self.client.get_user(username=username)
            if not user.data:
                logger.warning(f"用户 {username} 不存在")
                return self.get_mock_tweets(username)
            
            # 获取推文
            tweets = self.client.get_users_tweets(
                id=user.data.id,
                max_results=min(max_results, 100),
                tweet_fields=['created_at', 'public_metrics', 'context_annotations'],
                exclude=['retweets', 'replies']
            )
            
            if not tweets.data:
                return self.get_mock_tweets(username)
            
            result = []
            for tweet in tweets.data:
                result.append({
                    'id': str(tweet.id),
                    'content': tweet.text,
                    'created_at': tweet.created_at.isoformat() if tweet.created_at else None,
                    'likes': tweet.public_metrics['like_count'],
                    'retweets': tweet.public_metrics['retweet_count'],
                    'replies': tweet.public_metrics['reply_count'],
                    'author': username,
                    'type': 'text'
                })
            
            logger.info(f"✅ 成功获取 {username} 的 {len(result)} 条推文")
            return result
            
        except Exception as e:
            logger.error(f"获取 {username} 推文失败: {e}")
            return self.get_mock_tweets(username)
    
    def get_mock_tweets(self, username):
        """模拟数据"""
        return [
            {
                'id': f'mock_{username}_1',
                'content': f'Latest research insights from {username}. The future of AI is incredible! 🚀',
                'created_at': (datetime.now() - timedelta(hours=2)).isoformat(),
                'likes': 1247,
                'retweets': 389,
                'replies': 156,
                'author': username,
                'type': 'text'
            },
            {
                'id': f'mock_{username}_2', 
                'content': f'Sharing some thoughts on the latest developments in machine learning.',
                'created_at': (datetime.now() - timedelta(hours=6)).isoformat(),
                'likes': 856,
                'retweets': 234,
                'replies': 89,
                'author': username,
                'type': 'text'
            }
        ]

class ResearcherManager:
    def __init__(self):
        self.init_database()
        self.load_sample_data()
    
    def init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect('research_platform.db')
        cursor = conn.cursor()
        
        # 研究者表
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
        
        # 内容表
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
                FOREIGN KEY (researcher_id) REFERENCES researchers (id)
            )
        ''')
        
        # 监控任务表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS monitoring_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                researcher_id INTEGER,
                status TEXT DEFAULT 'active',
                last_check DATETIME DEFAULT CURRENT_TIMESTAMP,
                check_interval INTEGER DEFAULT 3600,
                FOREIGN KEY (researcher_id) REFERENCES researchers (id)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✅ 数据库初始化完成")
    
    def load_sample_data(self):
        """加载示例数据"""
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
researcher_manager = ResearcherManager()
twitter_api = TwitterAPI()

# 监控任务
class MonitoringService:
    def __init__(self):
        self.running = False
        self.thread = None
    
    def start_monitoring(self):
        """启动监控服务"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.thread.start()
            logger.info("🚀 监控服务已启动")
    
    def _monitoring_loop(self):
        """监控循环"""
        while self.running:
            try:
                self._check_researchers()
                time.sleep(1800)  # 每30分钟检查一次
            except Exception as e:
                logger.error(f"监控循环错误: {e}")
                time.sleep(60)
    
    def _check_researchers(self):
        """检查所有正在监控的研究者"""
        conn = sqlite3.connect('research_platform.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, name, x_account FROM researchers WHERE is_monitoring = 1')
        researchers = cursor.fetchall()
        
        for researcher_id, name, x_account in researchers:
            try:
                tweets = twitter_api.get_user_tweets(x_account, max_results=5)
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
                
                # 更新最后检查时间
                cursor.execute('''
                    UPDATE monitoring_tasks SET last_check = CURRENT_TIMESTAMP 
                    WHERE researcher_id = ?
                ''', (researcher_id,))
                
                logger.info(f"✅ 已更新 {name} 的内容")
                
            except Exception as e:
                logger.error(f"检查 {name} 时出错: {e}")
        
        conn.commit()
        conn.close()

monitoring_service = MonitoringService()

# API路由
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/researchers')
def get_researchers():
    """获取研究者列表"""
    conn = sqlite3.connect('research_platform.db')
    cursor = conn.cursor()
    
    search_query = request.args.get('search', '')
    
    if search_query:
        cursor.execute('''
            SELECT * FROM researchers 
            WHERE name LIKE ? OR company LIKE ? OR research_focus LIKE ?
            ORDER BY rank
        ''', (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%'))
    else:
        cursor.execute('SELECT * FROM researchers ORDER BY rank')
    
    researchers = []
    for row in cursor.fetchall():
        researchers.append({
            'id': row[0], 'rank': row[1], 'name': row[2], 'country': row[3],
            'company': row[4], 'research_focus': row[5], 'x_account': row[6],
            'followers_count': row[7], 'following_count': row[8],
            'is_monitoring': bool(row[10])
        })
    
    conn.close()
    return jsonify(researchers)

@app.route('/api/researcher/<int:researcher_id>')
def get_researcher_detail(researcher_id):
    """获取研究者详情"""
    conn = sqlite3.connect('research_platform.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM researchers WHERE id = ?', (researcher_id,))
    researcher = cursor.fetchone()
    
    if not researcher:
        return jsonify({'error': 'Researcher not found'}), 404
    
    # 获取最新内容
    cursor.execute('''
        SELECT * FROM x_content WHERE researcher_id = ? 
        ORDER BY created_at DESC LIMIT 10
    ''', (researcher_id,))
    content = cursor.fetchall()
    
    conn.close()
    
    return jsonify({
        'researcher': {
            'id': researcher[0], 'rank': researcher[1], 'name': researcher[2],
            'country': researcher[3], 'company': researcher[4], 
            'research_focus': researcher[5], 'x_account': researcher[6],
            'followers_count': researcher[7], 'following_count': researcher[8],
            'is_monitoring': bool(researcher[10])
        },
        'recent_content': [
            {
                'id': c[0], 'content': c[3], 'likes': c[5], 
                'retweets': c[6], 'replies': c[7], 'created_at': c[8]
            } for c in content
        ]
    })

@app.route('/api/content')
def get_content():
    """获取所有内容"""
    conn = sqlite3.connect('research_platform.db')
    cursor = conn.cursor()
    
    limit = request.args.get('limit', 20)
    content_type = request.args.get('type', 'all')
    
    query = '''
        SELECT c.*, r.name, r.x_account 
        FROM x_content c
        LEFT JOIN researchers r ON c.researcher_id = r.id
        ORDER BY c.created_at DESC
        LIMIT ?
    '''
    
    cursor.execute(query, (limit,))
    content_list = []
    
    for row in cursor.fetchall():
        content_list.append({
            'id': row[0],
            'content': row[3],
            'content_type': row[4],
            'likes_count': row[5],
            'retweets_count': row[6],
            'replies_count': row[7],
            'created_at': row[8],
            'collected_at': row[9],
            'author_name': row[10] or 'Unknown',
            'author_handle': row[11] or '@unknown'
        })
    
    conn.close()
    return jsonify(content_list)

@app.route('/api/start_monitoring', methods=['POST'])
def start_monitoring():
    """开始监控指定研究者"""
    data = request.get_json()
    researcher_ids = data.get('researcher_ids', [])
    
    if not researcher_ids:
        return jsonify({'error': 'No researchers selected'}), 400
    
    conn = sqlite3.connect('research_platform.db')
    cursor = conn.cursor()
    
    success_count = 0
    for researcher_id in researcher_ids:
        try:
            # 更新研究者监控状态
            cursor.execute('''
                UPDATE researchers SET is_monitoring = 1, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (researcher_id,))
            
            # 创建监控任务
            cursor.execute('''
                INSERT OR REPLACE INTO monitoring_tasks (researcher_id, status, last_check)
                VALUES (?, 'active', CURRENT_TIMESTAMP)
            ''', (researcher_id,))
            
            success_count += 1
            
        except Exception as e:
            logger.error(f"启动监控研究者 {researcher_id} 失败: {e}")
    
    conn.commit()
    conn.close()
    
    # 启动监控服务
    monitoring_service.start_monitoring()
    
    return jsonify({
        'message': f'成功启动监控 {success_count} 位研究者',
        'monitoring_count': success_count
    })

@app.route('/api/stop_monitoring', methods=['POST'])
def stop_monitoring():
    """停止监控指定研究者"""
    data = request.get_json()
    researcher_ids = data.get('researcher_ids', [])
    
    conn = sqlite3.connect('research_platform.db')
    cursor = conn.cursor()
    
    for researcher_id in researcher_ids:
        cursor.execute('''
            UPDATE researchers SET is_monitoring = 0, updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (researcher_id,))
        
        cursor.execute('''
            UPDATE monitoring_tasks SET status = 'inactive' 
            WHERE researcher_id = ?
        ''', (researcher_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'message': f'已停止监控 {len(researcher_ids)} 位研究者'})

@app.route('/api/fetch_content/<int:researcher_id>', methods=['POST'])
def fetch_researcher_content(researcher_id):
    """立即获取指定研究者的最新内容"""
    conn = sqlite3.connect('research_platform.db')
    cursor = conn.cursor()
    
    # 获取研究者信息
    cursor.execute('SELECT name, x_account FROM researchers WHERE id = ?', (researcher_id,))
    researcher = cursor.fetchone()
    
    if not researcher:
        return jsonify({'error': 'Researcher not found'}), 404
    
    name, x_account = researcher
    
    try:
        # 获取最新推文
        tweets = twitter_api.get_user_tweets(x_account, max_results=10)
        
        new_content_count = 0
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
        
        return jsonify({
            'message': f'成功获取 {name} 的内容',
            'new_content_count': new_content_count,
            'total_fetched': len(tweets)
        })
        
    except Exception as e:
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
    country_distribution = dict(cursor.fetchall())
    
    # 公司分布
    cursor.execute('SELECT company, COUNT(*) FROM researchers GROUP BY company')
    company_distribution = dict(cursor.fetchall())
    
    # 最近7天的内容趋势
    cursor.execute('''
        SELECT DATE(created_at), COUNT(*) 
        FROM x_content 
        WHERE created_at >= date('now', '-7 days')
        GROUP BY DATE(created_at)
        ORDER BY DATE(created_at)
    ''')
    content_trend = dict(cursor.fetchall())
    
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
        'monitoring_active': monitoring_service.running
    })

@app.route('/api/upload_excel', methods=['POST'])
def upload_excel():
    """上传Excel文件"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    try:
        # 简单处理Excel文件（不使用pandas）
        import openpyxl
        workbook = openpyxl.load_workbook(file)
        worksheet = workbook.active
        
        # 获取标题行
        headers = [cell.value for cell in worksheet[1]]
        logger.info(f"Excel headers: {headers}")
        
        # 处理数据行
        conn = sqlite3.connect('research_platform.db')
        cursor = conn.cursor()
        
        added_count = 0
        for row in worksheet.iter_rows(min_row=2, values_only=True):
            if len(row) >= 6 and row[1]:  # 至少有6列且名称不为空
                try:
                    cursor.execute('''
                        INSERT OR REPLACE INTO researchers 
                        (rank, name, country, company, research_focus, x_account)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        row[0], row[1], row[2], row[3], row[4], row[5]
                    ))
                    added_count += 1
                except Exception as e:
                    logger.error(f"插入数据行失败: {e}")
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': f'成功导入 {added_count} 位研究者数据',
            'total_rows': worksheet.max_row - 1,
            'imported': added_count
        })
        
    except Exception as e:
        logger.error(f"Excel处理失败: {e}")
        return jsonify({'error': f'文件处理失败: {str(e)}'}), 500

@app.route('/health')
def health_check():
    """健康检查"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'twitter_api': 'connected' if twitter_api.client else 'disconnected',
        'monitoring': 'active' if monitoring_service.running else 'inactive'
    })

if __name__ == '__main__':
    logger.info("🚀 AI研究者X内容学习平台启动中...")
    logger.info(f"Twitter API: {'✅ 已配置' if TWITTER_BEARER_TOKEN else '⚠️ 未配置，使用模拟数据'}")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
