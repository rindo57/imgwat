import os 
import sqlite3
from PIL import Image, ImageDraw, ImageFont
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

# Initialize Pyrogram client
api_id ="10247139" # Replace with your API ID
api_hash =  "96b46175824223a33737657ab943fd6a" # Replace with your API hash
bot_token = "8088647795:AAGdhC7SViH2dQcJP8rFSUCZfcCTyb5MO-0"  # Replace with your bot token
app = Client("WatermarkBot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

# Ensure watermarks directory exists
if not os.path.exists("watermarks"):
    os.makedirs("watermarks")

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect("watermark_bot.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS settings (
                 chat_id INTEGER PRIMARY KEY,
                 watermark_text TEXT,
                 watermark_image_path TEXT,
                 watermark_type TEXT DEFAULT 'text',  -- 'text' or 'image'
                 position TEXT DEFAULT 'bottom-right',
                 font_size INTEGER DEFAULT 30,
                 opacity REAL DEFAULT 0.7
                 )""")
    c.execute("""CREATE TABLE IF NOT EXISTS analytics (
                 chat_id INTEGER,
                 media_count INTEGER DEFAULT 0,
                 last_processed TIMESTAMP
                 )""")
    conn.commit()
    conn.close()

init_db()

# Function to apply text watermark
def apply_text_watermark(image_path, watermark_text, position, font_size, opacity):
    try:
        image = Image.open(image_path).convert("RGBA")
        width, height = image.size
        txt = Image.new("RGBA", image.size, (255, 255, 255, 0))
        font = ImageFont.truetype("arial.ttf", font_size)
        draw = ImageDraw.Draw(txt)
        
        # Calculate text position
        text_width, text_height = draw.textsize(watermark_text, font=font)
        if position == "bottom-right":
            x = width - text_width - 10
            y = height - text_height - 10
        elif position == "center":
            x = (width - text_width) // 2
            y = (height - text_height) // 2
        else:
            x, y = 10, 10  # Top-left default

        # Draw text with opacity
        draw.text((x, y), watermark_text, font=font, fill=(255, 255, 255, int(255 * opacity)))
        watermarked = Image.alpha_composite(image, txt)
        output_path = image_path.replace(".jpg", "_watermarked.jpg")
        watermarked.convert("RGB").save(output_path, "JPEG")
        return output_path
    except Exception as e:
        print(f"Error applying text watermark: {e}")
        return None

# Function to apply image watermark
def apply_image_watermark(image_path, watermark_image_path, position, opacity):
    try:
        image = Image.open(image_path).convert("RGBA")
        watermark = Image.open(watermark_image_path).convert("RGBA")
        width, height = image.size

        # Resize watermark to 20% of image width
        watermark_width = int(width * 0.2)
        aspect_ratio = watermark.width / watermark.height
        watermark_height = int(watermark_width / aspect_ratio)
        watermark = watermark.resize((watermark_width, watermark_height), Image.Resampling.LANCZOS)

        # Adjust watermark opacity
        watermark_data = watermark.getdata()
        new_data = [(r, g, b, int(a * opacity)) for r, g, b, a in watermark_data]
        watermark.putdata(new_data)

        # Calculate position
        if position == "bottom-right":
            x = width - watermark_width - 10
            y = height - watermark_height - 10
        elif position == "center":
            x = (width - watermark_width) // 2
            y = (height - watermark_height) // 2
        else:
            x, y = 10, 10  # Top-left default

        # Apply watermark
        image.paste(watermark, (x, y), watermark)
        output_path = image_path.replace(".jpg", "_watermarked.jpg")
        image.convert("RGB").save(output_path, "JPEG")
        return output_path
    except Exception as e:
        print(f"Error applying image watermark: {e}")
        return None

# Command: /start
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text(
        "Welcome to Advanced Watermark Bot! Add me as an admin to your channel with edit/delete permissions. Use /help for more info."
    )

# Command: /help
@app.on_message(filters.command("help") & filters.private)
async def help_command(client, message):
    await message.reply_text(
        "Use these commands:\n"
        "/setwatermark <text> - Set text watermark\n"
        "/setimagewatermark - Upload an image to set as watermark\n"
        "/setposition <top-left|center|bottom-right> - Set watermark position\n"
        "/setfontsize <size> - Set text watermark font size\n"
        "/setopacity <0.0-1.0> - Set watermark opacity\n"
        "/settype <text|image> - Choose watermark type\n"
        "/stats - View analytics\n"
        "Post images in your channel, and I'll watermark them automatically!"
    )

# Command: /setwatermark
@app.on_message(filters.command("setwatermark") & filters.private)
async def set_watermark(client, message):
    if len(message.command) < 2:
        await message.reply_text("Please provide watermark text, e.g., /setwatermark MyBrand")
        return
    watermark_text = " ".join(message.command[1:])
    conn = sqlite3.connect("watermark_bot.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (chat_id, watermark_text, watermark_type) VALUES (?, ?, 'text')",
              (message.chat.id, watermark_text))
    conn.commit()
    conn.close()
    await message.reply_text(f"Text watermark set to: {watermark_text}")

# Command: /setimagewatermark
@app.on_message(filters.command("setimagewatermark") & filters.private)
async def set_image_watermark(client, message):
    await message.reply_text("Please upload a PNG or JPEG image to use as your watermark.")
    # Store state to expect an image
    conn = sqlite3.connect("watermark_bot.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (chat_id, watermark_type) VALUES (?, 'pending_image')",
              (message.chat.id,))
    conn.commit()
    conn.close()

# Handle image upload for watermark
@app.on_message(filters.photo & filters.private)
async def handle_watermark_image(client, message):
    conn = sqlite3.connect("watermark_bot.db")
    c = conn.cursor()
    c.execute("SELECT watermark_type FROM settings WHERE chat_id = ?", (message.chat.id,))
    result = c.fetchone()
    if not result or result[0] != "pending_image":
        conn.close()
        return

    # Download and validate image
    file_path = await message.download()
    if not file_path.lower().endswith((".png", ".jpg", ".jpeg")):
        await message.reply_text("Please upload a PNG or JPEG image.")
        os.remove(file_path)
        conn.close()
        return

    # Save watermark image
    watermark_path = f"watermarks/{message.chat.id}.png"
    try:
        image = Image.open(file_path)
        image.save(watermark_path, "PNG")
        c.execute("UPDATE settings SET watermark_image_path = ?, watermark_type = 'image' WHERE chat_id = ?",
                  (watermark_path, message.chat.id))
        conn.commit()
        await message.reply_text("Image watermark set successfully!")
    except Exception as e:
        await message.reply_text(f"Error setting image watermark: {e}")
    finally:
        os.remove(file_path)
        conn.close()

# Command: /setposition
@app.on_message(filters.command("setposition") & filters.private)
async def set_position(client, message):
    positions = ["top-left", "center", "bottom-right"]
    if len(message.command) < 2 or message.command[1] not in positions:
        await message.reply_text(f"Please choose a position: {', '.join(positions)}")
        return
    position = message.command[1]
    conn = sqlite3.connect("watermark_bot.db")
    c = conn.cursor()
    c.execute("UPDATE settings SET position = ? WHERE chat_id = ?", (position, message.chat.id))
    conn.commit()
    conn.close()
    await message.reply_text(f"Watermark position set to: {position}")

# Command: /setfontsize
@app.on_message(filters.command("setfontsize") & filters.private)
async def set_fontsize(client, message):
    if len(message.command) < 2 or not message.command[1].isdigit():
        await message.reply_text("Please provide a valid font size, e.g., /setfontsize 30")
        return
    font_size = int(message.command[1])
    conn = sqlite3.connect("watermark_bot.db")
    c = conn.cursor()
    c.execute("UPDATE settings SET font_size = ? WHERE chat_id = ?", (font_size, message.chat.id))
    conn.commit()
    conn.close()
    await message.reply_text(f"Font size set to: {font_size}")

# Command: /setopacity
@app.on_message(filters.command("setopacity") & filters.private)
async def set_opacity(client, message):
    if len(message.command) < 2 or not 0.0 <= float(message.command[1]) <= 1.0:
        await message.reply_text("Please provide an opacity value between 0.0 and 1.0, e.g., /setopacity 0.7")
        return
    opacity = float(message.command[1])
    conn = sqlite3.connect("watermark_bot.db")
    c = conn.cursor()
    c.execute("UPDATE settings SET opacity = ? WHERE chat_id = ?", (opacity, message.chat.id))
    conn.commit()
    conn.close()
    await message.reply_text(f"Opacity set to: {opacity}")

# Command: /settype
@app.on_message(filters.command("settype") & filters.private)
async def set_type(client, message):
    types = ["text", "image"]
    if len(message.command) < 2 or message.command[1] not in types:
        await message.reply_text(f"Please choose a watermark type: {', '.join(types)}")
        return
    watermark_type = message.command[1]
    conn = sqlite3.connect("watermark_bot.db")
    c = conn.cursor()
    c.execute("UPDATE settings SET watermark_type = ? WHERE chat_id = ?", (watermark_type, message.chat.id))
    conn.commit()
    conn.close()
    await message.reply_text(f"Watermark type set to: {watermark_type}")

# Command: /stats
@app.on_message(filters.command("stats") & filters.private)
async def stats(client, message):
    conn = sqlite3.connect("watermark_bot.db")
    c = conn.cursor()
    c.execute("SELECT media_count, last_processed FROM analytics WHERE chat_id = ?", (message.chat.id,))
    result = c.fetchone()
    conn.close()
    if result:
        count, last = result
        await message.reply_text(f"Processed {count} media files. Last processed: {last}")
    else:
        await message.reply_text("No analytics available yet.")

# Handle media in channels
@app.on_message(filters.channel & filters.photo)
async def handle_channel_photo(client, message):
    conn = sqlite3.connect("watermark_bot.db")
    c = conn.cursor()
    c.execute("SELECT watermark_text, watermark_image_path, watermark_type, position, font_size, opacity FROM settings WHERE chat_id = ?", (message.chat.id,))
    settings = c.fetchone()
    if not settings or settings[2] not in ["text", "image"]:
        conn.close()
        return
    watermark_text, watermark_image_path, watermark_type, position, font_size, opacity = settings

    # Download the photo
    file_path = await message.download()
    if not file_path:
        conn.close()
        return

    # Apply appropriate watermark
    output_path = None
    if watermark_type == "text" and watermark_text:
        output_path = apply_text_watermark(file_path, watermark_text, position, font_size, opacity)
    elif watermark_type == "image" and watermark_image_path and os.path.exists(watermark_image_path):
        output_path = apply_image_watermark(file_path, watermark_image_path, position, opacity)

    if output_path:
        # Send watermarked image and delete original
        await message.reply_photo(output_path)
        await message.delete()
        
        # Update analytics
        c.execute("INSERT OR REPLACE INTO analytics (chat_id, media_count, last_processed) VALUES (?, COALESCE((SELECT media_count FROM analytics WHERE chat_id = ?) + 1, 1), ?)",
                  (message.chat.id, message.chat.id, datetime.now().isoformat()))
        conn.commit()
    
    os.remove(file_path)
    if output_path:
        os.remove(output_path)
    conn.close()

# Inline keyboard for settings preview
@app.on_message(filters.command("settings") & filters.private)
async def settings_menu(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Set Text Watermark", callback_data="set_watermark")],
        [InlineKeyboardButton("Set Image Watermark", callback_data="set_image_watermark")],
        [InlineKeyboardButton("Set Position", callback_data="set_position")],
        [InlineKeyboardButton("Set Font Size", callback_data="set_fontsize")],
        [InlineKeyboardButton("Set Opacity", callback_data="set_opacity")],
        [InlineKeyboardButton("Set Watermark Type", callback_data="set_type")]
    ])
    await message.reply_text("Adjust your watermark settings:", reply_markup=keyboard)

# Handle inline button clicks
@app.on_callback_query()
async def handle_callback(client, callback_query):
    data = callback_query.data
    if data == "set_watermark":
        await callback_query.message.reply_text("Send /setwatermark <text> to set text watermark.")
    elif data == "set_image_watermark":
        await callback_query.message.reply_text("Send /setimagewatermark and upload a PNG or JPEG image.")
    elif data == "set_position":
        await callback_query.message.reply_text("Send /setposition <top-left|center|bottom-right> to set position.")
    elif data == "set_fontsize":
        await callback_query.message.reply_text("Send /setfontsize <size> to set font size (for text watermarks).")
    elif data == "set_opacity":
        await callback_query.message.reply_text("Send /setopacity <0.0-1.0> to set opacity.")
    elif data == "set_type":
        await callback_query.message.reply_text("Send /settype <text|image> to choose watermark type.")
    await callback_query.answer()

if __name__ == "__main__":
    app.run()
