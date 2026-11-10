# AI Meal Logger

AI-powered meal logging via Telegram. Send a photo of your meal to the bot, and it identifies the food and logs it for you.

## Features

- Log meals by sending a photo in Telegram
- Automatic meal recognition using a vision model
- [Estimated calories / macros per meal]
- [Daily or weekly summary, e.g. `/summary`]
- [Where logs are stored: CSV, SQLite, Google Sheets, ...]

## How it works

1. You send a meal photo to the Telegram bot.
2. The image is sent to **Gemini 2.5 Flash Lite** for analysis.
3. The model returns the detected foods [and nutritional estimate].
4. The result is saved to [storage] and sent back to you in the chat.

> **Note on the model:** Gemma was the original choice for vision, but its vision endpoint wasn't reliably available through the API at the time of building, so the project uses Gemini 2.5 Flash Lite instead. The model is easy to swap in `[config file / variable]`.

## Tech stack

- Python [version]
- [python-telegram-bot / aiogram / ...]
- Google Gemini API (`gemini-2.5-flash-lite`)
- [Storage / other libraries]

## Setup

### Prerequisites

- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/)

### Installation

```bash
git clone https://github.com/LisaSpirina/[ai-meal-logger].git
cd [ai-meal-logger]
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the project root (never commit it):

```
TELEGRAM_BOT_TOKEN=your-telegram-token
GEMINI_API_KEY=your-gemini-key
```

### Run

```bash
python [main.py]
```

## Usage

| Command | Description |
|---|---|
| `/start` | Start the bot |
| [`/summary`] | [Show today's meals] |
| *send a photo* | Log a meal |

## Limitations

- Nutritional values are AI estimates, not exact measurements.
- Recognition quality depends on photo quality and the dish.

## Context

Built as a project for the Generative and Agentic AI course at HAW Hamburg.

## Authors

- [Lisa Spirina](https://github.com/LisaSpirina)
- [Aung Htet]([https://github.com/AungHtet-mm)

## License

MIT, see [LICENSE](LICENSE).
