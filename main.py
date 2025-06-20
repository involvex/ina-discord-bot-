import os
import sys
import random
import logging
import asyncio
import subprocess
import platform # For OS detection
import re
import time # For uptime tracking
from interactions import slash_command, slash_option, OptionType, Permissions, Embed, Activity, ActivityType, User, SlashContext, File, Member, ChannelType, Message, Role, AutocompleteContext
from interactions.models.discord.channel import GuildText # For specific channel type checking
from interactions.api.events.discord import MessageCreate # Import the event type
import logging
interactions_logger = logging.getLogger("interactions")
from typing import Optional
import packaging.version  # For version comparison
import json
import requests
import sqlite3 # Added for DB interaction
import datetime # For timestamps in logs
# --- Version Configuration ---
# Version is now always sourced from config.py (__version__)
from config import __version__ as config_version
version = config_version # For pre-commit hooks or other tools scanning this file.

from bot_client import bot # Import the bot instance 
from config import (
    __version__ as config_version, # Import with an alias
    BOT_START_TIME, DEFAULT_LOG_LEVEL, DEBUG_MODE_ENABLED,
    DB_NAME, OWNER_ID, BUILDS_FILE,
    GITHUB_REPO_OWNER, GITHUB_REPO_NAME, GITHUB_VERSION_FILE_URL, UPDATE_CHECK_INTERVAL_SECONDS,
    NEW_WORLD_WELCOME_MESSAGES, NW_FUNNY_STATUSES, SILLY_UPTIME_MESSAGES, BOT_INVITE_URL, SILLY_MENTION_RESPONSES,
    setup_logging
)
# __version__ is now directly from config_version where needed.
from common_utils import format_uptime, scale_value_with_gs, _cleanup_cache_files_recursive # Renamed import
from settings_manager import (
    save_welcome_setting, get_welcome_setting,
    save_logging_setting, get_logging_setting,
    is_bot_manager, add_bot_manager, remove_bot_manager, load_bot_managers
)
from db_utils import find_item_in_db, find_perk_in_db, get_db_connection
from recipes import get_recipe, calculate_crafting_materials, track_recipe # track_recipe uses its own JSON
from utils.image_utils import generate_petpet_gif # Assuming this path is correct

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# --- Logging Configuration ---
setup_logging() # Initialize logging

@slash_command("ping", description="Check if the bot is online.")
async def ping(ctx):
    latency_ms = round(bot.latency * 1000)
    await ctx.send(f"Pong! Ina is online. Latency: {latency_ms}ms")


@slash_command("help", description="Show all available commands and their descriptions")
@slash_option("command", "Get detailed help for a specific command", opt_type=OptionType.STRING, required=False)
async def help_command(ctx, command: Optional[str] = None):
    # Using a more structured dictionary for command information
    # Adding a 'category' field for better organization in the full help embed
    commands_info = {
        "ping": {"desc": "Check if the bot is online.", "usage": "/ping", "category": "General"},
        "help": {"desc": "Show available commands or help for a specific command.", "usage": "/help [command_name]", "category": "General"},
        "petpet": {"desc": "Give a New World petting ritual to a user!", "usage": "/petpet <user>", "category": "General"},
        "calculate": {"desc": "Perform a calculation with New World magic!", "usage": "/calculate <expression>", "category": "General"},
        "uptime": {"desc": "Show how long Ina has been adventuring online.", "usage": "/uptime", "category": "General"},
        "about": {"desc": "Show information about Ina's New World Bot.", "usage": "/about", "category": "General"},
        "nwdb": {"desc": "Look up items from New World Database.", "usage": "/nwdb <item_name>", "category": "New World"},
        "perk": {"desc": "Look up information about a specific New World perk.", "usage": "/perk <perk_name>", "category": "New World"},
        "recipe": {"desc": "Show the full recipe breakdown for a craftable item.", "usage": "/recipe <item_name>", "category": "New World"},
        "calculate_craft": {"desc": "Calculate resources needed to craft an item, including intermediates.", "usage": "/calculate_craft <item_name> [amount]", "category": "New World"},
        "build add": {"desc": "Add a build from nw-buddy.de.", "usage": "/build add <link> <name> [keyperks]", "category": "Builds"},
        "build list": {"desc": "Show a list of saved builds.", "usage": "/build list", "category": "Builds"},
        "build remove": {"desc": "Remove a saved build.", "usage": "/build remove <name>", "perms": "Manage Server or Bot Manager", "category": "Builds"},
        "manage update": {"desc": "Pulls updates from GitHub and restarts the bot.", "usage": "/manage update", "perms": "Bot Owner", "category": "Management"},
        "manage restart": {"desc": "Shuts down the bot for manual restart.", "usage": "/manage restart", "perms": "Bot Owner/Manager", "category": "Management"},
        "settings permit": {"desc": "Grants a user bot management permissions.", "usage": "/settings permit <user>", "perms": "Server Admin or Bot Owner", "category": "Settings"},
        "settings unpermit": {"desc": "Revokes a user's bot management permissions.", "usage": "/settings unpermit <user>", "perms": "Server Admin or Bot Owner", "category": "Settings"},
        "settings listmanagers": {"desc": "Lists users with bot management permissions.", "usage": "/settings listmanagers", "perms": "Server Admin or Bot Manager/Owner", "category": "Settings"},
        "manage debug": {"desc": "Enable or disable debug logging in the console.", "usage": "/manage debug <enable|disable>", "perms": "Bot Owner/Manager", "category": "Management"},
        "manage cleanup": {"desc": "Cleans up cached files like __pycache__.", "usage": "/manage cleanup", "perms": "Bot Owner/Manager", "category": "Management"},
        "settings welcomemessages": {"desc": "Manage welcome messages. Actions: enable, disable, status.", "usage": "/settings welcomemessages <action> [channel]", "perms": "Server Admin or Bot Manager/Owner", "category": "Settings"},
        "settings logging": {"desc": "Manage server activity logging. Actions: enable, disable, status.", "usage": "/settings logging <action> [channel]", "perms": "Server Admin or Bot Manager/Owner", "category": "Settings"}
    }

    if command:
        command_name_lookup = command.lower().strip()
        info_to_display = commands_info.get(command_name_lookup)

        if info_to_display:
            usage = info_to_display['usage']
            description = info_to_display['desc']
            permissions = info_to_display.get('perms')

            embed = Embed(title=f"Help: `{usage}`", color=0x7289DA) # Discord Blurple
            embed.description = description
            if permissions:
                embed.add_field(name="Permissions Required", value=permissions, inline=False)
            await ctx.send(embeds=embed)
        else:
            # Try to find commands that start with the input, for base commands like /build
            matching_commands_details = []
            for cmd_key, cmd_info in commands_info.items():
                if cmd_key.startswith(command_name_lookup):
                    matching_commands_details.append(f"`{cmd_info['usage']}`: {cmd_info['desc']}")
            
            if matching_commands_details:
                embed = Embed(title=f"Commands starting with '{command_name_lookup}'", color=0x7289DA)
                embed.description = "\n".join(matching_commands_details)
                await ctx.send(embeds=embed)
            else:
                await ctx.send(f"Command '{command}' not found. Use `/help` to see all commands.")
    else:
        # Group commands by category
        categorized_commands = {}
        for cmd_key, info in commands_info.items():
            category = info.get("category", "Uncategorized")
            if category not in categorized_commands:
                categorized_commands[category] = []
            categorized_commands[category].append(f"`{info['usage']}`: {info['desc']}")

        embeds_to_send = []
        current_embed = Embed(title="Ina's New World Bot Commands", color=0x5865F2) # A nice blue
        current_embed.description = "Here's a list of available commands. For more details on a specific command, use `/help [command_name]`."
        char_count = len(current_embed.title) + len(current_embed.description or "")

        # Define a preferred order for categories
        category_order = ["General", "New World", "Builds", "Settings", "Management", "Uncategorized"]

        for category_name in category_order:
            if category_name in categorized_commands:
                if category_name == "Management" and ctx.author.id != OWNER_ID:
                    continue # Skip the Management category if user is not the owner
                commands_in_category = categorized_commands[category_name] # Now this is safe
                field_value = "\n".join(commands_in_category)
                field_name = f"**{category_name}**"

                # Discord embed field value limit is 1024, total embed char limit is ~6000
                # Max 25 fields per embed
                if char_count + len(field_name) + len(field_value) > 5500 or len(current_embed.fields) >= 24:
                    embeds_to_send.append(current_embed)
                    current_embed = Embed(title="Ina's New World Bot Commands (Continued)", color=0x5865F2)
                    char_count = len(current_embed.title)
                
                current_embed.add_field(name=field_name, value=field_value, inline=False)
                char_count += len(field_name) + len(field_value)
        
        if current_embed.fields: # Add the last embed if it has fields
            embeds_to_send.append(current_embed)

        if not embeds_to_send:
            await ctx.send("No commands to display.", ephemeral=True)
            return

        for i, embed_to_send in enumerate(embeds_to_send):
            if i == 0:
                await ctx.send(embeds=embed_to_send)
            else:
                await ctx.followup.send(embeds=embed_to_send) # Use followup for subsequent messages


@slash_command("petpet", description="Give a New World petting ritual to a user!")
@slash_option("user", "The user to pet (Aeternum style)", opt_type=OptionType.USER, required=True)
async def petpet(ctx, user):
    await ctx.defer() # Defer response as GIF generation can take a moment

    avatar_url = user.avatar_url
    if not avatar_url:
        # Fallback if avatar_url is None (e.g., for users with default avatars)
        # user.display_avatar should provide a URL even for default avatars.
        avatar_url = user.display_avatar.url

    if not avatar_url: # Still no URL, something is wrong
        await ctx.send("Could not retrieve avatar for the user.", ephemeral=True)
        return

    gif_buffer = await generate_petpet_gif(str(avatar_url)) # Ensure URL is a string

    if gif_buffer:
        await ctx.send(files=[File(file=gif_buffer, file_name="petpet.gif")])
    else:
        await ctx.send("Sorry, I couldn't create the petpet animation right now. Maybe the winds of Aeternum are too wild!", ephemeral=True)

@slash_command("calculate", description="Perform a calculation with New World magic!")
@slash_option("expression", "The mathematical expression to calculate", opt_type=OptionType.STRING, required=True)
async def calculate(ctx, expression: str):
    try:
        allowed_names = {k: v for k, v in math.__dict__.items() if not k.startswith("_")}
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        await ctx.send(f"🔮 The result of `{expression}` is `{result}`.")
    except Exception as e:
        await ctx.send(f"The arcane calculation failed: {e}", ephemeral=True)


@slash_command(name="uptime", description="Shows how long Ina has been online.")
async def uptime_command(ctx: SlashContext):
    current_time = time.time()
    uptime_seconds = current_time - BOT_START_TIME
    human_readable_uptime = format_uptime(uptime_seconds)
    await ctx.send(f"🧭 Ina has been adventuring in Aeternum for: **{human_readable_uptime}**")

@slash_command(name="nwdb", description="Look up items from New World Database.")
@slash_option("item_name", "The name of the item to look up", opt_type=OptionType.STRING, required=True, autocomplete=True)
async def nwdb(ctx, item_name: str):
    await ctx.defer() # Defer the response immediately

    item_results = await find_item_in_db(item_name, exact_match=True) # Autocomplete should give an exact name

    if not item_results:
        # Fallback to a LIKE search if exact match (from potential direct input) fails
        item_results = await find_item_in_db(item_name, exact_match=False)
        if not item_results:
            await ctx.send(f"Item '{item_name}' not found in the database.", ephemeral=True)
            return
    
    item = item_results[0] # Take the first match

    def get_any(item_dict, keys, default):
        for k_csv_original in keys:
            # Sanitize k_csv_original the same way create_db.py does for column names
            k_db = k_csv_original.replace(' ', '_').replace('(', '').replace(')', '').replace('%', 'percent')
            if k_db in item_dict and item_dict[k_db] is not None:
                return item_dict[k_db]
        return default

    name = get_any(item, ['Name', 'name'], item_name) # 'Name' is likely the sanitized column
    item_id_for_url = get_any(item, ['Item ID', 'ItemID'], None) # Becomes 'Item_ID'
    description = get_any(item, ['Description', 'description', 'Flavor Text'], 'No description available.') # 'Flavor_Text'
    rarity = get_any(item, ['Rarity', 'rarity'], 'Unknown')
    tier = get_any(item, ['Tier', 'tier'], 'Unknown')
    icon_url = get_any(item, ['Icon', 'icon', 'Icon Path'], None) # 'Icon_Path' from CSV
    item_type_name = get_any(item, ['Item Type Name'], 'Unknown Type') # From 'Item Type Name' CSV header

    # New fields to fetch based on CSV headers
    weight = get_any(item, ['Weight'], None)
    max_stack = get_any(item, ['Max Stack Size'], None) # From 'Max Stack Size' CSV header
    ingredient_categories_raw = get_any(item, ['Ingredient Categories'], None) # From 'Ingredient Categories' CSV header

    # Build a NWDB-style embed
    embed = Embed()
    embed.title = name
    if item_id_for_url:
        # Ensure item_id_for_url is stripped of any potential non-URL safe characters if necessary,
        # though typically Item IDs are safe.
        embed.url = f"https://nwdb.info/db/item/{str(item_id_for_url).strip()}"
    else:
        logging.warning(f"Could not find Item ID for '{name}' to create NWDB link.")

    embed.color = 0x9b59b6 if str(rarity).lower() == 'artifact' else 0x7289da # Ensure rarity is string for .lower()
    if icon_url:
        embed.set_thumbnail(url=str(icon_url).strip()) # Ensure URL is string and stripped
    
    embed.add_field(name="Rarity", value=str(rarity), inline=True)
    embed.add_field(name="Tier", value=str(tier), inline=True)
    embed.add_field(name="Type", value=str(item_type_name), inline=True)

    if weight is not None: # Check for None because 0 is a valid weight
        embed.add_field(name="Weight", value=str(weight), inline=True)
    if max_stack:
        embed.add_field(name="Max Stack", value=str(max_stack), inline=True)

    if description and not str(description).startswith('Artifact_'): # Ensure description is string
        embed.add_field(name="Description", value=str(description), inline=False)
    
    
    gear_score = get_any(item, ['Gear Score', 'gear_score', 'GS'], None) # Becomes 'Gear_Score'
    if gear_score:
        embed.add_field(name="Gear Score", value=str(gear_score), inline=True)
    
    # Perks (if present)
    perks_raw = get_any(item, ['Perks', 'perks'], None) # This column might contain perk IDs or names
    PERK_PRETTY = { # This map might need to be more dynamic or comprehensive
        'PerkID_Artifact_Set1_HeavyChest': ("Artifact Set: Heavy Chest", "🟣"),
        'PerkID_Gem_EmptyGemSlot': ("Empty Gem Slot", "💠"),
        # ... more perk mappings
    }
    if perks_raw:
        perk_lines = []
        for perk_entry in str(perks_raw).split(","): # Ensure perks_raw is string
            perk_entry = perk_entry.strip()
            if not perk_entry:
                continue
            # Here, perk_entry might be a PerkID. You might need to look up its display name from the 'perks' table
            # For simplicity, using PERK_PRETTY or just the ID if not found.
            pretty, icon = PERK_PRETTY.get(perk_entry, (perk_entry, '•'))
            perk_lines.append(f"{icon} {pretty}")
        if perk_lines:
            embed.add_field(name="Perks", value="\n".join(perk_lines), inline=False)

    if ingredient_categories_raw:
        # The 'Ingredient Categories' column in items.csv uses '|' as a separator
        categories = [cat.strip() for cat in str(ingredient_categories_raw).split('|') if cat.strip()]
        if categories:
            embed.add_field(name="Ingredient Types", value=", ".join(categories), inline=False)

    # Crafting Info section
    is_recipe_item_flag = name.lower().startswith("recipe:")
    actual_item_name_from_recipe_item = None
    if is_recipe_item_flag:
        actual_item_name_from_recipe_item = name.lower().replace("recipe:", "").strip().title()
        embed.title = f"Recipe: {actual_item_name_from_recipe_item}" # Update title for recipe items
        # The embed.url already points to the "Recipe: ..." item page, which is fine.

    # Check if the item (or the item the recipe is for) can be crafted
    conn_check = get_db_connection()
    can_be_crafted_flag = False
    # If it's a recipe item, check if the *target* item is craftable. Otherwise, check the item itself.
    target_craft_check_name = actual_item_name_from_recipe_item if is_recipe_item_flag else name
    try:
        cursor_check = conn_check.cursor()
        cursor_check.execute("SELECT 1 FROM recipes WHERE lower(output_item_name) = ?", (target_craft_check_name.lower(),))
        if cursor_check.fetchone():
            can_be_crafted_flag = True
    except sqlite3.Error as e:
        logging.warning(f"Could not check if item {target_craft_check_name} is craftable due to DB error: {e}")
    finally:
        if conn_check:
            conn_check.close()

    craft_status_lines = []
    if is_recipe_item_flag:
        craft_status_lines.append(f"📜 This is a recipe scroll for **{actual_item_name_from_recipe_item}**.")
        embed.set_footer(text=f"Type /recipe item_name:\"{actual_item_name_from_recipe_item}\" to see its crafting details!")
    elif can_be_crafted_flag:
        craft_status_lines.append("✅ Can be crafted.")
        embed.set_footer(text=f"Type /calculate_craft item_name:\"{name}\" to calculate resources!")

    if not is_recipe_item_flag and (ingredient_categories_raw or 'resource' in str(item_type_name).lower()):
        craft_status_lines.append("🛠️ Used as a crafting material.")

    if craft_status_lines:
        embed.add_field(name="Crafting Info", value="\n".join(craft_status_lines), inline=False)

    await ctx.send(embeds=embed)


@nwdb.autocomplete("item_name")
async def nwdb_autocomplete(ctx: AutocompleteContext): # Corrected type hint for Autocomplete
    search_term = ctx.input_text.lower().strip() if ctx.input_text else ""
    if not search_term: # If search term is empty, send no choices
        await ctx.send(choices=[])
        return

    conn = get_db_connection()
    choices = []
    try:
        cursor = conn.cursor()
        # Query the 'Name' column from the 'items' table. Adjust if your column name differs.
        # create_db.py sanitizes column names, so 'Name' should be correct if original was 'Name' or 'name'.
        cursor.execute("SELECT Name FROM items WHERE lower(Name) LIKE ? LIMIT 25", ('%' + search_term + '%',))
        matches = cursor.fetchall()
        # The value sent to the command should be the exact item name for easier lookup
        choices = [{"name": row["Name"], "value": row["Name"]} for row in matches]
    except sqlite3.Error as e:
        logging.error(f"SQLite error in nwdb_autocomplete: {e}")
    finally:
        if conn:
            conn.close()
    await ctx.send(choices=choices)

import json

@slash_command(name="calculate_craft", description="Calculate all resources needed to craft an item, including intermediates.")
@slash_option("item_name", "The name of the item to craft", opt_type=OptionType.STRING, required=True, autocomplete=True)
@slash_option("amount", "How many to craft", opt_type=OptionType.INTEGER, required=False)
@slash_option("fort_bonus", "Fort bonus (yes/no, optional)", opt_type=OptionType.BOOLEAN, required=False)
@slash_option("armor_bonus", "Armor bonus % (2-10, optional)", opt_type=OptionType.NUMBER, required=False)
@slash_option("tradeskill", "Tradeskill (1-250, optional)", opt_type=OptionType.INTEGER, required=False)
async def calculate_craft(ctx, item_name: str, amount: int = None, fort_bonus: bool = None, armor_bonus: float = None, tradeskill: int = None):
    # Load user defaults
    user_id = str(ctx.author.id)
    defaults_path = "user_craft_defaults.json"
    try:
        with open(defaults_path, "r", encoding="utf-8") as f:
            user_defaults = json.load(f)
    except Exception:
        user_defaults = {}
    user_last = user_defaults.get(user_id, {})
    # Use last values if not provided
    item_name = item_name or user_last.get("item_name", "")
    amount = amount if amount is not None else user_last.get("amount", 1)
    fort_bonus = fort_bonus if fort_bonus is not None else user_last.get("fort_bonus", False)
    armor_bonus = armor_bonus if armor_bonus is not None else user_last.get("armor_bonus", 0)
    tradeskill = tradeskill if tradeskill is not None else user_last.get("tradeskill", 1)

    await ctx.defer() # Defer response
    recipe_details = None
    try:
        recipe_details = get_recipe(item_name)
    except Exception as e:
        logging.error(f"Unexpected error in calculate_craft calling get_recipe for '{item_name}': {e}", exc_info=True)
        await ctx.send(f"An unexpected error occurred while fetching recipe details for '{item_name}'. Please contact an admin.", ephemeral=True)
        return
    if not recipe_details:
        await ctx.send(f"Recipe for '{item_name}' not found or item is not craftable.", ephemeral=True)
        return
    all_materials = None
    try:
        all_materials = calculate_crafting_materials(item_name, amount or 1, include_intermediate=True)
    except Exception as e:
        logging.error(f"Unexpected error in calculate_craft calling calculate_crafting_materials for '{item_name}': {e}", exc_info=True)
        await ctx.send(f"An unexpected error occurred while calculating materials for '{item_name}'. Please contact an admin.", ephemeral=True)
        return
    if not all_materials:
        await ctx.send(f"Could not calculate materials for '{item_name}'. Ensure it's a craftable item with a known recipe.", ephemeral=True)
        return
    # Save user defaults
    user_defaults[user_id] = {
        "item_name": item_name,
        "amount": amount,
        "fort_bonus": fort_bonus,
        "armor_bonus": armor_bonus,
        "tradeskill": tradeskill
    }
    try:
        with open(defaults_path, "w", encoding="utf-8") as f:
            json.dump(user_defaults, f, indent=2)
    except Exception:
        pass
    # Apply bonuses
    armor_bonus = max(0, min(armor_bonus or 0, 10))
    tradeskill = max(1, min(tradeskill or 1, 250))
    fort_bonus_pct = 10 if fort_bonus else 0
    tradeskill_bonus_pct = (tradeskill - 1) * (300 / 249) if tradeskill > 1 else 0
    total_bonus = fort_bonus_pct + armor_bonus + tradeskill_bonus_pct
    bonus_factor = 1 - (total_bonus / 100)
    embed = Embed()
    embed.title = f"Crafting: {item_name.title()}"
    embed.color = 0x4CAF50
    embed.add_field(name="Amount", value=str(amount or 1), inline=True)
    embed.add_field(name="Fort Bonus", value="Yes" if fort_bonus else "No", inline=True)
    if armor_bonus:
        embed.add_field(name="Armor Bonus", value=f"{armor_bonus:.1f}%", inline=True)
    if tradeskill:
        embed.add_field(name="Tradeskill", value=f"{tradeskill} ({tradeskill_bonus_pct:.1f}% bonus)", inline=True)
    crafted_item_icon = None
    try:
        item_results = await find_item_in_db(item_name, exact_match=True)
        if item_results and (item_results[0].get("Icon") or item_results[0].get("Icon Path")):
            crafted_item_icon = item_results[0].get("Icon") or item_results[0].get("Icon Path")
    except Exception:
        crafted_item_icon = None
    if crafted_item_icon:
        embed.set_thumbnail(url=crafted_item_icon)
    MATERIAL_EMOJIS = {
        "prismatic leather": "🟣",
        "iron ingot": "⛓️",
        "leather": "🟤",
        "wood": "🪵",
        "fiber": "🧵",
        "cloth": "🧶",
        "stone": "🪨",
        "gold ingot": "🥇",
        "silver ingot": "🥈",
    }
    # If no materials, show the crafted item as a base material
    if not all_materials:
        all_materials = {item_name: amount or 1}

    # Load items_updated.json once and cache
    import os
    import json as _json
    if not hasattr(calculate_craft, "_items_cache"):
        items_path = os.path.join(os.path.dirname(__file__), "items_updated.json")
        try:
            with open(items_path, "r", encoding="utf-8") as f:
                raw_items = _json.load(f)
                # Filter out any non-dict entries
                calculate_craft._items_cache = [item for item in raw_items if isinstance(item, dict)]
        except Exception:
            calculate_craft._items_cache = []
    items_data = calculate_craft._items_cache

    embed.add_field(name="**Materials**", value="\u200b", inline=False)
    for mat, qty in all_materials.items():
        adj_qty = max(1, int(round(qty * bonus_factor)))
        emoji = MATERIAL_EMOJIS.get(mat.lower(), "")
        # Try to get icon for this material from items_updated.json
        icon_url = None
        for item in items_data:
            if (item.get("name", "").lower() == mat.lower()) or (item.get("Name", "").lower() == mat.lower()):
                icon_url = item.get("icon") or item.get("icon_url") or item.get("Icon") or item.get("Icon Path")
                break
        # Make material name a hyperlink if icon is available
        if icon_url:
            field_name = f"{emoji} [{mat.title()}]({icon_url})"
        else:
            field_name = f"{emoji} {mat.title()}".strip()
        if fort_bonus or armor_bonus or tradeskill:
            embed.add_field(
                name=field_name,
                value=f"{qty} → **{adj_qty}**",
                inline=False
            )
        else:
            embed.add_field(
                name=field_name,
                value=f"{qty}",
                inline=False
            )
    embed.set_footer(text="Bonuses reduce the required materials. Minimum per material is 1.")
    await ctx.send(embeds=embed)


@calculate_craft.autocomplete("item_name")
async def calculate_craft_autocomplete(ctx: AutocompleteContext):
    search_term = ctx.input_text.lower().strip() if ctx.input_text else ""
    if not search_term:
        await ctx.send(choices=[])
        return
    from db_utils import get_db_connection
    conn = get_db_connection()
    choices = []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT Name FROM items WHERE lower(Name) LIKE ? LIMIT 25", ('%' + search_term + '%',))
        matches = cursor.fetchall()
        choices = [{"name": row["Name"], "value": row["Name"]} for row in matches]
    except Exception as e:
        import logging
        logging.error(f"Error in calculate_craft_autocomplete: {e}")
    finally:
        if conn:
            conn.close()
    await ctx.send(choices=choices)


@slash_command(name="recipe", description="Show the full recipe breakdown for a craftable item and track it.")
@slash_option("item_name", "The name of the item to show the recipe for", opt_type=OptionType.STRING, required=True, autocomplete=True)
async def recipe(ctx, item_name: str):
    await ctx.defer() # Defer response

    # The get_recipe function (from recipes.py) handles the database lookup 
    # for recipe details in new_world_data.db.
    recipe_dict = None
    try:
        # Fetch recipe details from the database via recipes.py.
        recipe_dict = get_recipe(item_name)
    except Exception as e:
        logging.error(f"Unexpected error in /recipe calling get_recipe for '{item_name}': {e}", exc_info=True)
        await ctx.send(f"An unexpected error occurred while fetching recipe details for '{item_name}'. Please contact an admin.", ephemeral=True)
        return

    if not recipe_dict:
        # recipes.get_recipe returns None if not found in 'recipes' or derivable from 'items'
        await ctx.send(f"No recipe found for '{item_name}' in the local database or item data.", ephemeral=True)
        return

    # Track the recipe for the user - ensure track_recipe is adapted for DB if it writes data
    # track_recipe is now imported at the top of the file.
    # It uses 'tracked_recipes.json', separate from new_world_data.db
    user_id = str(ctx.author.id)
    try:
        track_recipe(user_id, item_name, recipe_dict)
    except Exception as e:
        logging.error(f"Error calling track_recipe for user {user_id}, item {item_name}: {e}", exc_info=True)
        # Optionally inform the user, or just log, as this is a secondary feature.
        # await ctx.send("Note: Could not save this recipe to your tracked list due to an error.", ephemeral=True)


    embed = Embed()
    # Use .get() with a fallback to item_name for title, and .title() for consistent casing
    embed.title = f"Recipe: {recipe_dict.get('output_item_name', item_name).title()}"
    embed.color = 0x9b59b6 # Purple
    embed.add_field(name="Station", value=str(recipe_dict.get("station", "-")), inline=True)
    embed.add_field(name="Skill", value=str(recipe_dict.get('skill', "-")) , inline=True)
    embed.add_field(name="Skill Level", value=str(recipe_dict.get("skill_level", "-")), inline=True)
    embed.add_field(name="Tier", value=str(recipe_dict.get("tier", "-")), inline=True)
    
    ing_lines = []
    for ing in recipe_dict.get("ingredients", []):
        # Ensure quantity and item name are present and stringified
        ing_lines.append(f"• {ing.get('quantity', '?')} {str(ing.get('item', 'Unknown Ingredient'))}")
    embed.add_field(name="Ingredients", value="\n".join(ing_lines) if ing_lines else "-", inline=False)

    # Add NWDB link for the crafted item by looking up its Item ID from the 'items' table
    crafted_item_name = recipe_dict.get('output_item_name', item_name)
    item_details_for_recipe = await find_item_in_db(crafted_item_name, exact_match=True)
    if item_details_for_recipe:
        item_id_for_url = item_details_for_recipe[0].get('Item_ID') # 'Item_ID' from sanitized 'Item ID'
        if item_id_for_url:
            embed.add_field(name="NWDB Link (Crafted Item)", value=f"[View on NWDB](https://nwdb.info/db/item/{str(item_id_for_url).strip()})", inline=False)

    await ctx.send(embeds=embed)


@recipe.autocomplete("item_name")
async def recipe_autocomplete(ctx: AutocompleteContext):
    search_term = ctx.input_text.lower().strip() if ctx.input_text else ""
    if not search_term:
        await ctx.send(choices=[])
        return
    from db_utils import find_item_in_db
    items = await find_item_in_db(search_term, exact_match=False)
    choices = [{"name": item["Name"], "value": item["Name"]} for item in items[:25]]
    await ctx.send(choices=choices)

# --- Build Management Commands ---
@slash_command(name="build", description="Manage saved New World builds.")
async def build_group(ctx: SlashContext):
    """Base command for build management."""
    pass

@build_group.subcommand(sub_cmd_name="add", sub_cmd_description="Add a build from nw-buddy.de.")
@slash_option("link", "The nw-buddy.de build link", opt_type=OptionType.STRING, required=True)
@slash_option("name", "A name for this build", opt_type=OptionType.STRING, required=True)
@slash_option("keyperks", "Comma-separated list of key perks (optional, paste from Perk stacks)", opt_type=OptionType.STRING, required=False)
async def build_add(ctx: SlashContext, link: str, name: str, keyperks: str = None):
    import requests
    from bs4 import BeautifulSoup
    import re
    # Validate link
    if not re.match(r"^https://(www\.)?nw-buddy.de/gearsets/", link):
        await ctx.send("Please provide a valid nw-buddy.de gearset link.", ephemeral=True)
        return
    perks_list = []
    if keyperks:
        perks_list = [p.strip() for p in keyperks.split(',') if p.strip()]
    else:
        try:
            resp = requests.get(link, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                # Look for 'Perk stacks' section
                perk_header = soup.find(lambda tag: tag.name in ['h2', 'h3', 'h4'] and 'perk stacks' in tag.get_text(strip=True).lower())
                if perk_header:
                    # Find the next ul or div after the header
                    next_elem = perk_header.find_next(['ul', 'div'])
                    if next_elem:
                        for li in next_elem.find_all(['li', 'div'], recursive=False):
                            text = li.get_text(strip=True)
                            if text:
                                perks_list.append(text)
        except Exception:
            pass
    # Save build
    try:
        with open(BUILDS_FILE, 'r', encoding='utf-8') as f:
            builds = json.load(f)
    except Exception:
        builds = [] # Initialize as an empty list if file not found or error
    builds.append({"name": name, "link": link, "keyperks": perks_list, "submitted_by": ctx.author.id})
    with open(BUILDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(builds, f, indent=2)
    await ctx.send(f"Build '{name}' added!", ephemeral=True)


@build_group.subcommand(sub_cmd_name="list", sub_cmd_description="Show a list of saved builds.")
async def build_list(ctx: SlashContext):
    try:
        with open(BUILDS_FILE, 'r', encoding='utf-8') as f:
            builds = json.load(f)
    except Exception:
        await ctx.send("No builds saved yet.", ephemeral=True)
        return
    if not builds:
        await ctx.send("No builds saved yet.", ephemeral=True)
        return
    embed = Embed()
    embed.title = "Saved Builds"
    embed.color = 0x3498db
    for build in builds:
        submitter_id = build.get('submitted_by')
        submitter_mention = f"<@{submitter_id}>" if submitter_id else "Unknown User"
        try:
            if submitter_id:
                user = await bot.fetch_user(submitter_id)
                submitter_mention = user.mention if user else f"User ID: {submitter_id}"
        except Exception: # Handle cases where user might not be fetchable
            submitter_mention = f"User ID: {submitter_id}"
        perks = ', '.join(build.get('keyperks', [])) or '-'
        embed.add_field(name=build['name'], value=f"[Link]({build['link']})\nKey Perks: {perks}\nSubmitted by: {submitter_mention}", inline=False)
    await ctx.send(embeds=embed)


@build_group.subcommand(
    sub_cmd_name="remove",
    sub_cmd_description="Remove a saved build (requires 'Manage Server' permission)."
)
@slash_option(
    "name",
    description="The name of the build to remove",
    opt_type=OptionType.STRING,
    required=True,
    autocomplete=True
)
async def build_remove(ctx: SlashContext, name: str):
    # Check for 'Manage Server' permission or if the user is a bot manager/owner
    if not ctx.author.has_permission(Permissions.MANAGE_GUILD) and not is_bot_manager(int(ctx.author.id)):
        await ctx.send("You need 'Manage Server' permission or be a Bot Manager to use this command.", ephemeral=True)
        return

    try:
        with open(BUILDS_FILE, 'r', encoding='utf-8') as f:
            builds = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        await ctx.send("No builds saved yet or build file is corrupted.", ephemeral=True)
        return

    original_length = len(builds)
    # Find the build by name (case-insensitive)
    builds_filtered = [b for b in builds if b.get("name", "").lower() != name.lower()]

    if len(builds_filtered) == original_length:
        await ctx.send(f"Build '{name}' not found.", ephemeral=True)
        return

    try:
        with open(BUILDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(builds_filtered, f, indent=2)
        await ctx.send(f"Build '{name}' removed successfully.", ephemeral=True)
    except Exception as e:
        logging.error(f"Error writing builds file after removing build: {e}")
        await ctx.send("An error occurred while trying to remove the build.", ephemeral=True)

@build_remove.autocomplete("name")
async def build_remove_autocomplete(ctx: AutocompleteContext): # Corrected type hint
    try:
        with open(BUILDS_FILE, 'r', encoding='utf-8') as f:
            builds_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError): # Handle empty or corrupt file
        await ctx.send(choices=[])
        return # Ensure return after sending empty choices
    search_term = ctx.input_text.lower().strip() if ctx.input_text else ""
    matches = [build.get("name") for build in builds_data if build.get("name") and search_term in build.get("name", "").lower()]
    choices = [{"name": build_name, "value": build_name} for build_name in list(set(matches))[:25]] # Use set for unique names
    await ctx.send(choices=choices)


@slash_command(name="perk", description="Look up information about a specific New World perk.")
@slash_option(
    "perk_name",
    description="The name of the perk to look up",
    opt_type=OptionType.STRING,
    required=True,
    autocomplete=True
)
async def perk_command(ctx, perk_name: str):
    await ctx.defer() # Defer as DB query might take a moment

    perk_results = await find_perk_in_db(perk_name, exact_match=True) 

    if not perk_results:
        perk_results = await find_perk_in_db(perk_name, exact_match=False) # Fallback for direct input
        if not perk_results:
            await ctx.send(f"Perk '{perk_name}' not found in the database.", ephemeral=True)
            return
    
    perk_info = perk_results[0] # Take the first match

    def get_any_perk_info(data_dict, keys, default):
        for k_csv_original in keys:
            # Sanitize k_csv_original the same way create_db.py does for column names
            k_db = k_csv_original.replace(' ', '_').replace('(', '').replace(')', '').replace('%', 'percent')
            if k_db in data_dict and data_dict[k_db] is not None:
                return data_dict[k_db]
        return default

    # Use sanitized key names based on create_db.py logic
    name_raw = get_any_perk_info(perk_info, ['Name', 'PerkName'], perk_name) # 'Name' or 'PerkName'
    description_raw = get_any_perk_info(perk_info, ['Description', 'Desc', 'description', 'DescText', 'EffectText'], 'No description available.')
    perk_type_raw = get_any_perk_info(perk_info, ['Type', 'PerkType', 'Category'], 'Unknown Type')
    icon_url = get_any_perk_info(perk_info, ['Icon', 'IconPath', 'icon_url'], None) # 'IconPath' or 'icon_url' from scrape_perks
    perk_id = get_any_perk_info(perk_info, ['PerkID', 'ID', 'id'], None) # 'PerkID' or 'id' from scrape_perks

    # Craft Mod specific info - these keys are based on common column names from NWDB data sources
    # (e.g., perks_scraped.csv) and how create_db.py might sanitize them.
    generated_label = get_any_perk_info(perk_info, ['GeneratedLabel', 'PerkApplicationType'], None)
    craft_mod_item_name = get_any_perk_info(perk_info, ['ItemName', 'IngredientName', 'CraftModItem'], None) # Item that applies the perk
    condition = get_any_perk_info(perk_info, ['ConditionDescription', 'ConditionText'], None)
    compatible_with_raw = get_any_perk_info(perk_info, ['EquipType', 'CompatibleItemTypes', 'CompatibleEquipment'], None)
    exclusive_labels_raw = get_any_perk_info(perk_info, ['ExclusiveLabels', 'ExclusiveLabel', 'MutatorGroup'], None)

    # Determine if it's a Craft Mod
    is_craft_mod_by_label = generated_label and 'crafting mod' in str(generated_label).lower()
    is_craft_mod_by_type = 'craft mod' in str(perk_type_raw).lower()
    is_craft_mod = is_craft_mod_by_label or is_craft_mod_by_type

    display_title = str(name_raw)
    if is_craft_mod:
        if "craft mod" not in str(name_raw).lower(): # Avoid "Craft Mod: Refreshing Craft Mod"
            display_title = f"Craft Mod: {str(name_raw)}"

    embed = Embed(title=display_title, color=0x1ABC9C) # Teal
    if icon_url:
        embed.set_thumbnail(url=str(icon_url).strip())

    # Scale description if applicable (ensure scale_value_with_gs is robust)
    scaled_description = scale_value_with_gs(str(description_raw))
    perk_type_display = str(perk_type_raw).strip() if perk_type_raw and str(perk_type_raw).strip() else "Unknown Type"

    embed.add_field(name="Description", value=scaled_description, inline=False)
    embed.add_field(name="Type", value=perk_type_display, inline=True)

    # This field is highly specific to Craft Mods
    if is_craft_mod and craft_mod_item_name and str(craft_mod_item_name).strip():
        # Only add if it's a craft mod AND has a craft mod item name
            embed.add_field(name="Crafted With / Source", value=str(craft_mod_item_name), inline=True)
        
    # Add "Scales with Gear Score" note if placeholders were in description, indicating bot performed scaling.
    # This can apply to any perk if its description in the DB uses the scaling placeholder.
    if re.search(r'\{\[.*?\]\}', str(description_raw)):
        embed.add_field(name="Scaling", value="Values scale with Gear Score (shown at 725 GS)", inline=True)

    # These fields will now be attempted for ALL perks if data is available
    condition_display = str(condition).strip() if condition and str(condition).strip() else "-"
    embed.add_field(name="Condition", value=condition_display, inline=False) # Often longer

    compatible_display = "-"
    if compatible_with_raw and str(compatible_with_raw).strip():
        compatible_list = [item.strip() for item in str(compatible_with_raw).split(',') if item.strip()]
        if compatible_list:
            # A more sophisticated mapping could be added here later to make names friendlier
            # e.g., "1HSword" -> "Sword", "2HGreatAxe" -> "Great Axe"
            compatible_display = ", ".join(compatible_list)
    embed.add_field(name="Compatible With", value=compatible_display, inline=False)

    exclusive_display = "-"
    # Handle cases where exclusive_labels_raw might be a single string or a comma-separated list
    # Prefer ExclusiveLabels (plural, from list) if available, then ExclusiveLabel (singular)
    labels_to_process = get_any_perk_info(perk_info, ['ExclusiveLabels'], None) # Check plural first
    if not labels_to_process or not str(labels_to_process).strip():
        labels_to_process = get_any_perk_info(perk_info, ['ExclusiveLabel', 'MutatorGroup'], None) # Fallback to singular

    if labels_to_process and str(labels_to_process).strip():
        exclusive_list = [label.strip() for label in str(exclusive_labels_raw).split(',') if label.strip()]
        if exclusive_list:
            exclusive_display = ", ".join(exclusive_list)
    embed.add_field(name="Exclusive Labels", value=exclusive_display, inline=True) # Usually short

    if perk_id:
        embed.add_field(name="NWDB Link", value=f"[View on NWDB](https://nwdb.info/db/perk/{str(perk_id).strip()})", inline=True)
    else:
        # If PerkID is not directly available, you might try to construct a search link
        # For now, keeping it simple. A search link could be:
        # search_name = urllib.parse.quote_plus(str(name_raw))
        # embed.add_field(name="NWDB Link", value=f"[Search on NWDB](https://nwdb.info/db/perks/?search={search_name})", inline=True)
        embed.add_field(name="NWDB Link", value="Perk ID not found for direct link", inline=True)

    embed.set_footer(text="Perk information from local data. Values may scale with Gear Score in-game.")
    await ctx.send(embeds=embed)

@perk_command.autocomplete("perk_name")
async def perk_autocomplete(ctx: AutocompleteContext): # Corrected type hint
    search_term = ctx.input_text.lower().strip() if ctx.input_text else ""
    if not search_term:
        await ctx.send(choices=[])
        return

    conn = get_db_connection()
    choices = []
    try:
        cursor = conn.cursor()
        # Query the 'Name' column from the 'perks' table. Adjust if your column name differs.
        # This assumes create_db.py stores the main perk name under a column like 'Name'.
        # The name from perks_scraped.csv is stored as 'name' by create_db.py if the CSV header is 'name'.
        # If create_db.py uses pandas and the CSV header is 'name', the SQL column will be 'name'.
        # If CSV header is 'Name', SQL column will be 'Name'.
        # Let's assume 'Name' is the target column name after sanitization or original.
        cursor.execute("SELECT Name FROM perks WHERE lower(Name) LIKE ? LIMIT 25", ('%' + search_term + '%',))
        db_matches = cursor.fetchall()
        # The value sent to the command should be the exact perk name for easier lookup
        choices = [{"name": row["Name"], "value": row["Name"]} for row in db_matches]
    except sqlite3.Error as e:
        logging.error(f"SQLite error in perk_autocomplete: {e}")
    finally:
        if conn:
            conn.close()
    await ctx.send(choices=choices)


@slash_command(name="about", description="Show information about Ina's New World Bot.")
async def about_command(ctx):
    embed = Embed(
        title="About Ina's New World Bot",
        description="Your friendly companion for all things Aeternum!",
        color=0x7289DA  # Discord Blurple
    )
    embed.add_field(
        name="Version",
        value=f"`{config_version}`", # Use imported config_version
        inline=True
    )
    embed.add_field(
        name="Creator",
        value="This bot was lovingly crafted by <@157968227106947072>.",
        inline=True # Changed to true to align better with version
    )
    embed.add_field(
        name="Credits & Data Sources",
        value="• Item and perk data often references [NWDB.info](https://nwdb.info).\n"
              "• Build functionality integrates with [NW-Buddy.de](https://nw-buddy.de).",
        inline=False
    )
    embed.set_footer(text="Ina's New World Bot is a fan-made project and is not affiliated with Amazon Games or New World.")
    await ctx.send(embeds=embed)

async def _perform_update_and_restart(slash_ctx: Optional[SlashContext] = None):
    """
    Handles the bot update process: executes the update script and stops the bot for restart.
    If slash_ctx is provided, sends feedback to the command invoker.
    Returns True if update script succeeded and bot stop was initiated, False otherwise.
    """
    # Determine OS and script details
    current_os = platform.system().lower()
    script_name = ""
    executable = ""

    if "windows" in current_os:
        script_name = "update_bot.ps1"
        executable = "powershell.exe"
        script_args = ['-ExecutionPolicy', 'Bypass', '-File']
    elif "linux" in current_os:
        script_name = "update_bot.sh"
        executable = "/bin/bash" # or "bash" if it's in PATH
        script_args = [] # No special args needed before the script path for bash
    else:
        await ctx.send(f"Unsupported operating system for automatic updates: {current_os}", ephemeral=True)
        return

    # Construct the path to the update script
    # Assumes main.py and the update script are in the same directory (the Git repo root).
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), script_name))

    if not os.path.exists(script_path):
        error_msg = f"Update script not found at: {script_path}"
        logging.error(error_msg)
        if slash_ctx:
            await slash_ctx.send(f"Error: Update script not found at the expected location: `{script_path}`.", ephemeral=True)
        return False

    initiator_desc = "Automatic update check"
    if slash_ctx and slash_ctx.author:
        initiator_desc = f"User {slash_ctx.author.username} ({slash_ctx.author.id})"

    try:
        logging.info(f"{initiator_desc} initiated bot update using {executable} with script: {script_path}")
        # The script (e.g., update_bot.sh or update_bot.ps1) is responsible for the actual Git operations,
        # including how updates are fetched (e.g., git pull, git reset --hard for force updates).
        # Using asyncio.create_subprocess_exec for non-blocking execution
        # Full command: executable *script_args script_path
        process = await asyncio.create_subprocess_exec(
            executable,
            *script_args, # Unpack arguments like -ExecutionPolicy Bypass -File
            script_path,  # The script itself is the last argument here
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate() # Wait for the script to complete

        stdout_str = stdout.decode('utf-8', errors='ignore')
        stderr_str = stderr.decode('utf-8', errors='ignore')

        if slash_ctx: # Send detailed feedback if initiated by command
            response_message = f"🚀 **Update Script Execution ({current_os.capitalize()})** 🚀\n"
            if process.returncode == 0:
                response_message += "✅ Script executed successfully.\n"
            else:
                response_message += f"⚠️ Script finished with exit code: {process.returncode}.\n"
            
            max_log_section_length = 850 # Max length for each log section

            if stdout_str:
                response_message += f"**Output:**\n```\n{stdout_str[:max_log_section_length]}\n```\n" # Using generic ```
                if len(stdout_str) > max_log_section_length:
                    response_message += f"... (output truncated)\n"
            if stderr_str:
                response_message += f"**Errors:**\n```\n{stderr_str[:max_log_section_length]}\n```\n" # Using generic ```
                if len(stderr_str) > max_log_section_length:
                    response_message += f"... (errors truncated)\n"
            
            if process.returncode == 0:
                response_message += "\n✅ **Updates pulled. Attempting to apply by restarting the bot...**\n"
                response_message += "ℹ️ The bot will shut down. An external process manager (e.g., PM2, systemd, Docker restart policy) is required to bring it back online with the updates."
            else:
                response_message += "\n❌ **Update script failed. Bot will not restart.**"

            if len(response_message) > 2000:
                response_message = (f"🚀 Update script finished with exit code: {process.returncode}. "
                                    f"Logs were too long to display here. Please check the console/logs. ")
                if process.returncode == 0:
                    response_message += "Bot will attempt to restart to apply updates."
                else:
                    response_message += "Bot will not restart."
            await slash_ctx.send(response_message, ephemeral=True)

        if process.returncode == 0:
            logging.info(f"Update script successful for {initiator_desc}. Stopping bot to apply updates.")
            if slash_ctx: await asyncio.sleep(3) # Ensure message is sent if slash_ctx exists
            await bot.stop()
            if not slash_ctx: # Log for automatic update
                logging.warning(f"Automatic update successful. Bot has been stopped for restart by process manager.")
            return True
        else:
            log_msg = f"Update script failed for {initiator_desc} with exit code {process.returncode}."
            if stdout: log_msg += f" Stdout: {stdout.decode(errors='ignore')}"
            if stderr: log_msg += f" Stderr: {stderr.decode(errors='ignore')}"
            logging.error(log_msg)
            if not slash_ctx: # Log for automatic update failure
                 logging.error(f"Automatic update failed. Script exit code: {process.returncode}.")
            return False
    except Exception as e:
        error_msg = f"An error occurred while {initiator_desc} tried to run update script '{script_name}': {e}"
        logging.error(error_msg, exc_info=True)
        if slash_ctx:
            await slash_ctx.send(error_msg, ephemeral=True)
        return False

# --- Bot Management Commands ---
@slash_command(name="manage", description="Manage bot operations (restricted).")
async def manage_group(ctx: SlashContext):
    """Base command for bot management."""
    pass

@manage_group.subcommand(
    sub_cmd_name="update",
    sub_cmd_description="Pulls updates from GitHub and restarts the bot (Owner only)."
)
async def manage_update(ctx: SlashContext):
    if ctx.author.id != OWNER_ID:
        await ctx.send("You do not have permission to use this command.", ephemeral=True)
        return

    await ctx.defer(ephemeral=True) # Acknowledge interaction, make response visible only to user
    await _perform_update_and_restart(slash_ctx=ctx)

@manage_group.subcommand(
    sub_cmd_name="restart",
    sub_cmd_description="Shuts down the bot for manual restart (Bot Owner/Manager only)."
)
async def manage_restart(ctx: SlashContext):
    if not is_bot_manager(int(ctx.author.id)) and ctx.author.id != OWNER_ID:
        await ctx.send("You do not have permission to use this command.", ephemeral=True)
        return

    guild_info = "a Direct Message"
    if ctx.guild:
        guild_info = f"guild {ctx.guild.name} ({ctx.guild.id})"

    logging.info(f"Restart command initiated by {ctx.author.username} ({ctx.author.id}) in {guild_info}.")

    await ctx.send(
        "✅ Bot shutdown command acknowledged. "
        "The bot process will now attempt to stop.\n"
        "ℹ️ **A manual restart of the bot's process on the server is required for it to come back online.**",
        ephemeral=True
    )
    # Gracefully stop the bot
    # Note: This stops the Python script. An external process manager (systemd, PM2, Docker, etc.)
    # or a wrapper script is needed to actually restart the bot process.
    await bot.stop()

@manage_group.subcommand(
    sub_cmd_name="debug",
    sub_cmd_description="Enable or disable debug logging in the console (Bot Owner/Manager only)."
)
@slash_option(
    name="action",
    description="Choose to enable or disable debug logging.",
    opt_type=OptionType.STRING,
    required=True,
    choices=[
        {"name": "Enable Debug Logging", "value": "enable"},
        {"name": "Disable Debug Logging", "value": "disable"},
    ]
)
async def manage_debug(ctx: SlashContext, action: str):
    global DEBUG_MODE_ENABLED # To update the global state variable
    if not is_bot_manager(int(ctx.author.id)) and ctx.author.id != OWNER_ID:
        await ctx.send("You do not have permission to use this command.", ephemeral=True)
        return # Ensure this return is here

    action = action.lower()
    root_logger = logging.getLogger()
    # interactions_logger is already defined globally

    if action == "enable":
        root_logger.setLevel(logging.DEBUG)
        interactions_logger.setLevel(logging.DEBUG)
        DEBUG_MODE_ENABLED = True
        await ctx.send("⚙️ Debug logging **enabled**. Console will now show verbose logs.", ephemeral=True)
        logging.debug("Debug mode has been enabled via command.")
    elif action == "disable":
        root_logger.setLevel(DEFAULT_LOG_LEVEL) # Revert to default (e.g., INFO)
        interactions_logger.setLevel(DEFAULT_LOG_LEVEL)
        DEBUG_MODE_ENABLED = False
        logging.info("Debug mode has been disabled via command.") # Log this at INFO before level changes fully
        await ctx.send("⚙️ Debug logging **disabled**. Console will revert to normal verbosity.", ephemeral=True)


# --- Settings Commands ---
@slash_command(name="settings", description="Manage bot settings (requires permissions).")
async def settings(ctx: SlashContext):
    """Base command for settings. Discord will typically show subcommands."""
    # This function body can be left empty or provide a generic help message
    # if called directly, though usually users will invoke subcommands.
    pass

@manage_group.subcommand(
    sub_cmd_name="cleanup",
    sub_cmd_description="Cleans up cached Python files (__pycache__, .pyc) (Bot Owner/Manager only)."
)
async def manage_cleanup(ctx: SlashContext):
    if not is_bot_manager(int(ctx.author.id)) and ctx.author.id != OWNER_ID:
        await ctx.send("You do not have permission to use this command.", ephemeral=True)
        return

    await ctx.defer(ephemeral=True)

    project_root = os.path.dirname(os.path.abspath(__file__))
    pycache_count, pyc_count, errors = await _cleanup_cache_files_recursive(project_root)

    # Remove large or unnecessary data files
    files_to_remove = [
        "items.csv", "perks.csv", "perks_scraped.csv", "perks_buddy.csv", "items.json", "new_world_world_data.db"
    ]
    removed_files = []
    for filename in files_to_remove:
        file_path = os.path.join(project_root, filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                removed_files.append(filename)
            except Exception as e:
                errors.append(f"Failed to remove {filename}: {e}")

    response_message = "🧹 **Cache Cleanup Report** 🧹\n"
    response_message += f"Removed `{pycache_count}` `__pycache__` directories.\n"
    response_message += f"Removed `{pyc_count}` `.pyc` files.\n"
    if removed_files:
        response_message += f"Removed data files: {', '.join(removed_files)}\n"

    if errors:
        response_message += "\n⚠️ **Errors Encountered:**\n"
        for error in errors[:5]: # Show up to 5 errors to keep message length reasonable
            response_message += f"- {error}\n"
        if len(errors) > 5:
            response_message += f"- ...and {len(errors) - 5} more errors (check bot logs for details).\n"
    else:
        response_message += "\n✅ Cleanup completed successfully with no errors."

    await ctx.send(response_message, ephemeral=True)

# --- Update items from nwdb.info and upload to git ---
import aiohttp
async def update_items_from_nwdb():
    items = []
    page = 1
    while True:
        url = f"https://nwdb.info/db/items/page/{page}.json"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    break
                data = await resp.json()
                if not data or not isinstance(data, list):
                    break
                items.extend(data)
                if len(data) < 100:  # Last page is usually < 100 items
                    break
                page += 1
    # Save to items_updated.json
    with open("items_updated.json", "w", encoding="utf-8") as f:
        import json
        json.dump(items, f, indent=2)
    return len(items)

@manage_group.subcommand(
    sub_cmd_name="update_items",
    sub_cmd_description="Scrape all items from nwdb.info and upload to git (Owner only)."
)
async def manage_update_items(ctx: SlashContext):
    if ctx.author.id != OWNER_ID:
        await ctx.send("You do not have permission to use this command.", ephemeral=True)
        return
    await ctx.defer(ephemeral=True)
    # Run the PowerShell script first
    import subprocess
    import os
    try:
        script_path = os.path.join(os.path.dirname(__file__), "scrapeitems.ps1")
        subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", script_path], check=True)
    except Exception as e:
        await ctx.send(f"Failed to run scrapeitems.ps1: {e}")
        return
    count = await update_items_from_nwdb()
    try:
        subprocess.run(["git", "add", "items.json"], check=True)
        subprocess.run(["git", "add", "items_updated.json"], check=True)
        subprocess.run(["git", "commit", "-m", f"Update items.json/items_updated.json ({count} items scraped from nwdb.info)"], check=True)
        subprocess.run(["git", "push"], check=True)
        await ctx.send(f"✅ Ran scrapeitems.ps1, scraped and uploaded {count} items to items.json/items_updated.json and pushed to git.")
    except Exception as e:
        await ctx.send(f"Scraped {count} items, but git commit/push failed: {e}")

@settings.subcommand(sub_cmd_name="permit", sub_cmd_description="Grants a user bot management permissions.")
@slash_option("user", "The user to grant permissions to.", opt_type=OptionType.USER, required=True)
async def settings_permit_subcommand(ctx: SlashContext, user: User): # Renamed to avoid conflict if settings was a class
    if not ctx.author.has_permission(Permissions.ADMINISTRATOR) and ctx.author.id != OWNER_ID:
        await ctx.send("You need Administrator permissions or be the Bot Owner to use this command.", ephemeral=True)
        return

    if add_bot_manager(int(user.id)):
        await ctx.send(f"✅ {user.mention} has been granted bot management permissions.", ephemeral=True)
    else:
        await ctx.send(f"ℹ️ {user.mention} already has bot management permissions.", ephemeral=True)

@settings.subcommand(sub_cmd_name="unpermit", sub_cmd_description="Revokes a user's bot management permissions.")
@slash_option("user", "The user to revoke permissions from.", opt_type=OptionType.USER, required=True)
async def settings_unpermit_subcommand(ctx: SlashContext, user: User): # Renamed
    if not ctx.author.has_permission(Permissions.ADMINISTRATOR) and ctx.author.id != OWNER_ID:
        await ctx.send("You need Administrator permissions or be the Bot Owner to use this command.", ephemeral=True)
        return

    if int(user.id) == OWNER_ID:
        await ctx.send("🚫 The bot owner's permissions cannot be revoked.", ephemeral=True)
        return

    if remove_bot_manager(int(user.id)):
        await ctx.send(f"✅ {user.mention}'s bot management permissions have been revoked.", ephemeral=True)
    else:
        await ctx.send(f"ℹ️ {user.mention} does not have bot management permissions.", ephemeral=True)

@settings.subcommand(sub_cmd_name="listmanagers", sub_cmd_description="Lists users with bot management permissions.")
async def settings_listmanagers_subcommand(ctx: SlashContext): # Renamed
    if not ctx.author.has_permission(Permissions.ADMINISTRATOR) and not is_bot_manager(int(ctx.author.id)) and ctx.author.id != OWNER_ID :
        await ctx.send("You need Administrator permissions or be a Bot Manager/Owner to use this command.", ephemeral=True)
        return

    managers = load_bot_managers()
    embed = Embed(title="👑 Bot Managers 👑", color=0xFFD700) # Gold color

    owner_user = await bot.fetch_user(OWNER_ID)
    if owner_user:
        embed.add_field(name="Bot Owner (Implicit Manager)", value=owner_user.mention, inline=False)
    else:
        embed.add_field(name="Bot Owner (Implicit Manager)", value=f"ID: {OWNER_ID} (User not found)", inline=False)

    if managers:
        manager_mentions = []
        for manager_id in managers:
            if manager_id == OWNER_ID: continue # Skip owner if already listed
            try:
                user = await bot.fetch_user(manager_id)
                manager_mentions.append(user.mention if user else f"ID: {manager_id} (User not found)")
            except Exception:
                manager_mentions.append(f"ID: {manager_id} (Error fetching user)")
        embed.add_field(name="Permitted Managers", value="\n".join(manager_mentions) if manager_mentions else "No additional managers permitted.", inline=False)
    else:
        embed.add_field(name="Permitted Managers", value="No additional managers permitted.", inline=False)
    await ctx.send(embeds=embed, ephemeral=True)


# Refactored welcome messages settings command
@settings.subcommand(
    sub_cmd_name="welcomemessages", 
    sub_cmd_description="Manage welcome messages for new members (enable/disable/status)."
)
@slash_option(
    name="action",
    description="The action to perform for welcome messages.",
    opt_type=OptionType.STRING,
    required=True,
    choices=[
        {"name": "Enable Welcome Messages", "value": "enable"},
        {"name": "Disable Welcome Messages", "value": "disable"},
        {"name": "Show Welcome Message Status", "value": "status"},
    ]
)
@slash_option(
    "channel",
    "The text channel for welcome messages (required if action is 'enable').",
    opt_type=OptionType.CHANNEL,
    required=False, # Optional at API level, checked in code
    channel_types=[ChannelType.GUILD_TEXT]
)
async def settings_welcomemessages_manager(ctx: SlashContext, action: str, channel: Optional[GuildText] = None):
    if not ctx.author.has_permission(Permissions.MANAGE_GUILD) and not is_bot_manager(int(ctx.author.id)):
        await ctx.send("You need 'Manage Server' permission or be a Bot Manager/Owner to use this command.", ephemeral=True)
        return
    if not ctx.guild:
        await ctx.send("This command can only be used in a server.", ephemeral=True)
        return

    action = action.lower() # Normalize action string

    if action == "enable":
        if not channel:
            await ctx.send("A channel is required to enable welcome messages. Please specify a channel.", ephemeral=True)
            return
        save_welcome_setting(str(ctx.guild.id), True, str(channel.id))
        await ctx.send(f"✅ Welcome messages are now **enabled** and will be sent to {channel.mention}.", ephemeral=True)
    elif action == "disable":
        save_welcome_setting(str(ctx.guild.id), False, None)
        await ctx.send("✅ Welcome messages are now **disabled** for this server.", ephemeral=True)
    elif action == "status":
        setting = get_welcome_setting(str(ctx.guild.id))
        if setting and setting.get("enabled") and setting.get("channel_id"):
            try:
                welcome_channel_obj = await bot.fetch_channel(int(setting['channel_id']))
                await ctx.send(f"ℹ️ Welcome messages are **enabled** and set to channel {welcome_channel_obj.mention}.", ephemeral=True)
            except Exception:
                await ctx.send(f"ℹ️ Welcome messages are **enabled** and set to channel ID `{setting['channel_id']}` (channel might be deleted or inaccessible).", ephemeral=True)
        else:
            await ctx.send("ℹ️ Welcome messages are currently **disabled** for this server.", ephemeral=True)
    else:
        # This case should ideally not be reached if choices are enforced by Discord
        await ctx.send("Invalid action specified. Please use 'enable', 'disable', or 'status'.", ephemeral=True)

# Refactored logging settings command
@settings.subcommand(
    sub_cmd_name="logging", 
    sub_cmd_description="Manage server activity logging (enable/disable/status)."
)
@slash_option(
    name="action",
    description="The action to perform for server activity logging.",
    opt_type=OptionType.STRING,
    required=True,
    choices=[
        {"name": "Enable Logging", "value": "enable"},
        {"name": "Disable Logging", "value": "disable"},
        {"name": "Show Logging Status", "value": "status"},
    ]
)
@slash_option(
    "channel",
    "The text channel for logs (required if action is 'enable').",
    opt_type=OptionType.CHANNEL,
    required=False, # Optional at API level, checked in code
    channel_types=[ChannelType.GUILD_TEXT]
)
async def settings_logging_manager(ctx: SlashContext, action: str, channel: Optional[GuildText] = None):
    if not ctx.author.has_permission(Permissions.MANAGE_GUILD) and not is_bot_manager(int(ctx.author.id)):
        await ctx.send("You need 'Manage Server' permission or be a Bot Manager/Owner to use this command.", ephemeral=True)
        return
    if not ctx.guild:
        await ctx.send("This command can only be used in a server.", ephemeral=True)
        return
    
    action = action.lower() # Normalize action string

    if action == "enable":
        if not channel:
            await ctx.send("A channel is required to enable logging. Please specify a channel.", ephemeral=True)
            return
        save_logging_setting(str(ctx.guild.id), True, str(channel.id))
        await ctx.send(f"✅ Server activity logging is now **enabled** and will be sent to {channel.mention}.", ephemeral=True)
    elif action == "disable":
        save_logging_setting(str(ctx.guild.id), False, None)
        await ctx.send("✅ Server activity logging is now **disabled** for this server.", ephemeral=True)
    elif action == "status":
        setting = get_logging_setting(str(ctx.guild.id))
        if setting and setting.get("enabled") and setting.get("channel_id"):
            try:
                log_channel_obj = await bot.fetch_channel(int(setting['channel_id']))
                await ctx.send(f"ℹ️ Server activity logging is **enabled** and set to channel {log_channel_obj.mention}.", ephemeral=True)
            except Exception:
                await ctx.send(f"ℹ️ Server activity logging is **enabled** and set to channel ID `{setting['channel_id']}` (channel might be deleted or inaccessible).", ephemeral=True)
        else:
            await ctx.send("ℹ️ Server activity logging is currently **disabled** for this server.", ephemeral=True)
    else:
        # This case should ideally not be reached if choices are enforced by Discord
        await ctx.send("Invalid action specified. Please use 'enable', 'disable', or 'status'.", ephemeral=True)

# Start background update check after bot is ready
@bot.event()
async def on_ready():
    import asyncio
    asyncio.create_task(check_for_updates())

# Mention handler
@bot.event()
async def on_message_create(event: MessageCreate): # Parameter is the event object
    """Handles new messages, specifically for bot mentions."""
    message: Message = event.message # Access the actual message from the event object

    if not message:
        return
    # Ensure message is a Message object, not a string or other type if dispatch is unexpected
    if not isinstance(message, Message):
        logging.warning(f"on_message_create: Extracted message is not of type Message. Type: {type(message)}. Value: {message}")
        return

    author = getattr(message, "author", None)
    if not author or getattr(author, "bot", False):
        return
    bot_self = getattr(bot, "me", None) or getattr(bot, "user", None)
    if not bot_self or not hasattr(bot_self, "id"):
        return
    bot_id = str(getattr(bot_self, "id", None))
    mentions = getattr(message, "mentions", []) or []
    mentioned_ids = {str(m.id) for m in mentions if hasattr(m, 'id')}
    content = getattr(message, "content", "") or getattr(message, "text", "")
    if bot_id in mentioned_ids or f"<@{bot_id}>" in content:
        channel_id = getattr(message, "channel_id", None)
        if channel_id:
            channel = await bot.fetch_channel(channel_id)
            # Only send if channel supports send (TextChannel, not GuildForum, GuildCategory, or None)
            if channel and hasattr(channel, 'send') and isinstance(channel, TextChannel): # More robust check
                await channel.send(random.choice(SILLY_MENTION_RESPONSES))

async def _log_server_activity(guild_id: str, embed: Embed, text_message: Optional[str] = None):
    """Helper function to send log messages to the configured log channel."""
    if not guild_id:
        return

    log_settings = get_logging_setting(str(guild_id))
    if log_settings and log_settings.get("enabled") and log_settings.get("channel_id"):
        log_channel_id = log_settings["channel_id"]
        try:
            log_channel = await bot.fetch_channel(int(log_channel_id))
            if log_channel and isinstance(log_channel, TextChannel): # Ensure it's a text channel
                if not embed.timestamp: # Add timestamp if not already set
                    embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
                await log_channel.send(content=text_message, embeds=embed)
            else:
                logging.warning(f"Log channel {log_channel_id} in guild {guild_id} is not a valid text channel or not found.")
        except Permissions.Missing:
            logging.error(f"Missing permissions to send log message in channel {log_channel_id} for guild {guild_id}.")
        except Exception as e:
            logging.error(f"Failed to send log message to channel {log_channel_id} in guild {guild_id}: {e}", exc_info=True)



@bot.event()
async def on_guild_member_add(event_name: str, member: Member):
    """Handles new member joins and sends a welcome message if configured."""
    if not member.guild:
        return # Should not happen for this event, but good practice

    # Defensive check if member is not actually a Member object
    if not isinstance(member, Member):
        logging.error(f"on_guild_member_add received non-Member object for member: {type(member)}. Value: {member}")
        # Attempt to fetch member if 'member' was an ID, though this is unlikely for this event
        # This part is highly speculative and depends on what 'member' might be if not a Member object.
        return

    guild_id_str = str(member.guild.id)
    settings = get_welcome_setting(guild_id_str)

    if settings and settings.get("enabled") and settings.get("channel_id"):
        channel_id = settings["channel_id"]
        try:
            # Ensure channel_id is an int for fetch_channel if it expects int
            channel = await bot.fetch_channel(int(channel_id))
            if channel and isinstance(channel, TextChannel): # Check if it's a text channel
                welcome_message = random.choice(NEW_WORLD_WELCOME_MESSAGES).format(
                    member_mention=member.mention,
                    guild_name=member.guild.name
                )
                await channel.send(welcome_message)
                logging.info(f"Sent welcome message to {member.username} in guild {member.guild.name} ({guild_id_str}), channel {channel.name} ({channel_id}).")
            else:
                logging.warning(f"Welcome message channel {channel_id} in guild {guild_id_str} is not a valid text channel or not found.")
        except Exception as e:
            logging.error(f"Failed to send welcome message in guild {guild_id_str}, channel {channel_id}: {e}", exc_info=True)

# --- Server Activity Logging Events ---
@bot.event()
async def on_message_delete(event_name: str, message: Message):
    if not isinstance(message, Message):
        logging.warning(f"on_message_delete received non-Message object: {type(message)}. Value: {message}")
        return
        
    # Original check:
    if not getattr(message, 'guild', None): # Only log guild messages
        return

    # Message content might not be available if not cached or intent is missing
    content = message.content if message.content else "[Content not available or message was an embed]"
    if len(content) > 1000: # Truncate long messages
        content = content[:1000] + "..."

    embed = Embed(
        title="🗑️ Message Deleted",
        color=0xFF0000, # Red
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.add_field(name="Author", value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
    embed.add_field(name="Channel", value=message.channel.mention, inline=True)
    embed.add_field(name="Content", value=f"```{content}```", inline=False)
    if message.attachments:
        embed.add_field(name="Attachments", value=f"{len(message.attachments)} attachment(s)", inline=True)
    embed.set_footer(text=f"Message ID: {message.id}")

    await _log_server_activity(str(message.guild.id), embed)

@bot.event()
async def on_message_update(event_name: str, before: Optional[Message] = None, after: Optional[Message] = None):
    # Defensive checks for types, as the original error implies _args might be empty for this event
    if not after:
        logging.warning(f"on_message_update for event '{event_name}' called without 'after' message. Before: {before}. This may indicate a library dispatch issue or an event without an 'after' payload.")
        return
    
    # Ensure 'after' is a Message object if it was provided
    if not isinstance(after, Message): # This check might be redundant if the above 'if not after:' catches it.
        logging.error(f"on_message_update: 'after' (value: {after}) is not a Message object. Type: {type(after)}. This indicates a library dispatch issue.")
        return
    if before is not None and not isinstance(before, Message):
        logging.warning(f"on_message_update: 'before' is not None and not a Message object. Type: {type(before)}, Value: {before}")
        # Depending on library behavior, 'before' might be None if not in cache.
        # If it's something else unexpected, it's an issue.

    if not getattr(after, 'guild', None) or not getattr(after, 'author', None) or getattr(after.author, 'bot', True): # Only log guild messages from users
        return
    if before and getattr(before, 'content', None) == getattr(after, 'content', None) and not (getattr(before, 'embeds', []) != getattr(after, 'embeds', [])): # Ignore if only embeds changed by bot itself or no actual content change
        return

    old_content = before.content if before and before.content else "[Content not available or was an embed]"
    new_content = after.content if after.content else "[Content not available or is an embed]"

    if len(old_content) > 450: old_content = old_content[:450] + "..."
    if len(new_content) > 450: new_content = new_content[:450] + "..."

    embed = Embed(
        title="✏️ Message Edited",
        description=f"Jump to Message",
        color=0x007FFF, # Blue
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    embed.add_field(name="Author", value=f"{after.author.mention} (`{after.author.id}`)", inline=True)
    embed.add_field(name="Channel", value=after.channel.mention, inline=True)
    embed.add_field(name="Before", value=f"```{old_content}```", inline=False)
    embed.add_field(name="After", value=f"```{new_content}```", inline=False)
    embed.set_footer(text=f"Message ID: {after.id}")

    await _log_server_activity(str(after.guild.id), embed)

@bot.event()
async def on_guild_member_remove(event_name: str, member: Member):
    if not isinstance(member, Member):
        logging.error(f"on_guild_member_remove received non-Member object: {type(member)}. Value: {member}")
        return

    if not getattr(member, 'guild', None):
        return

    embed = Embed(
        title="🚶 Member Left",
        description=f"{member.mention} (`{member.username}#{member.discriminator}` | `{member.id}`)",
        color=0xFFA500, # Orange
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    if getattr(member, 'avatar', None):
      embed.set_thumbnail(url=member.avatar.url)

    await _log_server_activity(str(member.guild.id), embed)

@bot.event()
async def on_guild_ban(event_name: str, guild_id: str, user: User): # Assuming guild_id and user are passed
    guild = await bot.fetch_guild(guild_id) # Fetch guild if only ID is provided
    if not guild: return

    if not isinstance(user, User):
        logging.error(f"on_guild_ban received non-User object: {type(user)}. Value: {user}")
        return

    embed = Embed(
        title="🔨 Member Banned",
        description=f"{user.mention} (`{user.username}#{user.discriminator}` | `{user.id}`)",
        color=0xDC143C, # Crimson
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    if getattr(user, 'avatar', None):
        embed.set_thumbnail(url=user.avatar.url)
    await _log_server_activity(str(guild.id), embed)

@bot.event()
async def on_guild_unban(event_name: str, guild_id: str, user: User):
    guild = await bot.fetch_guild(guild_id)
    if not guild: return

    if not isinstance(user, User):
        logging.error(f"on_guild_unban received non-User object: {type(user)}. Value: {user}")
        return

    embed = Embed(
        title="🤝 Member Unbanned",
        description=f"{user.mention} (`{user.username}#{user.discriminator}` | `{user.id}`)",
        color=0x32CD32, # LimeGreen
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    if getattr(user, 'avatar', None):
        embed.set_thumbnail(url=user.avatar.url)
    await _log_server_activity(str(guild.id), embed)

@bot.event()
async def on_guild_role_create(event_name: str, role: Role):
    if not isinstance(role, Role):
        logging.error(f"on_guild_role_create received non-Role object: {type(role)}. Value: {role}")
        return

    embed = Embed(
        title="✨ Role Created",
        description=f"Role: {role.mention} (`{role.name}` | `{role.id}`)",
        color=0x00FF00, # Green
    )
    if hasattr(role, 'guild') and role.guild: # Ensure role has guild context
        await _log_server_activity(str(role.guild.id), embed)

@bot.event()
async def on_guild_role_delete(event_name: str, role: Role): 
    if not isinstance(role, Role):
        logging.error(f"on_guild_role_delete received non-Role object: {type(role)}. Value: {role}")
        return

    embed = Embed(
        title="🗑️ Role Deleted",
        description=f"Role Name: `{role.name}` (ID: `{role.id}`)",
        color=0xFF4500, # OrangeRed
    )
    if hasattr(role, 'guild') and role.guild: # Ensure role has guild context
        await _log_server_activity(str(role.guild.id), embed)

async def rotate_funny_presence(bot, interval=60):
    await bot.wait_until_ready()
    while True:
        status = random.choice(NW_FUNNY_STATUSES)
        funny_status = f"{status['name']} – {status['state']}"

        # Calculate current uptime
        current_time_now = time.time()
        uptime_seconds = current_time_now - BOT_START_TIME
        formatted_uptime_str = format_uptime(uptime_seconds)

        # Choose a silly uptime message
        silly_template = random.choice(SILLY_UPTIME_MESSAGES)
        random_x = random.randint(5, 500) # Adjust range as needed
        activity_name_with_uptime = silly_template.format(x=random_x, uptime=formatted_uptime_str)

        activity_buttons = [
            {
                "label": "Add Ina's Bot to your Server",
                "url": BOT_INVITE_URL,
            }
        ]
        try:
            await bot.change_presence(activity=Activity(name=activity_name_with_uptime, type=ActivityType.PLAYING, buttons=activity_buttons))
        except Exception as e:
            logging.warning(f"Failed to set presence: {e}")
        await asyncio.sleep(interval)


async def check_for_updates():
    """Periodically checks GitHub for new bot releases and logs a notification if found."""
    await bot.wait_until_ready()
    logging.info(f"Ina's New World Bot version: {config_version} starting update checks.") # Use imported config_version
    while True:
        try:
            headers = {
                "Accept": "application/vnd.github.v3+json",
                # "User-Agent": "InaDiscordBotUpdateChecker/1.0" # Optional: Good practice for API requests
            }
            # Fetch the VERSION file from the main branch
            response = requests.get(GITHUB_VERSION_FILE_URL, headers=headers, timeout=15) # headers might not be strictly needed for raw.githubusercontent

            if response.status_code == 404:
                logging.info(f"VERSION file not found on main branch at {GITHUB_VERSION_FILE_URL}. Update check skipped.")
            elif response.status_code == 200:
                latest_version_str = response.text.strip() # The content of the VERSION file
                # Link to the main branch for update instructions/source
                update_source_url = f"https://github.com/{GITHUB_REPO_OWNER}/{GITHUB_REPO_NAME}/tree/main"

                if latest_version_str:
                    current_v = packaging.version.parse(config_version) # Use imported config_version
                    latest_v = packaging.version.parse(latest_version_str)

                    logging.debug(f"Update Check: Current bot version: {current_v}, Latest version on main branch: {latest_v}")

                    if latest_v > current_v:
                        logging.warning(
                            f"🎉 A new version of Ina's New World Bot is available: {latest_v} "
                            f"(current: {current_v}). Attempting automatic update and restart. Source: {update_source_url}"
                        )
                        await _perform_update_and_restart() # Automatic update, no context
                    else:
                        logging.info("Bot is up to date with the version on the main branch.")
                else:
                    logging.warning(f"VERSION file at {GITHUB_VERSION_FILE_URL} is empty or invalid.")
            else:
                logging.error(
                    f"Failed to fetch latest release info from GitHub. Status: {response.status_code}, "
                    f"Response: {response.text[:200]}"
                )
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error during GitHub update check: {e}")
        except packaging.version.InvalidVersion as e:
            logging.error(f"Error parsing version string during update check: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred during GitHub update check: {e}", exc_info=True)
        
        await asyncio.sleep(UPDATE_CHECK_INTERVAL_SECONDS)

def load_all_game_data():
    """
    Ensures the SQLite database file exists. If not, attempts to create and populate it.
    The actual data loading into the DB is handled by create_db.py.
    """
    logging.info("Verifying game data source (SQLite Database)...")

    if not os.path.exists(DB_NAME):
        logging.warning(
            f"Database file '{DB_NAME}' not found. Attempting to create and populate it now. "
            f"This may take some time and consume resources..."
        )
        try:
            from create_db import populate_db # Import here to avoid potential circular import issues at module load time
            populate_db() # This function from create_db.py prints its own progress
            if os.path.exists(DB_NAME):
                logging.info(f"Database '{DB_NAME}' created and populated successfully.")
            else:
                # This case means populate_db ran but didn't create the file, which indicates an issue in populate_db
                logging.error(
                    f"CRITICAL: populate_db() completed but database file '{DB_NAME}' still not found. "
                    f"Bot may not function correctly for data-dependent commands."
                )
        except ImportError:
            logging.error(
                "CRITICAL: Could not import 'populate_db' from 'create_db.py'. "
                "Database cannot be automatically created. Please run 'create_db.py' manually if possible."
            )
        except Exception as e:
            logging.error(
                f"CRITICAL: An error occurred while trying to automatically create/populate the database '{DB_NAME}': {e}. "
                f"Please run 'create_db.py' manually if possible. Bot may not function correctly.", exc_info=True
            )
    
    if os.path.exists(DB_NAME):
        logging.info(f"Database '{DB_NAME}' is available. Bot will use it for data lookups.")
    else:
        logging.critical(
            f"CRITICAL: Database file '{DB_NAME}' not found. "
            f"The bot relies on this database for item, perk, and recipe data. "
            f"Automatic creation failed or was not possible. Please ensure 'create_db.py' can run successfully or create the DB manually."
        )
    logging.info("Game data verification/creation process complete.")

@bot.event()
async def on_ready():
    # load_all_game_data() # Moved to be called before bot.start()
    asyncio.create_task(rotate_funny_presence(bot, interval=60))
    asyncio.create_task(check_for_updates())
    logging.info(f"Ina is ready! Logged in as {bot.user.username} ({bot.user.id})")

if __name__ == "__main__":
    load_all_game_data() # Load data before starting the bot
    try:
        bot.start()
    except Exception as e:
        logging.error(f"Failed to start the bot: {e}")
