import os
import time
import socket

class LLMock:
    """
    A mock LLM class that simulates the text generation process.
    Does not require torch or transformers, making it perfect for rapid prototyping
    and testing connection and client-server flows.
    """
    def __init__(self, model_name="Mock-Model-v2.0"):
        self.model_name = model_name
        self.hostname = socket.gethostname()

    def generate(self, prompt, history=None, max_new_tokens=4096, temperature=0.7, top_p=0.9):
        # Simulate thinking latency
        simulated_delay = min(5.0, max(0.5, len(prompt) * 0.005))
        time.sleep(simulated_delay)

        # Generate a simulated response
        prompt_lower = prompt.lower()
        if "hola" in prompt_lower or "hello" in prompt_lower or "saludos" in prompt_lower:
            response = (
                f"¡Hola! Soy {self.model_name}, ejecutándose en modo MOCK en el nodo '{self.hostname}'.\n\n"
                "Estoy listo para ayudarte a probar tu arquitectura cognitiva modular. "
                "En este modo de simulación, no consumo VRAM ni GPU, lo que te permite validar "
                "la comunicación de tus agentes rápidamente."
            )
        elif "codigo" in prompt_lower or "código" in prompt_lower or "write" in prompt_lower or "def " in prompt_lower or "class " in prompt_lower:
            response = (
                f"// Mock response from {self.model_name} on {self.hostname}\n"
                "def solve_problem(data):\n"
                "    \"\"\"\n"
                "    Esta es una función generada de prueba por el modelo mock.\n"
                "    \"\"\"\n"
                "    print(f\"Procesando datos en {self.hostname}...\")\n"
                "    result = [x * 2 for x in data]\n"
                "    return result\n"
            )
        else:
            response = (
                f"[MOCK RESPONSE - {self.model_name} @ {self.hostname}]\n\n"
                f"Recibí tu prompt de {len(prompt)} caracteres:\n"
                f"\"...{prompt[-100:] if len(prompt) > 100 else prompt}\"\n\n"
                f"Parámetros de generación:\n"
                f"- max_new_tokens: {max_new_tokens}\n"
                f"- temperature: {temperature}\n"
                f"- top_p: {top_p}\n\n"
                f"Esta es una respuesta simulada para que pruebes tu orquestador de agentes."
            )
        
        for word in response.split(" "):
            yield word + " "


class LLMReal:
    """
    A real LLM backend that loads weights using Hugging Face transformers.
    Imports torch and transformers lazily to avoid loading errors when running in Mock mode.
    """
    def __init__(self, model_path, device=None, load_in_8bit=False, load_in_4bit=False):
        self.model_path = model_path
        self.device = device
        self.load_in_8bit = load_in_8bit
        self.load_in_4bit = load_in_4bit
        self.model = None
        self.tokenizer = None
        self._load_model()

    def _load_model(self):
        print(f"Loading real LLM model from: {self.model_path}...")
        start_time = time.time()
        
        # Lazy imports
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as e:
            raise ImportError(
                "Failed to import torch/transformers. Please ensure they are installed in your active environment.\n"
                "You can run setup_env.sh to create a compatible conda environment."
            ) from e

        # Determine device
        if self.device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {self.device}")

        # Set load configuration
        kwargs = {}
        if self.device == "cuda":
            kwargs["torch_dtype"] = torch.float16
            if self.load_in_8bit:
                kwargs["load_in_8bit"] = True
                kwargs["device_map"] = "auto"
            elif self.load_in_4bit:
                kwargs["load_in_4bit"] = True
                kwargs["device_map"] = "auto"
            else:
                kwargs["device_map"] = "auto"
        else:
            # CPU fallback
            kwargs["torch_dtype"] = torch.float32

        # Check if loading from local directory
        local_files_only = False
        if os.path.isdir(self.model_path):
            print("Local model path detected. Enabling offline loading (local_files_only=True).")
            local_files_only = True

        print(f"Loading tokenizer...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, 
            trust_remote_code=True,
            local_files_only=local_files_only
        )
        
        print(f"Loading model weights (kwargs: {kwargs})...")
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            trust_remote_code=True,
            local_files_only=local_files_only,
            **kwargs
        )
        
        # If not using device_map='auto' and CUDA is available, move to target device manually
        if self.device == "cuda" and not (self.load_in_8bit or self.load_in_4bit):
            self.model = self.model.to("cuda")

        print(f"Model loaded successfully in {time.time() - start_time:.2f} seconds!")

    def generate(self, prompt, history=None, max_new_tokens=4096, temperature=0.7, top_p=0.9):
        import torch
        from transformers import TextIteratorStreamer
        from threading import Thread
        
        if self.model is None or self.tokenizer is None:
            raise ValueError("Model or tokenizer is not loaded properly.")

        # Prepare inputs
        if hasattr(self.tokenizer, "apply_chat_template") and self.tokenizer.chat_template is not None:
            messages = [
                {"role": "system", "content": "Eres un asistente de programación experto, útil y brillante. Respondes siempre en español, a menos que el usuario indique lo contrario."}
            ]
            if history:
                messages.extend(history)
            messages.append({"role": "user", "content": prompt})
            
            try:
                formatted_prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            except Exception:
                formatted_prompt = prompt
        else:
            formatted_prompt = prompt

        inputs = self.tokenizer(formatted_prompt, return_tensors="pt")
        inputs = {k: v.to(self.model.device) for k, v in inputs.items()}

        # Generation config
        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
        generation_kwargs = dict(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            do_sample=temperature > 0,
            pad_token_id=self.tokenizer.eos_token_id,
            streamer=streamer
        )
        
        thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()
        
        for new_text in streamer:
            yield new_text
