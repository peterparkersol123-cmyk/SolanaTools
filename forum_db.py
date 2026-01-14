import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional
import os

class ForumDatabase:
    def __init__(self, db_path: str = 'forum.db'):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Posts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                author TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Replies table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                author TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE
            )
        ''')

        conn.commit()
        conn.close()

    def create_post(self, title: str, content: str, author: str) -> Dict:
        """Create a new post"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        timestamp = datetime.utcnow().isoformat()

        cursor.execute(
            'INSERT INTO posts (title, content, author, timestamp) VALUES (?, ?, ?, ?)',
            (title, content, author, timestamp)
        )

        post_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {
            'id': post_id,
            'title': title,
            'content': content,
            'author': author,
            'timestamp': timestamp,
            'replies': []
        }

    def create_reply(self, post_id: int, content: str, author: str) -> Dict:
        """Create a new reply"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        timestamp = datetime.utcnow().isoformat()

        cursor.execute(
            'INSERT INTO replies (post_id, content, author, timestamp) VALUES (?, ?, ?, ?)',
            (post_id, content, author, timestamp)
        )

        reply_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {
            'id': reply_id,
            'content': content,
            'author': author,
            'timestamp': timestamp
        }

    def get_all_posts(self) -> List[Dict]:
        """Get all posts with their replies"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get all posts
        cursor.execute('SELECT * FROM posts ORDER BY created_at DESC')
        posts = [dict(row) for row in cursor.fetchall()]

        # Get replies for each post
        for post in posts:
            cursor.execute(
                'SELECT * FROM replies WHERE post_id = ? ORDER BY created_at ASC',
                (post['id'],)
            )
            post['replies'] = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return posts

    def get_post(self, post_id: int) -> Optional[Dict]:
        """Get a single post with replies"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM posts WHERE id = ?', (post_id,))
        post = cursor.fetchone()

        if not post:
            conn.close()
            return None

        post = dict(post)

        cursor.execute(
            'SELECT * FROM replies WHERE post_id = ? ORDER BY created_at ASC',
            (post_id,)
        )
        post['replies'] = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return post

    def delete_post(self, post_id: int) -> bool:
        """Delete a post and its replies"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM posts WHERE id = ?', (post_id,))
        affected = cursor.rowcount

        conn.commit()
        conn.close()

        return affected > 0
