#!/usr/bin/python2.7
from __future__ import print_function

import feedparser
import datetime
import dateutil.parser
import signal
import time
import requests
import threading
import os
import traceback
import random
import re
from db import FeedDB
from config import Config


def shorten_url(url, config):
    """
    Returns None on error
    """
    retries = 3
    while retries >= 0:
        # always sleep some time as a rate limit
        time.sleep(random.random() * 2)
        try:
            bitly = "{}/shorten?access_token={}&longUrl={}&domain=j.mp".format(
                "https://api-ssl.bitly.com/v3",
                config.bitly_apikey,
                url
            )
            response = requests.get(bitly)
            assert response.status_code == 200
            data = response.json()
            assert data['status_txt'] == 'OK'
            assert data['status_code'] == 200
            # Bitly will return a short url as text
            short_url = data['data']['url'].replace('http://', 'https://')
            if config.BITLY_OVERRIDE_DOMAIN:
                return short_url.replace('bit.ly', config.BITLY_OVERRIDE_DOMAIN)
            return short_url
        except Exception as e:
            print('Bitly error', e)
            retries -= 1
            time.sleep(random.random() * 5)


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

    def extract_url(self, newsitem, force_shorten=False):
        """
        Take our newsitem and return the title as a string. Take
        care of url shortening, as well.
        """
        newsurl = newsitem.link
        urllen = len(newsitem.link)

        # if we have a arXiv link, use the versioned link
        if re.match('https?://arxiv.org/', newsurl):
            matches = re.match(self.__config.find_pattern, newsitem.title)
            if matches and matches.groupdict().get('version'):
                url = "%s%s" % (newsitem.link, matches.groupdict()['version'])
                newsitem.link = url
                newsurl = url
                print("versioned url %s" % url)

        if force_shorten or (urllen > self.__config.SHORTEN_URLS):
            try:
                newsurl = shorten_url(newsitem.link, self.__config)
            except Exception as e:
                print('Error loading tinyurl', e)
                newsurl = None
            # If that fails, use the long version ... yes apparently it returns
            # the string "Error" on error
            if not newsurl:
                print("Link shortening failed", newsurl)
                newsurl = newsitem.link
            # the tinyurl library has http links hardcoded
            newsurl = newsurl.replace(
                'http://tinyurl.com', 'https://tinyurl.com'
            )

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
                    and not observations

                if not wait_for_observations and idle:
                    # Reverse the ordering. Oldest first.
                    for newsitem in news.entries[::-1]:
                        # formatting
                        newstitle = newsitem.title
                        newsdate = self.extract_date(newsitem)
                        fs = feed_info['title'] in self.__config.FORCE_SHORTEN
                        newsurl = self.extract_url(newsitem, force_shorten=fs)
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
                    print(feed_info['url'], "chan", \
                        self.__config.CHANNEL, "is idle")

            except Exception as e:
                tb = traceback.format_exc()
                print(e, tb)
                print("Error on url: {} error {} \n {}".format(
                    feed_info['url'], e, tb))

            if not forever:
                break

            # sleep frequency minutes
            time.sleep(int(feed_info['published'])*60)

if __name__ == "__main__":
    def print_line(feed_title, news_title, news_url, news_date):
        print(("[+]: {}||{}||{}||{}".format(
            feed_title.decode("utf-8"), news_title, news_url, news_date
        )))

    def main():
        config = Config()
        db = FeedDB(config)
        updater = FeedUpdater(config, db)
        updater.update_feeds(print_line, False)

    def signal_handler(signal, frame):
        print("Caught SIGINT, terminating.")
        os._exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    main()
