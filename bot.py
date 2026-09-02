import os
import random
import time
import json
import asyncio
import sys
import numpy as np
import textwrap
import urllib.request
import urllib.parse
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS

# 🛠️ MoviePy PIL Deprecation Fix
try:
    resample_filter = Image.Resampling.LANCZOS
except AttributeError:
    resample_filter = Image.ANTIALIAS
Image.ANTIALIAS = resample_filter

import edge_tts
from moviepy.editor import AudioFileClip, TextClip, ColorClip, ImageClip, CompositeVideoClip, CompositeAudioClip
from moviepy.audio.AudioClip import AudioClip

# ================== CONFIGURATION ==================
OUTPUT_FOLDER = "./output"
TEMP_FOLDER = "./temp"
JSON_FILE_PATH = "./questions.json"
HINDI_FONT = "./NirmalaB.ttf"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

TOTAL_QUESTIONS = 4 # Test Mode

# ================== DYNAMIC IMAGE FETCHER ==================
def fetch_related_image(keyword, index):
    print(f"🔍 '{keyword}' के लिए फोटो ढूँढ रहा हूँ...")
    img_path = os.path.join(TEMP_FOLDER, f"img_{index}.jpg")
    
    try:
        # Wikipedia API से फोटो निकालना
        encoded_kw = urllib.parse.quote(keyword)
        url = f"https://hi.wikipedia.org/w/api.php?action=query&prop=pageimages&titles={encoded_kw}&format=json&pithumbsize=600"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            pages = data['query']['pages']
            for page_id in pages:
                if 'thumbnail' in pages[page_id]:
                    img_url = pages[page_id]['thumbnail']['source']
                    urllib.request.urlretrieve(img_url, img_path)
                    print("✅ फोटो मिल गई!")
                    return img_path
    except Exception as e:
        print(f"⚠️ फोटो नहीं मिली: {e}")
        
    # अगर फोटो न मिले तो एक सफ़ेद Dummy Image बना दो
    img = Image.new('RGB', (600, 600), color=(240, 240, 240))
    d = ImageDraw.Draw(img)
    try: font = ImageFont.truetype(HINDI_FONT, 150)
    except: font = ImageFont.load_default()
    d.text((250, 200), "❓", fill=(100, 100, 100), font=font)
    img.save(img_path)
    return img_path

# ================== PERFECT HINDI TEXT GENERATOR ==================
def get_hindi_image_clip(text, filename, font_size, color_rgb, width_limit=50):
    font = ImageFont.truetype(HINDI_FONT, font_size)
    lines = textwrap.wrap(text, width=width_limit) 
    
    dummy_img = Image.new('RGBA', (1, 1))
    draw = ImageDraw.Draw(dummy_img)
    
    max_w = 0; y_text = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        max_w = max(max_w, bbox[2] - bbox[0])
        y_text += (bbox[3] - bbox[1]) + 15
        
    img = Image.new('RGBA', (max_w + 20, y_text + 20), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    y_text = 10
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        draw.text((10, y_text), line, font=font, fill=color_rgb) # Left Align
        y_text += (bbox[3] - bbox[1]) + 15
        
    filepath = os.path.join(TEMP_FOLDER, filename)
    img.save(filepath)
    return ImageClip(filepath)

def create_bg_with_border():
    bg_path = os.path.join(TEMP_FOLDER, "bg_border.jpg")
    img = Image.new('RGB', (1920, 1080), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([15, 15, 1905, 1065], outline=(0, 100, 0), width=10) # Green Border
    img.save(bg_path)
    return bg_path

# ================== AUDIO GENERATOR ==================
async def generate_voice(text, filename, voice_type="male"):
    filepath = os.path.join(TEMP_FOLDER, filename)
    voice_name = "hi-IN-MadhurNeural" if voice_type == "male" else "hi-IN-SwaraNeural"
    try:
        communicate = edge_tts.Communicate(text, voice_name, rate="+0%", volume="+50%")
        await communicate.save(filepath)
    except:
        tts = gTTS(text=text, lang='hi', slow=False)
        tts.save(filepath)
    return filepath

# ================== VIDEO CHUNK LOGIC ==================
async def make_video_chunk(quiz, index):
    print(f"\n🎬 रेंडर हो रहा है सवाल {index}/{TOTAL_QUESTIONS}")
    
    text_a = quiz['opt_a'].replace("A)", "").strip()
    text_b = quiz['opt_b'].replace("B)", "").strip()
    text_c = quiz['opt_c'].replace("C)", "").strip()
    correct_key = quiz['correct_key']
    ans_text = text_a if correct_key == 'A' else text_b if correct_key == 'B' else text_c

    # 1. Generate Separate Audios (For Sync)
    q_aud = AudioFileClip(await generate_voice(f"{index}. {quiz['question']}", f"q_{index}.mp3", "male"))
    a_aud = AudioFileClip(await generate_voice(f"ए, {text_a}", f"a_{index}.mp3", "male"))
    b_aud = AudioFileClip(await generate_voice(f"बी, {text_b}", f"b_{index}.mp3", "male"))
    c_aud = AudioFileClip(await generate_voice(f"सी, {text_c}", f"c_{index}.mp3", "male"))
    ans_aud = AudioFileClip(await generate_voice(f"सही जवाब है, {ans_text}", f"ans_{index}.mp3", "female"))

    # 2. Timing Logic (Syncing)
    t = 0.0
    s_q = t; t += q_aud.duration + 0.3
    s_a = t; t += a_aud.duration + 0.3
    s_b = t; t += b_aud.duration + 0.3
    s_c = t; t += c_aud.duration + 0.5
    s_timer = t; timer_dur = 5.0; t += timer_dur
    s_ans = t; t += ans_aud.duration + 1.5
    total_time = t

    # 3. Visuals Setup
    bg_path = create_bg_with_border()
    bg = ImageClip(bg_path).set_duration(total_time).set_fps(24)

    # 🖼️ Auto Image
    img_path = fetch_related_image(ans_text, index)
    side_img = ImageClip(img_path).resize(width=700).set_position((1100, 'center')).set_start(s_q).set_duration(total_time - s_q)

    # 🔠 Question (Blue)
    q_clip = get_hindi_image_clip(f"{index}. {quiz['question']}", f"img_q_{index}.png", 90, (0, 0, 200), 70)
    q_clip = q_clip.set_position((50, 60)).set_start(s_q).set_duration(total_time - s_q)

    # 🔠 Options (Black) - Pop up exactly when voice speaks
    y_opts = 350
    opt_a_clip = get_hindi_image_clip(f"A. {text_a}", f"img_oa_{index}.png", 80, (0, 0, 0)).set_position((100, y_opts)).set_start(s_a).set_duration(total_time - s_a)
    opt_b_clip = get_hindi_image_clip(f"B. {text_b}", f"img_ob_{index}.png", 80, (0, 0, 0)).set_position((100, y_opts+150)).set_start(s_b).set_duration(total_time - s_b)
    opt_c_clip = get_hindi_image_clip(f"C. {text_c}", f"img_oc_{index}.png", 80, (0, 0, 0)).set_position((100, y_opts+300)).set_start(s_c).set_duration(total_time - s_c)

    # ⏱️ Timer (Center)
    timer_vis = []
    for i in range(int(timer_dur)):
        tl = int(timer_dur) - i
        ts = s_timer + i
        n = TextClip(f"0{tl}", fontsize=150, color='red', font='Arial-Bold').set_position((800, 500)).set_start(ts).set_duration(1.0)
        timer_vis.append(n)

    # ✅ Highlight Answer (Green & Bold)
    ans_color = (0, 150, 0)
    y_ans = y_opts if correct_key == 'A' else (y_opts+150) if correct_key == 'B' else (y_opts+300)
    ans_clip = get_hindi_image_clip(f"{correct_key}. {ans_text}", f"img_ans_{index}.png", 85, ans_color)
    ans_clip = ans_clip.set_position((100, y_ans)).set_start(s_ans).set_duration(total_time - s_ans)
    ans_clip = ans_clip.resize(lambda t: min(1.1, 1 + t*2) if t < 0.1 else 1.1) # Pop Animation

    # 🎬 Compile
    final_audio = CompositeAudioClip([
        q_aud.set_start(s_q), a_aud.set_start(s_a), b_aud.set_start(s_b), 
        c_aud.set_start(s_c), ans_aud.set_start(s_ans)
    ])
    
    visuals = [bg, q_clip, side_img, opt_a_clip, opt_b_clip, opt_c_clip] + timer_vis + [ans_clip]
    video = CompositeVideoClip(visuals).set_audio(final_audio)
    
    out_path = os.path.join(TEMP_FOLDER, f"chunk_{index}.mp4")
    video.write_videofile(out_path, codec="libx264", audio_codec="aac", fps=24, preset="ultrafast", logger=None)
    
    for c in visuals: c.close()
    video.close(); final_audio.close()
    return out_path

# ================== MERGE LOGIC ==================
def merge_videos(chunk_files):
    print("🔄 वीडियो जोड़े जा रहे हैं...")
    concat_txt = os.path.join(TEMP_FOLDER, "files.txt")
    with open(concat_txt, "w") as f:
        for chunk in chunk_files: f.write(f"file '{os.path.basename(chunk)}'\n")
    
    final_output = os.path.join(OUTPUT_FOLDER, "FINAL_UPLOAD.mp4")
    os.system(f"ffmpeg -f concat -safe 0 -i {concat_txt} -c copy {final_output} -y")
    return final_output

async def main():
    print("🤖 GitHub Server चालू! (टेस्टिंग मोड - No YouTube Upload)")
    with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
        quizzes = json.load(f)[:TOTAL_QUESTIONS]
        
    chunk_files = []
    for i, quiz in enumerate(quizzes):
        chunk_files.append(await make_video_chunk(quiz, i+1))
        
    merge_videos(chunk_files)
    print("🎉 वीडियो तैयार है! गिटहब आर्टिफैक्ट में चेक करें।")

if __name__ == "__main__":
    asyncio.run(main())
