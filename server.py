import argparse
import json
import os
import socket
import sys
import atexit
import signal
from http.server import HTTPServer, BaseHTTPRequestHandler

# Import LLM backends
try:
    from llm_backend import LLMock, LLMReal
except ImportError:
    # If run in parent directory or path issue, add current directory to path
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from llm_backend import LLMock, LLMReal

# File to store connection information
CONNECTION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "connection.json")

# Global reference to backend for cleanup/signals
backend_instance = None

def get_free_port(start_port=8000, max_port=9000):
    """Finds a free port to bind to."""
    for port in range(start_port, max_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free ports available in the specified range.")

def clean_connection_file():
    """Removes the connection file upon server shutdown."""
    if os.path.exists(CONNECTION_FILE):
        try:
            os.remove(CONNECTION_FILE)
            print(f"Cleaned up connection file: {CONNECTION_FILE}")
        except Exception as e:
            print(f"Error cleaning up connection file: {e}")

# Register exit handler
atexit.register(clean_connection_file)

# Signal handler for graceful shutdown
def signal_handler(sig, frame):
    print(f"\nReceived signal {sig}. Shutting down server...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


class LLMRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence standard HTTP request logs to keep stdout clean for SLURM log files,
        # but print exceptions or custom logs when necessary.
        pass

    def _set_headers(self, status=200, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-type", content_type)
        # Enable CORS
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        # Handle pre-flight CORS requests
        self._set_headers(200)

    def do_GET(self):
        if self.path == "/status":
            self._handle_status()
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not Found"}).encode("utf-8"))

    def do_POST(self):
        if self.path == "/generate":
            self._handle_generate()
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not Found"}).encode("utf-8"))

    def _handle_status(self):
        status_data = {
            "status": "online",
            "mode": self.server.mode,
            "model": self.server.model_name,
            "node": socket.gethostname(),
            "pid": os.getpid(),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID", "N/A"),
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(status_data).encode("utf-8"))

    def _handle_generate(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)
        
        try:
            req_json = json.loads(post_data.decode("utf-8"))
        except json.JSONDecodeError:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode("utf-8"))
            return

        prompt = req_json.get("prompt", "")
        history = req_json.get("history", [])
        max_new_tokens = int(req_json.get("max_new_tokens", 512))
        temperature = float(req_json.get("temperature", 0.7))
        top_p = float(req_json.get("top_p", 0.9))

        if not prompt:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Prompt field is required"}).encode("utf-8"))
            return

        print(f"Generating for prompt: '{prompt[:40]}...' ({len(prompt)} chars, {len(history)} past msgs)")
        start_time = time.time()
        
        try:
            # Send headers for chunked streaming
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Transfer-Encoding', 'chunked')
            self.end_headers()

            # Stream the response
            for chunk in self.server.backend.generate(
                prompt=prompt,
                history=history,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_p=top_p
            ):
                if chunk:
                    encoded = chunk.encode('utf-8')
                    self.wfile.write(f"{len(encoded):X}\r\n".encode('utf-8'))
                    self.wfile.write(encoded)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
            
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            
            time_taken = time.time() - start_time
            print(f"Stream finished in {time_taken:.2f}s")
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._set_headers(500)
            self.wfile.write(json.dumps({
                "error": str(e),
                "status": "failed",
                "node": socket.gethostname()
            }).encode("utf-8"))


class LLMServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, mode, model_name, backend):
        super().__init__(server_address, RequestHandlerClass)
        self.mode = mode
        self.model_name = model_name
        self.backend = backend


def main():
    parser = argparse.ArgumentParser(description="LLM Local Server for Khipuf/SLURM")
    parser.add_argument("--mode", type=str, choices=["mock", "real"], default="mock",
                        help="Server mode: 'mock' (no GPU needed) or 'real' (requires CUDA & weights)")
    parser.add_argument("--model", type=str, default="Qwen/Qwen2.5-Coder-7B-Instruct",
                        help="Hugging Face model ID or absolute path (only used in 'real' mode)")
    parser.add_argument("--port", type=int, default=8000,
                        help="Start port to listen on (will scan upwards if unavailable)")
    parser.add_argument("--device", type=str, default=None,
                        help="PyTorch device: 'cuda', 'cpu', or auto-detect")
    parser.add_argument("--load_in_8bit", action="store_true", help="Load weights in 8-bit precision")
    parser.add_argument("--load_in_4bit", action="store_true", help="Load weights in 4-bit precision")
    
    args = parser.parse_args()

    print("=" * 60)
    print(f"Starting LLM Local Server on node '{socket.gethostname()}'")
    print(f"Mode: {args.mode.upper()}")
    if args.mode == "real":
        print(f"Model Path/ID: {args.model}")
    print("=" * 60)

    # Initialize backend
    if args.mode == "mock":
        backend = LLMock(model_name=f"Mock-{args.model.split('/')[-1]}")
    else:
        # LLMReal will import torch/transformers and load weights
        try:
            backend = LLMReal(
                model_path=args.model,
                device=args.device,
                load_in_8bit=args.load_in_8bit,
                load_in_4bit=args.load_in_4bit
            )
        except Exception as e:
            print(f"\nCRITICAL ERROR: Failed to load real LLM: {e}")
            sys.exit(1)

    # Find free port
    port = get_free_port(args.port)
    hostname = socket.gethostname()

    # Create server
    server = LLMServer(("", port), LLMRequestHandler, args.mode, args.model, backend)
    
    # Save connection info
    connection_info = {
        "host": hostname,
        "port": port,
        "mode": args.mode,
        "model": args.model,
        "pid": os.getpid(),
        "job_id": os.environ.get("SLURM_JOB_ID", "local"),
        "timestamp": time.time()
    }
    
    with open(CONNECTION_FILE, "w") as f:
        json.dump(connection_info, f, indent=4)
        
    print(f"\nServer is listening at: http://{hostname}:{port}")
    print(f"Connection metadata written to: {CONNECTION_FILE}")
    print("Use client.py on the login node to interact with this server.")
    print("Press Ctrl+C to stop.")
    print("-" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        clean_connection_file()

if __name__ == "__main__":
    import time # Needed for time tracking
    main()
