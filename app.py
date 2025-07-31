from flask import Flask, render_template, jsonify, request
import json
import tweepy
import os
import secrets
from datetime import datetime, timedelta
import sqlite3
import logging

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TWITTER_BEARER_TOKEN = os.environ.get('TWITTER_BEARER_TOKEN')

class TwitterAPI:
    def __init__(self):
        if TWITTER_BEARER_TOKEN:
            try:
                self.client = tweepy.Client(bearer_token=TWITTER_BEARER_TOKEN)
                logger.info("Twitter API 客户端初始化成功")
            except Exception as e:
                logger.error(f"Twitter API 初始化失败: {e}")
                self.client = None
        else:
            self.client = None
            logger.warning("Twitter Bearer Token 未配置，将使用模拟数据")
    
    def get_mock_data(self):
        return [
            {
                'id': 1,
                'author': 'Ilya Sutskever',
                'handle': '@ilyasut',
                'content': 'The future of AGI depends on our ability to understand and control emergent behaviors in large-scale neural networks.',
                'likes': 1247,
                'retweets': 389,
                'replies': 156,
                'time': '2h'
            },
            {
                'id': 2,
                'author': 'Geoffrey Hinton',
                'handle': '@geoffreyhinton', 
                'content': 'Reflections on 40 years of neural network research. The journey from backpropagation to transformers has been remarkable.',
                'likes': 2103,
                'retweets': 654,
                'replies': 278,
                'time': '4h'
            }
        ]

class ResearcherManager:
    def __init__(self):
        self.init_database()
        self.load_sample_data()
    
    def init_database(self):
        conn = sqlite3.connect('research_platform.db')
        cursor = conn.cursor()
        
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
                following_count TEXT DEFAULT '0'
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def load_sample_data(self):
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
            }
        ]
        
        conn = sqlite3.connect('research_platform.db')
        cursor = conn.cursor()
        
        for researcher in researchers_data:
            cursor.execute('''
                INSERT OR REPLACE INTO researchers 
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/researchers')
def get_researchers():
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
            'followers_count': row[7], 'following_count': row[8]
        })
    
    conn.close()
    return jsonify(researchers)

@app.route('/api/content')
def get_content():
    content = twitter_api.get_mock_data()
    return jsonify(content)

@app.route('/api/analytics')
def get_analytics():
    return jsonify({
        'total_researchers': 100,
        'total_content': 2347,
        'total_engagement': 45200,
        'content_distribution': {
            'text': 75,
            'images': 50, 
            'videos': 33
        }
    })

@app.route('/api/upload_excel', methods=['POST'])
def upload_excel():
    return jsonify({'message': 'Excel功能开发中，敬请期待'})

if __name__ == '__main__':
    print("🚀 AI研究者X内容学习平台启动中...")
    print(f"Twitter API: {'已配置' if TWITTER_BEARER_TOKEN else '使用模拟数据'}")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
