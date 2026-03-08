import numpy as np
import os
from tqdm import tqdm
import openai
from openai import OpenAI
import httpx
import urllib3
from dotenv import load_dotenv

# Load environment variables from .env file with explicit path (don't override existing)
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')
load_dotenv(dotenv_path=env_path, override=False)

# Get API key and validate
openai_key = os.getenv('OPENAI_API_KEY')
openai_base_url = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
print(f"[DEBUG] Loaded API key from .env: {openai_key[:15] + '...' if openai_key else 'None'}")
print(f"[DEBUG] Using base URL: {openai_base_url}")

if openai_key:
    # Remove any quotes if they exist
    openai_key = openai_key.strip('\'"')

def load_all_api_keys():
	"""Load all API keys from environment variables.
	Looks for OPENAI_API_KEY_1, OPENAI_API_KEY_2, ... in addition to OPENAI_API_KEY.
	Returns a list of valid API keys."""
	keys = []
	# Primary key
	primary = os.getenv('OPENAI_API_KEY', '').strip('\'\'"')
	if primary:
		keys.append(primary)
	# Numbered keys: OPENAI_API_KEY_1, OPENAI_API_KEY_2, ...
	for i in range(1, 20):  # Support up to 20 keys
		key = os.getenv(f'OPENAI_API_KEY_{i}', '').strip('\'\'"')
		if key and key not in keys:
			keys.append(key)
	print(f"[DEBUG] Found {len(keys)} API key(s)")
	return keys


def create_openai_client(api_key, base_url=None):
	"""Create an OpenAI client with the given API key."""
	http_client = httpx.Client(verify=False)
	urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
	return OpenAI(
		api_key=api_key,
		base_url=base_url or openai_base_url,
		http_client=http_client
	)
# map each term in text to word_id
def get_vocab_idx(split_text: str, tok_lens):

	vocab_idx = {}
	start = 0

	for w in split_text:
		# print(w, start, start + len(tok_lens[w]))
		if w not in vocab_idx:
			vocab_idx[w] = []

		vocab_idx[w].extend(np.arange(start, start + len(tok_lens[w])))

		start += len(tok_lens[w])

	return vocab_idx

# Removed get_hidden_states function - not needed for CPU-only version

def chunkify(text, token_lens, length=512):
	chunks = [[]]
	split_text = text.split()
	count = 0
	for word in split_text:
		new_count = count + len(token_lens[word]) + 2 # 2 for [CLS] and [SEP]
		if new_count > length:
			chunks.append([word])
			count = len(token_lens[word])
		else:
			chunks[len(chunks) - 1].append(word)
			count = new_count
	
	return chunks

def constructPrompt(args, init_prompt, main_prompt):
	if (args.llm == 'gpt'):
		return [
            {"role": "system", "content": init_prompt},
            {"role": "user", "content": main_prompt}]
	else:
		return init_prompt + "\n\n" + main_prompt

def initializeLLM(args):
	args.client = {}

	# Only OpenAI GPT is supported in CPU-only mode
	if args.llm == 'vllm':
		raise RuntimeError("vLLM is not supported in CPU-only mode. Please use --llm gpt instead.")
	
	if args.llm == 'gpt':
		# Create httpx client with SSL verification disabled for corporate firewalls
		http_client = httpx.Client(verify=False)
		# Suppress SSL warnings
		import urllib3
		urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
		
		args.client[args.llm] = OpenAI(
			api_key=openai_key,
			base_url=openai_base_url,
			http_client=http_client
		)
	else:
		raise ValueError(f"Unsupported LLM type: {args.llm}. Only 'gpt' is supported in CPU-only mode.")
	
	return args

def estimate_token_count(text):
	"""Estimate token count using ~4 characters per token heuristic."""
	if text is None:
		return 0
	return len(text) // 4

def truncate_messages_to_token_limit(messages, max_context_tokens=128000, reserved_output_tokens=3000):
	"""Truncate message content if total estimated tokens exceed the model's context limit.
	Preserves the system message and truncates the user message content if needed."""
	max_input_tokens = max_context_tokens - reserved_output_tokens
	
	# Estimate total tokens
	total_tokens = sum(estimate_token_count(m.get('content', '')) for m in messages)
	
	if total_tokens <= max_input_tokens:
		return messages  # No truncation needed
	
	print(f"[WARNING] Estimated {total_tokens} tokens exceeds limit {max_input_tokens}. Truncating...")
	
	# Calculate how many tokens we need to cut (add buffer for truncation marker)
	tokens_to_cut = total_tokens - max_input_tokens + 50  # 50 token buffer for marker text
	chars_to_cut = tokens_to_cut * 4  # Convert back to characters
	
	# Find the user message (usually the last/longest one) and truncate it
	truncated_messages = []
	for msg in messages:
		if msg['role'] == 'user' and chars_to_cut > 0:
			content = msg['content']
			if len(content) > chars_to_cut:
				# Truncate from the middle of the content (preserve start/end for context)
				keep_start = (len(content) - chars_to_cut) * 2 // 3
				keep_end = (len(content) - chars_to_cut) // 3
				truncated_content = content[:keep_start] + "\n\n... [TRUNCATED DUE TO TOKEN LIMIT] ...\n\n" + content[-keep_end:]
				truncated_messages.append({'role': msg['role'], 'content': truncated_content})
				chars_to_cut = 0
			else:
				# This message is smaller than what we need to cut - skip shouldn't happen often
				truncated_messages.append(msg)
		else:
			truncated_messages.append(msg)
	
	new_total = sum(estimate_token_count(m.get('content', '')) for m in truncated_messages)
	print(f"[INFO] Truncated from ~{total_tokens} to ~{new_total} estimated tokens.")
	return truncated_messages

def promptGPT(args, prompts, schema=None, max_new_tokens=16384, json_mode=True, temperature=0.1, top_p=0.99):
	# Allow overriding the model via environment variable for flexibility
	model = os.getenv('OPENAI_MODEL', 'gpt-5-2025-08-07')
	print(f"[DEBUG] Using LLM model: {model}")
	
	# Allow overriding temperature/top_p via env (set by web UI)
	env_temp = os.getenv('OPENAI_TEMPERATURE')
	env_top_p = os.getenv('OPENAI_TOP_P')
	if env_temp is not None:
		temperature = float(env_temp)
	if env_top_p is not None:
		top_p = float(env_top_p)
	
	# gpt-5-nano and some o1/o3 models only support temperature=1
	if 'gpt-5-2025-08-07' in model.lower() or 'o1' in model.lower() or 'o3' in model.lower():
		temperature = 1
		top_p = 1
	
	from concurrent.futures import ThreadPoolExecutor, as_completed
	import threading
	import time
	
	# Initialize API clients for round-robin usage
	if not hasattr(args, 'api_clients') or not args.api_clients:
		keys = load_all_api_keys()
		args.api_clients = [create_openai_client(k) for k in keys]
		if not args.api_clients:
			if hasattr(args, 'client') and 'gpt' in args.client:
				args.api_clients = [args.client['gpt']]
			else:
				raise ValueError("No valid OpenAI clients found. Please set OPENAI_API_KEY.")
				
	clients = args.api_clients
	num_clients = len(clients)
	print(f"[DEBUG] Using {num_clients} API key(s) for parallel processing.")
	
	lock = threading.Lock()
	client_idx = 0
	
	def process_prompt(idx, messages):
		nonlocal client_idx
		
		# Truncate messages if they exceed the model's context length
		messages = truncate_messages_to_token_limit(messages, max_context_tokens=128000, reserved_output_tokens=max_new_tokens)
		
		# Rotate clients thread-safely
		with lock:
			client = clients[client_idx % num_clients]
			client_idx += 1
			
		max_retries = 5
		for attempt in range(max_retries):
			try:
				kwargs = dict(
					model=model, stream=False, messages=messages,
					temperature=temperature, top_p=top_p,
					max_completion_tokens=max_new_tokens
				)
				
				if json_mode:
					# Try response_format with fallback chain:
					response_format_options = [
						{"type": "json_object"},
						{"type": "json_schema", "json_schema": {"name": "response", "strict": False, "schema": {"type": "object"}}},
						None,
					]
					
					last_err = None
					for rf_option in response_format_options:
						try:
							req = dict(kwargs)
							if rf_option is not None:
								req["response_format"] = rf_option
							response = client.chat.completions.create(**req)
							last_err = None
							break  # Success
						except openai.BadRequestError as rf_err:
							err_msg = str(rf_err).lower()
							if "response_format" in err_msg or "json" in err_msg:
								last_err = rf_err
								continue  # Try next format
							else:
								raise  # Non-format-related error
					
					if last_err is not None:
						raise last_err
				else:
					response = client.chat.completions.create(**kwargs)
				
				return idx, response.choices[0].message.content
				
			except (openai.InternalServerError, openai.APITimeoutError, openai.RateLimitError, openai.APIConnectionError) as e:
				wait_time = min(2 ** attempt * 5, 120)  # 5s, 10s, 20s, 40s, 80s
				print(f"[RETRY {attempt+1}/{max_retries}] {type(e).__name__}: {e}. Waiting {wait_time}s...")
				time.sleep(wait_time)
				if attempt == max_retries - 1:
					print(f"[ERROR] Max retries reached. Raising error.")
					raise
			except Exception as e:
				try:
					if isinstance(e, openai.BadRequestError):
						print("[ERROR] OpenAI BadRequestError:", e)
						print("[SUGGESTION] Ensure the model name in OPENAI_MODEL is correct.")
					else:
						print("[ERROR] LLM request failed:", e)
				except Exception:
					pass
				raise

	outputs = [None] * len(prompts)
	
	# Determine concurrency level - roughly 5 workers per API key, capped at 50
	workers = min(len(prompts), max(5, num_clients * 5), 50)
	
	with ThreadPoolExecutor(max_workers=workers) as executor:
		future_to_idx = {executor.submit(process_prompt, i, p): i for i, p in enumerate(prompts)}
		for future in tqdm(as_completed(future_to_idx), total=len(prompts), desc="LLM Inference"):
			idx, result = future.result()
			outputs[idx] = result
			
	return outputs

# Removed promptLlamaVLLM function - vLLM not supported in CPU-only mode

def promptLLM(args, prompts, schema=None, max_new_tokens=16384, json_mode=True, temperature=0.1, top_p=0.99):
	print(f"[LLM] Using: {args.llm.upper()}")  # Debug log
	if args.llm == 'gpt':
		return promptGPT(args, prompts, schema, max_new_tokens, json_mode, temperature, top_p)
	else:
		raise ValueError(f"Unknown LLM type: {args.llm}. Only 'gpt' is supported in CPU-only mode.")
	