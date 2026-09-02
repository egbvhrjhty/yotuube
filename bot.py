import os
import random
import time
import json
import asyncio
import sys
import numpy as np
import textwrap
import urllib.request
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

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

# ================== CONFIGURATION ==================
OUTPUT_FOLDER = "./output"
TEMP_FOLDER = "./temp"
JSON_FILE_PATH = "./questions.json"
TOKENS_FOLDER = "./tokens"  
HINDI_FONT = "./NirmalaB.ttf"
BGM_FILE = "./bgm.mp3"
THUMBNAIL_FILE = "./output/thumbnail.jpg"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

# 🧪 TEST MODE: सिर्फ 4 सवाल
TOTAL_QUESTIONS = 4 

# ================== AUTO DOWNLOAD BGM ==================
if not os.path.exists(BGM_FILE):
    print("📥 BGM नहीं मिला, ऑटोमैटिक कूल म्यूजिक डाउनलोड कर रहा हूँ...")
    try:
        urllib.request.urlretrieve("https://cdn.pixabay.com/download/audio/2022/05/16/audio_91b2c451db.mp3", BGM_FILE)
        print("✅ BGM डाउनलोड हो गया!")
    except:
        print("⚠️ BGM डाउनलोड फेल हो गया।")

# ================== PERFECT HINDI TEXT GENERATOR (PIL) ==================
def get_hindi_image_clip(text, filename, font_size, color_rgb, width_limit=50):
    font = ImageFont.truetype(HINDI_FONT, font_size)
    lines = textwrap.wrap(text, width=width_limit) 
    
    dummy_img = Image.new('RGBA', (1, 1))
    draw = ImageDraw.Draw(dummy_img)
    
    y_text = 0; max_w = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        max_w = max(max_w, bbox[2] - bbox[0])
        y_text += (bbox[3] - bbox[1]) + 15
        
    img = Image.new('RGBA', (max_w + 20, y_text + 20), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    y_text = 10
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        # Align Center
        draw.text(((max_w - w) / 2 + 10, y_text), line, font=font, fill=color_rgb)
        y_text += (bbox[3] - bbox[1]) + 15
        
    filepath = os.path.join(TEMP_FOLDER, filename)
    img.save(filepath)
    return ImageClip(filepath)

# ================== DATA LOGIC ==================
def get_questions():
    with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
        questions_list = json.load(f)
        
    if len(questions_list) < TOTAL_QUESTIONS:
        print(f"❌ सवाल कम हैं! कम से कम {TOTAL_QUESTIONS} चाहिए।")
        sys.exit(1)

    selected_quizzes = questions_list[:TOTAL_QUESTIONS]
    remaining_quizzes = questions_list[TOTAL_QUESTIONS:]
    
    with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(remaining_quizzes, f, ensure_ascii=False, indent=4)
        
    return selected_quizzes

# ================== DUAL VOICE TTS ==================
async def generate_voice(text, filename, voice_type="male"):
    filepath = os.path.join(TEMP_FOLDER, filename)
    voice_name = "hi-IN-MadhurNeural" if voice_type == "male" else "hi-IN-SwaraNeural"
    try:
        communicate = edge_tts.Communicate(text, voice_name, rate="+0%", volume="+50%")
        await communicate.save(filepath)
        return filepath
    except:
        tts = gTTS(text=text, lang='hi', slow=False)
        tts.save(filepath)
        return filepath

# ================== SYNTHETIC SFX ==================
def make_tick_sfx(duration=5.0):
    def sound_wave(t):
        t_mod = t % 1.0
        click = np.sin(2 * np.pi * 1000 * t_mod) * np.exp(-60 * t_mod)
        return np.where(t_mod < 0.1, click, 0)
    return AudioClip(lambda t: np.vstack([sound_wave(t), sound_wave(t)]).T, duration=duration, fps=44100).volumex(1.5)

# ================== AUTO THUMBNAIL ==================
def create_thumbnail(first_question_text):
    print("🎨 Thumbnail बना रहा है...")
    img = Image.new('RGB', (1920, 1080), color = (20, 20, 40))
    d = ImageDraw.Draw(img)
    try: font_large = ImageFont.truetype(HINDI_FONT, 120); font_small = ImageFont.truetype(HINDI_FONT, 80)
    except: font_large = ImageFont.load_default(); font_small = font_large

    d.text((100, 150), f"🔥 {TOTAL_QUESTIONS} MEGA GK QUIZ 🔥", fill=(255, 200, 0), font=font_large)
    d.text((100, 400), first_question_text[:50] + "...", fill=(255, 255, 255), font=font_small)
    d.text((100, 800), "99% लोग फेल! 🤔", fill=(255, 50, 50), font=font_large)
    img.save(THUMBNAIL_FILE)
    return THUMBNAIL_FILE

# ================== VIDEO GENERATOR LOOP ==================
async def make_video_chunk(quiz, index):
    print(f"\n🎬 रेंडर हो रहा है सवाल {index}/{TOTAL_QUESTIONS}")
    
    if index <= (TOTAL_QUESTIONS * 0.3): bg_color = (15, 32, 39) 
    elif index <= (TOTAL_QUESTIONS * 0.7): bg_color = (66, 39, 9) 
    else: bg_color = (60, 10, 10) 

    text_a = quiz['opt_a'].replace("A)", "").strip()
    text_b = quiz['opt_b'].replace("B)", "").strip()
    text_c = quiz['opt_c'].replace("C)", "").strip()
    correct_key = quiz['correct_key']
    correct_ans_text = text_a if correct_key == 'A' else text_b if correct_key == 'B' else text_c

    is_last = (index == TOTAL_QUESTIONS)
    
    # 🗣️ Voice Logic: Boy reads Q+Opts, Girl reads Ans
    speech_q_opts = f"{quiz['question']}... ऑप्शन ए, {text_a}... ऑप्शन बी, {text_b}... ऑप्शन सी, {text_c}"
    speech_ans = "इसका जवाब आप कमेंट्स में बताइए!" if is_last else f"सही जवाब है, {correct_ans_text}"

    q_opts_path = await generate_voice(speech_q_opts, f"q_{index}.mp3", "male")
    ans_path = await generate_voice(speech_ans, f"a_{index}.mp3", "female")

    aud_q_opts = AudioFileClip(q_opts_path).volumex(1.5)
    aud_ans = AudioFileClip(ans_path).volumex(1.5)

    # Timing
    t = 0.0
    s_q_opts = t; t += aud_q_opts.duration + 0.5
    timer_dur = 5.0
    s_timer = t; t += timer_dur
    s_ans = t; t += aud_ans.duration + 1.5
    total = t

    bg = ColorClip(size=(1920, 1080), color=bg_color).set_duration(total).set_fps(24)
    
    # Top Texts
    lvl_text = "LEVEL: EASY" if index <= (TOTAL_QUESTIONS * 0.3) else "LEVEL: MEDIUM" if index <= (TOTAL_QUESTIONS * 0.7) else "LEVEL: HARD 🔥"
    lvl_clip = TextClip(lvl_text, fontsize=45, color='yellow', font='Arial-Bold').set_position((50, 40)).set_start(0).set_duration(total)
    prog_clip = TextClip(f"Q: {index}/{TOTAL_QUESTIONS}", fontsize=45, color='white', font='Arial-Bold').set_position((1700, 40)).set_start(0).set_duration(total)

    # Perfect Hindi Texts
    q_clip = get_hindi_image_clip(quiz['question'], f"img_q_{index}.png", 85, (255,255,255)).set_position(('center', 150)).set_start(0).set_duration(total)
    
    y_opts = 450
    opt_a_clip = get_hindi_image_clip(f"A) {text_a}", f"img_a_{index}.png", 75, (255,255,255), 60).set_position((250, y_opts)).set_start(0).set_duration(total)
    opt_b_clip = get_hindi_image_clip(f"B) {text_b}", f"img_b_{index}.png", 75, (255,255,255), 60).set_position((250, y_opts+130)).set_start(0).set_duration(total)
    opt_c_clip = get_hindi_image_clip(f"C) {text_c}", f"img_c_{index}.png", 75, (255,255,255), 60).set_position((250, y_opts+260)).set_start(0).set_duration(total)

    tick = make_tick_sfx(timer_dur).set_start(s_timer)

    # Timer Visual
    timer_vis = []
    for i in range(int(timer_dur)):
        tl = int(timer_dur) - i
        ts = s_timer + i
        n = TextClip(f"{tl}", fontsize=130, color='red' if tl<=3 else 'yellow', font='Arial-Bold').set_position(('center', 800)).set_start(ts).set_duration(1.0)
        timer_vis.append(n)

    # ✅ Animated Answer Highlight (Green Bounce)
    ans_clip = None
    if not is_last:
        y_ans = y_opts if correct_key == 'A' else (y_opts+130) if correct_key == 'B' else (y_opts+260)
        ans_text = f"{correct_key}) " + (text_a if correct_key == 'A' else text_b if correct_key == 'B' else text_c)
        ans_clip = get_hindi_image_clip(ans_text, f"img_ans_{index}.png", 75, (0, 255, 0), 60)
        ans_clip = ans_clip.set_position((250, y_ans)).set_start(s_ans).set_duration(total - s_ans)
        ans_clip = ans_clip.resize(lambda t: min(1.15, 1 + t*1.5) if t < 0.1 else 1.15) # Pop Anim

    final_audio = CompositeAudioClip([aud_q_opts.set_start(s_q_opts), tick, aud_ans.set_start(s_ans)])
    visuals = [bg, lvl_clip, prog_clip, q_clip, opt_a_clip, opt_b_clip, opt_c_clip] + timer_vis
    
    if ans_clip: visuals.append(ans_clip)
    
    if is_last:
        suspense_clip = get_hindi_image_clip("👇 कमेंट में अपना जवाब दें! 👇", f"img_susp_{index}.png", 85, (0, 255, 255))
        suspense_clip = suspense_clip.set_position(('center', 800)).set_start(s_ans).set_duration(total - s_ans)
        visuals.append(suspense_clip)

    video = CompositeVideoClip(visuals).set_audio(final_audio)
    out_path = os.path.join(TEMP_FOLDER, f"chunk_{index}.mp4")
    video.write_videofile(out_path, codec="libx264", audio_codec="aac", fps=24, preset="ultrafast", logger=None)
    
    for c in visuals: c.close()
    video.close(); final_audio.close(); aud_q_opts.close(); aud_ans.close()
    
    return out_path

# ================== MERGE & BGM ==================
def merge_videos_and_add_bgm(chunk_files):
    print("🔄 वीडियो जोड़े जा रहे हैं...")
    concat_txt = os.path.join(TEMP_FOLDER, "files.txt")
    with open(concat_txt, "w") as f:
        for chunk in chunk_files: f.write(f"file '{os.path.basename(chunk)}'\n")
    
    merged_no_bgm = os.path.join(OUTPUT_FOLDER, "merged_no_bgm.mp4")
    final_output = os.path.join(OUTPUT_FOLDER, "FINAL_UPLOAD.mp4")
    
    os.system(f"ffmpeg -f concat -safe 0 -i {concat_txt} -c copy {merged_no_bgm} -y")
    
    if os.path.exists(BGM_FILE):
        print("🎵 बैकग्राउंड म्यूजिक (BGM) लगाया जा रहा है (High Volume)...")
        # 🔊 Volume increased to 0.25 (25%)
        cmd = f'ffmpeg -i {merged_no_bgm} -stream_loop -1 -i {BGM_FILE} -filter_complex "[1:a]volume=0.25[bgm];[0:a][bgm]amix=inputs=2:duration=first[aout]" -map 0:v -map "[aout]" -c:v copy -c:a aac {final_output} -y'
        os.system(cmd)
    else:
        os.rename(merged_no_bgm, final_output)
        
    return final_output

# ================== YOUTUBE UPLOAD ==================
def upload_to_youtube(video_file, thumbnail_file):
    print("🌐 YouTube पर अपलोड हो रहा है...")
    token_files = sorted([os.path.join(TOKENS_FOLDER, f) for f in os.listdir(TOKENS_FOLDER) if f.endswith('.json')])
    
    yt_title = "4 Most Important GK Questions in Hindi 🔥 | Test Mode"
    yt_desc = "Testing our Final Auto Video Setup!\n\n#gk #gkinhindi #test"
    
    request_body = {
        "snippet": {"title": yt_title, "description": yt_desc, "tags": ["gk", "hindi"], "categoryId": "27"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }

    for token_path in token_files:
        try:
            creds = Credentials.from_authorized_user_file(token_path, ["https://www.googleapis.com/auth/youtube.upload"])
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_path, 'w') as tf: tf.write(creds.to_json())
                    
            youtube = build('youtube', 'v3', credentials=creds)
            media = MediaFileUpload(video_file, chunksize=-1, resumable=True)
            request = youtube.videos().insert(part="snippet,status", body=request_body, media_body=media)
            response = request.execute()
            video_id = response['id']
            print(f"✅ तहलका! वीडियो LIVE हो गया: https://youtu.be/{video_id}")
            
            youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumbnail_file)).execute()
            print("✅ थंबनेल सेट हो गया!")
            return True
        except Exception as e:
            print(f"❌ अपलोड एरर: {e}")
            continue
    return False

# ================== MAIN EXECUTION ==================
async def main():
    print("🤖 GitHub Server चालू! टेस्टिंग मोड...")
    time.sleep(2) 
    
    quizzes = get_questions()
    create_thumbnail(quizzes[0]['question'])
    
    chunk_files = []
    for i, quiz in enumerate(quizzes):
        chunk_path = await make_video_chunk(quiz, i+1)
        chunk_files.append(chunk_path)
        
    final_video = merge_videos_and_add_bgm(chunk_files)
    upload_to_youtube(final_video, THUMBNAIL_FILE)

if __name__ == "__main__":
    asyncio.run(main())
