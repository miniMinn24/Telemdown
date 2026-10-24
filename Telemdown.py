#!/usr/bin/env python3
import sys

if sys.version_info < (3, 11):
    sys.exit(
        f"Telemdown needs Python 3.11 or newer (you have {sys.version_info[0]}.{sys.version_info[1]}). "
        "Download it from https://www.python.org/downloads/"
    )

import asyncio
import codecs
import json
import os
import re
import shlex
import shutil
import subprocess
import time
import tomllib
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import (
    ApiIdInvalidError,
    ChannelPrivateError,
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    PhoneNumberUnoccupiedError,
    RPCError,
    SessionPasswordNeededError,
)
from telethon.tl.types import PeerChannel

PROJECT_NAME = "Telemdown"
VERSION = "v.1.0.0"
REPO_URL = "https://github.com/miniMinn24/Telemdown"

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.toml"
SESSION_PATH = BASE_DIR / "session"  # Telethon creates session.session

# Supported link shapes:
#   t.me/c/<channel>/<msg>            private channel
#   t.me/c/<channel>/<topic>/<msg>    private channel, forum topic
#   t.me/<username>/<msg>             public channel
LINK_RE = re.compile(
    r"(?:https?://)?(?:t|telegram)\.me/"
    r"(?P<private>c/)?(?P<chat>\w+)/(?P<first>\d+)(?:/(?P<second>\d+))?"
)

if os.name == "nt":
    os.system("")  # enables ANSI colors in the Windows console

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")  # never crash on characters the console can't show
    except (AttributeError, ValueError):
        pass

if sys.stdout.isatty():
    GREEN = "\033[32m"
    RED = "\033[31m"
    BLUE = "\033[34m"       # Standard Blue
    LIGHT_BLUE = "\033[94m" # Bright/Light Blue (often better for terminals)
    DIM = "\033[2m"
    RESET = "\033[0m"
else:
    GREEN = RED = BLUE = LIGHT_BLUE = DIM = RESET = ""


class UserError(Exception):
    """An error with a message that is already friendly."""


class Cancelled(Exception):
    pass


# ---------------------------------------------------------------- terminal input

def masked_input(prompt: str, mask: str = "*") -> str:
    """Like input(), but shows `mask` for every typed character.

    Supports paste and backspace. Falls back to plain input() when stdin
    is not a terminal (pipes, tests).
    """
    if not sys.stdin.isatty():
        return input(prompt)

    sys.stdout.write(prompt)
    sys.stdout.flush()

    old = None
    if os.name != "nt":
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        tty.setcbreak(fd)  # char-by-char, no echo, Ctrl+C still works

    chars: list[str] = []
    try:
        while True:
            if os.name == "nt":
                import msvcrt

                ch = msvcrt.getwch()
                if ch in ("\x00", "\xe0"):  # arrow/function key: skip its 2nd code
                    msvcrt.getwch()
                    continue
            else:
                ch = sys.stdin.read(1)

            if ch in ("\r", "\n"):
                break
            if ch == "\x03":
                raise KeyboardInterrupt
            if ch in ("\x04", ""):
                raise EOFError
            if ch in ("\x7f", "\b"):
                if chars:
                    chars.pop()
                    sys.stdout.write("\b \b")
            elif ch.isprintable():
                chars.append(ch)
                sys.stdout.write(mask)
            sys.stdout.flush()
    finally:
        if old is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\n")
        sys.stdout.flush()
    return "".join(chars)


def pick_folder(start: Path) -> str | None:
    """Open a native folder-picker window. None = cancelled or unavailable.

    Tries osascript (macOS), kdialog (KDE), zenity (GTK), then tkinter.
    """
    title = f"{PROJECT_NAME}: choose download folder"
    commands = []
    if sys.platform == "darwin":
        commands.append(["osascript", "-e", f'POSIX path of (choose folder with prompt "{title}")'])
    if shutil.which("kdialog"):
        commands.append(["kdialog", "--getexistingdirectory", str(start), "--title", title])
    if shutil.which("zenity"):
        commands.append(["zenity", "--file-selection", "--directory", f"--title={title}", f"--filename={start}/"])

    for cmd in commands:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except OSError:
            continue
        chosen = result.stdout.strip()
        if result.returncode == 0 and chosen:
            return chosen
        if result.returncode == 1:  # user pressed Cancel
            return None

    try:
        import tkinter
        from tkinter import filedialog

        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        chosen = filedialog.askdirectory(title=title, initialdir=str(start))
        root.destroy()
        return chosen or None
    except Exception:
        return None


# ---------------------------------------------------------------- config

def ask_download_dir() -> str:
    default_dir = "./Downloads"
    raw = input(
        f"{LIGHT_BLUE}[+]{RESET} Download folder (press {GREEN}Enter{RESET} to browse, or type a path): "
    ).strip().strip("'\"")
    if raw:
        return raw
    picked = pick_folder(Path.home())
    if picked:
        print(f"    {DIM}-> {picked}{RESET}")
        return picked
    print(f"{DIM}    No folder chosen, using {default_dir}{RESET}")
    return default_dir


def save_config(api_id: int, api_hash: str, download_dir: str) -> None:
    """Write config.toml as UTF-8 (folder names may be non-ASCII), private to you on Linux/macOS."""
    text = (
        f"api_id = {api_id}\n"
        f"api_hash = {json.dumps(api_hash, ensure_ascii=False)}\n"
        f"download_dir = {json.dumps(download_dir, ensure_ascii=False)}\n"
    )
    # Create it with 0600 from the start so it is never briefly readable by others.
    fd = os.open(CONFIG_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    CONFIG_PATH.chmod(0o600)


def setup_config() -> None:
    print(f"""
                              
                 {LIGHT_BLUE}++{RESET}  {LIGHT_BLUE}{PROJECT_NAME} {BLUE}{VERSION}{RESET}
             {LIGHT_BLUE}++++++{RESET}  telegram media downloader for private channels
        {LIGHT_BLUE}++++++ ++++{RESET}  maintained by miniMinn24
    {LIGHT_BLUE}+++++++  ++++++{RESET}  {GREEN}{REPO_URL}{RESET}
 {LIGHT_BLUE}+++++++   +++++++{RESET}  
         {LIGHT_BLUE}+++++++++{RESET}  
         {LIGHT_BLUE}+++++++++{RESET}  
            {LIGHT_BLUE}+++++{RESET}   
              {LIGHT_BLUE}+++{RESET}   
    """)

    print(f"\nFirst-time setup (API ID / hash from my.telegram.org -> API development tools)\nPlease read the instructions first: {REPO_URL}#readme\n")
    while True:
        raw = masked_input(f"{LIGHT_BLUE}[+]{RESET} Your API ID: ").strip()
        if raw.isdigit():
            api_id = int(raw)
            break
        print(f"{RED} [error] In case you don't know, API ID should be a number.{RESET}")
    api_hash = masked_input(f"{LIGHT_BLUE}[+]{RESET} Your API hash: ").strip()
    download_dir = ask_download_dir()

    save_config(api_id, api_hash, download_dir)
    print(f"{GREEN}[success]{RESET} Saved to {CONFIG_PATH} ;-)\n")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        setup_config()
    with open(CONFIG_PATH, "rb") as f:
        cfg = tomllib.load(f)
    folder = Path(cfg["download_dir"]).expanduser()
    # Relative paths (like ./Downloads) are relative to the project, not to
    # whatever folder you happened to launch the script from.
    cfg["download_dir"] = folder if folder.is_absolute() else BASE_DIR / folder
    cfg["download_dir"].mkdir(parents=True, exist_ok=True)
    return cfg


# ---------------------------------------------------------------- helpers

def human(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class Progress:
    def __init__(self) -> None:
        self.start = time.monotonic()
        self.last = 0.0

    def __call__(self, done: int, total: int) -> None:
        now = time.monotonic()
        if done < total and now - self.last < 0.15:
            return
        self.last = now
        speed = done / max(now - self.start, 0.001)
        pct = done / total if total else 0
        cols = shutil.get_terminal_size((80, 20)).columns
        stats = f"{pct * 100:5.1f}%  {human(done)}/{human(total)}  {human(speed)}/s"
        width = min(24, cols - len(stats) - 5)
        bar = ""
        if width >= 8:  # on very narrow screens, skip the bar instead of wrapping lines
            filled = int(pct * width)
            bar = "█" * filled + "░" * (width - filled) + " "
        line = f"  {bar}{stats}"
        sys.stdout.write("\r" + line[: cols - 1].ljust(cols - 1))
        sys.stdout.flush()


# ---------------------------------------------------------------- links / files

_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_name(name: str, max_len: int = 100) -> str:
    """Make a Telegram file name valid on every OS (Windows is the strict one)."""
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .") or "file"
    stem, ext = os.path.splitext(name)
    ext = ext[:16]
    stem = stem[: max(1, max_len - len(ext))].rstrip(" .") or "file"
    if stem.upper() in _WINDOWS_RESERVED:
        stem = "_" + stem
    return stem + ext


def msg_key(m: re.Match) -> tuple:
    """Identify a post so the same link twice is only downloaded once."""
    return (bool(m["private"]), m["chat"], int(m["second"] or m["first"]))


def unique(matches: list[re.Match]) -> list[re.Match]:
    seen, out = set(), []
    for m in matches:
        key = msg_key(m)
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


def as_file(raw: str) -> Path | None:
    """If the input is a path to an existing file, return it.

    Handles quotes / escaped spaces (drag & drop into Konsole) and ~.
    Relative paths are tried from the current folder, then the project folder.
    """
    if os.name == "nt":
        parts = [raw.strip("\"'")]  # shlex would eat the backslashes in C:\paths
    else:
        try:
            parts = shlex.split(raw)
        except ValueError:
            parts = [raw]
    if len(parts) != 1:
        return None
    p = Path(parts[0]).expanduser()
    for candidate in (p, BASE_DIR / p):
        if candidate.is_file():
            return candidate
    return None


def looks_like_path(raw: str) -> bool:
    return (
        raw.endswith(".txt")
        or raw[:1] in ("/", ".", "~")
        or bool(re.match(r"[A-Za-z]:[\\/]", raw))  # C:\... on Windows
    )


def read_links_file(path: Path) -> list[re.Match]:
    """Every Telegram link in the file; blank lines and # comments are ignored."""
    data = path.read_bytes()
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        text = data.decode("utf-16", errors="ignore")  # Windows PowerShell's `>` writes UTF-16
    else:
        text = data.decode("utf-8-sig", errors="ignore")  # also strips Notepad's BOM
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    return list(LINK_RE.finditer("\n".join(lines)))


# ---------------------------------------------------------------- login

def ask_country_code() -> str:
    while True:
        cc = input(
            f"{LIGHT_BLUE}[+]{RESET} Country calling code, digits only (e.g. 1, 44, 95): "
        ).strip().lstrip("+")
        if cc.isdigit() and 1 <= len(cc) <= 3:
            return cc
        print(f"{RED}[error]{RESET} That should be 1-3 digits, like 44.")


def normalize_phone(raw: str, ask_cc=ask_country_code) -> str:
    """Turn what people actually type into international format (+<country><number>).

        +959123456789   -> +959123456789
        00959123456789  -> +959123456789
        09123456789     -> asks for the country code, then +<cc>9123456789
        959123456789    -> +959123456789 (assumed to include the country code)
    """
    digits = re.sub(r"\D", "", raw)  # drops spaces, dashes, brackets, "+"
    if not digits:
        return ""
    if raw.lstrip().startswith("+"):
        return "+" + digits
    if digits.startswith("00"):
        return "+" + digits[2:]
    if digits.startswith("0"):
        return "+" + ask_cc() + digits[1:]
    return "+" + digits


def ask_phone() -> str:
    while True:
        raw = input(f"{LIGHT_BLUE}[+]{RESET} Your phone number (local like 09... or +international): ")
        phone = normalize_phone(raw)
        if not phone:
            print(f"{RED}[error]{RESET} Please enter a phone number.")
            continue
        answer = input(
            f"{LIGHT_BLUE}[+]{RESET} Send the login code to {GREEN}{phone}{RESET}? [Y/n]: "
        ).strip().lower()
        if answer in ("", "y", "yes"):
            return phone


async def two_factor(client: TelegramClient) -> None:
    while True:
        password = masked_input(f"{LIGHT_BLUE}[+]{RESET} 2FA password: ")
        try:
            await client.sign_in(password=password)
            return
        except PasswordHashInvalidError:
            print(f"{RED}[error]{RESET} Wrong password, try again.")


async def login(client: TelegramClient) -> None:
    """Interactive first-time login that survives typos instead of crashing."""
    while True:
        phone = ask_phone()
        try:
            sent = await client.send_code_request(phone)
        except PhoneNumberInvalidError:
            print(f"{RED}[error]{RESET} Telegram says that phone number is invalid. Try again.\n")
            continue

        print(f"{DIM}Code sent. Check your Telegram app (or SMS).{RESET}")
        for _ in range(3):
            code = input(f"{LIGHT_BLUE}[+]{RESET} Login code: ").strip().replace(" ", "")
            try:
                await client.sign_in(phone, code, phone_code_hash=sent.phone_code_hash)
                return
            except SessionPasswordNeededError:
                await two_factor(client)
                return
            except PhoneCodeInvalidError:
                print(f"{RED}[error]{RESET} Wrong code, try again.")
            except PhoneCodeExpiredError:
                print(f"{RED}[error]{RESET} That code expired.")
                break
            except PhoneNumberUnoccupiedError:
                print(f"{RED}[error]{RESET} No Telegram account exists for {phone}.")
                break
        print(f"{DIM}Let's start over.{RESET}\n")


# ---------------------------------------------------------------- telegram

async def connect(cfg: dict) -> TelegramClient:
    client = TelegramClient(str(SESSION_PATH), cfg["api_id"], cfg["api_hash"])
    await client.connect()
    if not await client.is_user_authorized():
        await login(client)  # first run only; the session is saved afterwards
    SESSION_PATH.with_suffix(".session").chmod(0o600)
    me = await client.get_me()
    handle = f" (@{me.username})" if me.username else ""
    print(f"Logged in as {GREEN}{me.first_name}{handle}{RESET}")
    return client


async def resolve_chat(client: TelegramClient, cache: dict, private: bool, chat: str):
    key = (private, chat)
    if key in cache:
        return cache[key]

    if private:
        if not chat.isdigit():
            raise UserError(f"{DIM}[tip]{RESET} Private links look like {LIGHT_BLUE}t.me/c/<number>/<message>{RESET}.")
        ref = PeerChannel(int(chat))
    else:
        ref = chat

    try:
        entity = await client.get_entity(ref)
    except ValueError:
        # Entity not in the local cache yet: load the account's chats, retry once.
        if private:
            await client.get_dialogs()
        try:
            entity = await client.get_entity(ref)
        except ValueError:
            raise UserError(
                f"{RED}[error]{RESET} Can't find that chat. Is this the same account that's a member of it?"
            ) from None

    cache[key] = entity
    return entity


async def download_post(client: TelegramClient, cfg: dict, cache: dict, m: re.Match) -> tuple[Path, bool]:
    """Download one post. Returns (path, skipped) where skipped = already on disk."""
    private = bool(m["private"])
    msg_id = int(m["second"] or m["first"])  # with a topic id, the message id comes last

    entity = await resolve_chat(client, cache, private, m["chat"])
    msg = await client.get_messages(entity, ids=msg_id)
    if not msg:
        raise UserError(f"{RED}[error]{RESET} Message not found (wrong ID, or it was deleted).")
    if not msg.file:
        raise UserError(f"{RED}[error]{RESET} That post has no downloadable media.")

    kind = "video" if msg.video else "file"
    if msg.file.name:
        safe = safe_name(msg.file.name)
        dest = cfg["download_dir"] / f"{msg.id}_{safe}"
    else:
        dest = cfg["download_dir"] / f"{m['chat']}_{msg.id}{msg.file.ext or ''}"

    size = msg.file.size or 0
    if dest.exists() and size and dest.stat().st_size == size:
        print(f"{DIM}  Already downloaded: {dest.name}{RESET}")
        return dest, True

    part = dest.with_name(dest.name + ".part")
    print(f"  {kind}: {dest.name} ({human(size)})")
    try:
        await client.download_media(msg, file=str(part), progress_callback=Progress())
        part.replace(dest)
    finally:
        print()
        part.unlink(missing_ok=True)  # clean up if cancelled or failed
    return dest, False


def run_cancellable(loop: asyncio.AbstractEventLoop, coro):
    """Run a coroutine; Ctrl+C cancels just this job instead of killing the app."""
    task = loop.create_task(coro)
    try:
        return loop.run_until_complete(task)
    except KeyboardInterrupt:
        task.cancel()
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass
        raise Cancelled from None


def process(loop, client, cfg: dict, cache: dict, matches: list[re.Match]) -> None:
    """Download one or many posts, then print a summary when there were several."""
    total = len(matches)
    saved = skipped = 0
    failed: list[str] = []
    remaining = 0

    for i, m in enumerate(matches, 1):
        link = m.group(0)
        if total > 1:
            print(f"{LIGHT_BLUE}[{i}/{total}]{RESET} {link}")
        try:
            path, was_skipped = run_cancellable(loop, download_post(client, cfg, cache, m))
            if was_skipped:
                skipped += 1
            else:
                saved += 1
                print(f"{GREEN}[success]{RESET} Saved: {path}\n")
        except Cancelled:
            print(f"{RED}[cancelled]{RESET} Stopped.\n")
            remaining = total - i
            break
        except UserError as e:
            failed.append(link)
            print(f"{e}\n")
        except ChannelPrivateError:
            failed.append(link)
            print(f"{RED}[error]{RESET} This account can't access that channel.\n")
        except FloodWaitError as e:
            failed.append(link)
            print(f"{RED}[error]{RESET} Telegram rate limit: try again in {e.seconds}s.\n")
            remaining = total - i
            break  # the remaining posts would hit the same limit
        except (RPCError, ConnectionError, OSError) as e:
            failed.append(link)
            print(f"{RED}[error]{RESET} {type(e).__name__}: {e}\n")
        except Exception as e:  # keep the loop alive no matter what
            failed.append(link)
            print(f"{RED}[error]{RESET} Unexpected ({type(e).__name__}): {e}\n")

    if total > 1:
        parts = [f"{GREEN}{saved} saved{RESET}"]
        if skipped:
            parts.append(f"{skipped} already downloaded")
        if failed:
            parts.append(f"{RED}{len(failed)} failed{RESET}")
        if remaining:
            parts.append(f"{remaining} not attempted")
        print(f"{LIGHT_BLUE}[done]{RESET} " + " · ".join(parts))
        for link in failed:
            print(f"  {RED}✖{RESET} {link}")
        print()


# ---------------------------------------------------------------- main loop

def main() -> None:
    cfg = load_config()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        client = loop.run_until_complete(connect(cfg))
    except ApiIdInvalidError:
        print(f"{RED}[error]{RESET} Telegram rejected your API ID / hash. "
              f"Delete {CONFIG_PATH.name} and run again to re-enter them.")
        sys.exit(1)
    except FloodWaitError as e:
        print(f"{RED}[error]{RESET} Telegram rate limit: try again in {e.seconds}s.")
        sys.exit(1)
    except (ConnectionError, TimeoutError):
        print(f"{RED}[error]{RESET} Can't reach Telegram. Check your internet connection "
              "(or VPN/proxy) and try again.")
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(0)

    cache: dict = {}

    print(f"Saving to: {cfg['download_dir']}")
    print("Paste a post link, or the path to a .txt file with one link per line.")
    print("Ctrl+C cancels a download, q quits.\n")

    try:
        while True:
            try:
                raw = input("link › ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if raw.lower() in {"q", "quit", "exit"}:
                break
            if not raw:
                continue

            matches = list(LINK_RE.finditer(raw))
            if not matches:
                file = as_file(raw)
                if file:
                    matches = read_links_file(file)
                    if not matches:
                        print(f"{RED}[error]{RESET} No Telegram links found in {file}\n")
                        continue
                    print(f"{DIM}Loaded {len(matches)} link(s) from {file}{RESET}")
                elif looks_like_path(raw):
                    print(f"{RED}[error]{RESET} File not found: {raw}\n")
                    continue
                else:
                    print(f"{RED}[error]{RESET} That's not a Telegram post link or a file path.\n")
                    continue

            before = len(matches)
            matches = unique(matches)
            if len(matches) < before:
                print(f"{DIM}Removed {before - len(matches)} duplicate link(s){RESET}")

            process(loop, client, cfg, cache, matches)
    finally:
        loop.run_until_complete(client.disconnect())
        loop.close()
        print("Bye!")


if __name__ == "__main__":
    main()