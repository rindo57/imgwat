import os
import logging
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pyrogram import Client, filters
from pyrogram.types import Message

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
#API_ID = 123456  # Replace with your API ID
#API_HASH = "your_api_hash"  # Replace with your API Hash
#BOT_TOKEN = "your_bot_token"  # Replace with your bot token
API_ID ="10247139" # Replace with your API ID
API_HASH =  "96b46175824223a33737657ab943fd6a" # Replace with your API hash
BOT_TOKEN= "8088647795:AAGdhC7SViH2dQcJP8rFSUCZfcCTyb5MO-0"  # Replace with your bot token
# Default watermark settings (can be customized per channel)
DEFAULT_WATERMARK = {
    "text": "© MyChannel",
    "font": "arial.ttf",
    "size": 40,
    "color": (255, 255, 255, 128),  # RGBA (white with 50% opacity)
    "position": "bottom-right",
    "outline": (0, 0, 0, 128),  # Black outline for better visibility
    "stroke_width": 2
}

app = Client("auto_watermark_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def apply_watermark(image_path: str, output_path: str, settings: dict = None):
    """Apply watermark to an image"""
    if settings is None:
        settings = DEFAULT_WATERMARK

    try:
        # Open the original image
        original = Image.open(image_path).convert("RGBA")
        
        # Create a transparent layer for the watermark
        watermark = Image.new("RGBA", original.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(watermark)
        
        # Load font (fallback to default if specified font not found)
        try:
            font = ImageFont.truetype(settings["font"], settings["size"])
        except:
            font = ImageFont.load_default()
            logger.warning(f"Font {settings['font']} not found, using default font")
        
        # Calculate text size and position
        text = settings["text"]
        text_width, text_height = draw.textsize(text, font=font)
        width, height = original.size
        
        # Position mapping
        positions = {
            "top-left": (10, 10),
            "top-right": (width - text_width - 10, 10),
            "bottom-left": (10, height - text_height - 10),
            "bottom-right": (width - text_width - 10, height - text_height - 10),
            "center": ((width - text_width) // 2, (height - text_height) // 2)
        }
        
        x, y = positions.get(settings["position"], positions["bottom-right"])
        
        # Draw outline if specified
        if settings.get("outline") and settings.get("stroke_width", 0) > 0:
            for adj in range(1, settings["stroke_width"] + 1):
                for x_offset, y_offset in [(-adj, -adj), (-adj, adj), (adj, -adj), (adj, adj)]:
                    draw.text((x + x_offset, y + y_offset), text, font=font, fill=settings["outline"])
        
        # Draw main text
        draw.text((x, y), text, font=font, fill=settings["color"])
        
        # Combine original with watermark
        watermarked = Image.alpha_composite(original, watermark)
        
        # Save as JPEG (converting from RGBA)
        watermarked.convert("RGB").save(output_path, "JPEG", quality=95)
        return True
    
    except Exception as e:
        logger.error(f"Error applying watermark: {str(e)}")
        return False

@app.on_message(filters.channel & filters.photo)
async def auto_watermark(client: Client, message: Message):
    """Automatically watermark images posted in channels"""
    try:
        # Only process if bot is admin in the channel
        chat_id = message.chat.id
        bot_member = await client.get_chat_member(chat_id, "me")
       # if not bot_member.can_edit_messages:
           # return
        
        # Download the image
        temp_path = await message.download()
        if not temp_path:
            return
        
        # Apply watermark
        output_path = f"watermarked_{os.path.basename(temp_path)}.jpg"
        success = apply_watermark(temp_path, output_path)
        
        if success:
            # Edit the message with watermarked image
            await client.edit_message_media(
                chat_id=chat_id,
                message_id=message.id,
                media=output_path
            )
            logger.info(f"Successfully watermarked image in channel {chat_id}")
        
        # Clean up temporary files
        os.remove(temp_path)
        if os.path.exists(output_path):
            os.remove(output_path)
    
    except Exception as e:
        logger.error(f"Error in auto_watermark: {str(e)}")

@app.on_message(filters.command(["start", "help"]))
async def help_command(client: Client, message: Message):
    """Help command handler"""
    help_text = """
🤖 **Auto Watermark Bot** 🤖

This bot automatically adds watermarks to images posted in channels where it's an admin.

**Requirements:**
1. Add the bot as an admin to your channel
2. Ensure it has 'Edit Messages' permission

**Current Watermark Settings:**
- Text: {text}
- Position: {position}
- Size: {size}px
- Color: RGBA{color}

**Commands:**
- /settings - Configure watermark (in private chat)
- /preview - See a preview of current watermark
""".format(**DEFAULT_WATERMARK)
    
    await message.reply_text(help_text)

if __name__ == "__main__":
    logger.info("Starting Auto Watermark Bot...")
    app.run()
