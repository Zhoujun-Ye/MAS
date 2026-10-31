"""Container-side transport adapters for public assets, never test answers.

The PDF is an exact, hash-verified HTTP response. The GGUF loader uses the
official image's existing Hugging Face cache instead of an online file listing.
All other requests and all model execution retain their original implementation.
"""
import hashlib
import io
import os
from pathlib import Path

PDF_URL = 'https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf'
TOKENIZER_ASSETS = {
    'https://openaipublic.blob.core.windows.net/gpt-2/encodings/main/vocab.bpe': '1ce1664773c50f3e0cc8842619a93edc4624525b728b188a9e0be33b7726adc5',
    'https://openaipublic.blob.core.windows.net/gpt-2/encodings/main/encoder.json': '196139668be63f3b5d6574427317ae82f612a97c5d1cdaf36ed2256dbf636783',
    'https://openaipublic.blob.core.windows.net/encodings/r50k_base.tiktoken': '306cd27f03c1a714eca7108e03d66b7dc042abe8c258b44c199a7ed9838dd930',
    'https://openaipublic.blob.core.windows.net/encodings/p50k_base.tiktoken': '94b5ca7dff4d00767bc256fdd1b27e5b17361d7b8a5f968547f9f23eb70d2069',
    'https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken': '223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7',
    'https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken': '446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d',
}


def install_pdf(path, digest):
    body = Path(path).read_bytes()
    if hashlib.sha256(body).hexdigest() != digest:
        raise ValueError('Public PDF digest mismatch')
    import requests
    import httpx
    original_requests = requests.adapters.HTTPAdapter.send
    original_httpx = httpx.HTTPTransport.handle_request

    def send(adapter, request, **kwargs):
        if request.method == 'GET' and request.url == PDF_URL:
            response = requests.Response()
            response.status_code = 200
            response.url = request.url
            response.request = request
            response.headers.update({'Content-Type': 'application/pdf', 'Content-Length': str(len(body))})
            response.raw = io.BytesIO(body)
            return response
        return original_requests(adapter, request, **kwargs)

    def handle(transport, request):
        if request.method == 'GET' and str(request.url) == PDF_URL:
            return httpx.Response(200, headers={'Content-Type': 'application/pdf',
                                               'Content-Length': str(len(body))}, content=body)
        return original_httpx(transport, request)

    requests.adapters.HTTPAdapter.send = send
    httpx.HTTPTransport.handle_request = handle


def install_gguf():
    import llama_cpp
    from huggingface_hub import hf_hub_download
    original = llama_cpp.Llama.from_pretrained.__func__

    @classmethod
    def from_pretrained(cls, repo_id, filename, additional_files=None, local_dir=None,
                        local_dir_use_symlinks='auto', cache_dir=None, **kwargs):
        if os.environ.get('HF_HUB_OFFLINE') != '1':
            return original(cls, repo_id, filename, additional_files=additional_files,
                            local_dir=local_dir, local_dir_use_symlinks=local_dir_use_symlinks,
                            cache_dir=cache_dir, **kwargs)
        # Only exact filenames are supported offline; never guess a glob match
        # or substitute a different model when an asset is absent.
        if not filename or any(c in filename for c in '*?[') or additional_files or local_dir:
            raise ValueError('Offline GGUF requires a single exact cached filename')
        path = hf_hub_download(repo_id=repo_id, filename=filename,
                               cache_dir=cache_dir, local_files_only=True)
        return cls(model_path=path, **kwargs)

    llama_cpp.Llama.from_pretrained = from_pretrained


def install():
    profile = os.environ.get('COOPERBENCH_PUBLIC_ASSETS')
    if profile == 'pdf':
        install_pdf('/opt/cooperbench-public/dummy.pdf', os.environ['COOPERBENCH_PDF_SHA256'])
    elif profile == 'gguf':
        install_gguf()
