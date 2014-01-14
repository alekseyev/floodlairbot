floodlairbot
============

Twitter/IRC bot. Forked from https://github.com/sixohsix/twitter

- changed handling of authentication information
- fixed API URL
- fixed long retweets

Twitter API credentials
-----------------------

There should be a settings_local.py file in the current directory with contents like this:

    TWITTER = {
        "consumer_key": "HcBGhiIa6NjSNHuWkKxNwA",
        "consumer_secret": "CGIlIU7fVlTfXSLWv5mfn4BuZv0ToOH3pXiWbUcEs",
        "token": "353878060-1FfUmoLYuF7MBohKm4AoRAAsjZMXPtD22WLQVe6l",
        "token_secret": "a248mLreXpfofWMNdVipJV9cs7giQ5r8QPfW3eVc",
    }
