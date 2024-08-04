# Raindrop.io Telegram Bot

This bot allows you to:
* Save raindrops: just send/forward link to the bot, and bot will save it to 'Unsorted'
* Easily share your raindrops: type `@raindropiobot <search query>` in any chat and pick which raindrop you would like to share. You can use [advanced search operators](https://help.raindrop.io/using-search#operators) there!
* Save Telegram posts to Raindrop. Just forward single or multiple messages to bot and bot will guess is it just announce with link or article itself and handle it accordingly. **We have a nice 'reading mode' for such posts!**

This bot requires some configuration. Basically you need to create development app in your Raindrop.io account and share test token with bot. Bot will provide you detailed instruction, don't worry. 

---


## FAQ

> **Why not use OAuth?**

Yes, this bot doesn't use OAuth because (1) it first originated as bot for personal use, so it was fine using test tokens, implementing OAuth is just too much hustle. Pull requests are welcome tho.

> **Hmmm, I'm not feeling safe using this bot... Won't you steal all my data?**

I won't. However, I won't provide any guarantees that your data will be more safe on my server than anywhere else. In case of [suspected] compromising you can always revoke token.

> **Still not feeling safe. You can deploy different malicious code than published here**

Sure. That's main point of making this bot open source. I made code as much universal as I could, so you can deploy on your own server without hustle, check 'Deployment' section below. 


## Deployment

1. Create new telegram bot, enable inline mode.
1. Create `.env` file and put your credentials (including bot token from previous step) there. You can find example in `.env.example`.
1. Install `docker` and `docker-compose` if not already.
1. Optionally, if you would like to handle files larger than 20MB, you need to install [Telegram Bot server](https://github.com/tdlib/telegram-bot-api). It's included in docker-compose.yml, but you'll need to create your own 'Telegram app' [here](https://my.telegram.org/apps) and obtain `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`.
1. Run
    ```bash
    docker-compose up -d --build
    ```
1. You're awesome.

## Development

Restarting docker every time you make changes is a pain. For development, I use `start_local.sh` script which loads `.env` file, overwrites some env variables and runs bot. If you have idea how to make this flow better I'd be very interested, drop me a few lines in the Issues.

1. Create new telegram bot, enable inline mode.
1. Create `.env` file and put your credentials (including bot token from previous step) there. You can find example in `.env.example`.
1. Create virtual env and activate it:
    ```bash
   virtualenv -p python3.9 .venv && source .venv/bin/activate
    ```
1. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
1. Run bot:
    ```bash
    ./start_local.sh
    ```

## Contributions

Are more than welcome. Feel free to propose feature in Issues or even better submit Pull Request 🥰


## Notice

Again, **this isn't official bot**. I have no relation to Raindrop.io owner and developer, don't spam them about any questions or issues with this bot, instead open Issue here.