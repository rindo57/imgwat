# Advanced Telegram Watermarking Bot using Pyrogram
#
# This bot offers more features than a simple text watermark bot.
#
# Features:
# 1.  Text & Image Watermarks: Use either custom text or a logo image as a watermark.
# 2.  Full Customization:
#     - Watermark Position (9 options: corners, sides, center).
#     - Opacity/Transparency control.
#     - Padding from the edges.
# 3.  Interactive UI: Uses inline buttons for easy configuration.
# 4.  Per-Chat Settings: Each channel or group can have its own unique watermark settings.
# 5.  Persistent Storage: Uses SQLite to remember settings even if the bot restarts.
# 6.  Toggle On/Off: Easily enable or disable watermarking in any chat.
# 7.  Live Preview: Generate a sample to see how your watermark looks.
#
# To Run This Bot:
# 1. Install necessary libraries:
#    pip install pyrogram Pillow tgcrypto
#
# 2. Get API Credentials:
#    - Go to https://my.telegram.org and get your `API_ID` and `API_HASH`.
#
# 3. Create a Bot on Telegram:
#    - Talk to @BotFather on Telegram.
#    - Create a new bot to get a `BOT_TOKEN`.
#
# 4. Fill in the credentials below.
#
# 5. Run the script:
#    python your_script_name.py
#
# 6. Add the bot to your channel/group as an administrator with permissions
#    to 'Delete Messages' and 'Post Messages'.

import os
import sqlite3
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION ---
# Replace these with your actual credentials
API_ID ="10247139" # Replace with your API ID
API_HASH =  "96b46175824223a33737657ab943fd6a" # Replace with your API hash
BOT_TOKEN = "8088647795:AAGdhC7SViH2dQcJP8rFSUCZfcCTyb5MO-0"  # Replace with your bot token
# --- DATABASE SETUP ---
DB_FILE = "watermark_bot.db"

def init_db():
    """Initializes the SQLite database and creates the settings table if it doesn't exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            chat_id INTEGER PRIMARY KEY,
            is_enabled INTEGER DEFAULT 1,
            watermark_type TEXT DEFAULT 'text',
            watermark_text TEXT DEFAULT 'Your Channel',
            watermark_image_id TEXT,
            position TEXT DEFAULT 'bottom_right',
            opacity INTEGER DEFAULT 128,
            padding INTEGER DEFAULT 10,
            font_size INTEGER DEFAULT 30
        )
    ''')
    conn.commit()
    conn.close()

def get_settings(chat_id):
    """Retrieves settings for a specific chat, creating default ones if none exist."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM settings WHERE chat_id = ?", (chat_id,))
    settings = cursor.fetchone()
    if not settings:
        # Create default settings for a new chat
        cursor.execute("INSERT INTO settings (chat_id) VALUES (?)", (chat_id,))
        conn.commit()
        cursor.execute("SELECT * FROM settings WHERE chat_id = ?", (chat_id,))
        settings = cursor.fetchone()
    conn.close()
    
    # Convert tuple to a dictionary for easier access
    keys = ["chat_id", "is_enabled", "watermark_type", "watermark_text", "watermark_image_id", "position", "opacity", "padding", "font_size"]
    return dict(zip(keys, settings))

def update_setting(chat_id, key, value):
    """Updates a specific setting for a chat in the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE settings SET {key} = ? WHERE chat_id = ?", (value, chat_id))
    conn.commit()
    conn.close()

# Initialize the Pyrogram Client
app = Client("watermark_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# A dictionary to hold user states for conversational commands
user_states = {}

# --- CORE WATERMARKING LOGIC ---
async def apply_watermark(base_image_path: str, settings: dict, watermark_image_path: str = None):
    """
    Applies a text or image watermark to a base image based on the provided settings.
    Returns the path to the watermarked image.
    """
    try:
        base_image = Image.open(base_image_path).convert("RGBA")
        width, height = base_image.size
        
        # Create a transparent layer for the watermark
        watermark_layer = Image.new("RGBA", base_image.size, (255, 255, 255, 0))

        if settings['watermark_type'] == 'image' and watermark_image_path:
            watermark = Image.open(watermark_image_path).convert("RGBA")
            
            # Resize watermark to be 15% of the base image's width, preserving aspect ratio
            ratio = watermark.height / watermark.width
            new_width = int(width * 0.15)
            new_height = int(new_width * ratio)
            watermark = watermark.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Apply opacity
            if settings['opacity'] < 255:
                alpha = watermark.split()[3]
                alpha = alpha.point(lambda p: p * (settings['opacity'] / 255.0))
                watermark.putalpha(alpha)
            
            wm_w, wm_h = watermark.size
            
        else: # Default to text watermark
            draw = ImageDraw.Draw(watermark_layer)
            try:
                # Use a specific font file if available for better results
                font = ImageFont.truetype("arial.ttf", settings['font_size'])
            except IOError:
                # Fallback to a default font if 'arial.ttf' is not found
                font = ImageFont.load_default()

            text = settings['watermark_text']
            
            # Get text bounding box
            text_bbox = draw.textbbox((0, 0), text, font=font)
            wm_w = text_bbox[2] - text_bbox[0]
            wm_h = text_bbox[3] - text_bbox[1]

            # Draw text with specified opacity
            text_color = (255, 255, 255, settings['opacity'])
            draw.text((0, 0), text, font=font, fill=text_color)

        # Calculate position
        p = settings['padding']
        pos_map = {
            'top_left': (p, p),
            'top_center': ((width - wm_w) // 2, p),
            'top_right': (width - wm_w - p, p),
            'center_left': (p, (height - wm_h) // 2),
            'center': ((width - wm_w) // 2, (height - wm_h) // 2),
            'center_right': (width - wm_w - p, (height - wm_h) // 2),
            'bottom_left': (p, height - wm_h - p),
            'bottom_center': ((width - wm_w) // 2, height - wm_h - p),
            'bottom_right': (width - wm_w - p, height - wm_h - p),
        }
        position = pos_map.get(settings['position'], pos_map['bottom_right'])

        # Paste the watermark onto the base image
        if settings['watermark_type'] == 'image' and watermark_image_path:
            base_image.paste(watermark, position, watermark)
            final_image = base_image
        else:
            watermark_layer = watermark_layer.rotate(0, expand=1) # Can be used for rotation
            final_image = Image.alpha_composite(base_image, watermark_layer)

        # Save the final image
        output_path = f"watermarked_{os.path.basename(base_image_path)}"
        final_image.convert("RGB").save(output_path, "JPEG")
        return output_path

    except Exception as e:
        print(f"Error applying watermark: {e}")
        return None
    finally:
        # Close images if they are open
        if 'base_image' in locals() and base_image:
            base_image.close()
        if 'watermark' in locals() and watermark:
            watermark.close()


# --- PYROGRAM HANDLERS ---

@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    await message.reply_text(
        "**Welcome to the Advanced Watermark Bot!**\n\n"
        "I can automatically add a text or image watermark to photos you post in this chat.\n\n"
        "**To get started:**\n"
        "1. Make me an **admin** in your channel/group with 'Delete Messages' permission.\n"
        "2. Use the `/settings` command to configure your watermark.\n"
        "3. Use `/help` to see all available commands."
    )

@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    await message.reply_text(
        "**Here's how you can control me:**\n\n"
        "**/toggle**: Enable or disable watermarking in this chat.\n"
        "**/settings**: View your current watermark settings.\n"
        "**/set_text**: Set the text for your watermark.\n"
        "**/set_logo**: Set a logo/image as your watermark.\n"
        "**/set_position**: Choose where the watermark appears.\n"
        "**/set_opacity**: Set watermark transparency (0-100).\n"
        "**/set_padding**: Set distance from the edge in pixels.\n"
        "**/set_fontsize**: Set the font size for text watermarks.\n"
        "**/preview**: Get a sample watermarked image."
    )

@app.on_message(filters.command("settings"))
async def settings_command(client: Client, message: Message):
    settings = get_settings(message.chat.id)
    status = "✅ Enabled" if settings['is_enabled'] else "❌ Disabled"
    
    text = (
        f"**Current Watermark Settings for this Chat**\n\n"
        f"**Status**: {status}\n"
        f"**Type**: `{settings['watermark_type']}`\n"
        f"**Position**: `{settings['position']}`\n"
        f"**Opacity**: `{int((settings['opacity'] / 255) * 100)}%`\n"
        f"**Padding**: `{settings['padding']}px`\n\n"
    )
    if settings['watermark_type'] == 'text':
        text += (
            f"**Text**: `{settings['watermark_text']}`\n"
            f"**Font Size**: `{settings['font_size']}px`"
        )
    else:
        text += "**Logo**: " + ("Set" if settings['watermark_image_id'] else "Not Set")

    await message.reply_text(text)


@app.on_message(filters.command("toggle"))
async def toggle_command(client: Client, message: Message):
    settings = get_settings(message.chat.id)
    new_status = 1 - settings['is_enabled']
    update_setting(message.chat.id, 'is_enabled', new_status)
    status_text = "✅ Enabled" if new_status else "❌ Disabled"
    await message.reply_text(f"Watermarking has been **{status_text}** for this chat.")


# --- Conversational Handlers for Setting Values ---

@app.on_message(filters.command("set_text"))
async def set_text_prompt(client: Client, message: Message):
    await message.reply_text("Please send me the text you want to use as a watermark.")
    user_states[message.from_user.id] = ("awaiting_text", message.chat.id)

@app.on_message(filters.command("set_logo"))
async def set_logo_prompt(client: Client, message: Message):
    await message.reply_text("Please send me the photo you want to use as a watermark logo.")
    user_states[message.from_user.id] = ("awaiting_logo", message.chat.id)

@app.on_message(filters.command("set_opacity"))
async def set_opacity_prompt(client: Client, message: Message):
    await message.reply_text("Please send a number from 0 (transparent) to 100 (opaque) for the watermark opacity.")
    user_states[message.from_user.id] = ("awaiting_opacity", message.chat.id)

@app.on_message(filters.command("set_padding"))
async def set_padding_prompt(client: Client, message: Message):
    await message.reply_text("Please send a number for the padding (distance from the edge in pixels).")
    user_states[message.from_user.id] = ("awaiting_padding", message.chat.id)

@app.on_message(filters.command("set_fontsize"))
async def set_fontsize_prompt(client: Client, message: Message):
    await message.reply_text("Please send a number for the font size of the text watermark.")
    user_states[message.from_user.id] = ("awaiting_fontsize", message.chat.id)


@app.on_message(filters.private | filters.group)
async def handle_user_input(client: Client, message: Message):
    """Handles responses for the conversational commands."""
    if message.from_user.id not in user_states:
        return # Not a reply to a bot command, do nothing

    state, chat_id = user_states[message.from_user.id]

    if state == "awaiting_text":
        if message.text:
            update_setting(chat_id, 'watermark_text', message.text)
            update_setting(chat_id, 'watermark_type', 'text')
            await message.reply_text(f"✅ Watermark text set to: `{message.text}`. Type is now 'text'.")
        else:
            await message.reply_text("⚠️ Please send plain text.")
    
    elif state == "awaiting_logo":
        if message.photo:
            update_setting(chat_id, 'watermark_image_id', message.photo.file_id)
            update_setting(chat_id, 'watermark_type', 'image')
            await message.reply_text("✅ Logo watermark has been set! Type is now 'image'.")
        else:
            await message.reply_text("⚠️ Please send a photo, not a file or sticker.")

    elif state == "awaiting_opacity":
        try:
            opacity = int(message.text)
            if 0 <= opacity <= 100:
                # Convert 0-100 scale to 0-255 scale for PIL
                pil_opacity = int(opacity * 2.55)
                update_setting(chat_id, 'opacity', pil_opacity)
                await message.reply_text(f"✅ Opacity set to {opacity}%.")
            else:
                raise ValueError()
        except (ValueError, TypeError):
            await message.reply_text("⚠️ Invalid input. Please enter a number between 0 and 100.")

    elif state == "awaiting_padding":
        try:
            padding = int(message.text)
            if 0 <= padding <= 200:
                update_setting(chat_id, 'padding', padding)
                await message.reply_text(f"✅ Padding set to {padding}px.")
            else:
                raise ValueError()
        except (ValueError, TypeError):
            await message.reply_text("⚠️ Invalid input. Please enter a number for pixels (e.g., 10).")

    elif state == "awaiting_fontsize":
        try:
            size = int(message.text)
            if 10 <= size <= 200:
                update_setting(chat_id, 'font_size', size)
                await message.reply_text(f"✅ Font size set to {size}px.")
            else:
                raise ValueError()
        except (ValueError, TypeError):
            await message.reply_text("⚠️ Invalid input. Please enter a number between 10 and 200.")
    
    # Clear the user's state after handling the input
    del user_states[message.from_user.id]


# --- Position Setting with Inline Keyboard ---

@app.on_message(filters.command("set_position"))
async def set_position_command(client: Client, message: Message):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("↖️ Top Left", callback_data="pos_top_left"),
            InlineKeyboardButton("⬆️ Top Center", callback_data="pos_top_center"),
            InlineKeyboardButton("↗️ Top Right", callback_data="pos_top_right"),
        ],
        [
            InlineKeyboardButton("⬅️ Center Left", callback_data="pos_center_left"),
            InlineKeyboardButton("⏺️ Center", callback_data="pos_center"),
            InlineKeyboardButton("➡️ Center Right", callback_data="pos_center_right"),
        ],
        [
            InlineKeyboardButton("↙️ Bottom Left", callback_data="pos_bottom_left"),
            InlineKeyboardButton("⬇️ Bottom Center", callback_data="pos_bottom_center"),
            InlineKeyboardButton("↘️ Bottom Right", callback_data="pos_bottom_right"),
        ]
    ])
    await message.reply_text("Choose the watermark position:", reply_markup=keyboard)


@app.on_callback_query(filters.regex("^pos_"))
async def position_callback(client: Client, callback_query: CallbackQuery):
    position = callback_query.data.split("_", 1)[1]
    update_setting(callback_query.message.chat.id, 'position', position)
    await callback_query.edit_message_text(f"✅ Position set to **{position.replace('_', ' ')}**.")


# --- Preview Command ---

@app.on_message(filters.command("preview"))
async def preview_command(client: Client, message: Message):
    settings = get_settings(message.chat.id)
    
    # Create a dummy image for preview
    preview_img = Image.new('RGB', (800, 600), color = '#333')
    d = ImageDraw.Draw(preview_img)
    d.text((250, 280), "This is a preview image", fill=(255,255,255))
    preview_path = "preview_base.jpg"
    preview_img.save(preview_path)

    watermark_image_path = None
    if settings['watermark_type'] == 'image' and settings['watermark_image_id']:
        try:
            watermark_image_path = await client.download_media(settings['watermark_image_id'], file_name="watermark_logo_")
        except Exception as e:
            await message.reply_text(f"⚠️ Could not download your logo to create a preview. Error: {e}")
            return

    await message.reply_text("⏳ Generating preview...")
    
    final_image_path = await apply_watermark(preview_path, settings, watermark_image_path)

    if final_image_path:
        await message.reply_photo(
            photo=final_image_path,
            caption="Here's a preview of your watermark settings."
        )
    else:
        await message.reply_text("❌ Sorry, something went wrong while creating the preview.")

    # Cleanup
    if os.path.exists(preview_path):
        os.remove(preview_path)
    if watermark_image_path and os.path.exists(watermark_image_path):
        os.remove(watermark_image_path)
    if final_image_path and os.path.exists(final_image_path):
        os.remove(final_image_path)


# --- AUTOMATIC WATERMARKING HANDLER ---

@app.on_message(filters.photo & (filters.group | filters.channel))
async def watermark_photo(client: Client, message: Message):
    # Don't process messages sent by the bot itself
    if message.from_user and message.from_user.id == (await client.get_me()).id:
        return

    settings = get_settings(message.chat.id)
    
    # Only proceed if watermarking is enabled
    if not settings['is_enabled']:
        return

    # Check if the bot has delete permissions
    chat_member = await client.get_chat_member(message.chat.id, (await client.get_me()).id)
    if not chat_member.privileges or not chat_member.privileges.can_delete_messages:
        # Send a warning once if permissions are missing
        # A more robust solution would be to store if this warning was sent recently
        await message.reply_text("⚠️ **Permission Missing!**\nTo work correctly, I need to be an admin with the 'Delete Messages' permission. This allows me to replace the original photo with the watermarked version.")
        return

    original_photo_path = None
    watermark_image_path = None
    final_image_path = None

    try:
        await message.reply_text("⏳ Applying watermark...", quote=True)
        original_photo_path = await message.download(file_name="original_photo_")

        if settings['watermark_type'] == 'image' and settings['watermark_image_id']:
            try:
                watermark_image_path = await client.download_media(settings['watermark_image_id'], file_name="watermark_logo_")
            except Exception as e:
                # Fallback to text if logo can't be downloaded
                print(f"Could not download logo {settings['watermark_image_id']}: {e}")
                settings['watermark_type'] = 'text'

        final_image_path = await apply_watermark(original_photo_path, settings, watermark_image_path)

        if final_image_path:
            # Send the watermarked photo, preserving the original caption
            await client.send_photo(
                chat_id=message.chat.id,
                photo=final_image_path,
                caption=message.caption.markdown if message.caption else ""
            )
            # Delete the original message
            await message.delete()
        else:
            await message.reply_text("❌ Failed to apply watermark.")

    except Exception as e:
        print(f"An error occurred in watermark_photo handler: {e}")
        await message.reply_text("An unexpected error occurred. Please check my logs.")
    finally:
        # Clean up all temporary files
        if original_photo_path and os.path.exists(original_photo_path):
            os.remove(original_photo_path)
        if watermark_image_path and os.path.exists(watermark_image_path):
            os.remove(watermark_image_path)
        if final_image_path and os.path.exists(final_image_path):
            os.remove(final_image_path)
        
        # Delete the "Applying watermark..." message
        async for msg in client.get_chat_history(message.chat.id, limit=5):
            if msg.reply_to_message_id == message.id and "Applying watermark" in msg.text:
                await msg.delete()
                break


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    print("Initializing database...")
    init_db()
    print("Bot is starting...")
    app.run()
    print("Bot has stopped.")

