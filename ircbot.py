"""
twitterbot

  A twitter IRC bot. Twitterbot connected to an IRC server and idles in
  a channel, polling a twitter account and broadcasting all updates to
  friends.

USAGE

  twitterbot [config_file]

CONFIG_FILE

  The config file is an ini-style file that must contain the following:

[irc]
server: <irc_server>
port: <irc_port>
nick: <irc_nickname>
channel: <irc_channels_to_join>
prefixes: <prefix_type>

  If no config file is given "twitterbot.ini" will be used by default.

  The channel argument can accept multiple channels separated by commas.

  The default prefix type is 'cats'. You can also use 'none'.

LXj was here. He says 'Hi'.

Put your Twitter API keys in settings_local dawg

"""

from __future__ import print_function

from settings_local import TWITTER

BOT_VERSION = "TwitterBot 1.9.1 (http://mike.verdone.ca/twitter) // modified by LXj"

IRC_BOLD = chr(0x02)
IRC_ITALIC = chr(0x16)
IRC_UNDERLINE = chr(0x1f)
IRC_REGULAR = chr(0x0f)

import sys
import time
from datetime import datetime, timedelta
from email.utils import parsedate
try:
    from configparser import ConfigParser
except ImportError:
    from ConfigParser import ConfigParser
from heapq import heappop, heappush
import traceback
import os
import os.path

from twitter import Twitter, TwitterError, OAuth
from twitter.util import htmlentitydecode

PREFIXES = dict(
    cats=dict(
        new_tweet="=^_^= ",
        error="=O_o= ",
        inform="=o_o= "
        ),
    none=dict(
        new_tweet=""
        ),
    )
ACTIVE_PREFIXES=dict()

def get_prefix(prefix_typ=None):
    return ACTIVE_PREFIXES.get(prefix_typ, ACTIVE_PREFIXES.get('new_tweet', ''))


try:
    import irclib
except ImportError:
    raise ImportError(
        "This module requires python irclib available from "
        + "https://github.com/sixohsix/python-irclib/zipball/python-irclib3-0.4.8")

def debug(msg):
    # uncomment this for debug text stuff
    # print(msg, file=sys.stdout)
    pass

class SchedTask(object):
    def __init__(self, task, delta):
        self.task = task
        self.delta = delta
        self.next = time.time()

    def __repr__(self):
        return "<SchedTask %s next:%i delta:%i>" %(
            self.task.__name__, self.__next__, self.delta)

    def __lt__(self, other):
        return self.next < other.next

    def __call__(self):
        return self.task()

class Scheduler(object):
    def __init__(self, tasks):
        self.task_heap = []
        for task in tasks:
            heappush(self.task_heap, task)

    def next_task(self):
        now = time.time()
        task = heappop(self.task_heap)
        wait = task.next - now
        task.next = now + task.delta
        heappush(self.task_heap, task)
        if (wait > 0):
            time.sleep(wait)
        task()
        #debug("tasks: " + str(self.task_heap))

    def run_forever(self):
        while True:
            self.next_task()


class TwitterBot(object):
    def __init__(self, configFilename):
        self.configFilename = configFilename
        self.config = load_config(self.configFilename)

        global ACTIVE_PREFIXES
        ACTIVE_PREFIXES = PREFIXES[self.config.get('irc', 'prefixes')]

        self.twitter = Twitter(
            auth=OAuth(**TWITTER),
            api_version='1.1',
            domain='api.twitter.com')

        self.irc = irclib.IRC()
        self.irc.add_global_handler('privmsg', self.handle_privmsg)
        self.irc.add_global_handler('ctcp', self.handle_ctcp)
        self.irc.add_global_handler('umode', self.handle_umode)
        self.ircServer = self.irc.server()

        self.sched = Scheduler(
            (SchedTask(self.process_events, 1),
             SchedTask(self.check_statuses, 60)))
        self.lastUpdate = (datetime.utcnow() - timedelta(minutes=10)).utctimetuple()

    def check_statuses(self):
        debug("In check_statuses")
        try:
            updates = reversed(self.twitter.statuses.home_timeline())
        except Exception as e:
            print("Exception while querying twitter:", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            return

        nextLastUpdate = self.lastUpdate
        for update in updates:
            crt = parsedate(update['created_at'])
            if (crt > nextLastUpdate):
                if 'retweeted_status' in update:
                    text = 'RT @{}: {}'.format(
                        update['retweeted_status']['user']['screen_name'],
                        htmlentitydecode(
                            update['retweeted_status']['text'].replace('\n', ' '))
                        .encode('utf8', 'replace')
                    )
                else:
                    text = (htmlentitydecode(
                        update['text'].replace('\n', ' '))
                        .encode('utf8', 'replace'))

                msg = "%s %s%s:%s %s" % (
                    get_prefix(),
                    IRC_BOLD, update['user']['screen_name'],
                    IRC_BOLD, text.decode('utf8'))
                self.privmsg_channels(msg)

                nextLastUpdate = crt

        self.lastUpdate = nextLastUpdate

    def process_events(self):
        self.irc.process_once()

    def handle_privmsg(self, conn, evt):
        debug('got privmsg')
        args = evt.arguments()[0].split(' ')
        try:
            if (not args):
                return
            if (args[0] == 'follow' and args[1:]):
                self.follow(conn, evt, args[1])
            elif (args[0] == 'unfollow' and args[1:]):
                self.unfollow(conn, evt, args[1])
            else:
                conn.privmsg(
                    evt.source().split('!')[0],
                    "%sHi! I'm Twitterbot! you can (follow "
                    "<twitter_name>) to make me follow a user or "
                    "(unfollow <twitter_name>) to make me stop." %
                    get_prefix())
        except Exception:
            traceback.print_exc(file=sys.stderr)

    def handle_ctcp(self, conn, evt):
        args = evt.arguments()
        source = evt.source().split('!')[0]
        if (args):
            if args[0] == 'VERSION':
                conn.ctcp_reply(source, "VERSION " + BOT_VERSION)
            elif args[0] == 'PING':
                conn.ctcp_reply(source, "PING")
            elif args[0] == 'CLIENTINFO':
                conn.ctcp_reply(source, "CLIENTINFO PING VERSION CLIENTINFO")

    def handle_umode(self, conn, evt):
        """
        QuakeNet ignores all your commands until after the MOTD. This
        handler defers joining until after it sees a magic line. It
        also tries to join right after connect, but this will just
        make it join again which should be safe.
        """
        args = evt.arguments()
        if (args and args[0] == '+i'):
            channels = self.config.get('irc', 'channel').split(',')
            for channel in channels:
                self.ircServer.join(channel)

    def privmsg_channels(self, msg):
        return_response=True
        channels=self.config.get('irc','channel').split(',')
        return self.ircServer.privmsg_many(channels, msg.encode('utf8'))

    def follow(self, conn, evt, name):
        userNick = evt.source().split('!')[0]
        friends = [x['name'] for x in self.twitter.statuses.friends()]
        debug("Current friends: %s" %(friends))
        if (name in friends):
            conn.privmsg(
                userNick,
                "%sI'm already following %s." %(get_prefix('error'), name))
        else:
            try:
                self.twitter.friendships.create(id=name)
            except TwitterError:
                conn.privmsg(
                    userNick,
                    "%sI can't follow that user. Are you sure the name is correct?" %(
                        get_prefix('error')
                        ))
                return
            conn.privmsg(
                userNick,
                "%sOkay! I'm now following %s." %(get_prefix('followed'), name))
            self.privmsg_channels(
                "%s%s has asked me to start following %s" %(
                    get_prefix('inform'), userNick, name))

    def unfollow(self, conn, evt, name):
        userNick = evt.source().split('!')[0]
        friends = [x['name'] for x in self.twitter.statuses.friends()]
        debug("Current friends: %s" %(friends))
        if (name not in friends):
            conn.privmsg(
                userNick,
                "%sI'm not following %s." %(get_prefix('error'), name))
        else:
            self.twitter.friendships.destroy(id=name)
            conn.privmsg(
                userNick,
                "%sOkay! I've stopped following %s." %(
                    get_prefix('stop_follow'), name))
            self.privmsg_channels(
                "%s%s has asked me to stop following %s" %(
                    get_prefix('inform'), userNick, name))

    def _irc_connect(self):
        self.ircServer.connect(
            self.config.get('irc', 'server'),
            self.config.getint('irc', 'port'),
            self.config.get('irc', 'nick'))
        channels=self.config.get('irc', 'channel').split(',')
        for channel in channels:
            self.ircServer.join(channel)

    def run(self):
        self._irc_connect()

        while True:
            try:
                self.sched.run_forever()
            except KeyboardInterrupt:
                break
            except TwitterError:
                # twitter.com is probably down because it
                # sucks. ignore the fault and keep going
                pass
            except irclib.ServerNotConnectedError:
                # Try and reconnect to IRC.
                self._irc_connect()


def load_config(filename):
    # Note: Python ConfigParser module has the worst interface in the
    # world. Mega gross.
    cp = ConfigParser()
    cp.add_section('irc')
    cp.set('irc', 'port', '6667')
    cp.set('irc', 'nick', 'twitterbot')
    cp.set('irc', 'prefixes', 'cats')

    cp.read((filename,))

    # attempt to read these properties-- they are required
    cp.get('irc', 'server')
    cp.getint('irc', 'port')
    cp.get('irc', 'nick')
    cp.get('irc', 'channel')

    return cp

# So there was a joke here about the twitter business model
# but I got rid of it. Not because I want this codebase to
# be "professional" in any way, but because someone forked
# this and deleted the comment because they couldn't take
# a joke. Hi guy!
#
# Fact: The number one use of Google Code is to look for that
# comment in the Linux kernel that goes "FUCK me gently with
# a chainsaw." Pretty sure Linus himself wrote it.

def main():
    configFilename = "twitterbot.ini"
    if (sys.argv[1:]):
        configFilename = sys.argv[1]

    try:
        if not os.path.exists(configFilename):
            raise Exception()
        load_config(configFilename)
    except Exception as e:
        print("Error while loading ini file %s" %(
            configFilename), file=sys.stderr)
        print(e, file=sys.stderr)
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    bot = TwitterBot(configFilename)
    return bot.run()

if __name__ == "__main__":
    main()
