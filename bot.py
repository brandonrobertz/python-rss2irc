#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function
import ssl
import threading
import irc.bot
import irc.client
import irc.connection
import time
import re
import feedparser
import datetime
import dateutil.parser
import traceback
from colour import Colours
from db import FeedDB
from config import Config
from feedupdater import FeedUpdater


class IRCBot(irc.bot.SingleServerIRCBot):
    def __init__(self, config, db, on_connect_cb):
        self.__config = config
        self.__db = db
        self.__on_connect_cb = on_connect_cb
        self.__servers = [irc.bot.ServerSpec(
            self.__config.HOST, self.__config.PORT, self.__config.PASSWORD
        )]
        self.__first_start = False
        self.color_num = self.__config.num_col
        self.color_date = self.__config.date
        self.color_feedname = self.__config.feedname
        self.color_url = self.__config.url
        self.dateformat = self.__config.dateformat

        if self.__config.SSL:
            ssl_factory = irc.connection.Factory(wrapper=ssl.wrap_socket)
            super(IRCBot, self).__init__(
                self.__servers,
                self.__config.NICK,
                self.__config.NICK,
                connect_factory=ssl_factory
            )
        else:
            super(IRCBot, self).__init__(
                self.__servers, self.__config.NICK, self.__config.NICK
            )

    def on_welcome(self, connection, event):
        """
        Join the correct channel upon connecting. This runs when we first join
        the IRC server.
        """
        if self.__config.NICKSERV_PASSWORD:
            print("Identifying for nick", self.__config.NICK)
            msg = "IDENTIFY {} {}".format(
                self.__config.NICK, self.__config.NICKSERV_PASSWORD
            )
            connection.privmsg( "NICKSERV", msg)
        # make sure we join chans as the last thing
        if irc.client.is_channel(self.__config.CHANNEL):
            connection.join(self.__config.CHANNEL)

    def on_join(self, connection, event):
        """
        Set up some params and run callbacks on channel join messages
        (including our own)
        """
        if not self.__first_start:
            self.__on_connect_cb()
            self.__first_start = True

        # This is stupid don't do it
        # if self.__config.CHAN_WELCOME_MSG:
        #     connection.privmsg(
        #         self.__config.CHANNEL,
        #         self.__config.CHAN_WELCOME_MSG
        #     )

    def __handle_msg(self, msg):
        """Handles a cmd private message."""
        try:
            # Print help
            if msg == "!help":
                answer = self.__help_msg()

            # List all subscribed feeds
            elif msg == "!list":
                answer = ""
                for entry in self.__db.get_feeds():
                    answer += "#" + self.__get_colored_text(self.color_num,str(entry[0])) + ": " + entry[1] + ", " + self.__get_colored_text(self.color_url,str(entry[2])) + self.__get_colored_text(self.color_date,", updated every ") + self.__get_colored_text(self.color_num,str(entry[3])) + self.__get_colored_text(self.color_date," min") + "\n"

            # Print some simple stats (Feed / News count)
            elif msg == "!stats":
                feeds_count = self.__db.get_feeds_count()
                news_count = self.__db.get_news_count()
                answer = "Feeds: " + self.__get_colored_text(self.color_num,str(feeds_count)) + ", News: " + self.__get_colored_text(self.color_num,str(news_count))

            # Print last config.feedlimit news.
            elif msg == "!last":
                answer = ""
                items = self.__db.get_latest_news(self.__config.feedlimit)
                if not self.__config.feedorderdesc:
                    items = items[::-1]

                for entry in items:
                    answer += "#" + self.__get_colored_text(self.color_num,str(entry[0])) + ": " + entry[1] + ", " + self.__get_colored_text(self.color_url,str(entry[2])) + ", " + self.__get_colored_text(self.color_date,str(entry[3])) + "\n"

            # Print last config.feedlimit news for a specific feed
            elif msg.startswith("!lastfeed"):
                answer = ""
                try:
                    feedid = int(msg.replace("!lastfeed","").strip())
                except:
                    return self.__get_colored_text('1',"Wrong command: ") + \
                        msg + ", use: !lastfeed <feedid>"
                items = self.__db.get_news_from_feed(
                    feedid, self.__config.feedlimit
                )
                if not self.__config.feedorderdesc:
                    items = items[::-1]
                for entry in items:
                    answer += "#" + self.__get_colored_text(self.color_num,str(entry[0])) + ": " + entry[1] + ", " + self.__get_colored_text(self.color_url,str(entry[2])) + ", " + self.__get_colored_text(self.color_date,str(entry[3])) + "\n"

            # Else tell the user how to use the bot
            else:
                answer = "Use !help for possible commands."
        except Exception as e:
            tb = traceback.format_exc()
            print(e, tb)
            answer = "__handle_msg error: {} \n{}".format(e, tb)

        return answer

    def on_privmsg(self, connection, event):
        """
        Handles the bot's private messages
        """
        if (len(event.arguments) < 1) or (not self.__config.LISTEN_TO_PRIVMSG):
            return

        # Get the message and return an answer
        msg = event.arguments[0].lower().strip()

        answer = self.__handle_msg(msg)
        self.send_msg(event.source.nick, answer)

    def on_pubmsg(self, connection, event):
        """ Called when a channel we're in gets a message. We use it to handle
        bot commands (!help) and also keep track of how long since last
        message so we don't interrupt convos.

          event:
            type: pubmsg
            source: nick!ident@host.tld
            target: #chan
            arguments: [u'this is a message']
            tags: []
        """
        # update channel's last activity time
        self.__db.set_new_chan_message(self.__config.CHANNEL)

        # if we don't use public help commands or not a user message, bail
        public_help_cmd = not self.__config.ENABLE_PUBLIC_HELP_CMD
        not_enough_arguments = len(event.arguments) < 1
        if not_enough_arguments or not public_help_cmd:
            return

        # Get the message. We are only interested in "!help"
        msg = event.arguments[0].lower().strip()

        # Send the answer as a private message
        if msg == "!help":
            self.send_msg(event.source.nick, self.__help_msg())

    def on_nicknameinuse(self, connection, event):
        """Changes the nickname if necessary"""
        print("Nick in use")
        if not self.__config.NICKSERV_PASSWORD:
            connection.nick(connection.get_nickname() + "_")
        else:
            print("Ghosting nick")
            #connection.nick(self.__config.NICK)
            msg = "GHOST {} {}".format(
                self.__config.NICK, self.__config.NICKSERV_PASSWORD
            )
            connection.privmsg( "NICKSERV", msg)

    def send_msg(self, target, msg, sleep_s=2):
        """Sends the message 'msg' to 'target'"""
        try:
            msg = msg.replace('\n', ' ')
            # only take first 510 lines, IRC has a limit of 510 chars
            # per message including channel name, etc
            sub_line = re.findall('.{1,510}', msg)[0]
            self.connection.privmsg(target, sub_line)
            # Don't flood the target
            time.sleep(sleep_s)
        except Exception as e:
            tb = traceback.format_exc()
            print("send_msg error", e, "\n", tb)

    def rewrite_data(self, feedname, data, dtype='*'):
        """
        Rewrite feed data (title, url) based on specific feeds
        requirements/needs. return cleaned, stripped, rewritten input
        """
        for rw in self.__config.rewrites:
            rw_feedname = rw[0]
            searchterm  = rw[1]
            replacement = rw[2]
            rw_dtype    = rw[3]

            if rw_feedname != feedname:
                continue
            elif rw_dtype == '*' or rw_dtype == '*':
                # if either dtype is *, skip following checks
                pass
            elif rw_dtype != dtype:
                continue

            data = re.sub(searchterm, replacement, data)
        data = re.sub(r'\s+', ' ', data).strip()
        return data

    def test_ignore_item( self, feedname, title):
        """
        Ignore a feed based on a match or some other criteria
        """
        # feedname, string, False=ignore if not found|True=ignore if found
        ignores = (
            ('arXiv:stat.ML', '[stat.ML]', False),
        )
        for ig in ignores:
            print("ig", ig)
            if feedname != ig[0]:
                continue
            find_string = ig[1]
            # TODO: implement ignore if found
            if (not ig[2]) and (title.count(find_string) == 0):
                return True
        return False

    def post_news(self, feed_name, title, url, date):
        """
        Posts a new announcement to the channel. This gets
        called as a callback by the FeedUpdater.
        """
        #if self.test_ignore_item(str(feed_name), title):
        #    return
        title = self.rewrite_data( str(feed_name), title, dtype='title')
        url = self.rewrite_data( str(feed_name), url, dtype='url')
        print("---- VARS ----")
        print("name")
        print(str(feed_name))
        print("title")
        print(title)
        print("url")
        print(url)
        try:
            print("---- ARGS ----")
            args = {
                "name":  str(feed_name),
                "title": title,
                "url":   url
            }
            print(args)
            print("---- MSG ----")
            msg = "<{name}> {title} | {url}".format(**args)
            print("Sending msg", msg)
            self.send_msg(self.__config.CHANNEL, msg, sleep_s=2)
        except Exception as e:
            tb = traceback.format_exc()
            print("post news error", e, "\n", tb)

    def __get_colored_text(self, color, text):
        if not self.__config.use_colors:
            return text

        return Colours(color, text).get()

    def __help_msg(self):
        """
        Returns the help/usage message
        """
        return """
Help:
    Send all commands as a private message to {}
    - !help         Prints this help
    - !list         Prints all feeds
    - !stats        Prints some statistics
    - !last         Prints the last 10 entries
    - !lastfeed <feedid> Prints the last 10 entries from a specific feed
""".format(self.connection.get_nickname())

class Bot(object):
    def __init__(self):
        self.__config = Config()
        self.__missing_options = self.__check_config()
        if len(self.__missing_options) > 0:
            return None
        self.__db = FeedDB(self.__config)
        self.__irc = IRCBot(self.__config, self.__db, self.on_started)
        self.__feedupdater = FeedUpdater(self.__config, self.__db)
        self.__connected = False

    def __check_config(self):
        necessary_options = [
            "HOST", "PORT", "PASSWORD", "SSL", "CHANNEL", "NICK", "admin_nicks",
            "use_colors", "num_col", "date", "feedname",
            "dateformat", "feedlimit", "update_before_connecting", "url",
            "feedorderdesc"
        ]
        missing_options = []
        for key in necessary_options:
            if not hasattr(self.__config, key):
                missing_options.append(key)
        return missing_options

    def get_missing_options(self):
        return self.__missing_options

    def start(self):
        """Starts the IRC bot"""
        threading.Thread(target=self.__irc.start).start()

    def initial_feed_update(self):
        def print_feed_update(feed_title, news_title, news_url, news_date):
            print(("[+]: {}||{}||{}||{}".format(
                feed_title, news_title, news_url, news_date
            )))

        if self.__config.update_before_connecting:
            print("Started pre-connection updates!")
            self.__feedupdater.update_feeds(print_feed_update, False)
            print("DONE!")

    def on_started(self):
        """
        Gets executed after the IRC thread has successfully established a
        connection.
        """
        if not self.__connected:
            print("Connected!")
            self.__feedupdater.update_feeds(self.__irc.post_news, True)
            print("Started feed updates!")
            if self.__config.WAIT_FOR_FIRST_MSG:
                print("Clearing last messages table")
                self.__db.reset_messages_count()
            self.__connected = True
