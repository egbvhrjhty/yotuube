import os
import random
import time
import json
import asyncio
import sys
import numpy as np

# 🛠️ MoviePy PIL Error Fix (100% Safe)
from PIL import Image
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

# ⏱️ RANDOM WAIT SYSTEM (0 से 25 मिनट रुकेगा)
wait_seconds = random.randint(0, 1500)
print(f"🤖 GitHub Server चालू! वीडियो रेंडर करने से पहले {wait_seconds // 60} मिनट का रैंडम इंतज़ार कर रहा है...")
time.sleep(wait_seconds)
print("▶️ इंतज़ार ख़त्म! अब वीडियो बनाने का काम शुरू...")

# ==========================================
import edge_tts
from gtts import gTTS
from moviepy.editor import ColorClip, AudioFileClip, TextClip, ImageClip, CompositeVideoClip, CompositeAudioClip
from moviepy.audio.AudioClip import AudioClip

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from googleapiclient.errors import HttpError

OUTPUT_FOLDER = "./output"
TEMP_FOLDER = "./temp"
LOGO_PATH = "./logo.png"
JSON_FILE_PATH = "./questions.json"
TOKENS_FOLDER = "./tokens"  

os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)

HINDI_FONT = "./NirmalaB.ttf" 

# 🚀 नया फंक्शन: जो सवाल यूज़ होगा, वो डिलीट हो जाएगा
def get_quiz_data():
    with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
        questions_list = json.load(f)
        
    if len(questions_list) == 0:
        print("❌ सारे सवाल ख़त्म हो गए हैं! कृपया questions.json में नए सवाल डालें।")
        sys.exit(1)

    # रैंडम सवाल चुनो
    selected_quiz = random.choice(questions_list)
    
    # उस सवाल को लिस्ट से हटा दो (Delete)
    questions_list.remove(selected_quiz)
    
    # बची हुई लिस्ट को वापस JSON में सेव कर दो
    with open(JSON_FILE_PATH, 'w', encoding='utf-8') as f:
        json.dump(questions_list, f, ensure_ascii=False, indent=4)
        
    print(f"🗑️ सवाल इस्तेमाल हो गया, अब इसे JSON से डिलीट कर दिया गया है। बचे हुए सवाल: {len(questions_list)}")
    return selected_quiz

async def generate_voice(text, filename):
    filepath = os.path.join(TEMP_FOLDER, filename)
    try:
        communicate = edge_tts.Communicate(text, "hi-IN-MadhurNeural", rate="+5%", volume="+50%")
        await communicate.save(filepath)
        return filepath
    except:
        tts = gTTS(text=text, lang='hi', slow=False)
        tts.save(filepath)
        return filepath

def make_pop_sfx():
    return AudioClip(lambda t: np.vstack([np.sin(2 * np.pi * 400 * t) * np.exp(-30 * t)]*2).T, duration=0.2, fps=44100).volumex(1.5)

def make_tick_sfx(duration=5.0):
    def sound_wave(t):
        t_mod = t % 1.0
        click = np.sin(2 * np.pi * 1000 * t_mod) * np.exp(-60 * t_mod)
        return np.where(t_mod < 0.1, click, 0)
    return AudioClip(lambda t: np.vstack([sound_wave(t), sound_wave(t)]).T, duration=duration, fps=44100).volumex(3.0)

def make_ding_sfx():
    return AudioClip(lambda t: np.vstack([np.sin(2 * np.pi * 800 * t) * np.exp(-5 * t)]*2).T, duration=1.5, fps=44100).volumex(1.5)

def upload_to_youtube(video_file, quiz_question):
    print("🌐 YouTube सर्वर से कनेक्ट हो रहा है...")
    
    if not os.path.exists(TOKENS_FOLDER):
        print("❌ Tokens फोल्डर ही नहीं मिला!")
        return False

    token_files = sorted([os.path.join(TOKENS_FOLDER, f) for f in os.listdir(TOKENS_FOLDER) if f.endswith('.json')])
    
    if not token_files:
        print("❌ कोई Token नहीं मिला! GitHub Secrets चेक करें।")
        return False

    yt_title = f"{quiz_question} 🤔 | GK Quiz In Hindi | #shorts #gk"
    yt_desc = "क्या आपको इसका सही जवाब पता था? कमेंट करके ज़रूर बताएं! 👇\n#gkquiz #hindigk #shorts #education"
    yt_tags = ["gk shorts", "hindi gk", "quiz", "education shorts"]

    request_body = {
        "snippet": {"title": yt_title, "description": yt_desc, "tags": yt_tags, "categoryId": "27"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }

    uploaded = False

    for token_path in token_files:
        try:
            print(f"🔑 Try कर रहा है: {os.path.basename(token_path)} ...")
            creds = Credentials.from_authorized_user_file(token_path, ["https://www.googleapis.com/auth/youtube.upload"])
            
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_path, 'w') as token_file:
                    token_file.write(creds.to_json())
                    
            youtube = build('youtube', 'v3', credentials=creds)
            media = MediaFileUpload(video_file, chunksize=-1, resumable=True)
            
            request = youtube.videos().insert(part="snippet,status", body=request_body, media_body=media)
            response = request.execute()
            
            print(f"✅ तहलका! वीडियो LIVE हो गया: https://youtu.be/{response['id']}")
            uploaded = True
            break
            
        except HttpError as e:
            if 'quotaExceeded' in str(e):
                print(f"⚠️ {os.path.basename(token_path)} की लिमिट ख़त्म! अगले टोकन पर जा रहा है...")
                continue
            else:
                print(f"❌ अपलोड एरर: {e}")
                break

    if not uploaded:
        print("❌ सारे टोकन की लिमिट ख़त्म हो गई है!")
        return False
    return True

async def make_one_video():
    quiz = get_quiz_data()
    print(f"\n✨ सवाल चुना गया: {quiz['question']}")
    
    q_path = await generate_voice(f"प्रश्न है। {quiz['question']}", "q.mp3")
    a_path = await generate_voice(quiz['speak_a'], "a.mp3")
    b_path = await generate_voice(quiz['speak_b'], "b.mp3")
    c_path = await generate_voice(quiz['speak_c'], "c.mp3")
    ans_path = await generate_voice(quiz['answer_text'], "ans.mp3")

    aud_q = AudioFileClip(q_path).volumex(1.5)
    aud_a = AudioFileClip(a_path).volumex(1.5)
    aud_b = AudioFileClip(b_path).volumex(1.5)
    aud_c = AudioFileClip(c_path).volumex(1.5)
    aud_ans = AudioFileClip(ans_path).volumex(1.5)

    t = 0.0
    s_q = t; t += aud_q.duration + 0.3
    s_a = t; t += aud_a.duration + 0.3
    s_b = t; t += aud_b.duration + 0.3
    s_c = t; t += aud_c.duration + 0.5
    timer_dur = 5.0
    s_timer = t; t += timer_dur
    s_ans = t; t += aud_ans.duration + 1.0
    total = t

    bg = ColorClip(size=(1080, 1920), color=(20, 20, 25), duration=total).set_fps(24)
    header = TextClip("🧠 QUIZ CHALLENGE ⏱️", fontsize=70, color='yellow', font='Arial-Bold').set_position(('center', 150)).set_duration(total)
    q_clip = TextClip(quiz['question'], fontsize=80, color='white', font=HINDI_FONT, method='caption', size=(900, None)).set_position(('center', 350)).set_start(s_q).set_duration(total - s_q)

    ox = 200
    opt_a = TextClip(quiz['opt_a'], fontsize=85, color='white', font=HINDI_FONT).set_position((ox, 750)).set_start(s_a).set_duration(total - s_a)
    opt_b = TextClip(quiz['opt_b'], fontsize=85, color='white', font=HINDI_FONT).set_position((ox, 900)).set_start(s_b).set_duration(total - s_b)
    opt_c = TextClip(quiz['opt_c'], fontsize=85, color='white', font=HINDI_FONT).set_position((ox, 1050)).set_start(s_c).set_duration(total - s_c)

    pop_a = make_pop_sfx().set_start(s_a)
    pop_b = make_pop_sfx().set_start(s_b)
    pop_c = make_pop_sfx().set_start(s_c)

    timer_vis = []
    colors = {5:'lime', 4:'yellow', 3:'orange', 2:'#FF4500', 1:'red'}
    for i in range(int(timer_dur)):
        tl = int(timer_dur) - i
        ts = s_timer + i
        c = TextClip("⭕", fontsize=350, color='white', font='Arial').set_position(('center', 1300)).set_start(ts).set_duration(1.0)
        n = TextClip(f"{tl}", fontsize=180, color=colors.get(tl,'white'), font=HINDI_FONT).set_position(('center', 1400)).set_start(ts).set_duration(1.0)
        timer_vis.extend([c, n])

    tick = make_tick_sfx(timer_dur).set_start(s_timer)

    ans_clip = None
    if quiz['correct_key'] == 'A': ans_clip = TextClip(quiz['opt_a'], fontsize=85, color='#00FF00', font=HINDI_FONT).set_position((ox, 750)).set_start(s_ans).set_duration(total - s_ans)
    elif quiz['correct_key'] == 'B': ans_clip = TextClip(quiz['opt_b'], fontsize=85, color='#00FF00', font=HINDI_FONT).set_position((ox, 900)).set_start(s_ans).set_duration(total - s_ans)
    elif quiz['correct_key'] == 'C': ans_clip = TextClip(quiz['opt_c'], fontsize=85, color='#00FF00', font=HINDI_FONT).set_position((ox, 1050)).set_start(s_ans).set_duration(total - s_ans)

    ding = make_ding_sfx().set_start(s_ans)
    logo = ImageClip(LOGO_PATH).resize(width=150).set_position((880, 50)).set_duration(total) if os.path.exists(LOGO_PATH) else None

    final_audio = CompositeAudioClip([aud_q.set_start(s_q), aud_a.set_start(s_a), pop_a, aud_b.set_start(s_b), pop_b, aud_c.set_start(s_c), pop_c, tick, ding, aud_ans.set_start(s_ans)])
    visuals = [bg, header, q_clip, opt_a, opt_b, opt_c] + timer_vis
    if ans_clip: visuals.append(ans_clip)
    if logo: visuals.append(logo)

    video = CompositeVideoClip(visuals).set_audio(final_audio)
    out_path = os.path.join(OUTPUT_FOLDER, "short.mp4")
    
    print("🎬 वीडियो रेंडर हो रही है...")
    video.write_videofile(out_path, codec="libx264", audio_codec="aac", fps=24, logger=None)
    
    for c in visuals: c.close()
    video.close(); final_audio.close()
    
    success = upload_to_youtube(out_path, quiz['question'])
    
    # Cleanup
    os.remove(out_path)
    for f in os.listdir(TEMP_FOLDER): os.remove(os.path.join(TEMP_FOLDER, f))
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(make_one_video())
