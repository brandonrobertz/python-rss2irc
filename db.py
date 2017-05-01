#!/usr/bin/env python
# -*- coding: utf-8 -*-

from sqlite3worker import Sqlite3Worker
import os
import datetime
import time

class FeedDB(object):
    def __init__(self, config):
        self.__db_path = "./feeds.db"
        self.__db_worker = None
        self.__config = config
        self.__initiate_db()

    def __initiate_db(self):
        """Create a DB connection"""

        # If the database doesn't exist, create and prepopulate it with feeds.sql
        if not os.path.exists(self.__db_path):
            self.__db_worker = Sqlite3Worker(self.__db_path)
            self.__db_worker.execute('CREATE TABLE feeds (id INTEGER PRIMARY KEY AUTOINCREMENT, name CHAR(200) UNIQUE, url CHAR(200) UNIQUE, frequency INTEGER(3))')
            self.__db_worker.execute('CREATE TABLE news (id INTEGER PRIMARY KEY AUTOINCREMENT, title CHAR(255), url CHAR(255), feedid INTEGER, published TEXT, FOREIGN KEY(feedid) REFERENCES feeds(id))')
            self.__db_worker.execute('CREATE TABLE chat (id INTEGER PRIMARY KEY AUTOINCREMENT, chan CHAR(255), time REAL)')
            if os.path.exists("./feeds.sql"):
                f = open("./feeds.sql", "r")
                for insert in f.readlines():
                    self.__db_worker.execute(insert.strip())
                f.close()
        else:
            self.__db_worker = Sqlite3Worker(self.__db_path)

    def get_feeds(self):
        """Returns all feeds"""
        feeds = []
        for feed in self.__db_worker.execute("select id,name,url,frequency from feeds"):
            feeds.append(feed)
        return feeds

    def get_news_from_feed(self, feed_id, limit=10):
        """Returns 'limit' news from a specific feed"""
        news = []
        for item in self.__db_worker.execute("select id, title, url, published from news where feedid = :feedid order by id desc limit :limit", {'feedid': feed_id, 'limit':limit}):
            news.append(item)
        return news

    def get_latest_news(self, limit=10):
        """Returns 'limit' latest news"""
        news = []
        for item in self.__db_worker.execute("select id, title, url, published from news order by id desc limit :limit", {'limit':limit}):
            news.append(item)
        return news

    def get_feeds_count(self):
        """Returns the feed count"""
        count = self.__db_worker.execute("select count(id) from feeds")[0][0]
        return count

    def get_news_count(self):
        """Returns the news count"""
        count = self.__db_worker.execute("select count(id) from news")[0][0]
        return count

    def insert_news(self, feed_id, title, url, published):
        """Checks if a news item with the given information exists. If not, create a new entry."""
        exists = self.__db_worker.execute("select exists(select 1 FROM news WHERE feedid = :feedid and url = :url and published = :published LIMIT 1)", {'feedid': feed_id, 'url': url, 'published': published})[0][0]
        if exists:
            return False
        self.__db_worker.execute("INSERT INTO news (title, url, feedid, published) VALUES (:title, :url, :feedid, :published)", {'title': title, 'url': url, 'feedid': feed_id, 'published': published})
        return True

    def set_new_chan_message(self, chan):
        print "chan", chan
        results = self.__db_worker.execute(
            "select id from chat where chan = :chan",
            {"chan": chan}
        )
        print "results", results
        now = datetime.datetime.now()
        ts = time.mktime(now.timetuple())
        print "Setting timestamp", ts
        if not results:
            print "inserting"
            self.__db_worker.execute(
                "insert into chat (chan, time) values ( :chan, :time)",
                {"chan": chan, "time": ts}
            )
        else:
            pk = results[0][0]
            print "updating", pk
            self.__db_worker.execute(
                "update chat set time = :time where id = :id limit 1",
                {"time": ts, "id": pk}
            )
  
    def is_chan_idle(self, chan, minutes):
        # we want to check and see if we have a last message sent after
        # now minus N (idle) minutes. if we pull a record with a timestamp
        # greater than now - minutes, return false, room not idle
        now = datetime.datetime.now()
        now_minus = time.mktime((now - datetime.timedelta(minutes=minutes)).timetuple())
        results = self.__db_worker.execute(
            "select id from chat where time > :now_minus and chan = :chan",
            {"now_minus": now_minus, "chan": chan})
        if results:
            return False
        return True
