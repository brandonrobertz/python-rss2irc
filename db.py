#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import datetime
import time

import logging
logging.basicConfig(level=logging.ERROR)

from sqlite3worker import Sqlite3Worker

class FeedDB(object):
    def __init__(self, config):
        self.__db_path = "./feeds.db"
        self.__db_worker = None
        self.__config = config
        self.__initiate_db()

    def __initiate_db(self):
        """
        Create a DB connection and build tables if the DB file doesn't exist.
        Attempts to create tables every time.
        """
        # If the database doesn't exist, create and prepopulate it with feeds.sql
        self.__db_worker = Sqlite3Worker(self.__db_path)
        self.__db_worker.execute(
            'CREATE TABLE feeds (id INTEGER PRIMARY KEY AUTOINCREMENT, ' \
            'name CHAR(200) UNIQUE, url CHAR(200) UNIQUE, ' \
            'frequency INTEGER(3))'
        )
        self.__db_worker.execute(
            'CREATE TABLE news (id INTEGER PRIMARY KEY AUTOINCREMENT, ' \
            'title CHAR(255), url CHAR(255), feedid INTEGER, ' \
            'published TEXT, FOREIGN KEY(feedid) REFERENCES feeds(id))'
        )
        self.__db_worker.execute(
            'CREATE TABLE chat (id INTEGER PRIMARY KEY AUTOINCREMENT, ' \
            'chan CHAR(255), time REAL)'
        )
        if os.path.exists("./feeds.sql"):
            f = open("./feeds.sql", "r")
            for insert in f.readlines():
                self.__db_worker.execute(insert.strip())
            f.close()

    def get_feeds(self):
        """Returns all feeds"""
        feeds = []
        queryresult = self.__db_worker.execute(
            "select id,name,url,frequency from feeds"
        )
        for feed in queryresult:
            feeds.append(feed)
        return feeds

    def get_news_from_feed(self, feed_id, limit=10):
        """
        Returns 'limit' news from a specific feed
        """
        news = []
        params = {'feedid': feed_id, 'limit':limit}
        items = self.__db_worker.execute(
            "select id, title, url, published from news where " \
            "feedid = :feedid order by id desc limit :limit",
            params
        )
        for item in items:
            news.append(item)
        return news

    def get_latest_news(self, limit=10):
        """
        Returns 'limit' latest news
        """
        news = []
        params = { 'limit': limit}
        items = self.__db_worker.execute(
            "select id, title, url, published from news order by id desc " \
            "limit :limit", params
        )
        for item in items:
            news.append(item)
        return news

    def get_feeds_count(self):
        """Returns the feed count"""
        return self.__db_worker.execute("select count(id) from feeds")[0][0]

    def get_news_count(self):
        """
        Returns the news items count
        """
        return self.__db_worker.execute("select count(id) from news")[0][0]

    def insert_news(self, feed_id, title, url, published):
        """
        Checks if a news item with the given information exists. If not,
        create a new entry.
        """
        params = {
            'url': url
        }
        exists = self.__db_worker.execute(
            "select exists(select 1 FROM news WHERE url = :url LIMIT 1)",
            params
        )[0][0]
        if exists:
            return False
        params = {
            'title': title, 'url': url,
            'feedid': feed_id, 'published': published
        }
        self.__db_worker.execute(
            "INSERT INTO news (title, url, feedid, published) VALUES " \
            "(:title, :url, :feedid, :published)", params
        )
        return True

    def set_new_chan_message(self, chan):
        """
        Keep track of time of last message for a given channel. This enables
        us to not interrupt ongoing conversations in a chan.
        """
        results = self.__db_worker.execute(
            "select id from chat where chan = :chan",
            {"chan": chan}
        )
        now = datetime.datetime.now()
        ts = time.mktime(now.timetuple())
        if not results:
            self.__db_worker.execute(
                "insert into chat (chan, time) values ( :chan, :time)",
                {"chan": chan, "time": ts}
            )
        else:
            pk = results[0][0]
            self.__db_worker.execute(
                "update chat set time = :time where id = :id limit 1",
                {"time": ts, "id": pk}
            )
        print "New msg for", chan, "at", now

    def now_timestamp(self):
        """
        Get a timestamp for RIGHT NOW (float)
        """
        now = datetime.datetime.now()
        return time.mktime(now.timetuple())

    def reset_messages_count(self):
        """
        Reset the last chan messages table
        """
        return self.__db_worker.execute("delete from chat")

    def chan_messages_count(self, chan):
        """
        Get number of messages in a channel
        """
        return self.__db_worker.execute(
            "select count(*) from chat where chan = :chan",
            {"chan": chan}
        )[0][0]

    def now_minus_n_as_timestamp(self, n_minutes):
        """
        Return a timestamp from n_minutes ago
        """
        now = datetime.datetime.now()
        then = (now - datetime.timedelta(minutes=n_minutes))
        now_minus = time.mktime(then.timetuple())
        return now_minus

    def is_chan_idle(self, chan, minutes):
        """
        Return boolean, has channel been idle for specified minutes?
        """
        # we want to check and see if we have a last message sent after
        # now minus N (idle) minutes. if we pull a record with a timestamp
        # greater than now - minutes, return false, room not idle
        now_minus = self.now_minus_n_as_timestamp( minutes)
        params = {
            "chan": chan,
            "now_minus": now_minus
        }
        query = "select count(id) from chat where " \
            "time > :now_minus and chan = :chan;"
        results = self.__db_worker.execute( query, params)[0][0]
        if results:
            return False
        return True
