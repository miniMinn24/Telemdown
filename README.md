<div align='center'>

![Telemdown wofi](./screenshots/telemdown_banner.webp)

A simple tool that downloads media from **private Telegram channels** you belong to. 

![Selfhosted](https://img.shields.io/badge/Private-cdd6f4?style=for-the-badge)![Selfhosted](https://img.shields.io/badge/No_Thirdparty-9cc3f7?style=for-the-badge)![Selfhosted](https://img.shields.io/badge/Self_Hosted-5a89c7?style=for-the-badge)

![](https://img.shields.io/github/last-commit/miniMinn24/Telemdown?&style=for-the-badge&color=429ddb&logoColor=D9E0EE&labelColor=141a29)

</div>



## About Telemdown
Telegram's apps make it awkward to save lots of videos from a private channel. Telemdown uses your own Telegram account (through the official API, via [Telethon](https://github.com/LonamiWebs/Telethon)) so you can just paste links and download.

No Thirdparty, no sharing your API keys to public bots, no manual efforts... **just your own self-hosted tool!**

**Main Features**

- Paste a post link or multiple at once, and download them
- Batch mode: download multiple medias from a txt file of post links
- Works with private channels (`t.me/c/...`), forum topics and public channels

**Useful Features**
- Progress bar with speed and size,
- Auto skips files you already downloaded and removes duplicated links
- Unfinished downloads are never left behind as broken files
- Friendly errors instead of crashes + a summary after batches
- Native GUI folder picker when choosing where to save
- API ID, API hash and 2FA password are securely masked while you type


> [!Note]
> **Use it reposibly**. I suggest you to download content you own or have permission to save, **legally.** 
> Though I can't stop you from doing any authorized/unauthorized attempts :(
> 
> Telemdown is not affiliated with or endorsed by Telegram.

## Installation

### 1. Requirements

- **Python 3.11 or newer**
- A Telegram account that is a member of the channel you want to download from

### 2. Get your Telegram API ID and hash

You might think:
**Why ask for my own API credentials of my Telegram account?**

Telegram requires every API client to use its own credentials. They are free and take about a minute:
> *Since this is a self-hosting tool, even the author of this tool won't see your credentials. No worries -3-* 

1. Go to <https://my.telegram.org> and log in with your phone number (use international format, e.g. `+44...`). Telegram sends the login code to your Telegram app.



2. Click **API development tools**.
3. Fill in the form: any **App title** and **Short name**, and anything for platform. The URL and description can stay empty.
4. Click **Create application**.
5. Keep the page open. You need the **App api_id** (a number) and **App api_hash** (a long string) in the first-run setup below.

> [!CAUTION] 
> **Keep your API hash private and never post it publicly.**
> If someone else got your Telegram account's API keys, they would be able to control everything.

### 3. Install Telemdown

Download or clone this repository, then open a terminal in its folder.

**Linux / macOS**

```bash
# Download the repo
git clone https://github.com/miniMinn24/Telemdown.git
cd telemdown

# Create a reliable working environment
python3 -m venv .venv
source .venv/bin/activate

# Install required dependencies
pip install -r requirements.txt

# Run the tool
python3 Telemdown.py
```

**Windows (PowerShell)**

```powershell
# Download the repo
git clone https://github.com/miniMinn24/Telemdown.git
cd telemdown

# Create a reliable working environment
py -m venv .venv
.venv\Scripts\activate

# Install required dependencies
pip install -r requirements.txt

# Run the tool
py Telemdown.py
```

**Android (Termux)**

Install [Termux from F-Droid](https://f-droid.org/packages/com.termux/) (the Play Store version is outdated), then:

```bash
pkg update && pkg install python git
termux-setup-storage # lets Termux save to your phone's storage

git clone https://github.com/miniMinn24/Telemdown.git
cd telemdown

pip install -r requirements.txt
python Telemdown.py
```

On Termux there is no folder picker, so type a path such as `~/storage/downloads/Telemdown` when asked for the download folder.

**Optional speed-up:** `pip install cryptg` makes downloads noticeably faster. It is optional, and it may need build tools on some systems.

### 4. First run (Fun Part)

The first time you run it, Telemdown asks for:

1. **API ID** and **API hash** (from step 2). They show as `*` while you type.
2. **Download folder**. Press **Enter** to pick one in a window, or type a path.
3. **Your phone number**. It asks for your country code when needed and confirms the number before sending.
4. **The login code** Telegram sends to your Telegram app, and your **2FA password** if you have one.

Your settings are saved to `config.toml` and your login to `session.session`, so you only do this once.

## Usage

### Download one post from a private Telegram channel

1. In Telegram, right-click (or long-press) the post and choose **Copy Post Link**.
2. Paste it at the prompt:

```bash
link › https://t.me/c/1234567890/42
  video: 42_clip.mp4 (182.4 MB)
  ████████████░░░░░░░░░░░░  51.3%  93.6 MB/182.4 MB  14.2 MB/s
[success] Saved: /home/you/Downloads/42_clip.mp4

link ›
```

You can paste several links on one line, **separated by spaces.**

### Download many posts at once

Create a text file (for example: `private_movie_links.txt`) with one link per line:

```
# my videos (lines starting with # are ignored)
https://t.me/c/1234567890/42
https://t.me/c/1234567890/43
https://t.me/c/1234567890/44
...
```

Then enter the file's path at the prompt:

```bash
link › links.txt
Loaded 3 link(s) from links.txt
[1/3] https://t.me/c/1234567890/42
...
[done] 3 saved
```

You can also drag the file into the terminal window. Failed links are listed at the end so you can retry them.

### Controls

| Action | How |
| --- | --- |
| Cancel the current download (or whole batch) | `Ctrl+C` |
| Quit | `q`, `quit`, `exit`, or `Ctrl+C` at the prompt |

### Supported links

| Link | Type |
| --- | --- |
| `https://t.me/c/1234567890/42` | Private channel |
| `https://t.me/c/1234567890/6/42` | Private channel, forum topic |
| `https://t.me/channelname/42` | Public channel |

Each link downloads the media of that one post. If a post is part of an album, copy the link of each item you want.

### Changing settings

Edit `config.toml` to change the download folder, or delete it and run Telemdown again to redo the setup. To log in as a different account, delete `session.session`.

## Troubleshooting

- **"Can't find that chat"**: you are logged in with an account that is not a member of the channel.
- **"Telegram rejected your API ID / hash"**: delete `config.toml` and enter them again.
- **No folder window on Linux**: install `kdialog`, `zenity`, or Python's Tk (`sudo pacman -S tk` on Arch, `sudo apt install python3-tk` on Debian/Ubuntu). You can always type a path in terminal instead.
- **"Telegram rate limit"**: wait the shown number of seconds, then try again.

## Security

`config.toml` and `session.session` give full access to your Telegram account as this is where your Telegram Account's API keys are stored.

Though they are encrypted, **treat them like passwords**, never share them, and never commit them to git.

For open-source distributers, the included `.gitignore` already excludes them, along with your downloads and `links.txt`.


## License

This project is licensed under MIT