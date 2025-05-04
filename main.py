from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from vinted_scraper import VintedScraper
from time import sleep
import random

import os
TOKEN = os.getenv("TOKEN")

BOT_USERNAME = '@PricePal_demo_bot'

# Dictionary to store stop events for each user
user_stop_events = {}

# Define the list of countries and their corresponding domains with flag emojis
countries = [
    ("🇦🇹 Austria", "at"),
    ("🇧🇪 Belgium", "be"),
    ("🇭🇷 Croatia", "hr"),
    ("🇨🇿 Czech Republic", "cz"),
    ("🇩🇰 Denmark", "dk"),
    ("🇫🇮 Finland", "fi"),
    ("🇫🇷 France", "fr"),
    ("🇩🇪 Germany", "de"),
    ("🇬🇷 Greece", "gr"),
    ("🇭🇺 Hungary", "hu"),
    ("🇮🇹 Italy", "it"),
    ("🇱🇹 Lithuania", "lt"),
    ("🇱🇺 Luxembourg", "lu"),
    ("🇳🇱 Netherlands", "nl"),
    ("🇵🇱 Poland", "pl"),
    ("🇵🇹 Portugal", "pt"),
    ("🇷🇴 Romania", "ro"),
    ("🇸🇰 Slovakia", "sk"),
    ("🇪🇸 Spain", "es"),
    ("🇸🇪 Sweden", "se"),
    ("🇬🇧 United Kingdom", "uk"),
    ("🇺🇸 United States", "us")
]

# Function to run the scraper in a separate thread
def run_scraper(chat_id, base_url, search_text, run_time):
    def write_all_item_id(items):
        items_id = [item.id for item in items]
        with open(f'{chat_id}_ids.txt', 'w') as f:
            for item_id in items_id:
                f.write(f"{item_id}\n")

    def check_for_new_items(items):
        with open(f'{chat_id}_ids.txt', 'r') as f:
            old_items = {line.strip() for line in f}
        return [i for i, item in enumerate(items) if str(item.id) not in old_items]

    n = 0
    while n < run_time * 3:
        # Check if the stop event for this user is set
        if chat_id in user_stop_events and user_stop_events[chat_id].is_set():
            print(f"Stopping search for chat_id {chat_id}")
            break
        
        for i in range(2):
            # Check if stop_event is set before processing further
            if chat_id in user_stop_events and user_stop_events[chat_id].is_set():
                print(f"Stopping search for chat_id {chat_id} during iteration")
                break

            scraper = VintedScraper(base_url)
            params = {"search_text": search_text, "order": "newest_first"}
            items = scraper.search(params)

            if i == 0:
                write_all_item_id(items)
                sleep(random.randint(130, 160))
            else:
                # Check again after fetching new items
                if chat_id in user_stop_events and user_stop_events[chat_id].is_set():
                    print(f"Stopping search for chat_id {chat_id} after fetching new items")
                    break

                new_items = check_for_new_items(items)
                if new_items:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    # Prevent sending new items if stop_event is set
                    if chat_id in user_stop_events and user_stop_events[chat_id].is_set():
                        print(f"Stopping search for chat_id {chat_id} before sending items")
                        break

                    tasks = [send_new_items(chat_id, new_items, items)]
                    loop.run_until_complete(asyncio.gather(*tasks))
                    loop.close()
        else:
            # Continue only if the inner loop wasn't stopped
            n += 1
            continue

        # Break outer loop if the inner loop was stopped
        break


# Async function to send new items as messages
async def send_new_items(chat_id, new_items, items):
    app = Application.builder().token(TOKEN).build()
    async with app:
        for index in new_items:
            item = items[index]
            message = f"Title: {item.title}\nPrice: {item.price}\nURL: {item.url}"
            await app.bot.send_message(chat_id=chat_id, text=message, disable_web_page_preview=False)
            sleep(random.randint(5, 7))

# Commands
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! I'm PricePal, your Vinted search assistant. Use /search to find items or /help to see all commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 Available commands:\n"
        "🔹 /start - Start the bot\n"
        "🔹 /search - Search for items interactively\n"
        "🔹 /help - Get help\n"
        "🔹 /stop - Stop the ongoing search\n\n"
        "Feel free to reach out if you need assistance!"
    )

# Search command for interactive input
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id

    # Clear user-specific stop event and reinitialize
    if chat_id in user_stop_events:
        user_stop_events[chat_id].clear()
    else:
        user_stop_events[chat_id] = Event()

    # Clear previous user data
    context.user_data.clear()

    keyboard = [
        [InlineKeyboardButton(country, callback_data=domain) for country, domain in countries[i:i+2]]
        for i in range(0, len(countries), 2)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🌍 Please select the Vinted domain based on the country:",
        reply_markup=reply_markup
    )

# Callback query handler to handle the user's selection
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    domain = query.data
    context.user_data['domain'] = domain
    await query.message.reply_text("✏️ Great! Now, please enter your search term:")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if chat_id in user_stop_events:
        user_stop_events[chat_id].set()
        await update.message.reply_text("✅ Your search has been successfully stopped.")
    else:
        await update.message.reply_text("⚠️ You don't have any active searches to stop.")

# Text input handler for interactive inputs
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data
    chat_id = update.message.chat_id

    if 'search_term' not in user_data:
        user_data['search_term'] = update.message.text.strip()
        keyboard = [
            [InlineKeyboardButton("Seconds", callback_data="seconds"),
             InlineKeyboardButton("Minutes", callback_data="minutes"),
             InlineKeyboardButton("Hours", callback_data="hours")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⏱️ How would you like to specify the search duration? Choose a time unit:",
            reply_markup=reply_markup
        )
    elif 'time_unit' in user_data and 'time_value' not in user_data:
        try:
            user_data['time_value'] = int(update.message.text.strip())
            if user_data['time_value'] <= 0:
                raise ValueError("Time value must be positive.")
        except ValueError:
            await update.message.reply_text("⚠️ Please enter a valid positive number for the time value.")
            return
        
        # Start search after all inputs are collected
        base_url = f"https://www.vinted.{user_data['domain']}"
        search_text = user_data['search_term']
        time_multiplier = {"seconds": 1, "minutes": 60, "hours": 3600}
        run_time = user_data['time_value'] * time_multiplier[user_data['time_unit']]

        await update.message.reply_text(
            f"🔍 The search has started with the following details:\n"
            f"🌐 Domain: {base_url}\n"
            f"🔎 Search term: {search_text}\n"
            f"⏳ Duration: {user_data['time_value']} {user_data['time_unit']}.\n\n"
            "You can stop the search anytime using /stop.",
            disable_web_page_preview=True
        )

        # Start scraper in a separate thread
        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=100)
        loop.run_in_executor(executor, run_scraper, chat_id, base_url, search_text, run_time)

# Inline button handler
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data = context.user_data

    if query.data in ["seconds", "minutes", "hours"]:
        user_data['time_unit'] = query.data
        await query.edit_message_text("⏳ Please enter the time value (a positive number):")

# Error handler
async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f'Update {update} caused error {context.error}')
    if update and update.message:
        await update.message.reply_text("⚠️ An unexpected error occurred. Please try again later.")

if __name__ == '__main__':
    print("Starting bot...")

    app = Application.builder().token(TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('search', search_command))
    app.add_handler(CommandHandler('stop', stop_command))

    # Text and button handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(button_handler, pattern='^(seconds|minutes|hours)$'))
    app.add_handler(CallbackQueryHandler(button, pattern='^(' + '|'.join([domain for _, domain in countries]) + ')$'))

    # Error handler
    app.add_error_handler(error)

    # Polls the bot
    print("Polling...")
    app.run_polling(poll_interval=3)