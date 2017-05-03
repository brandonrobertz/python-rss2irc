#!/usr/bin/python2.7

import feedparser
import datetime
import dateutil.parser
import signal
import time
import tinyurl
import threading
import os
import traceback
from db import FeedDB
from config import Config

class FeedUpdater(object):

    def __init__(self, config, db):
        self.__config = config
        self.__db = db
        self.__threads = []

    def update_feeds(self, callback=None, forever=False):
        for feed in self.__db.get_feeds():
            t = threading.Thread(
                target=self.__fetch_feed,
                args=({
                    'id': feed[0],
                    'title': feed[1],
                    'url': feed[2],
                    'published': feed[3]
                }, callback, forever,
            ))
            t.start()
            self.__threads.append(t)

        if not forever:
            for thread in self.__threads:
                thread.join()
                self.__threads.remove(thread)

    def extract_date(self, newsitem):
        """
        Take a newsitem and return a human-friendly date string.
        """
        # Try to get the published or updated date. Otherwise set it to 'no date'
        try:
            # Get date and parse it
            newsdate = dateutil.parser.parse(newsitem.published)
            # Format date based on 'dateformat' in config.py
            return newsdate.strftime(self.__config.dateformat)
        except Exception:
            pass

        try:
            # Get date and parse it
            newsdate = dateutil.parser.parse(newsitem.updated)
            # Format date based on 'dateformat' in config.py
            return newsdate.strftime(self.__config.dateformat)
        except Exception:
            pass

        return "no date"

    def extract_url(self, newsitem):
        """
        Take our newsitem and return the title as a string. Take
        care of url shortening, as well.
        """
        newsurl = newsitem.link

        if self.__config.SHORTEN_URLS and len(newsitem.link) > self.__config.SHORTEN_URLS:
            newsurl = tinyurl.create_one(newsitem.link) # Create a short link
            if newsurl == "Error": #If that fails, use the long version
                print "Link shortening failed", newsurl
                newsurl = newsitem.link

        return newsurl

    def __fetch_feed(self, feed_info, callback, forever):
        """
        Fetches a RSS feed, parses it and updates the database and/or announces
        new news.
        """
        while True:
            try:
                # Parse a feed's url, do this before the idle check
                # because this can take a significant amount of time.
                # we want to eliminate race conditions as much as possible
                news = feedparser.parse( feed_info['url'] )

                # if we have no channel observations since startup, we need
                # to wait for one
                observations = self.__db.chan_messages_count(
                    self.__config.CHANNEL
                )

                # check to see  if we should check feed or not
                idle = self.__db.is_chan_idle(
                    self.__config.CHANNEL,
                    self.__config.IDLE_MINUTES
                )

                wait_for_observations = self.__config.WAIT_FOR_FIRST_MSG \
                    and observations

                print('wait?', wait_for_observations, 'idle?', idle)

                if not wait_for_observations and idle:
                    # Reverse the ordering. Oldest first.
                    for newsitem in news.entries[::-1]:
                        # formatting
                        newstitle = newsitem.title
                        newsdate = self.extract_date(newsitem)
                        newsurl = self.extract_url(newsitem)
                        # Update the database. If it's new, post it
                        is_new = self.__db.insert_news(
                            feed_info['id'],
                            newstitle,
                            newsitem.link,
                            newsdate
                        )
                        if is_new and callback is not None:
                            callback(
                                feed_info['title'],
                                newstitle,
                                newsurl,
                                newsdate
                            )
                else:
                    print feed_info['url'], "chan", \
                        self.__config.CHANNEL, "is idle"

            except Exception as e:
                tb = traceback.format_exc()
                print e, tb
                print "Error on title: {} error {} \n {}".format(
                    feed_info['title'], e, tb)

            if not forever:
                break

            # sleep frequency minutes
            time.sleep(int(feed_info['published'])*60)

if __name__ == "__main__":
    def print_line(feed_title, news_title, news_url, news_date):
        print(u"[+]: {}||{}||{}||{}".format(
            feed_title.decode("utf-8"), news_title, news_url, news_date
        ))

    def main():
        config = Config()
        db = FeedDB(config)
        updater = FeedUpdater(config, db)
        updater.update_feeds(print_line, False)

    def signal_handler(signal, frame):
        print "Caught SIGINT, terminating."
        os._exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    main()
