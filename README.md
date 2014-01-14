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
        "consumer_key": "***",
        "consumer_secret": "***",
        "token": "***",
        "token_secret": "***",
    }
