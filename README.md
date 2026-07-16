# Casurpie CLI
                  
       ▄█▄ ▄█▄       
       ▀█████▀       
         ▀█▀         

Casurpie CLI is a beautiful, hyper-responsive, and private local LLM terminal chat application. Designed with a premium minimalist aesthetic, it brings an elite chat experience directly to your terminal over SSH, using local AI models securely.

## Features

- **Premium Terminal UI**: A flawlessly responsive, dual-column welcome screen that mathematically adapts to any terminal width without breaking.
- **Native Scrolling**: Implemented using `prompt_toolkit`, allowing robust scrolling (PgUp / PgDn) that works perfectly even over SSH.
- **Real-Time Token Streaming**: Watch your local models generate responses live, with an integrated real-time timer and token-per-second (tok/s) metrics.
- **Cancel Capabilities**: Gracefully interrupt generation at any time with Ctrl+C while preserving the partial response in the LLM's context.
- **Local & Private**: Communicates securely with your local LLM backend. Zero data leaves your server.

## The Experience

```text
  ╭─ Casurpie CLI ──────────────────────────────────────────────────────── Mode: REAL ─╮
  │                                                                                    │
  │                 ▄█▄ ▄█▄                  │             Shortcuts & Tips            │
  │                 ▀█████▀                  │             ────────────────            │
  │                   ▀█▀                    │        Scroll Chat   PgUp / PgDn        │
  │                                          │        Send Msg      Alt + Enter        │
  │  Model: Qwen_Qwen2.5-Coder-7B-Instruct   │          Stop Gen      Ctrl + C         │
  │    Dir: /home/cesar.perales/LLM-Local    │      Exit CLI      'exit' / 'quit'      │
  │                                                                                    │
  ╰────────────────────────────────────────────────────────────────────────────────────╯
```

## Setup & Installation

1. Clone the repository:
   ```bash
   git clone git@github.com:CdeCasurpie/casurpie-cli.git
   cd casurpie-cli
   ```

2. Install dependencies:
   Make sure you have your conda environment ready.
   ```bash
   make setup
   ```

3. Start the Chat:
   ```bash
   make client
   ```

## Controls

- **Send Message**: `Alt + Enter` (or `Esc` then `Enter`)
- **Scroll Chat**: `Page Up` / `Page Down`
- **Interrupt Generation**: `Ctrl + C`
- **Exit**: Type `exit` or `quit`

---
Built for a seamless and aesthetically pleasing offline AI experience.
