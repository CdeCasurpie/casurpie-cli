#!/usr/bin/env python3
"""
LLM-Local Client — Terminal Chat TUI (V8: Perfect Scroll)
Uses a read-only TextArea with a custom Lexer for styling.
Provides flawless auto-scrolling to the bottom, and manual scrolling
via PageUp/PageDown without needing mouse support over SSH.
"""
import argparse
import json
import os
import sys
import io
import time
import urllib.request
import urllib.error
import threading
import shutil

CONNECTION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "connection.json")

def read_connection_info():
    if not os.path.exists(CONNECTION_FILE):
        print(f"\n[Error] Connection file not found at: {CONNECTION_FILE}")
        print("The LLM server is not running. Start it with:  make up")
        sys.exit(1)
    try:
        with open(CONNECTION_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Error] Failed to read connection file: {e}")
        sys.exit(1)

def check_status(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except:
        return None

def run_tui_chat(base_url, mode, model, args):
    from prompt_toolkit import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.layout import Layout, HSplit, Window, Dimension
    from prompt_toolkit.layout.controls import FormattedTextControl, BufferControl
    from prompt_toolkit.widgets import TextArea
    from prompt_toolkit.lexers import Lexer
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.styles import Style
    from prompt_toolkit.document import Document

    from prompt_toolkit.history import InMemoryHistory
    import textwrap

    model_short = model.split("/")[-1] if "/" in model else model
    is_generating = [False]
    cancel_event = threading.Event()
    app_ref = [None]
    
    chat_messages = [] # tuples of (role, text)
    chat_text_cache = [""]
    last_term_width = [shutil.get_terminal_size().columns]
    current_resp = [""]
    live_stats = [""]
    
    SYSTEM_PROMPT = """Eres un asistente de IA de élite, operando en un entorno local y privado.
Tienes memoria perfecta de este contexto de conversación; debes mantener la coherencia con los mensajes anteriores.
Eres altamente capaz, analítico y preciso. Tus respuestas son directas, concisas y orientadas a la acción, sin introducciones innecesarias.
¡Estás al nivel de los mejores modelos del mundo!"""

    api_history = [{"role": "system", "content": SYSTEM_PROMPT}]

    def invalidate():
        if app_ref[0]:
            app_ref[0].invalidate()

    # ── Custom Lexer for Chat Area ──
    class ChatLexer(Lexer):
        def lex_document(self, document):
            def get_line(lineno):
                try:
                    line = document.lines[lineno]
                except IndexError:
                    return []
                if line.startswith("  > You"):
                    return [("class:user-label", line)]
                elif line.startswith("  > LLM"):
                    return [("class:llm-label", line)]
                elif line.startswith("    ⏱"):
                    return [("class:stats", line)]
                elif line.startswith("    [Cancelled]") or line.startswith("    [Error]"):
                    return [("class:error", line)]
                elif line.startswith("  Type a"):
                    return [("class:dim", line)]
                elif line.startswith("  ╭─"):
                    res = []
                    idx1 = line.find("Casurpie CLI")
                    if idx1 != -1:
                        res.append(("class:wb", line[:idx1]))
                        res.append(("class:wt", "Casurpie CLI"))
                        rest = line[idx1+len("Casurpie CLI"):]
                    else:
                        rest = line
                        
                    idx2 = rest.find("Mode:")
                    if idx2 != -1:
                        res.append(("class:wb", rest[:idx2]))
                        res.append(("class:wi", "Mode: "))
                        end = rest.find(" ", idx2+6)
                        if end == -1: end = len(rest)
                        res.append(("class:wv", rest[idx2+6:end]))
                        res.append(("class:wb", rest[end:]))
                    else:
                        res.append(("class:wb", rest))
                    return res
                elif line.startswith("  ╰─"):
                    return [("class:wb", line)]
                elif line.startswith("  │"):
                    if "▄█▄" in line or "▀█████▀" in line or "▀█▀" in line:
                        idx1 = line.find("▄") if "▄" in line else line.find("▀")
                        idx2 = line.rfind("▄") if "▄" in line else line.rfind("▀")
                        if idx1 != -1 and idx2 != -1:
                            return [("class:wb", line[:idx1]), ("class:logo", line[idx1:idx2+1]), ("class:wb", line[idx2+1:])]
                        return [("class:wb", line)]
                        
                    parts = line.split("│")
                    res = []
                    for i, part in enumerate(parts):
                        if i > 0:
                            res.append(("class:wb", "│"))
                            
                        if not part:
                            continue
                            
                        if part == "  " and i == 0:
                            res.append(("class:wb", part))
                        elif part == "\n" and i == len(parts) - 1:
                            res.append(("", "\n"))
                        else:
                            if "Model: " in part:
                                sub = part.split("Model: ")
                                res.append(("class:wi", sub[0]))
                                res.append(("class:wi", "Model: "))
                                v_end = sub[1].find("  ")
                                if v_end == -1: v_end = len(sub[1])
                                res.append(("class:wv", sub[1][:v_end]))
                                res.append(("class:wi", sub[1][v_end:]))
                            elif "Dir: " in part:
                                sub = part.split("Dir: ")
                                res.append(("class:wi", sub[0]))
                                res.append(("class:wi", "Dir: "))
                                v_end = sub[1].find("  ")
                                if v_end == -1: v_end = len(sub[1])
                                res.append(("class:wv", sub[1][:v_end]))
                                res.append(("class:wi", sub[1][v_end:]))
                            elif "Shortcuts & Tips" in part:
                                sub = part.split("Shortcuts & Tips")
                                res.append(("class:wi", sub[0]))
                                res.append(("class:wt", "Shortcuts & Tips"))
                                res.append(("class:wi", sub[1]))
                            else:
                                res.append(("class:wi", part))
                    return res
                else:
                    return [("class:chat-text", line)]
            return get_line

    chat_area = TextArea(
        text="",
        read_only=True,
        scrollbar=True,
        lexer=ChatLexer(),
        wrap_lines=True,
    )

    # Indent wrapped lines to match the 4-space prefix
    def chat_line_prefix(line_no, wrap_count):
        if wrap_count > 0:
            return [("", "    ")]
        return []
    chat_area.window.get_line_prefix = chat_line_prefix

    # Right padding so text doesn't touch the scrollbar
    from prompt_toolkit.layout.margins import Margin
    class RightPaddingMargin(Margin):
        def get_width(self, get_ui_content): return 4
        def create_margin(self, window_render_info, width, height): return [("", " " * width)]
    
    chat_area.window.right_margins = [RightPaddingMargin()] + chat_area.window.right_margins

    # ── Input Area ──
    input_buffer = Buffer(multiline=True, history=InMemoryHistory())
    input_window = Window(
        content=BufferControl(buffer=input_buffer, focusable=True),
        height=Dimension(min=1, max=6, preferred=2),
        style="class:input-area",
        wrap_lines=True,
        get_line_prefix=lambda line_no, wrap_count: [("class:input-prompt", " > " if line_no == 0 else "   ")],
    )

    def get_sep():
        return [("class:sep-line", "─" * shutil.get_terminal_size().columns)]

    sep_top = Window(content=FormattedTextControl(text=get_sep), height=1)
    sep_bot = Window(content=FormattedTextControl(text=get_sep), height=1)

    def get_footer():
        gen_text = "  ⏳ Generating..." if is_generating[0] else ""
        return [("class:footer", f" LLM-Local │ Model: {model_short} │ Mode: {mode.upper()} │ Enter: send  Alt+Enter: ↵  Ctrl+C: stop{gen_text}")]
    footer = Window(content=FormattedTextControl(text=get_footer), height=1)

    layout = Layout(
        HSplit([chat_area, sep_top, input_window, sep_bot, footer]),
        focused_element=input_window,
    )

    style = Style.from_dict({
        "user-label":    "#db7093 bold",
        "llm-label":     "#ffffff bold",
        "chat-text":     "#f5d6c3",            # peach/durazno for everything typed by LLM
        "dim":           "#666666 italic",
        "stats":         "#888888 italic",
        "error":         "#ff5555 bold",
        "wb":            "#db7093",
        "logo":          "#db7093 bold",
        "wt":            "#ffffff bold",
        "wi":            "#aaaaaa",
        "wv":            "#e2b714",
        "sep-line":      "#555555",
        "input-area":    "#ffffff",
        "input-prompt":  "#db7093",
        "footer":        "#888888",
    })

    # ── Key Bindings ──
    kb = KeyBindings()

    @kb.add("enter")
    def handle_enter(event):
        if is_generating[0]: return
        text = input_buffer.text.strip()
        if not text: return
        input_buffer.append_to_history()
        input_buffer.set_document(Document(""), bypass_readonly=True)
        if text.lower() in ("exit", "quit"):
            event.app.exit()
            return

        is_generating[0] = True
        cancel_event.clear()
        current_resp[0] = ""
        live_stats[0] = ""
        
        # Immediately display user message and start LLM block
        chat_messages.append(("user", text))
        chat_text_cache[0] = build_history_text(last_term_width[0])
        chat_area.text = chat_text_cache[0] + f"\n  > LLM\n    "
        chat_area.buffer.cursor_position = len(chat_area.text)
        
        def do_generate():
            t0 = time.time()
            full_resp = ""
            last_ui_update = 0
            try:
                payload = {"prompt": text, "history": api_history, "max_new_tokens": args.max_tokens, "temperature": args.temp, "top_p": args.top_p}
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(f"{base_url}/generate", data=data, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=300) as response:
                    text_stream = io.TextIOWrapper(response, encoding="utf-8")
                    while not cancel_event.is_set():
                        chunk = text_stream.read(16)
                        if not chunk: break
                        full_resp += chunk
                        current_resp[0] = full_resp
                        
                        now = time.time()
                        if now - last_ui_update > 0.1:
                            elapsed = now - t0
                            tokens = max(1, len(full_resp) // 4)
                            tps = tokens / elapsed if elapsed > 0 else 0
                            live_stats[0] = f"\n\n    ⏱ {elapsed:.1f}s  •  ~{tokens} tokens  •  {tps:.1f} tok/s"
                            chat_area.text = chat_text_cache[0] + f"\n  > LLM\n    " + full_resp.replace("\n", "\n    ") + live_stats[0]
                            chat_area.buffer.cursor_position = len(chat_area.text)
                            invalidate()
                            last_ui_update = now
            except Exception as e:
                if not cancel_event.is_set():
                    live_stats[0] = f"\n\n    [Error] {e}\n"
                    chat_area.text = chat_text_cache[0] + f"\n  > LLM\n    " + full_resp.replace("\n", "\n    ") + live_stats[0]
            finally:
                elapsed = time.time() - t0
                tokens = max(1, len(full_resp) // 4)
                tps = tokens / elapsed if elapsed > 0 else 0
                is_generating[0] = False
                
                if cancel_event.is_set():
                    final_stats = f"\n\n    [Cancelled]\n"
                    api_history.append({"role": "user", "content": text})
                    api_history.append({"role": "assistant", "content": full_resp + "\n[Generación cancelada por el usuario]"})
                else:
                    final_stats = f"\n\n    ⏱ {elapsed:.2f}s  •  ~{tokens} tokens  •  {tps:.1f} tok/s\n"
                    api_history.append({"role": "user", "content": text})
                    api_history.append({"role": "assistant", "content": full_resp})
                
                # Commit to history
                chat_messages.append(("llm", full_resp.replace("\n", "\n    ") + final_stats))
                chat_text_cache[0] = build_history_text(last_term_width[0])
                chat_area.text = chat_text_cache[0]
                chat_area.buffer.cursor_position = len(chat_area.text)
                invalidate()

        threading.Thread(target=do_generate, daemon=True).start()

    @kb.add("escape", "enter")
    def _(event): input_buffer.insert_text("\n")

    @kb.add("c-c")
    def _(event):
        if is_generating[0]: cancel_event.set()
        else: input_buffer.set_document(Document(""), bypass_readonly=True)

    @kb.add("c-d")
    def _(event):
        if is_generating[0]: cancel_event.set()
        event.app.exit()

    # Manual Scroll Bindings via Buffer cursor manipulation
    @kb.add("pageup")
    def _(event):
        doc = chat_area.buffer.document
        chat_area.buffer.cursor_position = doc.translate_row_col_to_index(max(0, doc.cursor_position_row - 20), 0)

    @kb.add("pagedown")
    def _(event):
        doc = chat_area.buffer.document
        chat_area.buffer.cursor_position = doc.translate_row_col_to_index(min(doc.line_count - 1, doc.cursor_position_row + 20), 0)

    @kb.add("c-up")
    def _(event):
        doc = chat_area.buffer.document
        chat_area.buffer.cursor_position = doc.translate_row_col_to_index(max(0, doc.cursor_position_row - 1), 0)

    @kb.add("c-down")
    def _(event):
        doc = chat_area.buffer.document
        chat_area.buffer.cursor_position = doc.translate_row_col_to_index(min(doc.line_count - 1, doc.cursor_position_row + 1), 0)

    # ── Welcome Screen & Responsive History ──
    def get_welcome_text(width):
        bw = width - 10
        if bw > width - 6:
            bw = max(2, width - 6)
        if bw < 5:
            bw = 5
            
        left_title = " Casurpie CLI "
        right_title = f" Mode: {mode.upper()} "
        
        if bw < len(left_title) + len(right_title) + 5:
            right_title = ""
            
        fill = bw - 2 - len(left_title) - len(right_title)
        if fill < 0:
            left_title = left_title[:max(0, bw - 2)]
            fill = 0
            
        top_border = f"  ╭─{left_title}" + "─" * fill + right_title + "─╮"
        
        logo = [" ▄█▄ ▄█▄ ", " ▀█████▀ ", "   ▀█▀   "]
        
        lines = ["\n", top_border, f"  │{' ' * bw}│"]
        
        if bw > 75:
            lw = max(40, bw // 2)
            rw = bw - lw - 1
            
            left_col = []
            for l in logo:
                if len(l) > lw: l = l[:lw]
                left_col.append(l.center(lw))
            left_col.append(" " * lw)
            
            for w in textwrap.wrap(f"Model: {model_short}", width=max(1, lw-2), break_long_words=True):
                left_col.append(f" {w.center(max(1, lw-2))} ")
            for w in textwrap.wrap(f"Dir: {os.getcwd()}", width=max(1, lw-2), break_long_words=True):
                left_col.append(f" {w.center(max(1, lw-2))} ")
                
            right_col = [
                " Shortcuts & Tips ".center(rw),
                " ──────────────── ".center(rw),
                "Scroll Chat   PgUp / PgDn".center(rw),
                "Send Msg      Alt + Enter".center(rw),
                "Stop Gen      Ctrl + C".center(rw),
                "Exit CLI      'exit' / 'quit'".center(rw),
            ]
            
            max_h = max(len(left_col), len(right_col))
            
            def vcenter_col(col, target_h, width):
                pad_total = target_h - len(col)
                pad_top = pad_total // 2
                pad_bot = pad_total - pad_top
                return [" " * width] * pad_top + col + [" " * width] * pad_bot
                
            left_col = vcenter_col(left_col, max_h, lw)
            right_col = vcenter_col(right_col, max_h, rw)
            
            for l, r in zip(left_col, right_col):
                lines.append(f"  │{l}│{r}│")
        else:
            for l in logo:
                if len(l) > bw: l = l[:bw]
                lines.append(f"  │{l.center(bw)}│")
            lines.append(f"  │{' ' * bw}│")
            
            def add_wrapped(text):
                wrapped = textwrap.wrap(text, width=max(1, bw-2), break_long_words=True)
                for w in wrapped:
                    lines.append(f"  │ {w.center(max(1, bw-2))} │")
                    
            add_wrapped(f"Model: {model_short}")
            add_wrapped(f"Dir: {os.getcwd()}")
        
        lines.append(f"  │{' ' * bw}│")
        lines.append(f"  ╰{'─' * bw}╯")
        lines.append("\n  Type a message below and press Enter.\n")
        return "\n".join(lines)
    
    def build_history_text(width):
        out = get_welcome_text(width)
        for role, text in chat_messages:
            if role == "user":
                out += f"\n  > You\n"
                for line in text.split("\n"):
                    out += f"    {line}\n"
            elif role == "llm":
                out += f"\n  > LLM\n    {text}\n"
        return out
        
    chat_text_cache[0] = build_history_text(last_term_width[0])
    chat_area.text = chat_text_cache[0]
    chat_area.buffer.cursor_position = len(chat_area.text)

    def on_before_render(app):
        current_width = shutil.get_terminal_size().columns
        if current_width != last_term_width[0]:
            last_term_width[0] = current_width
            chat_text_cache[0] = build_history_text(current_width)
            if is_generating[0]:
                chat_area.text = chat_text_cache[0] + f"\n  > LLM\n    " + current_resp[0].replace("\n", "\n    ") + live_stats[0]
            else:
                chat_area.text = chat_text_cache[0]
            # No cursor adjustment here so we don't yank the user to the bottom if they were scrolling

    app = Application(
        layout=layout,
        style=style,
        key_bindings=kb,
        full_screen=True,
        mouse_support=False,
        before_render=on_before_render,
    )
    app_ref[0] = app
    app.run()
    print("\nGoodbye!")

def run_simple_chat(base_url, mode, model, args):
    model_short = model.split("/")[-1] if "/" in model else model
    C_R = "\033[0m"; C_P = "\033[38;5;218m"; C_W = "\033[38;5;255m"
    C_G = "\033[38;5;245m"; C_D = "\033[2m"; C_PC = "\033[38;5;223m"
    print(f"\n  {C_P}LLM-Local{C_R} — {model_short} ({mode.upper()})\n")
    chat_history = []
    while True:
        try:
            print(f"\n  {C_P}>{C_R} ", end="")
            text = input().strip()
            if not text: continue
            if text.lower() in ("exit", "quit"):
                print(f"\n{C_G}Goodbye!{C_R}\n"); break

            print(f"\n  {C_W}> LLM{C_R}\n    ", end="", flush=True)
            payload = {"prompt": text, "history": chat_history, "max_new_tokens": args.max_tokens, "temperature": args.temp, "top_p": args.top_p}
            req = urllib.request.Request(f"{base_url}/generate", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
            full = ""; t0 = time.time()
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    ts = io.TextIOWrapper(resp, encoding="utf-8")
                    while True:
                        c = ts.read(16)
                        if not c: break
                        out = c.replace("\n", "\n    ")
                        print(f"{C_PC}{out}{C_R}", end="", flush=True); full += c
            except KeyboardInterrupt: print(f"\n    {C_G}[Cancelled]{C_R}")
            except Exception as e: print(f"\n    [Error] {e}")
            el = time.time() - t0; tk = max(1, len(full)//4); tps = tk/el if el > 0 else 0
            print(f"\n    {C_G}{C_D}⏱ {el:.2f}s  •  ~{tk} tokens  •  {tps:.1f} tok/s{C_R}")
            chat_history.append({"role": "user", "content": text})
            chat_history.append({"role": "assistant", "content": full})
        except KeyboardInterrupt: print()
        except EOFError: print(f"\nGoodbye!\n"); break

def main():
    parser = argparse.ArgumentParser(description="LLM-Local Client")
    parser.add_argument("--prompt", type=str)
    parser.add_argument("--chat", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--host", type=str)
    parser.add_argument("--port", type=int)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--temp", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--simple", action="store_true", help="Simple mode")
    args = parser.parse_args()

    if args.host and args.port:
        host, port, mode, model = args.host, args.port, "manual", "manual"
    else:
        conn = read_connection_info()
        host, port = conn["host"], conn["port"]
        mode, model = conn["mode"], conn.get("model", "N/A")

    base_url = f"http://{host}:{port}"
    if args.status:
        s = check_status(f"{base_url}/status")
        if s: print("ONLINE\n" + json.dumps(s, indent=2))
        else: print("OFFLINE")
        return
    if args.prompt:
        req = urllib.request.Request(f"{base_url}/generate", data=json.dumps({"prompt": args.prompt, "max_new_tokens": args.max_tokens, "temperature": args.temp, "top_p": args.top_p}).encode("utf-8"), headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                ts = io.TextIOWrapper(resp, encoding="utf-8")
                while True:
                    c = ts.read(64)
                    if not c: break
                    print(c, end="", flush=True)
            print()
        except Exception as e: print(f"[Error] {e}")
        return

    if args.simple: run_simple_chat(base_url, mode, model, args)
    else:
        try: run_tui_chat(base_url, mode, model, args)
        except ImportError:
            print("[Warning] prompt_toolkit not found, using simple mode.")
            run_simple_chat(base_url, mode, model, args)

if __name__ == "__main__":
    main()
