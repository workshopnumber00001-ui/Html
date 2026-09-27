import os, zipfile, tempfile, shutil, asyncio, time
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageNotModified

# Global variable to track cancellation
cancelled_tasks = set()

def format_size(size_bytes):
    """Convert bytes to human readable format (MB/GB)"""
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

def progress_simple(current, total, start_time, status_text, task_id):
    """Simplified progress display with cancel button"""
    try:
        # Check if cancelled
        if task_id in cancelled_tasks:
            return None, True

        elapsed = time.time() - start_time
        if elapsed < 0.001:
            elapsed = 0.001
        speed = current / elapsed if elapsed > 0 else 0

        # Format speed
        if speed < 1024:
            speed_str = f"{speed:.2f} B/s"
        elif speed < 1024 * 1024:
            speed_str = f"{speed / 1024:.2f} KB/s"
        else:
            speed_str = f"{speed / (1024 * 1024):.2f} MB/s"

        # Format current and total
        cur_str = format_size(current)
        tot_str = format_size(total)

        # Progress percentage
        percentage = (current / total) * 100

        # ETA
        eta = (total - current) / speed if speed > 0 else 0
        if eta < 60:
            eta_str = f"{eta:.0f} sec"
        elif eta < 3600:
            eta_str = f"{eta / 60:.1f} min"
        else:
            eta_str = f"{eta / 3600:.1f} hr"

        # Simple progress bar with 🟩 and ⬜ (optional, but simple)
        filled = int(10 * current // total)
        bar = '🟩' * filled + '⬜' * (10 - filled)

        # Message text
        text = f'''<blockquote>`╭──⌯═════{status_text}══════⌯──╮
├📊 {bar}
├📈 Progress ➤ {percentage:.1f}%
├⚡ Speed ➤ {speed_str}
├📟 Proceed ➤ {cur_str}
├⏱️ ETA ➤ {eta_str}
╰─═══✨🦋𝐔𝐧𝐳𝐢𝐩 𝐁𝐨𝐭🦋✨═══─╯`</blockquote>'''

        cancel_button = InlineKeyboardMarkup([[
            InlineKeyboardButton("𝘊𝘢𝘯𝘤𝘦𝘭 𝘛𝘢𝘴𝘬", callback_data=f"cancel_{task_id}")
        ]])

        return text, cancel_button, False

    except Exception as e:
        print(f"Progress error: {e}")
        # Fallback: just show current size
        cur_str = format_size(current)
        text = f"📥 {status_text}: {cur_str}"
        cancel_button = InlineKeyboardMarkup([[
            InlineKeyboardButton("𝘊𝘢𝘯𝘤𝘦𝘭 𝘛𝘢𝘴𝘬", callback_data=f"cancel_{task_id}")
        ]])
        return text, cancel_button, False

async def unzip_handler(client: Client, message: Message):
    task_id = str(int(time.time() * 1000))

    reply = message.reply_to_message
    if not reply or not reply.document:
        return await message.reply_text("**Reply to a .zip file with `/unzip` or `/unzip password`**")

    file_name = reply.document.file_name or "archive.zip"
    if not file_name.lower().endswith(".zip"):
        return await message.reply_text("**Reply `/unzip` or `/unzip password` only .zip file**")

    parts = message.text.split(maxsplit=1)
    password = parts[1].strip() if len(parts) > 1 else None

    file_name = file_name.replace('_', ' ').replace('.zip', '').replace('.Zip', '')
    await message.reply_text(f"<blockquote><b>🗜️ Archive : {file_name}</b></blockquote>")
    status = await message.reply_text("📥 **Downloading archive...**")
    temp_dir = tempfile.mkdtemp(prefix="unzip_")
    zip_path = os.path.join(temp_dir, f"{file_name}.zip")

    # Download with progress
    try:
        start_time = time.time()
        last_update = 0

        async def progress_callback(current, total):
            nonlocal last_update
            try:
                # Throttle updates to avoid flooding (update every 1 second)
                now = time.time()
                if now - last_update < 1.0:
                    return
                last_update = now

                if task_id in cancelled_tasks:
                    raise Exception("Task cancelled by user")

                text, cancel_btn, cancelled = progress_simple(current, total, start_time, "𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐢𝐧𝐠", task_id)
                if cancelled:
                    raise Exception("Task cancelled by user")

                if text:
                    try:
                        await status.edit(text, reply_markup=cancel_btn)
                    except MessageNotModified:
                        pass
            except Exception as e:
                if "cancelled" in str(e).lower():
                    raise Exception("Task cancelled by user")

        await client.download_media(reply.document.file_id, zip_path, progress=progress_callback)

        if task_id in cancelled_tasks:
            raise Exception("Task cancelled by user")

        await status.edit("✅ **Download completed!**")
        await asyncio.sleep(1)

    except Exception as e:
        if "cancelled" in str(e).lower():
            await status.edit("❌ **Task cancelled by user!**")
        else:
            await status.edit(f"__**Failed Reason in Download:**__\n<blockquote><b>{e}</b></blockquote>")
        shutil.rmtree(temp_dir, ignore_errors=True)
        cancelled_tasks.discard(task_id)
        return

    # Extraction (similar simple progress)
    await status.edit("🗜️ **Extracting archive...**")
    extract_dir = os.path.join(temp_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path) as zf:
            # Check password
            first_file = zf.infolist()[0]
            try:
                with zf.open(first_file, pwd=None) as f:
                    f.read(1)
                needs_password = False
            except RuntimeError:
                needs_password = True

            if needs_password and not password:
                await status.edit("🔒 **This archive is password-protected.**\n**🖊️ Reply to the ZIP with:** `/unzip password`")
                shutil.rmtree(temp_dir, ignore_errors=True)
                cancelled_tasks.discard(task_id)
                return

            pwd_bytes = password.encode("utf-8") if password else None

            total_files = len(zf.infolist())
            extracted = 0
            last_extract_update = 0

            for file_info in zf.infolist():
                if task_id in cancelled_tasks:
                    raise Exception("Task cancelled by user")

                zf.extract(file_info, path=extract_dir, pwd=pwd_bytes)
                extracted += 1

                now = time.time()
                if now - last_extract_update >= 1.0 or extracted == total_files:
                    last_extract_update = now
                    percentage = (extracted / total_files) * 100
                    filled = int(10 * extracted // total_files)
                    bar = '🟩' * filled + '⬜' * (10 - filled)
                    text = f'''<blockquote>`╭──⌯═════𝐄𝐱𝐭𝐫𝐚𝐜𝐭𝐢𝐧𝐠══════⌯──╮
├📊 {bar}
├📈 Progress ➤ {percentage:.1f}%
├📟 Files ➤ {extracted}/{total_files}
╰─═══✨🦋𝐔𝐧𝐳𝐢𝐩 𝐁𝐨𝐭🦋✨═══─╯`</blockquote>'''
                    cancel_btn = InlineKeyboardMarkup([[
                        InlineKeyboardButton("𝘊𝘢𝘯𝘤𝘦𝘭 𝘛𝘢𝘴𝘬", callback_data=f"cancel_{task_id}")
                    ]])
                    try:
                        await status.edit(text, reply_markup=cancel_btn)
                    except MessageNotModified:
                        pass

    except Exception as e:
        if "cancelled" in str(e).lower():
            await status.edit("❌ **Task cancelled by user!**")
        else:
            await status.edit(f"__**Failed Reason in Extraction:**__\n<blockquote><b>{e}</b></blockquote>")
        shutil.rmtree(temp_dir, ignore_errors=True)
        cancelled_tasks.discard(task_id)
        return

    # List files and upload (same as before, but ensure cancel checks)
    entries = sorted(os.listdir(extract_dir))
    if not entries:
        await status.edit("__**Failed Reason:**__\n<blockquote><b>Empty .zip file</b></blockquote>")
        shutil.rmtree(temp_dir, ignore_errors=True)
        cancelled_tasks.discard(task_id)
        return

    list_lines = ["<blockquote><b>🔎 फ़ाइल/फ़ोल्डर सूची:</b></blockquote>"]
    for e in entries:
        e_path = os.path.join(extract_dir, e)
        if os.path.isdir(e_path):
            list_lines.append(f"📁 **{e}**")
        else:
            list_lines.append(f"📄 **{e}**")
    await status.edit("\n".join(list_lines))
    await asyncio.sleep(2)

    # Collect all files
    all_files = []
    root_files = [e for e in entries if os.path.isfile(os.path.join(extract_dir, e))]
    for fname in root_files:
        all_files.append({
            'path': os.path.join(extract_dir, fname),
            'caption': f"📄 **{fname}**\n<blockquote><b>🗜️ Archive : {file_name}</b></blockquote>",
        })

    top_dirs = [e for e in entries if os.path.isdir(os.path.join(extract_dir, e))]
    for d in top_dirs:
        folder_path = os.path.join(extract_dir, d)
        for root, _, files in os.walk(folder_path):
            rel_root = os.path.relpath(root, folder_path)
            for fname in files:
                abs_path = os.path.join(root, fname)
                rel_path_display = fname if rel_root == "." else os.path.join(rel_root, fname)
                all_files.append({
                    'path': abs_path,
                    'caption': f"📄 **{rel_path_display}**\n<blockquote><b>🗜️ Archive: {file_name}\n📁 Folder: {d}</b></blockquote>",
                })

    if not all_files:
        await message.reply_text("⚠️ **No files found to upload!**")
        shutil.rmtree(temp_dir, ignore_errors=True)
        cancelled_tasks.discard(task_id)
        return

    total_uploads = len(all_files)
    upload_status = await message.reply_text("📤 **Preparing to upload files...**")
    upload_start = time.time()

    for idx, file_info in enumerate(all_files, 1):
        if task_id in cancelled_tasks:
            await upload_status.edit("❌ **Task cancelled by user!**")
            break

        # Update progress
        percentage = (idx / total_uploads) * 100
        filled = int(10 * idx // total_uploads)
        bar = '🟩' * filled + '⬜' * (10 - filled)

        elapsed = time.time() - upload_start
        if idx > 1:
            avg = elapsed / (idx - 1)
            eta = avg * (total_uploads - idx + 1)
            eta_str = f"{eta:.0f} sec" if eta < 60 else f"{eta / 60:.1f} min" if eta < 3600 else f"{eta / 3600:.1f} hr"
        else:
            eta_str = "Calculating..."

        text = f'''<blockquote>`╭──⌯═════𝐔𝐩𝐥𝐨𝐚𝐝𝐢𝐧𝐠══════⌯──╮
├📊 {bar}
├📈 Progress ➤ {percentage:.1f}%
├📟 Files ➤ {idx}/{total_uploads}
├⏱️ ETA ➤ {eta_str}
├📁 Current ➤ {os.path.basename(file_info['path'])}
╰─═══✨🦋𝐔𝐧𝐳𝐢𝐩 𝐁𝐨𝐭🦋✨═══─╯`</blockquote>'''
        cancel_btn = InlineKeyboardMarkup([[
            InlineKeyboardButton("𝘊𝘢𝘯𝘤𝘦𝘭 𝘛𝘢𝘴𝘬", callback_data=f"cancel_{task_id}")
        ]])
        try:
            await upload_status.edit(text, reply_markup=cancel_btn)
        except MessageNotModified:
            pass

        await message.reply_document(file_info['path'], caption=file_info['caption'])
        await asyncio.sleep(1)

    if task_id not in cancelled_tasks:
        await upload_status.delete()
        if top_dirs:
            folder_list = "\n".join([f"📁 **{d}**" for d in top_dirs])
            await message.reply_text(f"<blockquote><b>**📑 Total Files: {total_uploads}**\n📂 Folders uploaded:</b>\n{folder_list}</blockquote>")
        await message.reply_text(f"**⋅ ─ UPLOADING ✩ COMPLETED ✩ ─ ⋅**")

    shutil.rmtree(temp_dir, ignore_errors=True)
    cancelled_tasks.discard(task_id)

async def cancel_unzip_callback(client: Client, callback_query):
    task_id = callback_query.data.split("_")[1]
    cancelled_tasks.add(task_id)
    await callback_query.answer("❌ Task cancelled by user!")
    await callback_query.message.edit("⚠️ **Task cancelled by user!**")

def register_unzip_handlers(bot):
    @bot.on_message(filters.command(["unzip"]))
    async def call_unzip_handler(client: Client, message: Message):
        await unzip_handler(client, message)

    @bot.on_callback_query(filters.regex(r"cancel_"))
    async def cancel_handler(client: Client, callback_query):
        await cancel_unzip_callback(client, callback_query)
