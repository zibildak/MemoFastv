import asyncio
import os
import re
import threading
import json
import sys
import time
import traceback
from pathlib import Path

import sounddevice as sd
from google import genai
from google.genai import types
from ui import JarvisUI
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def kill_other_agent_instances():
    """Çakışmaları önlemek için eski asistan sürecini PID dosyasından okuyup öldür"""
    import os
    import sys
    import subprocess
    
    pid_file = Path(get_base_dir()) / "agent.pid"
    current_pid = os.getpid()
    
    # 1. Eski PID dosyasını oku ve süreci öldür
    if pid_file.exists():
        try:
            old_pid = int(pid_file.read_text(encoding="utf-8").strip())
            if old_pid != current_pid:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/PID", str(old_pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    import signal
                    os.kill(old_pid, signal.SIGKILL)
                print(f"[JARVIS] Eski asistan süreci (PID {old_pid}) öldürüldü.")
        except Exception as e:
            print(f"[JARVIS] Eski süreç öldürülemedi veya zaten kapalı: {e}")
            
    # 2. Yeni PID'yi dosyaya yaz
    try:
        pid_file.write_text(str(current_pid), encoding="utf-8")
    except Exception as e:
        print(f"[JARVIS] PID dosyası yazılamadı: {e}")


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

def _get_api_key() -> str:
    try:
        appdata = os.getenv("APPDATA")
        if appdata:
            settings_path = os.path.join(appdata, "MemoFast", "settings.json")
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    key = json.load(f).get("gemini_api_key", "").strip()
                    if key:
                        # Anahtar şifreli olabilir (ana uygulama Fernet ile saklıyor)
                        try:
                            sys.path.insert(0, str(BASE_DIR.parent))
                            from crypto_manager import decrypt_value
                            key = decrypt_value(key)
                        except Exception:
                            pass
                        return key
    except Exception as e:
        print(f"[JARVIS] Failed to read MemoFast settings API key: {e}")

    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are MEMO, the official AI assistant of MemoFast. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

TOOL_DECLARATIONS = [
    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Jarvis. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "control_memofast",
        "description": (
            "Controls the MemoFast GUI application. Use this to perform actions inside MemoFast. "
            "You can switch pages, read the current state/data of the application, select games, call internal methods, or click buttons. "
            "Always specify the target action and any required arguments."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "The action type to perform: 'switch_page' | 'get_state' | 'select_game' | 'call_method'"
                },
                "page_index": {
                    "type": "INTEGER",
                    "description": "The index of the page to switch to (0=Library, 1=Auto Translate, 2=Optimizer, 4=Update, 5=Settings, 7=Trainer, 8=Puzzle, 9=OCR, 11=Community, 12=Free Games, 13=RPG Maker)"
                },
                "game_name": {
                    "type": "STRING",
                    "description": "The name of the game to select (required for 'select_game' action)"
                },
                "method_name": {
                    "type": "STRING",
                    "description": "The name of the method to call on MainWindow (e.g. 'install_selected_game' to start translation, 'scan_games' to scan, 'fetch_free_games' to check free campaigns)"
                },
                "method_args": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Optional string arguments for the method being called"
                }
            },
            "required": ["action"]
        }
    },
]

MEMOFAST_ALLOWED_TOOLS = {"control_memofast", "save_memory", "shutdown_jarvis"}
MEMOFAST_TOOL_DECLARATIONS = [
    tool for tool in TOOL_DECLARATIONS
    if tool.get("name") in MEMOFAST_ALLOWED_TOOLS
]

class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None

    def notify_state(self, state: str):
        def _notify():
            try:
                import requests
                requests.post("http://127.0.0.1:5003/state", json={"state": state}, timeout=1.0)
            except:
                pass
        threading.Thread(target=_notify, daemon=True).start()

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
            self.notify_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")
            self.notify_state("LISTENING")
        else:
            self.notify_state("MUTED")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        knowledge_str = ""
        knowledge_path = BASE_DIR / "core" / "knowledge.md"
        if knowledge_path.exists():
            try:
                knowledge_str = "\n\n" + knowledge_path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"[JARVIS] Failed to read knowledge.md: {e}")

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y - %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)
        if knowledge_str:
            parts.append(knowledge_str)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": MEMOFAST_TOOL_DECLARATIONS}, {"google_search": {}}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                     )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")
        self.notify_state("THINKING")

        if name not in MEMOFAST_ALLOWED_TOOLS:
            result = (
                "Bu MEMO modu sadece MemoFast'i yonetir."
            )
            self.ui.write_log(f"DENIED: {name}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
                self.notify_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": result}
            )

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        result = "Done."

        try:
            if name == "control_memofast":
                import requests
                try:
                    res = requests.post("http://127.0.0.1:5003/agent", json=args, timeout=4.0)
                    if res.status_code == 200:
                        rdata = res.json()
                        if args.get("action") == "get_state":
                            result = json.dumps(rdata.get("state", {}), ensure_ascii=False)
                        else:
                            result = rdata.get("message", "Done.")
                    else:
                        result = f"MemoFast köprüsünden hata döndü: HTTP {res.status_code}"
                except Exception as e:
                    result = f"MemoFast köprüsüne bağlanılamadı: {e}"

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")
                def _shutdown():
                    import time, os
                    time.sleep(1)
                    os._exit(0)
                threading.Thread(target=_shutdown, daemon=True).start()

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")
            self.notify_state("LISTENING")
        else:
            self.notify_state("MUTED")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        _first_mic_log = [True]

        def callback(indata, frames, time_info, status):
            try:
                with self._speaking_lock:
                    jarvis_speaking = self._is_speaking
                if not jarvis_speaking and not self.ui.muted:
                    data = indata.tobytes()
                    if _first_mic_log[0]:
                        print(f"[JARVIS] 🎤 İlk mikrofon verisi gönderiliyor ({len(data)} bytes)")
                        _first_mic_log[0] = False
                    loop.call_soon_threadsafe(
                        self.out_queue.put_nowait,
                        {"data": data, "mime_type": "audio/pcm"}
                    )
            except Exception as cb_err:
                print(f"[JARVIS] ⚠️ Mic callback error: {cb_err}")

        device_index = None
        try:
            saved_index = None
            saved_name = None
            appdata = os.getenv("APPDATA")
            if appdata:
                settings_path = os.path.join(appdata, "MemoFast", "settings.json")
                if os.path.exists(settings_path):
                    with open(settings_path, "r", encoding="utf-8") as f:
                        _cfg = json.load(f)
                        saved_index = _cfg.get("microphone_device")
                        saved_name = _cfg.get("microphone_device_name")

            if saved_index is None:
                with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
                    saved_index = json.load(f).get("microphone_device")

            # [FIX] Cihaz numaraları Windows'ta kayabilir (kulaklık takılınca vb.).
            # Önce KAYITLI İSME göre güncel listede ara; isim bulunursa onu kullan.
            # Sayısal index yalnızca isim eşleşmezse yedek olarak kullanılır.
            devices = sd.query_devices()
            if saved_name:
                for i, d in enumerate(devices):
                    if d["max_input_channels"] > 0 and d["name"] == saved_name:
                        device_index = i
                        break
                if device_index is None:
                    # Tam eşleşme yoksa kısmi eşleşme dene (isim kesilmiş olabilir)
                    for i, d in enumerate(devices):
                        if d["max_input_channels"] > 0 and (
                            saved_name in d["name"] or d["name"] in saved_name
                        ):
                            device_index = i
                            break

            if device_index is None and saved_index is not None:
                saved_index = int(saved_index)
                # Index geçerli bir GİRİŞ cihazı mı kontrol et
                if 0 <= saved_index < len(devices) and devices[saved_index]["max_input_channels"] > 0:
                    device_index = saved_index

            if device_index is not None:
                print(f"[JARVIS] 🎤 Mikrofon çözümlendi: {device_index} ({devices[device_index]['name']})")
        except Exception as e:
            print(f"[JARVIS] Mic config read error (using default): {e}")

        try:
            while True:
                try:
                    with sd.InputStream(
                        samplerate=SEND_SAMPLE_RATE,
                        channels=CHANNELS,
                        dtype="int16",
                        blocksize=CHUNK_SIZE,
                        device=device_index,
                        callback=callback,
                    ):
                        print(f"[JARVIS] 🎤 Mic stream open (Device Index: {device_index})")
                        while True:
                            await asyncio.sleep(0.1)
                except Exception as mic_error:
                    if device_index is not None:
                        print(f"[JARVIS] ⚠️ Selected mic failed ({device_index}): {mic_error}. Trying default mic.")
                        device_index = None
                        continue
                    raise
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        print(f"[JARVIS] 📥 Audio chunk alındı: {len(response.data)} bytes")
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Memo: {full_out}")
                            out_buf = []

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[JARVIS] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            print(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()
        _first_play = True

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                if _first_play:
                    print(f"[JARVIS] 🔊 İlk ses chunk'ı çalınıyor: {len(chunk)} bytes")
                    _first_play = False
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        while True:
            try:
                print("[JARVIS] 🔌 Connecting...")
                self.ui.set_state("CONNECTING")
                self.notify_state("CONNECTING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)
                    self._turn_done_event = asyncio.Event()

                    print("[JARVIS] ✅ Connected.")
                    self.ui.set_state("LISTENING")
                    self.notify_state("LISTENING")
                    self.ui.write_log("SYS: MEMO online.")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

            except Exception as e:
                print(f"[JARVIS] ⚠️ {e}")
                traceback.print_exc()
                self.notify_state("ERROR")
            self.set_speaking(False)
            self.ui.set_state("THINKING")
            self.notify_state("THINKING")
            print("[JARVIS] 🔄 Reconnecting in 3s...")
            await asyncio.sleep(3)

def main():
    kill_other_agent_instances()
    if "--headless" in sys.argv:
        class HeadlessJarvisUI:
            def __init__(self):
                self.muted = False
                self.current_file = None
                self.on_text_command = None
                class DummyRoot:
                    def mainloop(self):
                        while True:
                            time.sleep(1)
                self.root = DummyRoot()

            def set_state(self, state: str):
                print(f"[JARVIS STATE] -> {state}")

            def write_log(self, text: str):
                print(f"[JARVIS LOG] -> {text}")

            def wait_for_api_key(self):
                pass

            def start_speaking(self):
                self.set_state("SPEAKING")

            def stop_speaking(self):
                if not self.muted:
                    self.set_state("LISTENING")

        ui = HeadlessJarvisUI()
        jarvis = JarvisLive(ui)
        
        orig_notify = jarvis.notify_state
        def new_notify(state):
            print(f"[Bridge State] {state}")
            orig_notify(state)
        jarvis.notify_state = new_notify

        def runner():
            try:
                asyncio.run(jarvis.run())
            except KeyboardInterrupt:
                print("\n🔴 Shutting down...")
            except Exception as e:
                print(f"\n🔴 Error: {e}")

        threading.Thread(target=runner, daemon=True).start()
        ui.root.mainloop()
    else:
        ui = JarvisUI("face.png")

        def runner():
            ui.wait_for_api_key()
            jarvis = JarvisLive(ui)
            try:
                asyncio.run(jarvis.run())
            except KeyboardInterrupt:
                print("\n🔴 Shutting down...")

        threading.Thread(target=runner, daemon=True).start()
        ui.root.mainloop()

if __name__ == "__main__":
    main()
